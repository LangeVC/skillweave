"""Deterministic live/replay projection (SW1311-OBSERVER-001, criterion 4, 7, 8).

This module turns ordered typed records — dispatch events, trace job records,
review dispositions and handoff/checkpoint records — into a single,
deterministic :class:`Projection` an operator consumes. The projection is a
*pure function* of the ordered input: replaying the same order from sequence
zero produces the same final projection (criterion 7), and a consumer that
disconnects and reconnects, or replays from zero, sees the identical state
(criterion 8).

It exposes exactly the required operator surface (criterion 4): run, wave, lane,
criterion group, job state, heartbeat age, evidence, review disposition, rounds
remaining, integration eligibility and gate state. Nothing here launches a
worker, mutates a product file, or carries transition authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from skillweave.trace.handoff import ControllerCheckpoint, Handoff
from skillweave.trace.review import ReviewVerdict


@dataclass(frozen=True)
class RunCell:
    """The run-scoped view of one run (criterion 4, 10).

    ``coverage_boundary`` is the run-scoped boundary: the projection is scoped
    to a single run id and never claims a persistent lease, offset or
    autonomous resume across process recreation (criterion 10).
    """

    run_id: str
    wave: str = ""
    coverage_boundary: str = ""


@dataclass(frozen=True)
class LaneCell:
    """One lane's view: name, disposition and rounds remaining."""

    lane_id: str
    role: str = ""
    disposition: Optional[str] = None
    rounds_remaining: Optional[int] = None


@dataclass(frozen=True)
class JobCell:
    """One job's view: state, heartbeat age, evidence and criterion group."""

    job_id: str
    state: str = ""
    heartbeat_age_s: Optional[float] = None
    evidence: tuple[str, ...] = ()
    criterion_group: tuple[int, ...] = ()


@dataclass(frozen=True)
class Projection:
    """The full deterministic operator projection of one run (criterion 4).

    ``run`` / ``waves`` / ``lanes`` / ``jobs`` carry the operator surface;
    ``groups`` records criterion-group coverage; ``heartbeats`` the last
    heartbeat per job with its age; ``evidence`` the known receipt references;
    ``dispositions`` the review disposition per lane; ``rounds_remaining`` the
    correction budget; ``integration_eligible`` and ``gate_state`` the final
    operator facts.
    """

    run: RunCell
    waves: tuple[str, ...] = ()
    lanes: tuple[LaneCell, ...] = ()
    jobs: tuple[JobCell, ...] = ()
    groups: tuple[tuple[int, ...], ...] = ()
    evidence: tuple[str, ...] = ()
    dispositions: Mapping[str, str] = field(default_factory=dict)
    rounds_remaining: Optional[int] = None
    integration_eligible: bool = False
    gate_state: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run": {
                "run_id": self.run.run_id,
                "wave": self.run.wave,
                "coverage_boundary": self.run.coverage_boundary,
            },
            "waves": list(self.waves),
            "lanes": [
                {
                    "lane_id": l.lane_id,
                    "role": l.role,
                    "disposition": l.disposition,
                    "rounds_remaining": l.rounds_remaining,
                }
                for l in self.lanes
            ],
            "jobs": [
                {
                    "job_id": j.job_id,
                    "state": j.state,
                    "heartbeat_age_s": j.heartbeat_age_s,
                    "evidence": list(j.evidence),
                    "criterion_group": list(j.criterion_group or ()),
                }
                for j in self.jobs
            ],
            "groups": [list(g) for g in self.groups],
            "evidence": list(self.evidence),
            "dispositions": dict(self.dispositions),
            "rounds_remaining": self.rounds_remaining,
            "integration_eligible": self.integration_eligible,
            "gate_state": self.gate_state,
        }


@dataclass(frozen=True)
class ProjectionEvent:
    """One ordered projection input: a typed event or a typed record.

    ``sequence`` orders the stream; reordering by sequence must leave the final
    projection identical (it is folded in order). ``payload`` holds the typed
    fields the projector consumes.
    """

    sequence: int
    payload: Mapping[str, Any]


