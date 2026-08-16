"""
SW-135-010 (dispatch 1, criteria 1 and 5): DagScheduler — graph to batches,
cycles are errors, determinism.

Criterion 1: a graph of tasks with ``depends_on`` becomes ordered batches;
a cyclic graph is reported as an error, never silently dropped.
Criterion 5: determinism — the same graph yields the same batches in the same
order; a test records it.

Self-contained ``sys.path`` handling (independent of conftest/pytest).
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.dagscheduler import (
    Task,
    Batch,
    CyclicGraphError,
    UnknownDependencyError,
    build_batches,
)


def _ids(batches):
    return [batch.task_ids for batch in batches]


def test_linear_chain_produces_one_task_per_batch():
    tasks = [
        Task(id="a"),
        Task(id="b", depends_on=["a"]),
        Task(id="c", depends_on=["b"]),
    ]
    assert _ids(build_batches(tasks)) == [["a"], ["b"], ["c"]]


def test_diamond_produces_layered_batches():
    tasks = [
        Task(id="a"),
        Task(id="b", depends_on=["a"]),
        Task(id="c", depends_on=["a"]),
        Task(id="d", depends_on=["b", "c"]),
    ]
    assert _ids(build_batches(tasks)) == [["a"], ["b", "c"], ["d"]]


def test_cycle_raises_and_names_the_nodes():
    tasks = [
        Task(id="a", depends_on=["c"]),
        Task(id="b", depends_on=["a"]),
        Task(id="c", depends_on=["b"]),
    ]
    try:
        build_batches(tasks)
        assert False, "expected CyclicGraphError"
    except CyclicGraphError as e:
        assert e.unresolved == ["a", "b", "c"]
        assert "a" in str(e) and "b" in str(e) and "c" in str(e)


def test_self_cycle_is_a_cycle():
    tasks = [Task(id="a", depends_on=["a"])]
    try:
        build_batches(tasks)
        assert False, "expected CyclicGraphError"
    except CyclicGraphError as e:
        assert e.unresolved == ["a"]


def test_unknown_dependency_is_an_error_not_silent_drop():
    tasks = [Task(id="a", depends_on=["ghost"])]
    try:
        build_batches(tasks)
        assert False, "expected UnknownDependencyError"
    except UnknownDependencyError as e:
        assert e.task_id == "a"
        assert e.missing == "ghost"


def test_independent_tasks_share_one_batch_in_id_order():
    tasks = [
        Task(id="z"),
        Task(id="m"),
        Task(id="a"),
    ]
    assert _ids(build_batches(tasks)) == [["a", "m", "z"]]


def test_determinism_same_graph_same_batches_under_permutation():
    def graph(order):
        return [
            Task(id="compile", depends_on=[]),
            Task(id="lint", depends_on=[]),
            Task(id="test", depends_on=["compile"]),
            Task(id="package", depends_on=["compile", "lint"]),
            Task(id="release", depends_on=["test", "package"]),
        ]

    expected = [["compile", "lint"], ["package", "test"], ["release"]]
    # Feed the graph in three different input orders; output must not change.
    assert _ids(build_batches(graph(0))) == expected
    assert _ids(build_batches(list(reversed(graph(0))))) == expected
    assert _ids(build_batches([graph(0)[4], graph(0)[0], graph(0)[3],
                               graph(0)[1], graph(0)[2]])) == expected


def test_duplicate_task_ids_are_rejected():
    tasks = [Task(id="a"), Task(id="a")]
    try:
        build_batches(tasks)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "a" in str(e)


def _run_all() -> int:
    tests = [
        test_linear_chain_produces_one_task_per_batch,
        test_diamond_produces_layered_batches,
        test_cycle_raises_and_names_the_nodes,
        test_self_cycle_is_a_cycle,
        test_unknown_dependency_is_an_error_not_silent_drop,
        test_independent_tasks_share_one_batch_in_id_order,
        test_determinism_same_graph_same_batches_under_permutation,
        test_duplicate_task_ids_are_rejected,
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
