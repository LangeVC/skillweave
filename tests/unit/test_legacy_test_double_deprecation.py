"""Tests for Legacy Executor Test-Double and Deprecation Notice (SW-DEPR-001).

Guarantees machine-checked:
1. Legacy executor is converted to an explicit Test-Double in `skillweave.legacy.test_double`.
2. Direct invocation of simulation functions emits `TestDoubleWarning` or `LegacyExecutorWarning`.
3. `skillweave.legacy` and `skillweave.executor` expose explicit `MIGRATION_NOTICE`.
4. `skillweave.executor` is deprecated and delegates to the test double with `DeprecationWarning`.
5. Canonical path (`skillweave.runsvc`, `skillweave.selfhost`) is free of simulation references.
6. Public package `skillweave` does not export simulating executors in its top-level namespace.
"""

from __future__ import annotations

import ast
import sys
import warnings
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import skillweave
import skillweave.executor as public_executor_shim
import skillweave.legacy as legacy_pkg
from skillweave.legacy import (  # noqa: E402
    LegacyExecutorWarning,
    SimulatedExecutorTestDouble,
    TestDoubleWarning,
    call_legacy_simulator,
    call_test_double,
    quarantine_warning as _quarantine_warning,
    simulate_functions,
    test_double_warning as _test_double_warning,
)
from skillweave.legacy.test_double import (
    simulate_step as _simulate_step,
    simulate_step_parallel as _simulate_step_parallel,
    simulate_subagent_execution as _simulate_subagent_execution,
)
from skillweave.models import StepSpec, WorkflowContext


def test_migration_notice_present_in_legacy_and_executor():
    assert hasattr(legacy_pkg, "MIGRATION_NOTICE")
    assert "SW-DEPR-001" in legacy_pkg.MIGRATION_NOTICE
    assert "test_double" in legacy_pkg.MIGRATION_NOTICE

    assert hasattr(public_executor_shim, "MIGRATION_NOTICE")
    assert "SW-DEPR-001" in public_executor_shim.MIGRATION_NOTICE
    assert "deprecated" in public_executor_shim.MIGRATION_NOTICE.lower()


def test_test_double_functions_emit_warning():
    step = StepSpec(id="s1", name="Test Step", purpose="testing", instructions="do work")
    ctx = WorkflowContext(sequence_id="test-seq", mode="execute", status="running")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = _simulate_step(step, ctx)
        assert res["step_id"] == "s1"
        assert res["status"] == "completed"

    test_warnings = [w for w in caught if issubclass(w.category, TestDoubleWarning)]
    assert len(test_warnings) >= 1
    assert "SW-DEPR-001" in str(test_warnings[0].message)


def test_simulated_executor_test_double_class():
    double = SimulatedExecutorTestDouble(max_workers=2, timeout=5)
    step = StepSpec(id="s2", name="Class Test Step", purpose="testing", instructions="do work")
    ctx = WorkflowContext(sequence_id="test-seq2", mode="execute", status="running")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = double.execute_step(step, ctx)
        assert res["step_id"] == "s2"

    test_warnings = [w for w in caught if issubclass(w.category, TestDoubleWarning)]
    assert len(test_warnings) >= 1


def test_public_executor_shim_warns_on_invocation():
    step = StepSpec(id="s3", name="Shim Test Step", purpose="testing", instructions="do work")
    ctx = WorkflowContext(sequence_id="test-seq3", mode="execute", status="running")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = public_executor_shim.simulate_step(step, ctx)
        assert res["step_id"] == "s3"

    dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(dep_warnings) >= 1
    assert "deprecated" in str(dep_warnings[0].message).lower()


def test_no_public_executor_in_skillweave_all_points_to_simulation():
    # Verify that skillweave.__all__ does not export 'executor' or 'simulate_*'
    for name in skillweave.__all__:
        assert not name.startswith("simulate_"), f"skillweave.__all__ exports simulation function {name}"
        assert name != "executor", "skillweave.__all__ exports 'executor'"


def test_canonical_paths_are_free_of_simulation():
    canonical_files = [
        _src / "skillweave" / "runsvc" / "service.py",
        _src / "skillweave" / "selfhost" / "runner.py",
    ]
    legacy_tokens = [
        "skillweave.executor",
        "simulate_step_parallel",
        "simulate_subagent_execution",
        "simulate_step",
    ]
    for p in canonical_files:
        assert p.exists()
        text = p.read_text()
        for tok in legacy_tokens:
            assert tok not in text, f"{p} references legacy token {tok!r}"


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
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
