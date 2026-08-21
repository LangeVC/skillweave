"""Tests for the pinned-SHA review gate (SW-REVIEW-001).

Proves a review child-run starts only after push/fetch against a pinned remote
SHA, and that both a full-SHA mismatch and a write attempt block the review
before it starts.

Self-contained sys.path handling, following the sibling-test convention.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.review import ReviewGate, ReviewGateError, ReviewRun  # noqa: E402

FULL_A = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
FULL_B = "b2c3d4e5f60718293a4b5c6d7e8f90123456789"


def test_review_starts_only_after_pin_matches_fetched_sha():
    gate = ReviewGate()
    run = gate.evaluate(
        review_id="rev-1",
        pinned_remote_sha=FULL_A,
        fetched_sha=FULL_A,
        subject_repo="skillweave",
    )
    assert isinstance(run, ReviewRun)
    assert run.pinned_remote_sha == FULL_A
    assert run.fetched_sha == FULL_A


def test_full_sha_mismatch_blocks_review():
    gate = ReviewGate()
    try:
        gate.evaluate(
            review_id="rev-2",
            pinned_remote_sha=FULL_A,
            fetched_sha=FULL_B,
            subject_repo="skillweave",
        )
    except ReviewGateError as exc:
        assert "mismatch" in exc.reason
    else:
        raise AssertionError("full-SHA mismatch must block the review")


def test_short_or_ambiguous_pin_is_refused():
    gate = ReviewGate()
    for bad in ("", "abc123", "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678Z"):
        try:
            gate.pin(bad)
        except ReviewGateError:
            pass
        else:
            raise AssertionError(f"pin {bad!r} must be refused as not a full SHA")


def test_reviewer_write_attempt_blocks_before_execution():
    from skillweave.runtime.authority import AuthorityGuard  # noqa: E402

    # A reviewer is technically read-only per the authority matrix, so its
    # write/commit/push attempts are all refused before execution.
    guard = AuthorityGuard()
    assert guard.can_perform("reviewer", "write") is False
    assert guard.can_perform("reviewer", "commit") is False
    assert guard.can_perform("reviewer", "push") is False
    assert guard.can_perform("reviewer", "mutate_run_state") is False

    # The gate refuses a role that can write: an ops role is never allowed to
    # run a review child-run on a mutable path.
    gate = ReviewGate()
    try:
        gate.assert_read_only("ops")
    except ReviewGateError as exc:
        assert exc.code == "REVIEW_WRITE_ATTEMPT_BLOCKED"
    else:
        raise AssertionError("an ops (writable) role must be refused a review path")


def test_read_only_role_passes_the_readonly_check():
    gate = ReviewGate()
    # A reviewer is read-only, so the read-only check passes (this is the
    # positive precondition that lets the evaluate() step proceed).
    gate.assert_read_only("reviewer")


def test_wrong_role_blocks_review():
    gate = ReviewGate()
    try:
        gate.evaluate(
            review_id="rev-3",
            pinned_remote_sha=FULL_A,
            fetched_sha=FULL_A,
            subject_repo="skillweave",
            role="ops",
        )
    except ReviewGateError as exc:
        assert exc.code == "REVIEW_WRONG_ROLE"
    else:
        raise AssertionError("an ops role must not run as a review child-run")


def _run_all() -> int:
    tests = [
        test_review_starts_only_after_pin_matches_fetched_sha,
        test_full_sha_mismatch_blocks_review,
        test_short_or_ambiguous_pin_is_refused,
        test_reviewer_write_attempt_blocks_before_execution,
        test_read_only_role_passes_the_readonly_check,
        test_wrong_role_blocks_review,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
