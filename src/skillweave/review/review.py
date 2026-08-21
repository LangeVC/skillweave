"""Review gate: pinned remote SHA + reviewer read-only (SW-REVIEW-001).

A review child-run is gated on two conditions, both checked *before* the review
may start:

1. **Pin match.** The reviewer's fetched HEAD must equal the pinned full remote
   SHA. A full-SHA mismatch (the remote moved, the wrong commit was fetched, or
   the pin was tampered with) raises :class:`ReviewGateError` and blocks the
   review. Only a full 40-hex SHA is accepted as a pin; a short ref is refused
   outright so the pin is never ambiguous.

2. **Read-only.** A write attempt by the reviewer is refused via
   ``AuthorityGuard.assert_can_write`` before execution — the reviewer role is
   read-only and never granted write/commit/push/mutation, so the attempt
   raises ``AuthorityError`` and the review does not proceed.

The gate's ``evaluate`` returns a :class:`ReviewRun` only when both hold; it
never starts a process itself. The actual review body is the caller's concern
(driven through the run service / fan-out), which the gate merely releases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from skillweave.runtime.authority import AuthorityGuard, Role

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class ReviewGateError(Exception):
    """A review child-run is blocked from starting.

    ``reason`` names the violation: a pin mismatch or a write attempt. The
    review never starts in either case — the failure is closed, not partial."""

    def __init__(self, reason: str, code: str = "REVIEW_GATE_BLOCKED"):
        self.reason = reason
        self.code = code
        super().__init__(f"[{code}] {reason}")


@dataclass
class ReviewRun:
    """A startable review, released only after pin match + read-only proven."""

    review_id: str
    pinned_remote_sha: str
    fetched_sha: str
    subject_repo: str
    started_at: str


class ReviewGate:
    """Gates a review child-run on a pinned remote SHA and reviewer read-only.

    Construct with an ``AuthorityGuard`` (fresh, or shared) and the identity of
    the subject. ``evaluate`` is the single entry point a dispatcher uses before
    it may start a review child-run.
    """

    def __init__(self, guard: Optional[AuthorityGuard] = None):
        self.guard = guard or AuthorityGuard()

    @staticmethod
    def _normalize(sha: str) -> str:
        return (sha or "").strip().lower()

    def pin(self, pinned_remote_sha: str) -> str:
        """Validate and normalise a pin. Only a full 40-hex SHA is accepted."""
        norm = self._normalize(pinned_remote_sha)
        if not _FULL_SHA.match(norm):
            raise ReviewGateError(
                f"pinned remote SHA '{pinned_remote_sha}' is not a full 40-hex "
                "commit id; refusing an ambiguous pin"
            )
        return norm

    def assert_read_only(self, role: str = Role.REVIEWER.value) -> None:
        """Prove the role is read-only before a review may start.

        The review may proceed only when the running role is *technically*
        read-only (per the authority matrix). A role with any write, commit, or
        push capability is refused: a review must never run on a mutable path.
        """
        for action in ("write", "commit", "push", "mutate_run_state"):
            if self.guard.can_perform(role, action):
                raise ReviewGateError(
                    f"role '{role}' is not read-only: it can '{action}'; a review "
                    "must run read-only", code="REVIEW_WRITE_ATTEMPT_BLOCKED",
                )

    def evaluate(
        self,
        *,
        review_id: str,
        pinned_remote_sha: str,
        fetched_sha: str,
        subject_repo: str,
        role: str = Role.REVIEWER.value,
    ) -> ReviewRun:
        """Release a review child-run only when pin matches and role is read-only.

        Raises :class:`ReviewGateError` on a full-SHA mismatch or a write attempt.
        Returns a :class:`ReviewRun` otherwise.
        """
        pin = self.pin(pinned_remote_sha)
        fetched = self._normalize(fetched_sha)
        if fetched != pin:
            raise ReviewGateError(
                f"full-SHA mismatch: pinned {pin} != fetched {fetched}; review blocked"
            )
        if role != Role.REVIEWER.value:
            raise ReviewGateError(
                f"review must run under '{Role.REVIEWER.value}', not '{role}'",
                code="REVIEW_WRONG_ROLE",
            )
        self.assert_read_only(role)
        return ReviewRun(
            review_id=review_id,
            pinned_remote_sha=pin,
            fetched_sha=fetched,
            subject_repo=subject_repo,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
