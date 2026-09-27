"""Intervention telemetry: restart, malformed, and desync events (SW-157-TELEMETRY-001).

This module owns the intervention-telemetry contract and its measured receipt.
It defines three distinct typed events, enforces a privacy-safe payload (no PII,
no raw output, no model-specific identifiers), and emits each event through the
shared :class:`~skillweave.dispatch.events.DispatchEventStream` with a measured
receipt digest so the closeout consumer can verify delivery without a provider.

Nothing here launches a worker, names a model, or depends on a provider. The
closeout/retro consumer is provider-free: it reads the stream's typed events and
counts restart/malformed/desync occurrences, deriving a receipt digest from the
counts alone.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, List, Optional

from skillweave.dispatch.contracts import EventType, ProcessStatus, TaskStatus
from skillweave.dispatch.events import DispatchEventStream

# ── Privacy-safe payload: no PII, no model names, no raw output ──────────────

#: Fields that must never appear in an intervention payload. Rejected at emit.
_PRIVACY_BLOCKED = (
    "model", "model_id", "model_name", "provider", "provider_id",
    "stdout", "stderr", "output", "log_lines", "trace",
    "pid", "process_id", "log_size", "log_file_size",
    "api_key", "token", "secret", "credential",
    "user_id", "user_name", "email",
)

#: The only allowed payload keys for intervention events. Anything else is refused.
_ALLOWED_PAYLOAD_KEYS = frozenset({
    "reason", "attempt", "max_attempts", "lane_id", "wave",
    "dispatch_id", "child_key", "elapsed_ms", "signal",
})


class InterventionTelemetryError(ValueError):
    """Raised when an intervention payload violates privacy or schema."""


def _refuse_privacy(key: str) -> None:
    raise InterventionTelemetryError(
        f"intervention payload carries a blocked privacy key '{key}'"
    )


def _validate_payload(payload: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Validate and return a privacy-safe, schema-constrained payload."""
    if not payload:
        return {}
    for key in payload:
        if key in _PRIVACY_BLOCKED:
            _refuse_privacy(key)
        if key not in _ALLOWED_PAYLOAD_KEYS:
            raise InterventionTelemetryError(
                f"intervention payload key '{key}' is not in the allowed set"
            )
    return dict(payload)


# ── Receipt digest: a measured, content-addressed proof of emission ──────────

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _receipt_digest(restart_count: int, malformed_count: int, desync_count: int) -> str:
    """Derive a deterministic receipt digest from the three intervention counters.

    The closeout consumer verifies delivery by recomputing this digest from the
    same counters — no provider and no external system is needed.
    """
    payload = json.dumps(
        {"restart": restart_count, "malformed": malformed_count, "desync": desync_count},
        sort_keys=True,
    )
    return _sha256_hex(payload.encode("utf-8"))


# ── Intervention emitter ─────────────────────────────────────────────────────

@dataclass
class InterventionEmitter:
    """Emit restart, malformed, and desync events through the shared event stream.

    Each event is privacy-validated before emission. Counters are tracked so the
    closeout consumer can verify the receipt digest without a provider.
    """

    stream: DispatchEventStream
    restart_count: int = 0
    malformed_count: int = 0
    desync_count: int = 0

    def _emit(
        self,
        event_type: EventType,
        *,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        safe = _validate_payload(payload)
        event = self.stream.emit(
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            event_type=event_type,
            process_status=ProcessStatus.LAUNCH_FAILED,
            task_status=TaskStatus.FAILED,
            payload=safe,
        )
        return event.to_dict()

    def emit_restart(
        self,
        *,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        reason: str,
        attempt: int,
        max_attempts: int,
        child_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """Emit an ``intervention_restart`` event.

        ``reason`` must be a non-PII string describing why the restart occurred.
        ``attempt``/``max_attempts`` track the retry position.
        """
        self.restart_count += 1
        payload: dict[str, Any] = {
            "reason": reason,
            "attempt": attempt,
            "max_attempts": max_attempts,
        }
        if child_key:
            payload["child_key"] = child_key
        return self._emit(
            EventType.INTERVENTION_RESTART,
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            payload=payload,
        )

    def emit_malformed(
        self,
        *,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        reason: str,
        elapsed_ms: Optional[int] = None,
    ) -> dict[str, Any]:
        """Emit an ``intervention_malformed`` event.

        ``reason`` describes what was malformed (contract, payload, state).
        ``elapsed_ms`` is the optional observation-to-detection latency.
        """
        self.malformed_count += 1
        payload: dict[str, Any] = {"reason": reason}
        if elapsed_ms is not None:
            payload["elapsed_ms"] = elapsed_ms
        return self._emit(
            EventType.INTERVENTION_MALFORMED,
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            payload=payload,
        )

    def emit_desync(
        self,
        *,
        wave: str,
        lane_id: str,
        dispatch_id: str,
        reason: str,
        signal: Optional[str] = None,
    ) -> dict[str, Any]:
        """Emit an ``intervention_desync`` event.

        ``reason`` describes the desync (e.g. state divergence, clock skew).
        ``signal`` is an optional signal name if a signal triggered detection.
        """
        self.desync_count += 1
        payload: dict[str, Any] = {"reason": reason}
        if signal:
            payload["signal"] = signal
        return self._emit(
            EventType.INTERVENTION_DESYNC,
            wave=wave,
            lane_id=lane_id,
            dispatch_id=dispatch_id,
            payload=payload,
        )

    @property
    def receipt_digest(self) -> str:
        """The measured receipt digest for this emitter's intervention counts."""
        return _receipt_digest(self.restart_count, self.malformed_count, self.desync_count)

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of intervention counters and receipt digest."""
        return {
            "restart_count": self.restart_count,
            "malformed_count": self.malformed_count,
            "desync_count": self.desync_count,
            "receipt_digest": self.receipt_digest,
        }


# ── Provider-free closeout/retro consumer ─────────────────────────────────────

@dataclass
class InterventionCloseout:
    """Provider-free closeout consumer for intervention telemetry.

    Reads intervention event counts from a stream's typed events and derives a
    receipt digest. No provider, no model, and no external system is consulted.
    """

    restart_count: int = 0
    malformed_count: int = 0
    desync_count: int = 0
    _digest: Optional[str] = None

    def consume(self, events: List[dict[str, Any]]) -> None:
        """Consume typed events and tally intervention counts."""
        for event in events:
            etype = event.get("event_type", "")
            if etype == EventType.INTERVENTION_RESTART.value:
                self.restart_count += 1
            elif etype == EventType.INTERVENTION_MALFORMED.value:
                self.malformed_count += 1
            elif etype == EventType.INTERVENTION_DESYNC.value:
                self.desync_count += 1
        self._digest = _receipt_digest(
            self.restart_count, self.malformed_count, self.desync_count
        )

    @property
    def receipt_digest(self) -> str:
        """The receipt digest computed from consumed intervention counts."""
        if self._digest is None:
            self._digest = _receipt_digest(
                self.restart_count, self.malformed_count, self.desync_count
            )
        return self._digest

    def verify(self, emitter_digest: str) -> bool:
        """Verify that the closeout digest matches the emitter's receipt."""
        return self.receipt_digest == emitter_digest

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of closeout counters and receipt digest."""
        return {
            "restart_count": self.restart_count,
            "malformed_count": self.malformed_count,
            "desync_count": self.desync_count,
            "receipt_digest": self.receipt_digest,
        }


__all__ = [
    "InterventionTelemetryError",
    "InterventionEmitter",
    "InterventionCloseout",
    "_receipt_digest",
    "_validate_payload",
]
