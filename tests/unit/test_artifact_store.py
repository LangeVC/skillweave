"""SW-ART-001: content-addressed raw artifact store + immutable receipt.

A receipt resolves its raw bytes via digest. Mutation or absence of the stored
bytes must close the resolution path (fail closed), never yield wrong data.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.registry import (
    RawArtifactStore,
    ArtifactReceipt,
    ArtifactIntegrityError,
)


def _receipt(sha256: str) -> ArtifactReceipt:
    return ArtifactReceipt(
        artifact_id="evd-1",
        sha256=sha256,
        schema_version="1",
        producer_command="pytest",
        subject_repo="skillweave",
        subject_commit="abc123",
        created_at="2026-08-16T00:00:00Z",
        evidence_type="artifact",
        purpose="resolve",
    )


def test_receipt_resolves_bytes():
    store = RawArtifactStore()
    digest = store.put(b"raw-bytes-abc")
    receipt = _receipt(digest)
    assert store.resolve_receipt(receipt) == b"raw-bytes-abc"


def test_mutated_bytes_fail_closed():
    store = RawArtifactStore()
    digest = store.put(b"original")
    store.mock_mutate(digest, b"tampered")
    try:
        store.resolve(digest)
        assert False, "mutated bytes must not resolve"
    except ArtifactIntegrityError:
        pass


def test_missing_bytes_fail_closed():
    store = RawArtifactStore()
    digest = store.put(b"will-be-lost")
    store.delete(digest)
    try:
        store.resolve(digest)
        assert False, "missing bytes must not resolve"
    except ArtifactIntegrityError:
        pass


def test_put_is_content_addressed_and_immutable():
    store = RawArtifactStore()
    d1 = store.put(b"same")
    d2 = store.put(b"same")
    assert d1 == d2  # identical content -> identical address


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
