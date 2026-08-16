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
    build_sessions,
    build_schedule,
    Schedule,
    Sequence,
    MissingSessionBoundaryError,
    SessionBatch,
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


# --- Dispatch 3 (criteria 7, 8, 10): session_boundary carried and enforced ---


def test_session_boundary_is_carried_explicitly_on_every_batch():
    # Criterion 7: each emitted batch IS a session boundary and carries the
    # marker explicitly, so a consumer never has to infer where one ends.
    seq = Sequence(session_boundary="chain-1", tasks=[
        Task(id="a", write_scope=["/src/a/**"]),
        Task(id="b", depends_on=["a"], write_scope=["/src/b/**"]),
    ])
    sessions = build_sessions(seq)
    assert len(sessions) >= 1
    for sb in sessions:
        assert sb.session_boundary == "chain-1"


def test_sequence_without_session_boundary_is_refused_naming_the_key():
    # Criterion 8 + 10(a): a sequence that does not declare session_boundary is
    # REFUSED, not defaulted; the error names the missing key.
    seq = Sequence(session_boundary=None, tasks=[Task(id="a")])
    try:
        build_sessions(seq)
        assert False, "expected MissingSessionBoundaryError"
    except MissingSessionBoundaryError as e:
        assert "session_boundary" in str(e)


def test_overlapping_scopes_are_never_emitted_as_fanout_sessions():
    # Criterion 10(b): a session batch whose lanes overlap in write scope is
    # never emitted as fan-out. Overlap forces inline (disjoint batches).
    seq = Sequence(session_boundary="chain-2", tasks=[
        Task(id="a", write_scope=["/src/shared/**"]),
        Task(id="b", write_scope=["/src/shared/**"]),
    ])
    sessions = build_sessions(seq)
    for sb in sessions:
        modes = [lane.execution_mode for lane in sb.lanes]
        if EXECUTION_MODE_FANOUT in modes:
            scopes = [tuple(sorted(lane.task.write_scope))
                      for lane in sb.lanes
                      if lane.execution_mode == EXECUTION_MODE_FANOUT]
            assert len(scopes) == 1, (
                "fan-out lanes must be pairwise disjoint; got a shared batch"
            )
    # and the specific pair here must both be inline, in separate batches.
    flattened = [(lane.task_id, lane.execution_mode)
                 for sb in sessions for lane in sb.lanes]
    assert ("a", EXECUTION_MODE_INLINE) in flattened
    assert ("b", EXECUTION_MODE_INLINE) in flattened


# --- Dispatch 4 (criteria 3, 4, 6): max_parallel, gate gating, no runner ---


def _schedule_lane_ids(schedule):
    return [[lane.task_id for lane in sb.lanes] for sb in schedule.batches]


def test_max_parallel_splits_fanout_into_chunks():
    # Criterion 3: four disjoint tasks, max_parallel=2 -> at most 2 lanes per
    # batch, split deterministically by id order.
    seq = Sequence(session_boundary="c", tasks=[
        Task(id="a", write_scope=["/src/a/**"]),
        Task(id="b", write_scope=["/src/b/**"]),
        Task(id="c", write_scope=["/src/c/**"]),
        Task(id="d", write_scope=["/src/d/**"]),
    ])
    sched = build_schedule(seq, max_parallel=2)
    assert _schedule_lane_ids(sched) == [["a", "b"], ["c", "d"]]
    assert sched.blocked == []


def test_max_parallel_none_keeps_one_fanout_batch():
    seq = Sequence(session_boundary="c", tasks=[
        Task(id="a", write_scope=["/src/a/**"]),
        Task(id="b", write_scope=["/src/b/**"]),
        Task(id="c", write_scope=["/src/c/**"]),
    ])
    sched = build_schedule(seq)
    assert _schedule_lane_ids(sched) == [["a", "b", "c"]]


def test_max_parallel_zero_or_negative_is_an_error():
    seq = Sequence(session_boundary="c", tasks=[Task(id="a")])
    for bad in (0, -1):
        try:
            build_schedule(seq, max_parallel=bad)
            assert False, "expected ValueError for max_parallel=%r" % bad
        except ValueError:
            pass


