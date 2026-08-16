"""
Regression tests for AuthorityGuard.can_perform fail-closed behaviour.

A guard that returns True for unknown actions fails open. The fix under test
is that an unrecognised action must fall through to False, while every known
action branch keeps its existing behaviour.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import pytest

from skillweave.runtime.authority import AuthorityGuard, Role


class TestCanPerformFailClosed:

    def test_unknown_action_denied_for_mutating_role(self):
        guard = AuthorityGuard()
        assert guard.can_perform(Role.OPERATOR.value, "delete_everything") is False

    def test_unknown_action_denied_for_read_only_role(self):
        guard = AuthorityGuard()
        assert guard.can_perform(Role.OBSERVER.value, "sudo") is False

    def test_unknown_action_denied_for_unknown_role(self):
        guard = AuthorityGuard()
        assert guard.can_perform("nonexistent_role", "do_anything") is False


class TestKnownActionsPreserved:

    def test_operator_can_approve_gate(self):
        guard = AuthorityGuard()
        assert guard.can_perform(Role.OPERATOR.value, "approve_gate") is True

    def test_ops_cannot_approve_gate(self):
        guard = AuthorityGuard()
        assert guard.can_perform(Role.OPS.value, "approve_gate") is False

    def test_reviewer_can_review_gate(self):
        guard = AuthorityGuard()
        assert guard.can_perform(Role.REVIEWER.value, "review_gate") is True

    def test_observer_cannot_review_gate(self):
        guard = AuthorityGuard()
        assert guard.can_perform(Role.OBSERVER.value, "review_gate") is False

    def test_ops_can_mutate_run_state(self):
        guard = AuthorityGuard()
        assert guard.can_perform(Role.OPS.value, "mutate_run_state") is True

    def test_observer_cannot_mutate_run_state(self):
        guard = AuthorityGuard()
        assert guard.can_perform(Role.OBSERVER.value, "mutate_run_state") is False
