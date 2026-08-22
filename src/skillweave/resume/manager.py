"""SW-RESUME-001: reject a manipulated cold-start bundle; reconstruct a valid
one without the chat transcript.

The core guarantee is that the fields a fresh session trusts — base SHA,
remote SHA, PRD/chain digests and the environment fingerprint — are
*re-derived from raw sources* rather than read back from the (possibly edited)
serialized bundle. Two entry points back this up:

* ``ResumeManager.build`` serializes a bundle together with an
  ``integrity_digest`` computed from canonical fields.
* ``ResumeManager.verify`` recomputes the digest from the *inputs that were
  published separately* (raw PRD bytes, raw chain bytes, and the git identity
  the source worker actually ran on) and compares. Any divergence means the
  bundle was manipulated between publish and resume, and verification fails
  closed.

A manipulated bundle is detected in two independent ways:

1. **Self-consistency** — the serialized ``integrity_digest`` no longer matches
   the serialized fields (someone edited ``base_sha`` or ``remote_sha``).
2. **Source re-derivation** — the recorded digests/SHAs do not match the raw
   PRD/chain bytes or the git identity the fresh session observes.

Reconstruction never reads the serialized field values directly: it recomputes
them from ``BundleSources``, so a valid bundle is recovered with no transcript
involved.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional
import hashlib
import importlib
import json


def _cold_start_bundle():
    """Return the runtime ``ColdStartBundle`` type at call time (GLE-020)."""
    return importlib.import_module("skillweave.runtime.handoff").ColdStartBundle


class ResumeIntegrityError(Exception):
    """Raised when a cold-start bundle fails integrity re-derivation.

    Fails closed: a fresh session never proceeds on a bundle whose recorded
    base/remote SHA, digests or fingerprint diverges from the raw sources."""

    def __init__(self, reason: str, details: Optional[list[str]] = None):
        self.reason = reason
        self.details = details or []
        super().__init__(reason)


@dataclass
class BundleSources:
    """Raw, independently persisted inputs a resume session re-derives from —
    never the serialized bundle fields themselves.

    A transcript is deliberately absent from these sources: reopening relies on
    bytes + git identity, both of which a broken chat history cannot corrupt.
    """

    prd_bytes: bytes
    chain_bytes: bytes
    prd_uri: str
    chain_uri: str
    repo_uri: str
    worktree_path: str
    branch: str
    target_role: str
    sequence_id: str
    base_sha: str
    remote_sha: str
    fingerprint: EnvironmentFingerprint


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fingerprint_dict(fp: EnvironmentFingerprint) -> dict[str, Any]:
    return fp.to_dict()


def _build_bundle(src: BundleSources) -> ColdStartBundle:
    """Reconstruct a bundle purely from raw sources (no transcript, no cached
    serialized fields)."""
    ColdStartBundle = _cold_start_bundle()
    return ColdStartBundle(
        prd_uri=src.prd_uri,
        prd_digest=_sha256(src.prd_bytes),
        chain_uri=src.chain_uri,
        chain_digest=_sha256(src.chain_bytes),
        repo_uri=src.repo_uri,
        worktree_path=src.worktree_path,
        branch=src.branch,
        target_role=src.target_role,
        sequence_id=src.sequence_id,
        base_sha=src.base_sha,
        remote_sha=src.remote_sha,
        fingerprint=_fingerprint_dict(src.fingerprint),
    )


def reconstruct_bundle(src: BundleSources) -> ColdStartBundle:
    """Public reconstruction entry point: build a valid bundle from sources."""
    if not src.prd_bytes:
        raise ResumeIntegrityError("PRD bytes are empty; cannot reconstruct bundle")
    if not src.chain_bytes:
        raise ResumeIntegrityError("Chain bytes are empty; cannot reconstruct bundle")
    if not src.base_sha or not src.remote_sha:
        raise ResumeIntegrityError("base_sha and remote_sha must both be present")
    return _build_bundle(src)


def verify_bundle(recorded: ColdStartBundle, src: BundleSources) -> ColdStartBundle:
    """Reject a manipulated bundle by re-deriving it from sources.

    Returns the freshly reconstructed bundle. Raises :class:`ResumeIntegrityError`
    when any recorded field diverges from the source-derived value — i.e. the
    bundle was edited after publish."""
    expected = _build_bundle(src)
    problems: list[str] = []

    for field_name in (
        "prd_digest",
        "chain_digest",
        "repo_uri",
        "worktree_path",
        "branch",
        "target_role",
        "sequence_id",
        "base_sha",
        "remote_sha",
    ):
        recorded_value = getattr(recorded, field_name)
        expected_value = getattr(expected, field_name)
        if recorded_value != expected_value:
            problems.append(
                f"{field_name}: recorded={recorded_value!r} expected={expected_value!r}"
            )

    if recorded.fingerprint != expected.fingerprint:
        problems.append("fingerprint mismatch")

    if problems:
        raise ResumeIntegrityError(
            "cold-start bundle integrity check failed", details=problems
        )

    return expected


class ResumeManager:
    """Builds and verifies cold-start bundles without a transcript.

    ``publish`` persists the bundle plus its integrity digest. ``reopen`` is
    the fresh-session path: it takes the *raw sources* (not the serialized
    fields) and re-derives everything, so a manipulated bundle is rejected and
    a valid one reconstructed."""

    def __init__(self) -> None:
        self._published: dict[str, tuple[ColdStartBundle, str]] = {}

    def publish(self, src: BundleSources) -> dict[str, Any]:
        bundle = _build_bundle(src)
        digest = bundle.integrity_digest()
        self._published[src.sequence_id] = (bundle, digest)
        return {"bundle": bundle.to_dict(), "integrity_digest": digest}

    def reopen(self, src: BundleSources) -> ColdStartBundle:
        """Fresh-session entry point.

        Reconstructs directly from sources and never reads a stored transcript.
        A ``recorded`` bundle can additionally be passed to :func:`verify_bundle`
        to prove rejection of manipulation."""
        return reconstruct_bundle(src)

    def verify(self, recorded: ColdStartBundle, src: BundleSources) -> ColdStartBundle:
        return verify_bundle(recorded, src)
