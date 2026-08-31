"""Unit tests for planning dispatchability gates and assessments (SW-PLAN-001).

Tests:
1. DispatchabilityStatus enum and DispatchabilityAssessment serialization.
2. Read-only units: ready when unblocked and role is present.
3. Mutating units: ineligible if missing repo, full 40-hex base SHA, or execution model.
4. Dependency blockers: status is BLOCKED when dependencies are incomplete.
5. Already completed, running, or failed units.
6. Evaluator and helper methods: evaluate_dispatchability, validate_dispatchability, get_dispatchable_units.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.core.planning import (  # noqa: E402
    DecompositionPlan,
    DecompositionUnit,
    DispatchabilityAssessment,
    DispatchabilityError,
    DispatchabilityEvaluator,
    DispatchabilityRequirement,
    DispatchabilityStatus,
    create_decomposition_plan,
    evaluate_dispatchability,
    get_dispatchable_units,
    validate_dispatchability,
)


def test_read_only_unit_dispatchable():
    unit = DecompositionUnit(
        id="read-1",
        name="Review Spec",
        role="architect",
        mutating=False,
    )
    assessment = evaluate_dispatchability(unit)
    assert assessment.is_dispatchable is True
    assert assessment.status == DispatchabilityStatus.READY
    assert len(assessment.blockers) == 0
    assert len(assessment.missing_requirements) == 0


def test_mutating_unit_missing_repo_ineligible():
    unit = DecompositionUnit(
        id="mut-1",
        name="Write Code",
        role="engineer",
        mutating=True,
        repo="",  # Missing repo
        base_sha="a" * 40,
        execution_model="deepseek-v4-flash",
    )
    assessment = evaluate_dispatchability(unit)
    assert assessment.is_dispatchable is False
    assert assessment.status == DispatchabilityStatus.INELIGIBLE
    assert "repo" in assessment.missing_requirements


def test_mutating_unit_missing_sha_ineligible():
    unit = DecompositionUnit(
        id="mut-2",
        name="Write Code",
        role="engineer",
        mutating=True,
        repo="forgejo/skillweave",
        base_sha=None,  # Missing base SHA
        execution_model="deepseek-v4-flash",
    )
    assessment = evaluate_dispatchability(unit)
    assert assessment.is_dispatchable is False
    assert assessment.status == DispatchabilityStatus.INELIGIBLE
    assert "base_sha" in assessment.missing_requirements


def test_mutating_unit_missing_model_ineligible():
    unit = DecompositionUnit(
        id="mut-3",
        name="Write Code",
        role="engineer",
        mutating=True,
        repo="forgejo/skillweave",
        base_sha="a" * 40,
        execution_model="",  # Missing execution model
    )
    assessment = evaluate_dispatchability(unit)
    assert assessment.is_dispatchable is False
    assert assessment.status == DispatchabilityStatus.INELIGIBLE
    assert "execution_model" in assessment.missing_requirements


def test_mutating_unit_valid_is_ready():
    unit = DecompositionUnit(
        id="mut-valid",
        name="Write Code",
        role="engineer",
        mutating=True,
        repo="forgejo/skillweave",
        base_sha="b" * 40,
        execution_model="deepseek-v4-flash",
    )
    assessment = evaluate_dispatchability(unit)
    assert assessment.is_dispatchable is True
    assert assessment.status == DispatchabilityStatus.READY


def test_dependency_blockers():
    unit = DecompositionUnit(
        id="dep-step",
        name="Needs predecessor",
        role="qa",
        depends_on=["task-01", "task-02"],
    )
    # Neither dependency completed
    assessment = evaluate_dispatchability(unit, completed_ids=[])
    assert assessment.is_dispatchable is False
    assert assessment.status == DispatchabilityStatus.BLOCKED
    assert assessment.blockers == ["task-01", "task-02"]

    # Only one dependency completed
    assessment2 = evaluate_dispatchability(unit, completed_ids=["task-01"])
    assert assessment2.is_dispatchable is False
    assert assessment2.status == DispatchabilityStatus.BLOCKED
    assert assessment2.blockers == ["task-02"]

    # Both dependencies completed
    assessment3 = evaluate_dispatchability(unit, completed_ids=["task-01", "task-02"])
    assert assessment3.is_dispatchable is True
    assert assessment3.status == DispatchabilityStatus.READY
    assert len(assessment3.blockers) == 0


def test_already_completed_and_running_states():
    unit = DecompositionUnit(id="u1", name="U1", role="eng")

    completed_res = evaluate_dispatchability(unit, completed_ids=["u1"])
    assert completed_res.is_dispatchable is False
    assert completed_res.status == DispatchabilityStatus.COMPLETED

    running_res = evaluate_dispatchability(unit, running_ids=["u1"])
    assert running_res.is_dispatchable is False
    assert running_res.status == DispatchabilityStatus.DISPATCHED

    failed_res = evaluate_dispatchability(unit, failed_ids=["u1"])
    assert failed_res.is_dispatchable is False
    assert failed_res.status == DispatchabilityStatus.FAILED


def test_validate_dispatchability_raises():
    unit = DecompositionUnit(id="blocked", name="Blocked", role="eng", depends_on=["parent"])
    with pytest.raises(DispatchabilityError, match="is not dispatchable"):
        validate_dispatchability(unit, completed_ids=[])


def test_get_dispatchable_units_from_plan():
    units = [
        DecompositionUnit(id="ready1", name="Ready 1", role="eng"),
        DecompositionUnit(id="ready2", name="Ready 2", role="eng"),
        DecompositionUnit(id="blocked1", name="Blocked 1", role="eng", depends_on=["ready1"]),
        DecompositionUnit(id="ineligible1", name="Bad Mutating", role="eng", mutating=True, repo=None),
    ]
    plan = create_decomposition_plan("P", "Obj", units)

    dispatchable = get_dispatchable_units(plan, completed_ids=[])
    assert [u.id for u in dispatchable] == ["ready1", "ready2"]

    dispatchable_after_r1 = get_dispatchable_units(plan, completed_ids=["ready1"])
    assert [u.id for u in dispatchable_after_r1] == ["ready2", "blocked1"]


def test_dispatchability_assessment_serialization():
    assessment = DispatchabilityAssessment(
        unit_id="test-u",
        is_dispatchable=False,
        status=DispatchabilityStatus.BLOCKED,
        reasons=["Blocked by d1"],
        blockers=["d1"],
    )
    d = assessment.to_dict()
    assert d["unit_id"] == "test-u"
    assert d["status"] == "blocked"

    reconstituted = DispatchabilityAssessment.from_dict(d)
    assert reconstituted.unit_id == "test-u"
    assert reconstituted.status == DispatchabilityStatus.BLOCKED
    assert reconstituted.blockers == ["d1"]


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
