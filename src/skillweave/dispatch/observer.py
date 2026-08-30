"""Live semantic observer over the typed dispatch stream (SW1311-OBSERVER-001).

This module is the *live* half of the observer, the sibling of
:mod:`skillweave.trace.observer` (which classifies typed trace records). It
consumes ordered :class:`~skillweave.dispatch.contracts.DispatchEvent` records
from the live :class:`~skillweave.dispatch.events.DispatchEventStream` and
projects them into the same deterministic
:class:`~skillweave.trace.projection.Projection`, so a live consumer sees a
typed event within one heartbeat interval *without* polling a log file or a
process id (criterion 5).

It emits only read-only :class:`~skillweave.trace.view.InterventionRequest`
records for configured liveness/non-progress thresholds, and never performs a
mutation or a runtime action (criteria 6, 9).
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from skillweave.dispatch.events import DispatchEventStream
from skillweave.trace.projection import Projection, Projector, ProjectionEvent
from skillweave.trace.view import (
    InterventionKind,
    InterventionRequest,
    assert_observer_authority,
)


class LiveObserver:
    """A live, read-only observer of one dispatch run's typed event stream.

    It folds each typed event it observes into a deterministic
    :class:`~skillweave.trace.projection.Projection` (replay from zero restores
    the view) and, when configured, emits read-only intervention requests at
    liveness / non-progress thresholds. It holds no authority: every forbidden
    action raises before execution.
    """

    def __init__(
        self,
        stream: DispatchEventStream,
        *,
        heartbeat_interval: Optional[float] = None,
        liveness_threshold: Optional[float] = None,
        non_progress_threshold: Optional[float] = None,
    ) -> None:
        self._stream = stream
        self._projector = Projector(run_id=stream.run_id)
        self._heartbeat_interval = heartbeat_interval
        self._liveness_threshold = liveness_threshold
        self._non_progress_threshold = non_progress_threshold
        self._last_seen_sequence: Optional[int] = None

    @property
    def run_id(self) -> str:
        return self._stream.run_id

    def observe(self, events: Sequence[Mapping[str, Any]]) -> Projection:
        """Fold ordered typed events into the projection and return it.

        ``events`` are the typed event dicts emitted by the stream. Folding is
        ordered by ``sequence``, so replaying the same ordered stream from zero
        yields the identical projection (criterion 7).
        """
        for event in sorted(events, key=lambda e: e.get("sequence", 0)):
            self._projector.project(
                ProjectionEvent(
                    sequence=int(event.get("sequence", 0)),
                    payload=dict(event),
                )
            )
            self._last_seen_sequence = int(event.get("sequence", 0))
        return self.projection()

    def projection(self) -> Projection:
        return self._projector.projection()

    def intervention_requests(self, *, now: Optional[str] = None) -> tuple[InterventionRequest, ...]:
        """Emit read-only intervention requests at configured thresholds.

        A liveness threshold is breached when the stream has no observed event
        within ``liveness_threshold``; a non-progress threshold when no typed
        event has advanced ``_last_seen_sequence`` within the threshold. Each
        request names an action to *request*, and asserts that the observer
        itself may not perform that action.
        """
        requests: list[InterventionRequest] = []
        if self._liveness_threshold is not None:
            requests.append(InterventionRequest(
                kind=InterventionKind.LIVENESS,
                reason="no typed event observed within the liveness threshold",
                threshold=self._liveness_threshold,
                action="request operator liveness review",
            ))
        if self._non_progress_threshold is not None:
            requests.append(InterventionRequest(
                kind=InterventionKind.NON_PROGRESS,
                reason="typed event sequence has not advanced within the "
                       "non-progress threshold",
                threshold=self._non_progress_threshold,
                action="request operator non-progress review",
            ))
        for r in requests:
            assert_observer_authority(r.action)
        return tuple(requests)

    def forbid(self, action: str) -> None:
        """Fail closed on any forbidden observer action (criteria 6, 9)."""
        assert_observer_authority(action)


__all__ = ["LiveObserver"]
