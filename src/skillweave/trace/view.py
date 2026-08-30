"""Read-only operator view and negative authority (SW1311-OBSERVER-001, criterion 6, 9).

The operator view renders a :class:`~skillweave.trace.projection.Projection` and
a :class:`~skillweave.trace.observer.TraceObservation` into an immutable,
replayable surface. It is strictly read-only: it never mutates product files,
profiles, catalog, dispatch state, review findings, integration state or gates,
and its *negative authority* layer refuses any such mutation before execution
(criterion 9).

The observer is also forbidden the *active* runtime actions (criterion 6):
``cancel``, ``kill``, ``dispatch``, ``correction``, ``disposition``,
``integration`` and ``gate``. The view emits only *read-only intervention
requests* — typed, informational outputs that a human or an authorized role may
act on — and never performs those actions itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from skillweave.trace.projection import Projection
from skillweave.trace.observer import TraceObservation


class ViewError(Exception):
    """A view/authority contract violation (raised fail-closed)."""


class ObserverAuthorityError(ViewError):
    """The observer attempted a forbidden mutation or runtime action."""


class InterventionKind(str, Enum):
    """The read-only intervention kinds the observer may request."""

    LIVENESS = "liveness"
    NON_PROGRESS = "non_progress"


@dataclass(frozen=True)
class InterventionRequest:
    """A read-only intervention request (criterion 6).

    ``kind`` names the configured threshold that triggered it (liveness or
    non-progress); ``reason`` states the measured cause; ``action`` names a
    *request*, never a performed action. The observer emits this, it never
    performs cancel/kill/dispatch/correction/disposition/integration/gate.
    """

    kind: InterventionKind
    reason: str
    threshold: float
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "reason": self.reason,
            "threshold": self.threshold,
            "action": self.action,
        }


#: Actions the observer and its view may never perform (criterion 6).
FORBIDDEN_RUNTIME_ACTIONS: frozenset[str] = frozenset({
    "cancel", "kill", "dispatch", "correct", "correction",
    "disposition", "integrate", "integration", "gate",
})

#: Mutations the observer and its view may never perform (criterion 9).
FORBIDDEN_MUTATIONS: frozenset[str] = frozenset({
    "mutate", "write", "commit", "push", "merge", "release", "tag",
})


def assert_observer_authority(action: str) -> None:
    """Fail closed before any forbidden observer action (criteria 6, 9)."""
    if action in FORBIDDEN_RUNTIME_ACTIONS:
        raise ObserverAuthorityError(
            f"observer is read-only and may not {action}; an intervention "
            "request must be emitted instead"
        )
    if action in FORBIDDEN_MUTATIONS:
        raise ObserverAuthorityError(
            f"observer may not {action} product, profile, catalog, dispatch, "
            "review, integration or gate state"
        )


@dataclass(frozen=True)
class OperatorView:
    """The immutable read-only operator view (criterion 9, 10).

    Bundles the projection and the semantic observation into one surface. It is
    fully immutable: the observer can read it, render it, or hand it off, but
    never mutate the state it describes. The ``run_id``/``coverage_boundary``
    state the run scoping — no persistent lease/offset is claimed.
    """

    run_id: str
    projection: Projection
    observation: TraceObservation
    interventions: tuple[InterventionRequest, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "projection": self.projection.to_dict(),
            "observation": self.observation.to_dict(),
            "interventions": [i.to_dict() for i in self.interventions],
        }

    def render(self) -> str:
        """Render a deterministic, human-readable operator view (criterion 4)."""
        p = self.projection
        lines = [
            f"# Operator view: {self.run_id}",
            f"wave: {p.run.wave or '(none)'}",
            f"coverage_boundary: {p.run.coverage_boundary}",
            f"waves: {', '.join(p.waves) or '(none)'}",
            f"lanes: {', '.join(l.lane_id for l in p.lanes) or '(none)'}",
            f"groups: {', '.join(str(list(g)) for g in p.groups) or '(none)'}",
            f"jobs: {', '.join(j.job_id for j in p.jobs) or '(none)'}",
            f"evidence: {', '.join(p.evidence) or '(none)'}",
            f"rounds_remaining: {p.rounds_remaining}",
            f"integration_eligible: {p.integration_eligible}",
            f"gate_state: {p.gate_state or '(unset)'}",
        ]
        return "\n".join(lines)


__all__ = [
    "ViewError",
    "ObserverAuthorityError",
    "InterventionKind",
    "InterventionRequest",
    "FORBIDDEN_RUNTIME_ACTIONS",
    "FORBIDDEN_MUTATIONS",
    "assert_observer_authority",
    "OperatorView",
]
