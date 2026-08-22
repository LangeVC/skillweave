"""FFR-700-2 (dispatch 1 of 2): session_boundary required; parallel lanes
dispatched as subagents.

Covers the two acceptance criteria of this dispatch:

1. ``sequences/*.yaml`` carries an explicit ``session_boundary: batch``, and the
   executor refuses a sequence that does not declare one.
2. Lanes marked ``parallel_lanes`` are dispatched as subagents rather than
   executed inline.

Self-contained ``sys.path`` handling (independent of conftest/pytest).
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.promptchain.execute import (  # noqa: E402
    SequenceDeclaration,
    Lane,
    INLINE,
    SUBAGENT,
    MissingSessionBoundaryError,
    load_sequence,
    build_dispatch_plan,
    execute_sequence,
)


def _decl(session_boundary="batch"):
    return {
        "sequence_type": "build",
        "session_boundary": session_boundary,
        "phases": [
            {
                "phase": "build",
                "parallel_lanes": [
                    {"id": "T1"},
                    {"id": "T2"},
                ],
                "serialized_lanes": [
                    {"id": "T3"},
                ],
            },
        ],
    }


# --- Criterion 1: session_boundary declared and refused when missing ---


def test_sequence_with_session_boundary_is_accepted():
    seq = load_sequence(_decl("batch"))
    assert seq.has_boundary is True
    assert seq.session_boundary == "batch"


def test_sequence_without_session_boundary_is_refused_naming_the_key():
    decl = _decl("batch")
    del decl["session_boundary"]
    try:
        load_sequence(decl)
        assert False, "expected MissingSessionBoundaryError"
    except MissingSessionBoundaryError as e:
        assert "session_boundary" in str(e)


def test_sequence_with_empty_session_boundary_is_refused():
    for bad in ("", None):
        decl = _decl(bad)
        try:
            load_sequence(decl)
            assert False, "expected MissingSessionBoundaryError"
        except MissingSessionBoundaryError:
            pass


def test_build_plan_refuses_missing_boundary():
    seq = SequenceDeclaration(session_boundary=None)
    try:
        build_dispatch_plan(seq)
        assert False, "expected MissingSessionBoundaryError"
    except MissingSessionBoundaryError:
        pass


# --- Criterion 2: parallel_lanes dispatched as subagents ---


def test_parallel_lanes_are_dispatched_as_subagents():
    plan = build_dispatch_plan(load_sequence(_decl("batch")))
    modes = {e.lane_id: e.mode for e in plan.entries}
    assert modes["T1"] == SUBAGENT
    assert modes["T2"] == SUBAGENT


def test_serialized_lanes_stay_inline():
    plan = build_dispatch_plan(load_sequence(_decl("batch")))
    modes = {e.lane_id: e.mode for e in plan.entries}
    assert modes["T3"] == INLINE


def test_no_parallel_lane_is_inline():
    plan = build_dispatch_plan(load_sequence(_decl("batch")))
    for entry in plan.entries:
        if entry.mode == INLINE:
            assert entry.lane_id not in {"T1", "T2"}, (
                "a parallel lane was dispatched inline"
            )


def test_lane_kind_is_derived_from_the_block_not_invented():
    seq = load_sequence(_decl("batch"))
    by_id = {lane.id: lane.kind for lane in seq.all_lanes()}
    assert by_id["T1"] == "parallel"
    assert by_id["T2"] == "parallel"
    assert by_id["T3"] == "serialized"


def test_execute_sequence_returns_a_plan_and_uses_the_seam():
    calls = []

    def fake_fanout(commands, **kwargs):
        calls.append(list(commands))
        return None

    seq = load_sequence(_decl("batch"))
    plan = execute_sequence(seq, fanout=fake_fanout)
    assert plan.modes() == [SUBAGENT, SUBAGENT, INLINE]
    # The seam was handed the parallel lane ids only, never the serialized ones.
    assert calls == [["T1", "T2"]]


def test_execute_sequence_without_parallel_lanes_does_not_call_seam():
    decl = {
        "sequence_type": "build",
        "session_boundary": "batch",
        "phases": [
            {"phase": "build", "serialized_lanes": [{"id": "T3"}]},
        ],
    }
    called = []

    def fake_fanout(*args, **kwargs):
        called.append(True)
        return None

    plan = execute_sequence(load_sequence(decl), fanout=fake_fanout)
    assert plan.modes() == [INLINE]
    assert called == []


def _run_all() -> int:
    tests = [
        test_sequence_with_session_boundary_is_accepted,
        test_sequence_without_session_boundary_is_refused_naming_the_key,
        test_sequence_with_empty_session_boundary_is_refused,
        test_build_plan_refuses_missing_boundary,
        test_parallel_lanes_are_dispatched_as_subagents,
        test_serialized_lanes_stay_inline,
        test_no_parallel_lane_is_inline,
        test_lane_kind_is_derived_from_the_block_not_invented,
        test_execute_sequence_returns_a_plan_and_uses_the_seam,
        test_execute_sequence_without_parallel_lanes_does_not_call_seam,
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
