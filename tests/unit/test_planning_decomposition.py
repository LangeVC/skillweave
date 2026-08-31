"""Unit tests for planning decomposition metadata (SW-PLAN-001).

Tests:
1. DecompositionUnit creation, field validation, and Fibonacci points.
2. DecompositionMetadata calculation (total points, mutating count, depth, criteria coverage).
3. DecompositionPlan validation, cycle detection, and duplicate ID prevention.
4. Topological batching (get_ready_units, get_execution_batches).
5. Serialization to and from dict and JSON.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.core.planning import (  # noqa: E402
    ComplexityLevel,
    CriterionCoverageError,
    DecompositionError,
    DecompositionMetadata,
    DecompositionPlan,
    DecompositionStrategy,
    DecompositionUnit,
    DependencyCycleError,
    FIBONACCI_POINTS,
    create_decomposition_plan,
)


def test_decomposition_unit_valid():
    unit = DecompositionUnit(
        id="unit-1",
        name="Setup DB",
        role="database-engineer",
        description="Initialize migration schema",
        mutating=True,
        points=3,
        depends_on=[],
        acceptance_criteria=[1, 2],
        write_scope=["src/db/**"],
        repo="forgejo/skillweave",
        base_sha="a" * 40,
        execution_model="deepseek-v4-flash",
    )
    unit.validate()
    d = unit.to_dict()
    assert d["id"] == "unit-1"
    assert d["points"] == 3
    assert d["mutating"] is True

    reconstituted = DecompositionUnit.from_dict(d)
    assert reconstituted.id == "unit-1"
    assert reconstituted.points == 3
    assert reconstituted.base_sha == "a" * 40


def test_decomposition_unit_invalid_points():
    with pytest.raises(DecompositionError, match="points 4 must be one of"):
        DecompositionUnit(
            id="unit-bad",
            name="Bad points",
            role="engineer",
            points=4,  # Not in Fibonacci (1, 2, 3, 5, 8, 13)
        ).validate()


def test_decomposition_unit_invalid_base_sha():
    with pytest.raises(DecompositionError, match="base_sha must be 40 hex characters"):
        DecompositionUnit(
            id="unit-bad-sha",
            name="Bad SHA",
            role="engineer",
            base_sha="short-sha",
        ).validate()


def test_decomposition_plan_metadata_calculation():
    units = [
        DecompositionUnit(
            id="u1",
            name="Setup",
            role="infra",
            mutating=False,
            points=2,
            acceptance_criteria=["AC-1"],
        ),
        DecompositionUnit(
            id="u2",
            name="Implement core",
            role="backend",
            mutating=True,
            points=5,
            depends_on=["u1"],
            acceptance_criteria=["AC-2"],
        ),
        DecompositionUnit(
            id="u3",
            name="Add tests",
            role="qa",
            mutating=True,
            points=3,
            depends_on=["u2"],
            acceptance_criteria=["AC-1", "AC-3"],
        ),
    ]

    plan = create_decomposition_plan(
        plan_id="PLAN-001",
        objective="Build Core Feature",
        units=units,
        strategy=DecompositionStrategy.DAG,
        complexity=ComplexityLevel.MEDIUM,
    )

    meta = plan.metadata
    assert meta.total_units == 3
    assert meta.total_points == 10  # 2 + 5 + 3
    assert meta.mutating_units == 2
    assert meta.read_only_units == 1
    assert meta.max_dependency_depth == 3  # u1 -> u2 -> u3
    assert meta.criteria_coverage["AC-1"] == ["u1", "u3"]
    assert meta.criteria_coverage["AC-2"] == ["u2"]
    assert meta.criteria_coverage["AC-3"] == ["u3"]


def test_decomposition_plan_cycle_detection():
    units = [
        DecompositionUnit(id="a", name="A", role="eng", depends_on=["c"]),
        DecompositionUnit(id="b", name="B", role="eng", depends_on=["a"]),
        DecompositionUnit(id="c", name="C", role="eng", depends_on=["b"]),
    ]
    plan = DecompositionPlan(
        plan_id="PLAN-CYCLE",
        objective="Test cycle",
        metadata=DecompositionMetadata(source_id="test"),
        units=units,
    )
    with pytest.raises(DependencyCycleError, match="Dependency cycle detected"):
        plan.validate()


def test_decomposition_plan_duplicate_id():
    units = [
        DecompositionUnit(id="dup", name="First", role="eng"),
        DecompositionUnit(id="dup", name="Second", role="eng"),
    ]
    plan = DecompositionPlan(
        plan_id="PLAN-DUP",
        objective="Test duplicate",
        metadata=DecompositionMetadata(source_id="test"),
        units=units,
    )
    with pytest.raises(DecompositionError, match="Duplicate unit ID detected: 'dup'"):
        plan.validate()


def test_decomposition_plan_ready_units_and_batches():
    units = [
        DecompositionUnit(id="p1", name="Parallel 1", role="eng"),
        DecompositionUnit(id="p2", name="Parallel 2", role="eng"),
        DecompositionUnit(id="seq1", name="Sequential 1", role="eng", depends_on=["p1", "p2"]),
        DecompositionUnit(id="seq2", name="Sequential 2", role="eng", depends_on=["seq1"]),
    ]
    plan = create_decomposition_plan(
        plan_id="PLAN-BATCH",
        objective="Test batches",
        units=units,
    )

    ready0 = plan.get_ready_units([])
    assert {u.id for u in ready0} == {"p1", "p2"}

    ready1 = plan.get_ready_units(["p1"])
    assert {u.id for u in ready1} == {"p2"}

    ready2 = plan.get_ready_units(["p1", "p2"])
    assert [u.id for u in ready2] == ["seq1"]

    batches = plan.get_execution_batches()
    assert len(batches) == 3
    assert {u.id for u in batches[0]} == {"p1", "p2"}
    assert [u.id for u in batches[1]] == ["seq1"]
    assert [u.id for u in batches[2]] == ["seq2"]


def test_decomposition_plan_serialization():
    units = [
        DecompositionUnit(id="u1", name="U1", role="eng", points=1),
    ]
    plan = create_decomposition_plan("P1", "Objective 1", units)
    json_str = plan.to_json()

    loaded = DecompositionPlan.from_json(json_str)
    assert loaded.plan_id == "P1"
    assert loaded.objective == "Objective 1"
    assert len(loaded.units) == 1
    assert loaded.units[0].id == "u1"
    assert loaded.metadata.total_points == 1


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
