"""Pinned-SHA review gating (SW-REVIEW-001).

A review child-run must not begin until the subject has been pushed to the
remote and the reviewer has fetched a pinned full SHA. Two violations block
the review before it starts:

* a **full-SHA mismatch** — the pinned remote SHA does not equal the fetched
  HEAD — blocks the review;
* a **write attempt** by the reviewer blocks (reviewers are read-only, enforced
  via ``runtime.authority`` before execution).

The module owns the gate, not the review logic. It consumes the authority
guard (for write blocking) and the workspace provider / git identity (for the
SHA pin), and refuses to hand out a startable review until both conditions hold.
"""

from .review import (
    ReviewGate,
    ReviewGateError,
    ReviewRun,
)

__all__ = [
    "ReviewGate",
    "ReviewGateError",
    "ReviewRun",
]
