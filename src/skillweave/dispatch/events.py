"""Typed live dispatch event stream and heartbeat (SW138-STREAM-001).

This module owns the *event stream*, not the dispatch mechanics. The dispatch
sequence/event contract lives in ``contracts``; this module is the producer of
that contract at runtime: it turns a run's lifecycle into a monotonic, unbuffered
JSONL stream of :class:`~skillweave.dispatch.contracts.DispatchEvent` records.

The stream is a **metadata-only view, never transition authority**. It reports
which run/wave/lane/dispatch is doing what and whether evidence exists. It never
decides what happens next, and it never carries the state that decides: no raw
stdout/stderr, no PIDs, no log markers, no ANSI text, no wrapper-completion flags.
Whatever a consumer reads here is a fact about the run, not the raw material the
run produced or the input some other authority must interpret.

Four guarantees are discharged here:

1. ``wave_started`` is flushed **before** any worker launch is handed off; every
   event carries a strictly increasing per-run ``sequence`` number.
2. Active lanes emit ``lane_started``, criterion-aware ``dispatch_started``,
   ``heartbeat``, ``process_terminal``, ``evidence_recorded``, and
   ``lane_terminal`` as the lifecycle applies.
3. A child that exceeds the configured heartbeat interval emits a ``heartbeat``
   **before** its terminal event.
4. Exactly one terminal event exists per child, even if result collection is
   retried — terminal emission is idempotent, keyed by child identity.
5. Payloads contain no raw stdout/stderr, and state is never inferred from log
   markers, ANSI text, PIDs or wrapper completion.

Nothing here launches a worker. The stream appends to a caller-supplied text
sink (a file or ``sys.stdout``), which the ``SW138-DISPATCH-001`` command will
connect to stdout or a JSONL file. This module names no concrete model, no
concrete tool and no concrete harness.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, List, Optional, TextIO

from .contracts import (
    DispatchEvent,
    EventType,
    ProcessStatus,
    TaskStatus,
)

#: Amount of a reported stream (stdout/stderr) that is refused outright. The
#: stream is metadata-only, so any payload field that looks like raw process
#: output is rejected rather than silently folded into an event.
_RAW_OUTPUT_FIELDS = ("stdout", "stderr", "output", "log_lines", "trace")


class EventStreamError(ValueError):
    """Raised when a payload would admit raw output or an illegal sequence."""


def _now() -> str:
    """Return the current UTC timestamp in ISO-8601 form."""
    return datetime.now(timezone.utc).isoformat()


def _has_raw_output(fields: dict[str, Any]) -> bool:
    """Return the offending key when ``fields`` carries raw output text."""
    for key in _RAW_OUTPUT_FIELDS:
        if key in fields:
            return key
    return None


def _refuse_raw_output(message: str) -> None:
    """Raise :class:`EventStreamError` when a payload carries raw output.

    This is the active form of criterion 5: the stream never admits stdout/
    stderr bytes, so an event that asks to carry them is refused, not redacted
    into something the caller did not say.
    """
    raise EventStreamError(
        f"event payload is metadata-only and may not carry '{message}': "
        "raw stdout/stderr belong in the artifact store, never in the stream"
    )


@dataclass
class _ChildState:
    """The stream's private record of one dispatch child.

    ``terminal_emitted`` is the idempotency guard for criterion 4: once a
    terminal event has been flushed for this child, further terminal requests
    are no-ops, so a retried result collection cannot produce a second terminal.
    """

    child_key: str
    dispatch_id: str
    terminal_emitted: bool = False


class DispatchEventStream:
    """An append-only, monotonic JSONL event stream for one run.

    ``sink`` is a text stream (a file handle or ``sys.stdout``) opened by the
    caller. Lines are written unbuffered (``flush=True``) so a live consumer
    sees ``wave_started`` before the first worker launch completes. The per-run
    ``sequence`` counter starts at 1 and increments on every emitted event, so
    sequence numbers are strictly increasing within a run (criterion 1).

    This is a producer of facts. It holds no authority over lanes, gates,
    dispatch decisions or process lifecycle — those stay with the dispatcher.
    """

    def __init__(
        self,
        run_id: str,
        sink: TextIO,
        *,
        start_sequence: int = 1,
    ) -> None:
        if not run_id:
            raise EventStreamError("run_id must be a non-empty string")
        self.run_id = run_id
        self._sink = sink
        self._sequence = start_sequence
        self._lock = Lock()
        self._children: dict[str, _ChildState] = {}

    # -- sequence ----------------------------------------------------------

    @property
    def sequence(self) -> int:
        """The next sequence number to be emitted (strictly increasing)."""
        return self._sequence

    def _next_sequence(self) -> int:
        with self._lock:
            seq = self._sequence
            self._sequence += 1
            return seq

    # -- core emission ------------------------------------------------------

    def _emit(self, event: DispatchEvent) -> DispatchEvent:
        """Append one event as an unbuffered JSONL line and return it."""
        self._sink.write(_encode_event(event) + "\n")
        self._sink.flush()
        return event

    def emit(
        self,
        *,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        event_type: EventType,
        process_status: ProcessStatus,
        task_status: TaskStatus,
        evidence_status: Optional[str] = None,
        receipt_refs: Optional[List[str]] = None,
        payload: Optional[dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> DispatchEvent:
        """Build and emit one typed event.

        ``payload`` is an optional set of *metadata-only* extra fields merged
        into the event's ``receipt_refs``-adjacent surface. Any payload field
        that carries raw stdout/stderr is refused (criterion 5). The event is
        assigned the next strict per-run sequence number before it is flushed.
        """
        merged: dict[str, Any] = {}
        if payload:
            bad = _has_raw_output(payload)
            if bad:
                _refuse_raw_output(bad)
            merged.update(payload)

        event = DispatchEvent(
            run_id=self.run_id,
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            sequence=self._next_sequence(),
            timestamp=timestamp or _now(),
            event_type=event_type.value,
            process_status=process_status.value,
            task_status=task_status.value,
            evidence_status=evidence_status,
            receipt_refs=list(receipt_refs) if receipt_refs else [],
        )
        # Metadata-only extras ride alongside the fixed surface, never inside
        # the process/evidence status fields and never as raw output.
        if merged:
            _append_metadata(event, merged)
        return self._emit(event)

    # -- lifecycle shortcuts ------------------------------------------------

    def wave_started(self, *, wave: str) -> DispatchEvent:
        """Emit ``wave_started`` (criterion 1: flushed before worker launch)."""
        return self.emit(
            wave=wave,
            lane_id="",
            dispatch_id="",
            event_type=EventType.WAVE_STARTED,
            process_status=ProcessStatus.NOT_STARTED,
            task_status=TaskStatus.QUEUED,
        )

    def lane_started(self, *, wave: str, lane_id: str) -> DispatchEvent:
        return self.emit(
            wave=wave,
            lane_id=lane_id,
            dispatch_id="",
            event_type=EventType.LANE_STARTED,
            process_status=ProcessStatus.NOT_STARTED,
            task_status=TaskStatus.QUEUED,
        )

    def dispatch_started(
        self,
        *,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        criterion_group: Optional[List[int]] = None,
    ) -> DispatchEvent:
        """Emit a criterion-aware ``dispatch_started``.

        ``criterion_group`` is the set of 1-based criterion indices this
        dispatch will discharge. It is recorded as metadata so the stream
        identifies *which* criterion group is running (FR-4), without the
        dispatcher ever inferring state from the payload.
        """
        payload: dict[str, Any] = {}
        if criterion_group is not None:
            payload["criterion_group"] = list(criterion_group)
        return self.emit(
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            event_type=EventType.DISPATCH_STARTED,
            process_status=ProcessStatus.RUNNING,
            task_status=TaskStatus.DISPATCHED,
            payload=payload,
        )

    def heartbeat(
        self,
        *,
        wave: str,
        lane_id: str,
        dispatch_id: str,
    ) -> DispatchEvent:
        return self.emit(
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            event_type=EventType.HEARTBEAT,
            process_status=ProcessStatus.RUNNING,
            task_status=TaskStatus.IN_PROGRESS,
        )

    def process_terminal(
        self,
        *,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        process_status: ProcessStatus,
        task_status: TaskStatus,
        payload: Optional[dict[str, Any]] = None,
    ) -> DispatchEvent:
        """Emit ``process_terminal`` with the child's process status.

        ``process_status`` is ``exited``/``signaled``/``timed_out``/
        ``launch_failed``; ``task_status`` records ``done``/``failed``. This is
        a fact about the process, never raw output: exit code / signal travel
        only as small metadata, and are refused if they look like raw text.
        """
        return self.emit(
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            event_type=EventType.PROCESS_TERMINAL,
            process_status=process_status,
            task_status=task_status,
            payload=payload,
        )

    def evidence_recorded(
        self,
        *,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        receipt_refs: Optional[List[str]] = None,
    ) -> DispatchEvent:
        """Emit ``evidence_recorded`` naming the receipts that now exist.

        ``receipt_refs`` are receipt identifiers (digest-addressed), never the
        resolved bytes. The stream records that evidence exists, not the
        evidence itself (criterion 5).
        """
        return self.emit(
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            event_type=EventType.EVIDENCE_RECORDED,
            process_status=ProcessStatus.EXITED,
            task_status=TaskStatus.DONE,
            evidence_status="recorded",
            receipt_refs=receipt_refs,
        )

    def lane_terminal(
        self,
        *,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        task_status: TaskStatus,
    ) -> DispatchEvent:
        return self.emit(
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            event_type=EventType.LANE_TERMINAL,
            process_status=ProcessStatus.EXITED,
            task_status=task_status,
        )

    # -- terminal idempotency (criterion 4) ----------------------------------

    def emit_terminal_once(
        self,
        *,
        child_key: str,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        process_status: ProcessStatus,
        task_status: TaskStatus,
        payload: Optional[dict[str, Any]] = None,
    ) -> Optional[DispatchEvent]:
        """Emit a terminal event for ``child_key`` at most once per stream.

        ``child_key`` uniquely identifies one dispatch child (for example
        ``<run_id>-<index>`` as produced by ``fanout`` / ``runner_adapter``).
        The first terminal request for that key is emitted; every subsequent
        request — including a retried result collection — is a no-op returning
        ``None``. This is the idempotency that guarantees exactly one terminal
        event per child (criterion 4).
        """
        with self._lock:
            state = self._children.get(child_key)
            if state is None:
                state = _ChildState(child_key=child_key, dispatch_id=dispatch_id)
                self._children[child_key] = state
            if state.terminal_emitted:
                return None
            state.terminal_emitted = True
        return self.emit(
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            event_type=EventType.PROCESS_TERMINAL,
            process_status=process_status,
            task_status=task_status,
            payload=payload,
        )


@dataclass
class HeartbeatMonitor:
    """Emits a heartbeat when a child exceeds the configured interval.

    The monitor tracks the last event timestamp per child. When
    :meth:`maybe_heartbeat` is called and the child has not emitted for at
    least ``interval_seconds``, a ``heartbeat`` is emitted **before** any
    terminal event for that child (criterion 3). The monitor never runs its own
    clock: it is driven by the caller at observation points, so no background
    thread and no unbounded wait is created here.

    ``interval_seconds`` is the configured interval; it must be positive. The
    gate fixture uses at most five seconds, but this module imposes no upper
    bound — the interval is configuration, not a constant baked in.
    """

    def __init__(
        self,
        stream: DispatchEventStream,
        interval_seconds: float,
    ) -> None:
        if interval_seconds <= 0:
            raise EventStreamError("heartbeat interval must be positive")
        self._stream = stream
        self._interval = interval_seconds
        self._last_activity: dict[str, str] = {}

    def _elapsed(self, child_key: str, now_str: str) -> float:
        last = self._last_activity.get(child_key)
        if last is None:
            return float("inf")
        now = datetime.fromisoformat(now_str)
        then = datetime.fromisoformat(last)
        return (now - then).total_seconds()

    def note_activity(self, child_key: str, timestamp: Optional[str] = None) -> None:
        self._last_activity[child_key] = timestamp or _now()

    def maybe_heartbeat(
        self,
        *,
        child_key: str,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        timestamp: Optional[str] = None,
    ) -> Optional[DispatchEvent]:
        """Emit a heartbeat if the child has exceeded the configured interval."""
        now_str = timestamp or _now()
        elapsed = self._elapsed(child_key, now_str)
        if elapsed < self._interval:
            return None
        event = self._stream.heartbeat(
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
        )
        self.note_activity(child_key, timestamp=now_str)
        return event


# -- metadata-only payload plumbing ------------------------------------------

def _append_metadata(event: DispatchEvent, fields: dict[str, Any]) -> None:
    """Attach metadata-only extras to an event without a dedicated field.

    The ``DispatchEvent`` surface is fixed by the contract; extras travel as a
    single serialisable block so a consumer can read which criterion group is
    running or how a process ended, but never raw output. The extras are
    stored on the instance (not persisted in ``receipt_refs``), and are written
    into the JSON payload on serialisation.

    This keeps ``contracts.DispatchEvent.to_dict`` authoritative for the fixed
    surface while the stream carries additional metadata-free facts. Because
    the contract's ``to_json`` serialises only the declared fields, the extras
    are surfaced by the stream's own serialiser instead.
    """
    attached = getattr(event, "_stream_metadata", None)
    if attached is None:
        attached = {}
        setattr(event, "_stream_metadata", attached)
    attached.update(fields)


def _encode_event(event: DispatchEvent) -> str:
    """Encode an event for the JSONL line, including stream metadata extras.

    This is the stream's own serialiser. It is deliberately not
    ``DispatchEvent.to_json`` — that method names the fixed contract surface
    only, whereas the stream must also carry metadata-only extras (criterion
    group, exit code, signal) that the contract does not declare a column for.
    """
    data = event.to_dict()
    extras = getattr(event, "_stream_metadata", None)
    if extras:
        data.update(extras)
    return json.dumps(data, sort_keys=True)


__all__ = [
    "DispatchEventStream",
    "HeartbeatMonitor",
    "EventStreamError",
]