class Projector:
    """Fold an ordered stream of typed events into a deterministic projection.

    The projector is a pure state reducer: it holds no clock, no file handle
    and no process handle. Feed it ordered :class:`ProjectionEvent` items and
    read :meth:`projection`. Replaying the same ordered items from zero yields
    an equal projection (criterion 7, 8).
    """

    def __init__(self, run_id: str) -> None:
        self._run = RunCell(run_id=run_id, coverage_boundary=f"run:{run_id}")
        self._waves: list[str] = []
        self._lanes: dict[str, LaneCell] = {}
        self._jobs: dict[str, JobCell] = {}
        self._groups: list[tuple[int, ...]] = []
        self._evidence: list[str] = []
        self._dispositions: dict[str, str] = {}
        self._rounds_remaining: Optional[int] = None
        self._integration_eligible: bool = False
        self._gate_state: Optional[str] = None
        self._heartbeat_times: dict[str, str] = {}
        self._sequence = 0

    def project(self, event: ProjectionEvent) -> None:
        """Fold one ordered event into the projection."""
        self._sequence = event.sequence
        payload = event.payload
        event_type = payload.get("event_type", "")

        wave = payload.get("wave")
        if wave and wave not in self._waves:
            self._waves.append(wave)

        lane_id = payload.get("lane_id")
        if lane_id:
            self._lanes.setdefault(
                lane_id,
                LaneCell(lane_id=lane_id, role=payload.get("role", "")),
            )

        group = payload.get("criterion_group")
        if group:
            g = tuple(int(i) for i in group)
            if g not in self._groups:
                self._groups.append(g)

        refs = payload.get("receipt_refs") or payload.get("evidence") or []
        for ref in refs:
            if ref and ref not in self._evidence:
                self._evidence.append(ref)

        dispatch_id = payload.get("dispatch_id") or payload.get("job_id")
        state = payload.get("job_state") or payload.get("process_status") or event_type

        if event_type == "heartbeat":
            if dispatch_id:
                # The heartbeat timestamp is a typed fact of the event. If the
                # event does not carry one, there is no deterministic fact to
                # derive an age from, so nothing is recorded (no wall clock).
                self._heartbeat_times[dispatch_id] = payload.get("timestamp")

        disposition = payload.get("disposition")
        if disposition and lane_id:
            self._dispositions[lane_id] = disposition

        if "rounds_remaining" in payload:
            self._rounds_remaining = payload["rounds_remaining"]

        if payload.get("integration_eligible") is not None:
            self._integration_eligible = bool(payload["integration_eligible"])

        if payload.get("gate_state"):
            self._gate_state = payload["gate_state"]

        job_id = payload.get("job_id") or dispatch_id
        if job_id:
            self._jobs[job_id] = JobCell(
                job_id=job_id,
                state=state,
                heartbeat_age_s=self._heartbeat_age(job_id, payload),
                evidence=tuple(self._evidence),
                criterion_group=group,
            )

    def _heartbeat_age(self, job_id: str, payload: Mapping[str, Any]) -> Optional[float]:
        """Derive a heartbeat's age purely from typed facts (deterministic).

        Age is ``reference - heartbeat_timestamp``, where ``reference`` is the
        deterministic projection reference: the most recent typed event's
        ``timestamp`` as it is folded. Both terms are typed facts carried by
        the serialized stream, so replaying identical bytes at any wall-clock
        time yields an identical projection (replays are deterministic). The
        reference advances as newer typed events arrive, preserving live
        freshness without any wall-clock read during fold/replay.
        """
        ts = self._heartbeat_times.get(job_id)
        reference = payload.get("timestamp")
        if ts is None or reference is None:
            return None
        try:
            heartbeat_t = datetime.fromisoformat(ts)
            reference_t = datetime.fromisoformat(reference)
        except ValueError:
            return None
        elapsed = (reference_t - heartbeat_t).total_seconds()
        return round(elapsed, 3)

    def apply_handoff(self, handoff: Handoff) -> None:
        """Fold a typed handoff's disposition / rounds into the projection."""
        lane_id = handoff.destination_role
        cell = self._lanes.setdefault(lane_id, LaneCell(lane_id=lane_id))
        self._lanes[lane_id] = LaneCell(
            lane_id=cell.lane_id,
            role=handoff.destination_role,
            disposition=cell.disposition,
            rounds_remaining=handoff.correction_budget,
        )
        self._rounds_remaining = handoff.correction_budget

    def apply_checkpoint(self, checkpoint: ControllerCheckpoint) -> None:
        """Fold a controller checkpoint's budget / verdict into the projection."""
        budgets = checkpoint.correction_budgets
        if budgets:
            self._rounds_remaining = min(budgets.values())
        if checkpoint.latest_verdict is not None:
            self._gate_state = checkpoint.latest_verdict.value
            self._integration_eligible = (
                checkpoint.latest_verdict is ReviewVerdict.REVIEW_PASS
            )

    def projection(self) -> Projection:
        """The current deterministic projection (a snapshot)."""
        return Projection(
            run=self._run,
            waves=tuple(self._waves),
            lanes=tuple(self._lanes.values()),
            jobs=tuple(self._jobs.values()),
            groups=tuple(self._groups),
            evidence=tuple(self._evidence),
            dispositions=dict(self._dispositions),
            rounds_remaining=self._rounds_remaining,
            integration_eligible=self._integration_eligible,
            gate_state=self._gate_state,
        )


def builds_identical_projection(a: Projection, b: Projection) -> bool:
    """True when two projections are equal (criterion 7, 8)."""
    return a.to_dict() == b.to_dict()


__all__ = [
    "RunCell",
    "LaneCell",
    "JobCell",
    "Projection",
    "ProjectionEvent",
    "Projector",
    "builds_identical_projection",
]
