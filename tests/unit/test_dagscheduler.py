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
    build_lanes,
    EXECUTION_MODE_FANOUT,
    EXECUTION_MODE_INLINE,
)
from skillweave.runtime.write_scope import WriteScopeClaim


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


# --- Dispatch 2 (criteria 2 and 9): write-scope fan-out vs inline ---


def _lane_ids(lane_batches):
    return [[lane.task_id for lane in group] for group in lane_batches]


def _mode(lane_batches, task_id):
    for group in lane_batches:
        for lane in group:
            if lane.task_id == task_id:
                return lane.execution_mode
    return None


def test_disjoint_scopes_share_one_batch_as_fanout():
    tasks = [Task(id="a", write_scope=["/src/a/**"]),
             Task(id="b", write_scope=["/src/b/**"])]
    lanes = build_lanes(tasks)
    assert _lane_ids(lanes) == [["a", "b"]]
    assert _mode(lanes, "a") == EXECUTION_MODE_FANOUT
    assert _mode(lanes, "b") == EXECUTION_MODE_FANOUT


def test_overlapping_scopes_never_share_a_batch():
    # a and c both write /src/shared — they must be inline and separated.
    tasks = [Task(id="a", write_scope=["/src/shared/**"]),
             Task(id="b", write_scope=["/src/b/**"]),
             Task(id="c", write_scope=["/src/shared/**"])]
    lanes = build_lanes(tasks)
    # b is disjoint, so it fans out alone; a and c are inline, one per batch.
    assert _lane_ids(lanes) == [["b"], ["a"], ["c"]]
    assert _mode(lanes, "b") == EXECUTION_MODE_FANOUT
    assert _mode(lanes, "a") == EXECUTION_MODE_INLINE
    assert _mode(lanes, "c") == EXECUTION_MODE_INLINE


def test_ancestor_scope_overlaps_descendant():
    # /src is an ancestor of /src/a: overlap via paths_overlap, not substring.
    tasks = [Task(id="a", write_scope=["/src"]),
             Task(id="b", write_scope=["/src/a/**"])]
    lanes = build_lanes(tasks)
    assert _lane_ids(lanes) == [["a"], ["b"]]
    assert _mode(lanes, "a") == EXECUTION_MODE_INLINE
    assert _mode(lanes, "b") == EXECUTION_MODE_INLINE


def test_sibling_prefixes_that_are_not_ancestors_do_not_overlap():
    # /src/foobar and /src/foo must NOT overlap (separator boundary in 009).
    tasks = [Task(id="a", write_scope=["/src/foo"]),
             Task(id="b", write_scope=["/src/foobar"])]
    lanes = build_lanes(tasks)
    assert _lane_ids(lanes) == [["a", "b"]]
    assert _mode(lanes, "a") == EXECUTION_MODE_FANOUT
    assert _mode(lanes, "b") == EXECUTION_MODE_FANOUT


def test_held_claim_forces_inline():
    # b's scope is already held by another run; b must not fan out.
    held = [WriteScopeClaim(claim_id="c1", run_id="other",
                            resolved_path="/src/b", created_at="t")]
    tasks = [Task(id="a", write_scope=["/src/a/**"]),
             Task(id="b", write_scope=["/src/b/**"])]
    lanes = build_lanes(tasks, held_claims=held)
    assert _lane_ids(lanes) == [["a"], ["b"]]
    assert _mode(lanes, "a") == EXECUTION_MODE_FANOUT
    assert _mode(lanes, "b") == EXECUTION_MODE_INLINE


def test_dependencies_still_layer_with_write_scopes():
    # depends_on ordering is preserved; scopes only split within a layer.
    tasks = [Task(id="a", write_scope=["/x"]),
             Task(id="b", depends_on=["a"], write_scope=["/y"]),
             Task(id="c", depends_on=["a"], write_scope=["/x"])]
    lanes = build_lanes(tasks)
    # layer 0: a fan-out alone; layer 1: b (disjoint) and c (overlaps a? no,
    # /y vs /x disjoint -> both fan-out share batch)
    assert _lane_ids(lanes) == [["a"], ["b", "c"]]


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
        test_disjoint_scopes_share_one_batch_as_fanout,
        test_overlapping_scopes_never_share_a_batch,
        test_ancestor_scope_overlaps_descendant,
        test_sibling_prefixes_that_are_not_ancestors_do_not_overlap,
        test_held_claim_forces_inline,
        test_dependencies_still_layer_with_write_scopes,
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
