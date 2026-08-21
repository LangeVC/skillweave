"""SW-AUTH-001: reviewer is technically read-only.

A reviewer's write, commit, push, and state-mutation attempts must be blocked
BEFORE execution. Mutating actions all resolve to False for the reviewer.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.authority import AuthorityGuard, Role, AuthorityError, is_read_only


def test_reviewer_is_read_only():
    assert is_read_only(Role.REVIEWER.value) is True
    assert is_read_only(Role.OPS.value) is False


def test_reviewer_blocked_from_write_commit_push_mutate():
    guard = AuthorityGuard()
    for action in ("write", "commit", "push", "mutate_run_state", "merge", "release", "tag"):
        assert guard.can_perform(Role.REVIEWER.value, action) is False, (
            f"reviewer must not perform {action}"
        )


def test_reviewer_blocked_before_execution_via_assert():
    guard = AuthorityGuard()
    for action in ("write", "commit", "push", "mutate_run_state"):
        blocked = False
        try:
            guard.assert_can_write(Role.REVIEWER.value, action)
        except AuthorityError:
            blocked = True
        assert blocked is True, f"reviewer {action} must raise before execution"


def test_reviewer_can_still_review():
    guard = AuthorityGuard()
    assert guard.can_perform(Role.REVIEWER.value, "review_gate") is True
    assert guard.can_perform(Role.REVIEWER.value, "approve_gate") is True


def test_ops_can_still_write():
    guard = AuthorityGuard()
    assert guard.can_perform(Role.OPS.value, "write") is True
    assert guard.can_perform(Role.OPS.value, "commit") is True
    assert guard.can_perform(Role.OPS.value, "push") is True


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
