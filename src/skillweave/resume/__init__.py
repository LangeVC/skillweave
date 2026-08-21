"""SW-RESUME-001: cold-start resume without chat transcript dependency.

A :class:`ResumeManager` builds a ``ColdStartBundle`` with *real* base and
remote SHA, content digests of the PRD and chain, and an environment
fingerprint; it then re-derives those digests from raw bytes and git identity
on a fresh session. A bundle whose recorded SHA/digest was edited after the
fact fails the re-derivation and is rejected; a valid bundle is reconstructed
from sources only, never from a transcript or from the serialized fields
themselves.
"""

from .manager import (
    ResumeManager,
    ResumeIntegrityError,
    BundleSources,
    reconstruct_bundle,
    verify_bundle,
)

__all__ = [
    "ResumeManager",
    "ResumeIntegrityError",
    "BundleSources",
    "reconstruct_bundle",
    "verify_bundle",
]
