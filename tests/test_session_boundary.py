"""FFR-700-2: session_boundary required; parallel lanes dispatched as
subagents; a cold session resumes from the state file alone and runs one batch.

Covers all four acceptance criteria of this lane:

1. ``sequences/*.yaml`` carries an explicit ``session_boundary: batch``, and the
   executor refuses a sequence that does not declare one.
2. Lanes marked ``parallel_lanes`` are dispatched as subagents rather than
   executed inline.
3. Demonstrated, not asserted: one batch is executed by a session that receives
   the state file and nothing else.
4. Red proof: a sequence without ``session_boundary`` is rejected, and a second
   batch in the same session is refused.

Self-contained ``sys.path`` handling (independent of conftest/pytest).
"""

import subprocess
import sys
import tempfile
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
    BatchCommand,
    SessionState,
    Session,
    SessionConsumedError,
    load_state_file,
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


# --- Criterion 3: a cold session resumes from the state file alone ---


def _state(session_boundary="batch", batch_index=0, commands=None):
    if commands is None:
        commands = [
            BatchCommand(
                lane_id="T1",
                mode=SUBAGENT,
                command=[sys.executable, "-c", "print('batch-0-T1')"],
            ),
            BatchCommand(
                lane_id="T3",
                mode=INLINE,
                command=[sys.executable, "-c", "print('batch-0-T3')"],
            ),
        ]
    return SessionState(
        session_boundary=session_boundary,
        batch_index=batch_index,
        commands=commands,
    )


def test_cold_session_executes_one_batch_from_state_file_alone():
    # A real subprocess must actually run, proving execution (not an assertion
    # that a plan was built). The session receives only the state object — no
    # sequence, no declaration, no transcript.
    state = _state(
        commands=[
            BatchCommand(
                lane_id="T1",
                mode=INLINE,
                command=[sys.executable, "-c", "print('real-cold-execution')"],
            ),
        ]
    )
    captured = {}

    def inline(argv):
        out = subprocess.run(argv, capture_output=True, check=True)
        captured["stdout"] = out.stdout.decode().strip()
        return out

    session = Session(state=state)
    result = session.run(inline=inline)

    assert result.ran_any is True
    assert result.inline_lane_ids == ["T1"]
    # The batch really executed, not merely planned.
    assert captured["stdout"] == "real-cold-execution"


def test_state_file_round_trips_boundary_and_batch():
    state = _state(batch_index=2)
    d = state.to_dict()
    assert d["session_boundary"] == "batch"
    assert d["batch_index"] == 2
    back = SessionState.from_dict(d)
    assert back.session_boundary == "batch"
    assert back.batch_index == 2
    assert [c.lane_id for c in back.commands] == ["T1", "T3"]


def test_load_state_file_reads_boundary_from_disk():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        import yaml

        yaml.safe_dump(_state().to_dict(), fh)
        path = fh.name
    try:
        state = load_state_file(path)
        assert state.session_boundary == "batch"
        assert state.batch_index == 0
    finally:
        Path(path).unlink()


# --- Criterion 4 (red proof): missing boundary rejected; second batch refused ---


def test_state_file_without_session_boundary_is_rejected():
    for bad in ("", None):
        state = _state(session_boundary=bad)
        try:
            Session(state=state).run(inline=lambda argv: None)
            assert False, "expected MissingSessionBoundaryError"
        except MissingSessionBoundaryError:
            pass


def test_state_file_from_dict_without_boundary_is_rejected():
    d = _state().to_dict()
    del d["session_boundary"]
    try:
        SessionState.from_dict(d)
        assert False, "expected MissingSessionBoundaryError"
    except MissingSessionBoundaryError as e:
        assert "session_boundary" in str(e)


def test_second_batch_in_same_session_is_refused():
    ran = []

    def inline(argv):
        ran.append(list(argv))
        return None

    state = _state(
        batch_index=0,
        commands=[
            BatchCommand(
                lane_id="T3",
                mode=INLINE,
                command=[sys.executable, "-c", "print('batch-0')"],
            ),
        ],
    )
    session = Session(state=state)
    first = session.run(inline=inline)
    assert first.batch_index == 0
    assert len(ran) == 1

    # A second batch in the same session is refused, never run.
    try:
        session.run(inline=inline)
        assert False, "second batch in the same session must be refused"
    except SessionConsumedError as e:
        assert e.batch_index == 0
    # Only the first batch's lane ever executed; the second never ran.
    assert len(ran) == 1


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
        test_cold_session_executes_one_batch_from_state_file_alone,
        test_state_file_round_trips_boundary_and_batch,
        test_load_state_file_reads_boundary_from_disk,
        test_state_file_without_session_boundary_is_rejected,
        test_state_file_from_dict_without_boundary_is_rejected,
        test_second_batch_in_same_session_is_refused,
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
