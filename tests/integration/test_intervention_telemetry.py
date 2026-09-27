"""Integration tests for intervention telemetry (SW-157-TELEMETRY-001).

Covers:
1. Distinct restart/malformed/desync events with privacy-safe payloads.
2. Measured receipt digest that the closeout consumer can verify.
3. Provider-free closeout/retro consumption.
4. Privacy negative: blocked payload keys are refused.
"""

import io
import json
import sys
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
from skillweave.dispatch.events import DispatchEventStream  # noqa: E402
from skillweave.telemetry_intervention import (  # noqa: E402
    InterventionTelemetryError,
    InterventionEmitter,
    InterventionCloseout,
    _receipt_digest,
    _validate_payload,
)


def _stream(run_id="run-1"):
    sink = io.StringIO()
    return DispatchEventStream(run_id, sink), sink


def _lines(sink):
    return [json.loads(ln) for ln in sink.getvalue().splitlines() if ln.strip()]


# ── Event emission ────────────────────────────────────────────────────────

def test_emit_restart_event():
    stream, sink = _stream()
    emitter = InterventionEmitter(stream)
    result = emitter.emit_restart(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="process terminated unexpectedly",
        attempt=1, max_attempts=3, child_key="run-1-0",
    )
    assert emitter.restart_count == 1
    assert emitter.malformed_count == 0
    assert emitter.desync_count == 0
    events = _lines(sink)
    assert len(events) == 1
    ev = events[0]
    assert ev["event_type"] == "intervention_restart"
    assert ev["process_status"] == "launch_failed"
    assert ev["task_status"] == "failed"
    assert ev["reason"] == "process terminated unexpectedly"
    assert ev["attempt"] == 1
    assert ev["max_attempts"] == 3
    assert ev["child_key"] == "run-1-0"


def test_emit_malformed_event():
    stream, sink = _stream()
    emitter = InterventionEmitter(stream)
    emitter.emit_malformed(
        wave="0", lane_id="L1", dispatch_id="d2",
        reason="contract payload invalid", elapsed_ms=42,
    )
    assert emitter.malformed_count == 1
    events = _lines(sink)
    ev = events[0]
    assert ev["event_type"] == "intervention_malformed"
    assert ev["reason"] == "contract payload invalid"
    assert ev["elapsed_ms"] == 42


def test_emit_desync_event():
    stream, sink = _stream()
    emitter = InterventionEmitter(stream)
    emitter.emit_desync(
        wave="0", lane_id="L2", dispatch_id="d3",
        reason="state divergence detected", signal="SIGTERM",
    )
    assert emitter.desync_count == 1
    events = _lines(sink)
    ev = events[0]
    assert ev["event_type"] == "intervention_desync"
    assert ev["reason"] == "state divergence detected"
    assert ev["signal"] == "SIGTERM"


def test_emit_multiple_intervention_events():
    stream, sink = _stream()
    emitter = InterventionEmitter(stream)
    emitter.emit_restart(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="retry", attempt=1, max_attempts=3,
    )
    emitter.emit_malformed(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="bad payload",
    )
    emitter.emit_restart(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="retry", attempt=2, max_attempts=3,
    )
    emitter.emit_desync(
        wave="0", lane_id="L2", dispatch_id="d3",
        reason="clock skew",
    )
    assert emitter.restart_count == 2
    assert emitter.malformed_count == 1
    assert emitter.desync_count == 1
    events = _lines(sink)
    assert len(events) == 4


# ── Privacy negative ──────────────────────────────────────────────────────

def test_refuses_model_key_in_payload():
    with pytest.raises(InterventionTelemetryError, match="blocked privacy key"):
        _validate_payload({"reason": "ok", "model": "gpt-4"})


def test_refuses_provider_key_in_payload():
    with pytest.raises(InterventionTelemetryError, match="blocked privacy key"):
        _validate_payload({"reason": "ok", "provider": "openai"})


def test_refuses_stdout_in_payload():
    with pytest.raises(InterventionTelemetryError, match="blocked privacy key"):
        _validate_payload({"reason": "ok", "stdout": "some output"})


def test_refuses_unknown_key():
    with pytest.raises(InterventionTelemetryError, match="not in the allowed set"):
        _validate_payload({"reason": "ok", "unknown_field": "value"})


