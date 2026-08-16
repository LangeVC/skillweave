"""Write-scope arbitration: claim and release, not just validate.

``preflight.validate_write_scope`` checks the write scope of a SINGLE envelope.
It does not arbitrate between two lanes that want the same paths. Two workers
can therefore be let loose on the same files even though each was validated
correctly on its own.

This module turns validation into a locking primitive: a run can CLAIM a write
scope before touching it and RELEASE it when done. A second claim on an
overlapping scope is rejected while the first is held. Overlap is determined
over resolved absolute paths (the same resolution ``004`` uses), never over raw
string prefixes.

It deliberately does NOT schedule: no dependency resolution, no batch building,
no ordering. Claim, conflict, release — nothing else. Ordering is 010's job.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from typing import Optional


class ScopeConflictError(Exception):
    """Raised when a claim overlaps an already-held write scope."""

    def __init__(self, run_id: str, holder_run_id: str, overlapping_path: str):
        self.run_id = run_id
        self.holder_run_id = holder_run_id
        self.overlapping_path = overlapping_path
        super().__init__(
            f"Write-scope conflict for run '{run_id}': path "
            f"'{overlapping_path}' is already held by run '{holder_run_id}'"
        )


def resolve_scope_path(raw_path: str) -> str:
    """Resolve a single scope string to an absolute directory path.

    Mirrors ``SessionEnvelope.validate_write_scope``: a trailing ``**`` marks a
    recursive scope and is stripped; everything else is resolved with
    ``os.path.abspath`` (lexical resolution, not ``realpath`` — same as 004).
    The root ``/`` is represented by ``os.sep``.
    """
    cleaned = raw_path.replace("**", "").rstrip("/")
    if cleaned == "":
        return os.sep
    return os.path.abspath(cleaned)


def paths_overlap(resolved_a: str, resolved_b: str) -> bool:
    """Return True when two resolved scope paths overlap.

    Two paths overlap when one is equal to the other or one is an ancestor of
    the other (with a separator boundary, so ``/a/foobar`` and ``/a/foo`` do not
    overlap). The filesystem root overlaps everything below it.
    """
    if resolved_a == os.sep or resolved_b == os.sep:
        return True
    if resolved_a == resolved_b:
        return True
    if resolved_a.startswith(resolved_b + os.sep):
        return True
    if resolved_b.startswith(resolved_a + os.sep):
        return True
    return False


@dataclass
class WriteScopeClaim:
    claim_id: str
    run_id: str
    resolved_path: str
    created_at: str
    released_at: Optional[str] = None

    @property
    def held(self) -> bool:
        return self.released_at is None

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "run_id": self.run_id,
            "resolved_path": self.resolved_path,
            "created_at": self.created_at,
            "released_at": self.released_at,
        }
