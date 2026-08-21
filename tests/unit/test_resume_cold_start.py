"""SW-RESUME-001: cold-start bundle with real base/remote SHA, digests and
fingerprint; a fresh session rejects a manipulated bundle and reconstructs a
valid one without transcript.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.handoff import ColdStartBundle
from skillweave.runtime.checkpoint import EnvironmentFingerprint
from skillweave.resume import (
    ResumeManager,
    ResumeIntegrityError,
    BundleSources,
    reconstruct_bundle,
    verify_bundle,
)


def _fingerprint(commit_sha: str = "base-commit-123", branch: str = "feature/x") -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        hostname="host-a",
        os_name="Darwin 24",
        python_version="3.11.0",
        branch=branch,
        commit_sha=commit_sha,
    )


def _sources(**overrides) -> BundleSources:
    base = dict(
        prd_bytes=b"PRD-body-v1",
        chain_bytes=b"chain-sequence-v1",
        prd_uri="file:///planning/prd.json",
        chain_uri="file:///planning/sequences.yaml",
        repo_uri="git@canonical/skillweave.git",
        worktree_path="/tmp/wt",
        branch="feature/x",
        target_role="ops",
        sequence_id="SW-137-I02",
        base_sha="base-commit-123",
        remote_sha="remote-commit-456",
        fingerprint=_fingerprint(),
    )
    base.update(overrides)
    return BundleSources(**base)


def test_reconstruct_bundle_carries_real_base_and_remote_sha():
    bundle = reconstruct_bundle(_sources())
    assert bundle.base_sha == "base-commit-123"
    assert bundle.remote_sha == "remote-commit-456"
    # digests are derived from raw bytes, not copied from a transcript
    assert bundle.prd_digest != ""
    assert bundle.chain_digest != ""


def test_reconstruct_derives_digests_from_raw_bytes():
    bundle = reconstruct_bundle(_sources())
    import hashlib
    assert bundle.prd_digest == hashlib.sha256(b"PRD-body-v1").hexdigest()
    assert bundle.chain_digest == hashlib.sha256(b"chain-sequence-v1").hexdigest()


def test_reconstruct_embeds_environment_fingerprint():
    bundle = reconstruct_bundle(_sources())
    assert bundle.fingerprint is not None
    assert bundle.fingerprint["commit_sha"] == "base-commit-123"
    assert bundle.fingerprint["branch"] == "feature/x"


def test_verify_accepts_unmodified_bundle():
    src = _sources()
    bundle = reconstruct_bundle(src)
    result = verify_bundle(bundle, src)
    assert result.base_sha == src.base_sha


def test_verify_rejects_manipulated_base_sha():
    src = _sources()
    bundle = reconstruct_bundle(src)
    bundle.base_sha = "attacker-edited-sha"
    try:
        verify_bundle(bundle, src)
        assert False, "edited base_sha must be rejected"
    except ResumeIntegrityError as e:
        assert any("base_sha" in d for d in e.details)


def test_verify_rejects_manipulated_remote_sha():
    src = _sources()
    bundle = reconstruct_bundle(src)
    bundle.remote_sha = "attacker-edited-remote"
    try:
        verify_bundle(bundle, src)
        assert False, "edited remote_sha must be rejected"
    except ResumeIntegrityError:
        pass


def test_verify_rejects_manipulated_prd_digest():
    src = _sources()
    bundle = reconstruct_bundle(src)
    bundle.prd_digest = "deadbeef"
    try:
        verify_bundle(bundle, src)
        assert False, "edited prd_digest must be rejected"
    except ResumeIntegrityError:
        pass


def test_verify_rejects_manipulated_fingerprint():
    src = _sources()
    bundle = reconstruct_bundle(src)
    bundle.fingerprint["commit_sha"] = "attacker-commit"
    try:
        verify_bundle(bundle, src)
        assert False, "edited fingerprint must be rejected"
    except ResumeIntegrityError:
        pass


def test_integrity_digest_covers_sha_and_fingerprint():
    src = _sources()
    bundle = reconstruct_bundle(src)
    d1 = bundle.integrity_digest()
    bundle.base_sha = "other"
    d2 = bundle.integrity_digest()
    assert d1 != d2


def test_resume_manager_publish_and_reopen_no_transcript():
    src = _sources()
    mgr = ResumeManager()
    published = mgr.publish(src)
    assert published["integrity_digest"]
    # a fresh session reopens from raw sources only, not the serialized bundle
    reopened = mgr.reopen(src)
    assert reopened.base_sha == src.base_sha
    assert reopened.prd_digest == published["bundle"]["prd_digest"]


def test_reconstruct_rejects_empty_sources():
    try:
        reconstruct_bundle(_sources(prd_bytes=b""))
        assert False, "empty PRD bytes must be rejected"
    except ResumeIntegrityError:
        pass


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in _tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
