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


# ── Privacy negative: value-level (secrets and absolute paths) ────────────
#
# Key validation is not enough: an allowed key can smuggle secret material or a
# local filesystem path through its *value*. These tests pin the value-level
# contract that GATE-C_PRIVACY_VALUE_BYPASS found missing.

def test_masks_absolute_posix_path_in_reason():
    out = _validate_payload({"reason": "failed reading /Users/alice/.ssh/id_rsa"})
    assert "alice" not in out["reason"]
    assert "/Users/alice" not in out["reason"]
    assert "[REDACTED]" in out["reason"]


def test_masks_nested_absolute_path_in_reason():
    out = _validate_payload({"reason": "log at /var/log/skillweave/run-1.jsonl"})
    assert "/var/log/skillweave" not in out["reason"]
    assert "[REDACTED]" in out["reason"]


def test_masks_windows_absolute_path():
    out = _validate_payload({"reason": r"failed at C:\Users\bob\secrets.txt"})
    assert "bob" not in out["reason"]
    assert "[REDACTED]" in out["reason"]


def test_masks_bare_home_directory():
    out = _validate_payload({"reason": "cwd was /home/alice"})
    assert "alice" not in out["reason"]
    assert "[REDACTED]" in out["reason"]


def test_masks_bearer_token_in_signal():
    out = _validate_payload({"signal": "auth failed Bearer sk-abcdef1234567890"})
    assert "sk-abcdef1234567890" not in out["signal"]
    assert "[REDACTED_SECRET]" in out["signal"]


def test_masks_api_key_assignment_in_reason():
    out = _validate_payload({"reason": "retry with api_key=supersecretvalue"})
    assert "supersecretvalue" not in out["reason"]
    assert "[REDACTED_SECRET]" in out["reason"]


def test_masks_pem_private_key_block():
    out = _validate_payload(
        {"reason": "-----BEGIN RSA PRIVATE KEY----- leaked"}
    )
    assert "BEGIN RSA PRIVATE KEY" not in out["reason"]
    assert "[REDACTED_SECRET]" in out["reason"]


def test_refuses_secret_smuggled_past_redaction():
    # Key-level checks must not be the only defence: a blocked denomination can
    # ride inside an *allowed* key's value. Masking hides the bytes, but the
    # round-trip still has to be lossy in the caller's favour — the raw secret
    # must not survive into the emitted payload.
    raw = "sk-livesecret-abc123"
    out = _validate_payload({"reason": f"auth failed api_key={raw}"})
    assert raw not in json.dumps(out)
    assert "sk-livesecret" not in json.dumps(out)
    assert "[REDACTED_SECRET]" in out["reason"]


def test_refuses_unmaskable_secret_denomination():
    # A value that still carries an unmasked credential after redaction is a
    # hard stop: the refusal path exists so a future shape that masking misses
    # cannot silently reach the stream.
    from skillweave.telemetry_intervention import _assert_no_secret

    with pytest.raises(InterventionTelemetryError, match="secret material"):
        _assert_no_secret("reason", "api_key=AKIAIOSFODNN7EXAMPLE")


def test_masks_absolute_path_in_dispatch_id():
    # The gate named dispatch_id explicitly: it may not smuggle a local path.
    out = _validate_payload({"dispatch_id": "/Users/alice/.ssh/id_rsa"})
    assert "/Users/alice" not in out["dispatch_id"]
    assert "id_rsa" not in out["dispatch_id"]
    assert out["dispatch_id"] == "[REDACTED]"


def test_masks_absolute_path_in_signal():
    out = _validate_payload({"signal": "/home/alice/secrets/run-1"})
    assert "alice" not in out["signal"]
    assert "[REDACTED]" in out["signal"]


def test_masks_home_tilde_path():
    out = _validate_payload({"reason": "read ~/.ssh/id_rsa failed"})
    assert "~/.ssh" not in out["reason"]
    assert "id_rsa" not in out["reason"]
    assert "[REDACTED]" in out["reason"]


def test_identifier_fields_mask_secret_and_path():
    # No identifier exemption: a secret in child_key is masked, and a path-shaped
    # identifier is masked too. Clean identifiers still pass through (see below).
    out = _validate_payload(
        {"child_key": "/Users/alice/repo/run-1/token=abcdef123456"}
    )
    assert "/Users/alice" not in out["child_key"]
    assert "abcdef123456" not in out["child_key"]


def test_clean_identifier_preserved():
    out = _validate_payload(
        {"wave": "wave-0", "lane_id": "L1", "dispatch_id": "d1", "signal": "SIGTERM"}
    )
    assert out == {
        "wave": "wave-0", "lane_id": "L1", "dispatch_id": "d1", "signal": "SIGTERM",
    }


def test_clean_value_is_untouched():
    out = _validate_payload({"reason": "process terminated unexpectedly"})
    assert out["reason"] == "process terminated unexpectedly"


def test_masked_value_reaches_emitted_stream():
    stream, sink = _stream()
    emitter = InterventionEmitter(stream)
    emitter.emit_malformed(
        wave="0", lane_id="L1", dispatch_id="d2",
        reason="crash in /Users/alice/project/secret.log",
    )
    ev = _lines(sink)[0]
    assert "/Users/alice" not in ev["reason"]
    assert "alice" not in ev["reason"]
    assert "[REDACTED]" in ev["reason"]


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