def test_refuses_secret_in_payload():
    with pytest.raises(InterventionTelemetryError, match="blocked privacy key"):
        _validate_payload({"reason": "ok", "api_key": "sk-123"})


def test_refuses_pid_in_payload():
    with pytest.raises(InterventionTelemetryError, match="blocked privacy key"):
        _validate_payload({"reason": "ok", "pid": 1234})


# ── Measured receipt digest ───────────────────────────────────────────────

def test_receipt_digest_deterministic():
    d1 = _receipt_digest(2, 1, 0)
    d2 = _receipt_digest(2, 1, 0)
    assert d1 == d2
    assert len(d1) == 64  # SHA-256 hex


def test_receipt_digest_changes_with_counts():
    d1 = _receipt_digest(1, 0, 0)
    d2 = _receipt_digest(2, 0, 0)
    assert d1 != d2


def test_emitter_snapshot_includes_digest():
    stream, _ = _stream()
    emitter = InterventionEmitter(stream)
    emitter.emit_restart(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="retry", attempt=1, max_attempts=3,
    )
    emitter.emit_malformed(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="bad payload",
    )
    snap = emitter.snapshot()
    assert snap["restart_count"] == 1
    assert snap["malformed_count"] == 1
    assert snap["desync_count"] == 0
    assert len(snap["receipt_digest"]) == 64
    assert snap["receipt_digest"] == emitter.receipt_digest


# ── Provider-free closeout consumption ────────────────────────────────────

def test_closeout_consumes_intervention_events():
    stream, sink = _stream()
    emitter = InterventionEmitter(stream)
    emitter.emit_restart(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="retry", attempt=1, max_attempts=3,
    )
    emitter.emit_malformed(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="bad payload",
    )
    emitter.emit_desync(
        wave="0", lane_id="L2", dispatch_id="d3",
        reason="state divergence",
    )

    events = _lines(sink)
    closeout = InterventionCloseout()
    closeout.consume(events)

    assert closeout.restart_count == 1
    assert closeout.malformed_count == 1
    assert closeout.desync_count == 1
    assert len(closeout.receipt_digest) == 64


def test_closeout_verify_matches_emitter():
    stream, sink = _stream()
    emitter = InterventionEmitter(stream)
    emitter.emit_restart(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="retry", attempt=1, max_attempts=3,
    )
    emitter.emit_desync(
        wave="0", lane_id="L2", dispatch_id="d3",
        reason="state divergence",
    )

    events = _lines(sink)
    closeout = InterventionCloseout()
    closeout.consume(events)

    assert closeout.verify(emitter.receipt_digest)


def test_closeout_verify_detects_mismatch():
    stream, sink = _stream()
    emitter = InterventionEmitter(stream)
    emitter.emit_restart(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="retry", attempt=1, max_attempts=3,
    )

    events = _lines(sink)
    closeout = InterventionCloseout()
    closeout.consume(events)

    # Tampered digest should not match
    wrong = _receipt_digest(99, 0, 0)
    assert not closeout.verify(wrong)


def test_closeout_empty_stream():
    closeout = InterventionCloseout()
    closeout.consume([])
    assert closeout.restart_count == 0
    assert closeout.malformed_count == 0
    assert closeout.desync_count == 0
    assert closeout.receipt_digest == _receipt_digest(0, 0, 0)


def test_closeout_ignores_non_intervention_events():
    stream, sink = _stream()
    stream.wave_started(wave="0")
    stream.lane_started(wave="0", lane_id="L1")
    # Also emit one intervention event
    emitter = InterventionEmitter(stream)
    emitter.emit_restart(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="retry", attempt=1, max_attempts=3,
    )

    events = _lines(sink)
    closeout = InterventionCloseout()
    closeout.consume(events)

    # Only the intervention event should be counted
    assert closeout.restart_count == 1
    assert closeout.malformed_count == 0
    assert closeout.desync_count == 0


def test_closeout_snapshot():
    stream, sink = _stream()
    emitter = InterventionEmitter(stream)
    emitter.emit_restart(
        wave="0", lane_id="L1", dispatch_id="d1",
        reason="retry", attempt=1, max_attempts=3,
    )

    events = _lines(sink)
    closeout = InterventionCloseout()
    closeout.consume(events)

    snap = closeout.snapshot()
    assert snap["restart_count"] == 1
    assert snap["malformed_count"] == 0
    assert snap["desync_count"] == 0
    assert len(snap["receipt_digest"]) == 64
