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
import threading
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


# ── Concurrency: serialized emission, ordered persisted JSONL, one terminal ─

class _SynchronizedSink(io.StringIO):
    """A thread-safe text sink for concurrent emitters.

    ``StringIO`` is not safe for concurrent writes; the stream's own lock
    already serializes emission, but the live reader (the getvalue()/read path)
    and the terminal idempotency still need a safe sink under the stress test.
    """

    def __init__(self):
        super().__init__()
        self._read_lock = threading.Lock()

    def write(self, s):
        with self._read_lock:
            super().write(s)
        return len(s)

    def getvalue(self):
        with self._read_lock:
            return super().getvalue()


def _join_stream(stream):
    from threading import Thread

    def worker(index):
        for _ in range(2000):
            stream.heartbeat(wave="w", lane_id=f"l{index}", dispatch_id=f"d{index}")

    threads = [Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_concurrent_emission_persists_strictly_increasing_order():
    """Serialized emission keeps the persisted JSONL strictly increasing.

    The prior commit released the lock between sequence assignment and the
    sink write, so concurrent emitters produced adjacent inversions. This test
    drives 8 emitters x 2000 events and asserts the persisted sequence is
    strictly increasing with unique, gap-free values.
    """
    sink = _SynchronizedSink()
    stream = DispatchEventStream("run-concurrent", sink)
    _join_stream(stream)
    sequences = [e["sequence"] for e in _lines(sink)]
    assert len(sequences) == 8 * 2000
    assert len(set(sequences)) == len(sequences), "sequences must be unique"
    assert sequences == sorted(sequences), "persisted order must be monotonic"
    assert all(
        b == a + 1 for a, b in zip(sequences, sequences[1:])
    ), "sequences must be gap-free and strictly increasing"


def test_concurrent_terminal_once_is_exactly_one_per_child():
    """Concurrent/retried terminal collection yields one terminal per child.

    Restructures the terminal guard and emission into a single serialized
    emission operation (no nested-lock deadlock), so a child whose terminal is
    requested concurrently still persists exactly one terminal event.
    """
    sink = _SynchronizedSink()
    stream = DispatchEventStream("run-terminal", sink)
    keys = [f"run-terminal-{i}" for i in range(8)]
    args = [
        dict(
            child_key=k,
            wave="w",
            lane_id="l",
            dispatch_id=f"d{i}",
            process_status=ProcessStatus.EXITED,
            task_status=TaskStatus.DONE,
        )
        for i, k in enumerate(keys)
    ]

    def collector(i):
        a = args[i]
        for _ in range(200):
            stream.emit_terminal_once(
                child_key=keys[i],
                wave=a["wave"],
                lane_id=a["lane_id"],
                dispatch_id=a["dispatch_id"],
                process_status=a["process_status"],
                task_status=a["task_status"],
            )

    threads = [threading.Thread(target=collector, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    events = _lines(sink)
    terminals = [e for e in events if e["event_type"] == EventType.PROCESS_TERMINAL.value]
    assert len(terminals) == 8
    seen_keys = {e["dispatch_id"] for e in terminals}
    assert seen_keys == {f"d{i}" for i in range(8)}, "one terminal per child"
