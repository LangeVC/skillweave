"""Tests for condition expression evaluator."""

import pytest
from skillweave.studio.hooks.engine.condition import evaluate_condition, ConditionError


class TestEvaluateCondition:
    def test_empty_condition_returns_true(self):
        assert evaluate_condition("", {}) is True
        assert evaluate_condition("   ", {}) is True

    def test_none_condition_returns_true(self):
        # None is handled by the caller, but empty string is safe
        assert evaluate_condition("", {}) is True

    def test_simple_equality(self):
        assert evaluate_condition("phase == 'build'", {"phase": "build"}) is True
        assert evaluate_condition("phase == 'build'", {"phase": "test"}) is False

    def test_not_equal(self):
        assert evaluate_condition("phase != 'test'", {"phase": "build"}) is True
        assert evaluate_condition("phase != 'build'", {"phase": "build"}) is False

    def test_and_operator(self):
        ctx = {"phase": "build", "position": "pre"}
        assert evaluate_condition("phase == 'build' and position == 'pre'", ctx) is True
        assert evaluate_condition("phase == 'build' and position == 'post'", ctx) is False

    def test_or_operator(self):
        ctx = {"phase": "test", "position": "pre"}
        assert evaluate_condition("phase == 'build' or phase == 'test'", ctx) is True
        assert evaluate_condition("phase == 'build' or phase == 'release'", ctx) is False

    def test_in_operator(self):
        ctx = {"phase": "build"}
        assert evaluate_condition("phase in ('build', 'test')", ctx) is True
        assert evaluate_condition("phase in ('release', 'launch')", ctx) is False

    def test_not_in_operator(self):
        ctx = {"phase": "observe"}
        assert evaluate_condition("phase not in ('build', 'test')", ctx) is True

    def test_boolean_values(self):
        ctx = {"gate_decision": True}
        assert evaluate_condition("gate_decision == True", ctx) is True
        assert evaluate_condition("gate_decision == False", ctx) is False

    def test_none_value(self):
        ctx = {"gate_decision": None}
        assert evaluate_condition("gate_decision == None", ctx) is True

    def test_not_operator(self):
        ctx = {"gate_decision": False}
        assert evaluate_condition("not gate_decision", ctx) is True

    def test_invalid_syntax_raises(self):
        with pytest.raises(ConditionError, match="Invalid condition syntax"):
            evaluate_condition("phase ==", {"phase": "build"})

    def test_disallowed_function_call_raises(self):
        with pytest.raises(ConditionError, match="Disallowed expression"):
            evaluate_condition("__import__('os')", {})

    def test_disallowed_attribute_access_raises(self):
        with pytest.raises(ConditionError, match="Disallowed expression"):
            evaluate_condition("phase.upper()", {"phase": "build"})

    def test_unknown_variable_raises(self):
        with pytest.raises(ConditionError, match="Unknown variable"):
            evaluate_condition("unknown_var == 'x'", {"phase": "build"})

    def test_complex_expression(self):
        ctx = {"phase": "build", "position": "pre", "gate_decision": True}
        expr = "phase == 'build' and position == 'pre' and gate_decision == True"
        assert evaluate_condition(expr, ctx) is True

    def test_string_comparison(self):
        ctx = {"position": "post"}
        assert evaluate_condition("position == 'post'", ctx) is True
