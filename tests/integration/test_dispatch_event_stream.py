"""Integration tests for the typed live dispatch event stream (SW138-STREAM-001).

Covers the five acceptance criteria end to end against the real contract and
the real runtime runner/registry seams, following the self-contained sys.path
convention of ``test_dispatch_contract.py`` and ``test_dispatch_timeout.py``:

1. ``wave_started`` is flushed before the first worker launch, and every event
   carries a strictly increasing per-run sequence number.
2. Active lanes emit ``lane_started``, criterion-aware ``dispatch_started``,
   ``heartbeat``, ``process_terminal``, ``evidence_recorded`` and
   ``lane_terminal`` as applicable.
3. A child that exceeds the configured heartbeat interval emits a heartbeat
   before its terminal event.
4. Exactly one terminal event exists per child even if result collection is
   retried.
5. Payloads carry no raw stdout/stderr, and state is never inferred from log
   markers, ANSI text, PIDs, or wrapper completion.

The stream is metadata-only and never transition authority: the test proves
the produced JSONL names facts (which criterion group runs, how a process
ended) without ever containing the raw bytes a worker emitted.
"""

import io
import json
import sys
import time
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.dispatch.contracts import (  # noqa: E402
    EventType,
    ProcessStatus,
    TaskStatus,
)
from skillweave.dispatch.events import (  # noqa: E402
    DispatchEventStream,
    HeartbeatMonitor,
    EventStreamError,
)


def _stream(run_id="run-1"):
    sink = io.StringIO()
    return DispatchEventStream(run_id, sink), sink


def _lines(sink):
    return [json.loads(ln) for ln in sink.getvalue().splitlines() if ln.strip()]


# ── Criterion 1: wave_started first, strictly increasing sequence ──────────

def test_wave_started_precedes_worker_launch_and_sequences_increase():
    stream, sink = _stream()
    # The wave is announced before any lane/dispatch/worker event.
    first = stream.wave_started(wave="wave-0")
    stream.lane_started(wave="wave-0", lane_id="ops-a")
    stream.dispatch_started(
        wave="wave-0", lane_id="ops-a", dispatch_id="d-0", criterion_group=[1, 2]
    )
    events = _lines(sink)
    assert events[0]["event_type"] == EventType.WAVE_STARTED.value
    assert events[0]["sequence"] == 1
    sequences = [e["sequence"] for e in events]
    assert sequences == sorted(sequences)
    assert len(sequences) == len(set(sequences)), "sequence must be strictly increasing"
    assert first.sequence == 1


def test_sequences_strictly_increase_across_a_full_run():
    stream, sink = _stream()
    stream.wave_started(wave="w")
    for i in range(5):
        stream.heartbeat(wave="w", lane_id="l", dispatch_id="d")
    assert [e["sequence"] for e in _lines(sink)] == [1, 2, 3, 4, 5, 6]


# ── Criterion 2: the full lifecycle for an active lane ─────────────────────

def test_active_lane_emits_the_full_typed_lifecycle():
    stream, sink = _stream()
    stream.wave_started(wave="wave-0")
    stream.lane_started(wave="wave-0", lane_id="ops")
    stream.dispatch_started(
        wave="wave-0", lane_id="ops", dispatch_id="d-0", criterion_group=[1]
    )
    stream.heartbeat(wave="wave-0", lane_id="ops", dispatch_id="d-0")
    stream.process_terminal(
        wave="wave-0",
        lane_id="ops",
        dispatch_id="d-0",
        process_status=ProcessStatus.EXITED,
        task_status=TaskStatus.DONE,
    )
    stream.evidence_recorded(
        wave="wave-0", lane_id="ops", dispatch_id="d-0", receipt_refs=["r-1"]
    )
    stream.lane_terminal(
        wave="wave-0", lane_id="ops", dispatch_id="d-0", task_status=TaskStatus.DONE
    )

    events = _lines(sink)
    by_type = {e["event_type"] for e in events}
    expected = {
        EventType.WAVE_STARTED.value,
        EventType.LANE_STARTED.value,
        EventType.DISPATCH_STARTED.value,
        EventType.HEARTBEAT.value,
        EventType.PROCESS_TERMINAL.value,
        EventType.EVIDENCE_RECORDED.value,
        EventType.LANE_TERMINAL.value,
    }
    assert expected <= by_type


def test_dispatch_started_is_criterion_aware():
    stream, sink = _stream()
    stream.dispatch_started(
        wave="wave-0", lane_id="ops", dispatch_id="d-0", criterion_group=[2, 3]
    )
    dispatched = _lines(sink)[0]
    assert dispatched["criterion_group"] == [2, 3]


# ── Criterion 3: heartbeat before terminal when interval exceeded ──────────

def test_heartbeat_emitted_before_terminal_when_interval_exceeded():
    stream, sink = _stream()
    monitor = HeartbeatMonitor(stream, interval_seconds=0.5)
    child = "run-1-0"
    monitor.note_activity(child, timestamp=_t(-2.0))  # two seconds ago

    hb = monitor.maybe_heartbeat(
        child_key=child, wave="w", lane_id="ops", dispatch_id="d-0",
        timestamp=_t(0.0),
    )
    assert hb is not None
    terminal = stream.emit_terminal_once(
        child_key=child,
        wave="w",
        lane_id="ops",
        dispatch_id="d-0",
        process_status=ProcessStatus.EXITED,
        task_status=TaskStatus.DONE,
    )
    assert terminal is not None

    events = _lines(sink)
    types = [e["event_type"] for e in events]
    assert EventType.HEARTBEAT.value in types
    assert types.index(EventType.HEARTBEAT.value) < types.index(
        EventType.PROCESS_TERMINAL.value
    )