def test_max_parallel_does_not_split_inline_lanes():
    # Inline lanes are already one-per-batch; max_parallel must not touch them.
    seq = Sequence(session_boundary="c", tasks=[
        Task(id="a", write_scope=["/src/shared/**"]),
        Task(id="b", write_scope=["/src/shared/**"]),
    ])
    sched = build_schedule(seq, max_parallel=1)
    assert _schedule_lane_ids(sched) == [["a"], ["b"]]


def test_failed_gate_does_not_release_dependents():
    # Criterion 4: a has gate g; g failed -> b is NOT released.
    seq = Sequence(session_boundary="c", tasks=[
        Task(id="a", gate="g"),
        Task(id="b", depends_on=["a"]),
    ])
    sched = build_schedule(seq, gate_results={"g": False})
    assert sched.blocked == ["b"]
    assert _schedule_lane_ids(sched) == [["a"]]


def test_passed_gate_releases_dependents():
    seq = Sequence(session_boundary="c", tasks=[
        Task(id="a", gate="g1"),
        Task(id="b", depends_on=["a"]),
    ])
    sched = build_schedule(seq, gate_results={"g1": True})
    assert sched.blocked == []
    assert _schedule_lane_ids(sched) == [["a"], ["b"]]


def test_missing_gate_result_blocks_dependents():
    # A gate with no recorded result is treated as not-passed (blocking).
    seq = Sequence(session_boundary="c", tasks=[
        Task(id="a", gate="g1"),
        Task(id="b", depends_on=["a"]),
    ])
    sched = build_schedule(seq)
    assert sched.blocked == ["b"]


def test_gate_failure_is_transitive():
    # a(gate g failed) blocks b; b blocks c even though c has no gate of its own.
    seq = Sequence(session_boundary="c", tasks=[
        Task(id="a", gate="g"),
        Task(id="b", depends_on=["a"]),
        Task(id="c", depends_on=["b"]),
    ])
    sched = build_schedule(seq, gate_results={"g": False})
    assert sched.blocked == ["b", "c"]
    assert _schedule_lane_ids(sched) == [["a"]]


def test_blocked_tasks_are_reported_not_silently_dropped():
    # The schedule names what did not run; nothing vanishes from the result.
    seq = Sequence(session_boundary="c", tasks=[
        Task(id="a", gate="g"),
        Task(id="b", depends_on=["a"]),
        Task(id="x"),
    ])
    sched = build_schedule(seq, gate_results={"g": False})
    assert sched.blocked == ["b"]
    # x is independent and still scheduled alongside a.
    assert _schedule_lane_ids(sched) == [["a", "x"]]


def test_scheduler_knows_no_runner_and_starts_no_processes():
    # Criterion 6: the scheduler module must never import or invoke the runner
    # adapter, nor spawn a process. Proven by inspecting the source: no import
    # of runner_adapter and no process-spawning call.
    src = Path(__file__).resolve().parent.parent.parent / "src"
    module = (src / "skillweave" / "runtime" / "dagscheduler.py").read_text()
    forbidden = [
        "import runner_adapter",
        "from .runner_adapter",
        "from skillweave.runtime.runner_adapter",
        "import subprocess",
        "from subprocess",
        "os.system",
        "os.popen",
        "os.fork",
        "os.exec",
        "Popen",
    ]
    for token in forbidden:
        assert token not in module, f"dagscheduler.py must not contain {token!r}"


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
        test_session_boundary_is_carried_explicitly_on_every_batch,
        test_sequence_without_session_boundary_is_refused_naming_the_key,
        test_overlapping_scopes_are_never_emitted_as_fanout_sessions,
        test_max_parallel_splits_fanout_into_chunks,
        test_max_parallel_none_keeps_one_fanout_batch,
        test_max_parallel_zero_or_negative_is_an_error,
        test_max_parallel_does_not_split_inline_lanes,
        test_failed_gate_does_not_release_dependents,
        test_passed_gate_releases_dependents,
        test_missing_gate_result_blocks_dependents,
        test_gate_failure_is_transitive,
        test_blocked_tasks_are_reported_not_silently_dropped,
        test_scheduler_knows_no_runner_and_starts_no_processes,
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