def test_no_heartbeat_within_the_configured_interval():
    stream, sink = _stream()
    monitor = HeartbeatMonitor(stream, interval_seconds=60.0)
    child = "run-1-0"
    monitor.note_activity(child, timestamp=_t(-1.0))
    hb = monitor.maybe_heartbeat(
        child_key=child, wave="w", lane_id="l", dispatch_id="d", timestamp=_t(0.0)
    )
    assert hb is None
    assert _lines(sink) == []


# ── Criterion 4: exactly one terminal per child across retries ─────────────

def test_exactly_one_terminal_per_child_even_when_retried():
    stream, sink = _stream()
    args = dict(
        child_key="run-1-0",
        wave="w",
        lane_id="ops",
        dispatch_id="d-0",
        process_status=ProcessStatus.EXITED,
        task_status=TaskStatus.DONE,
    )
    first = stream.emit_terminal_once(**args)
    assert first is not None
    for _ in range(2):
        assert stream.emit_terminal_once(**args) is None
    events = _lines(sink)
    terminals = [e for e in events if e["event_type"] == EventType.PROCESS_TERMINAL.value]
    assert len(terminals) == 1


def test_distinct_children_get_distinct_terminals():
    stream, sink = _stream()
    stream.emit_terminal_once(
        child_key="run-1-0", wave="w", lane_id="a", dispatch_id="d-0",
        process_status=ProcessStatus.EXITED, task_status=TaskStatus.DONE,
    )
    stream.emit_terminal_once(
        child_key="run-1-1", wave="w", lane_id="a", dispatch_id="d-1",
        process_status=ProcessStatus.SIGNALED, task_status=TaskStatus.FAILED,
    )
    events = _lines(sink)
    terminals = [e for e in events if e["event_type"] == EventType.PROCESS_TERMINAL.value]
    assert len(terminals) == 2


# ── Criterion 5: metadata-only, no raw output, no inferred state ───────────

def test_payloads_are_metadata_only():
    stream, sink = _stream()
    stream.wave_started(wave="w")
    stream.evidence_recorded(
        wave="w", lane_id="ops", dispatch_id="d", receipt_refs=["recv-1"]
    )
    for event in _lines(sink):
        for key in ("stdout", "stderr", "output", "log_lines", "trace"):
            assert key not in event


def test_refuses_raw_stdout_in_payload():
    stream, _ = _stream()
    with pytest.raises(EventStreamError):
        stream.emit(
            wave="w",
            lane_id="l",
            dispatch_id="d",
            event_type=EventType.PROCESS_TERMINAL,
            process_status=ProcessStatus.EXITED,
            task_status=TaskStatus.DONE,
            payload={"stdout": "some worker output"},
        )


def test_event_does_not_carry_pid_or_log_markers():
    stream, sink = _stream()
    stream.emit(
        wave="w",
        lane_id="l",
        dispatch_id="d",
        event_type=EventType.PROCESS_TERMINAL,
        process_status=ProcessStatus.EXITED,
        task_status=TaskStatus.DONE,
        payload={"exit_code": 0, "signal": None},
    )
    raw = sink.getvalue()
    assert "pid" not in raw.lower()
    assert "\x1b[" not in raw  # no ANSI escape sequences


# ── end-to-end against the real runtime runner adapter ─────────────────────

def test_stream_consumes_real_runner_result_as_metadata_only():
    """A real worker run feeds the stream facts, never the raw bytes.

    Runs ``echo`` through the runtime runner adapter, then publishes only the
    process outcome as typed events. The stream must record ``exited``/``done``
    and the receipt references, while the echoed stdout stays out of the
    stream (it lives in the runner's receipt, addressed by digest).
    """
    from skillweave.runtime.runner_adapter import run_command

    result = run_command(
        ["/bin/echo", "secret-worker-output"],
        run_id="run-real",
        subject_repo="skillweave/skillweave",
        subject_commit="0" * 40,
        tool="stub",
        model="model-xyz",
    )
    assert result.succeeded

    stream, sink = _stream(run_id="run-real")
    ps = (
        ProcessStatus.EXITED
        if result.termination == "exited"
        else ProcessStatus.SIGNALED
    )
    ts = TaskStatus.DONE if result.succeeded else TaskStatus.FAILED
    stream.emit_terminal_once(
        child_key="run-real-0",
        wave="w",
        lane_id="ops",
        dispatch_id="d-0",
        process_status=ps,
        task_status=ts,
    )
    stream.evidence_recorded(
        wave="w",
        lane_id="ops",
        dispatch_id="d-0",
        receipt_refs=[result.stdout_receipt.artifact_id],
    )

    for event in _lines(sink):
        raw = json.dumps(event)
        assert "secret-worker-output" not in raw
    terminal = _lines(sink)[0]
    assert terminal["process_status"] == "exited"
    assert terminal["task_status"] == "done"


def _t(offset_seconds: float) -> str:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    return (now + timedelta(seconds=offset_seconds)).isoformat()
