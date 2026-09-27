"""Automated S3-Gate remediation slicing (SW-158-RETRO-004).

The S3-Gate emits ``REVIEW_BLOCKER`` lines when a stage gate fails. This module
turns that gate output into *spawn-ready* remediation micro-lanes with the
controller in the loop and no human in it for a standard blocker:

1. **Parse** every ``REVIEW_BLOCKER`` line in the gate output into a typed,
   fail-closed :class:`S3GateBlocker` (full 40-hex SHAs enforced by a local
   ``_is_full_sha`` helper, GLE-020 — no optional ``skillweave.runtime`` import).
2. **Slice** the blockers into disjoint micro-lanes with the existing pure
   planner :func:`skillweave.dispatch.remediation.plan_remediation`, so
   multi-domain failures never serialize together.
3. **Start** the lanes through an injected, provider-neutral spawn seam. The
   default seam is inert — it records intents and launches nothing — so the
   controller's decision is testable and this module names no harness, model or
   provider.

A *standard* blocker is one whose severity is ``blocker`` or ``major`` (the
severities a gate auto-remediates) with a correction round still available in
the bounded budget. For those :func:`requires_human_intervention` returns
``False`` and the controller spawns the lane itself. The controller escalates to
a human only for a non-standard severity or an exhausted correction budget — and
then it spawns nothing, because an unauthorized mutation must never start
itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from skillweave.dispatch.remediation import (
    RemediationDomain,
    RemediationMicroLane,
    RemediationPlan,
    plan_remediation,
)
from skillweave.trace.contracts import content_id
from skillweave.trace.handoff import CONTROLLER_ROLE
from skillweave.trace.review import Severity

#: The gate-failure token the S3-Gate emits when a stage gate fails.
REVIEW_BLOCKER = "REVIEW_BLOCKER"

#: The gate-release token the S3-Gate emits on success. Freigabe lines carry
#: no failure and are ignored by the parser.
REVIEW_FREIGABE = "REVIEW_FREIGABE"

#: The severities a gate may remediate without a human in the loop.
STANDARD_SEVERITIES: frozenset[Severity] = frozenset({Severity.BLOCKER, Severity.MAJOR})

#: Default bounded correction rounds before an exhausted budget escalates.
DEFAULT_MAX_ROUNDS = 3

#: Canonical field aliases accepted by the ``key=value`` line form.
_FIELD_ALIASES: dict[str, str] = {
    "lane": "lane",
    "lane_id": "lane",
    "repo": "repo",
    "base": "base",
    "base_sha": "base",
    "subject": "subject",
    "subject_sha": "subject",
    "gate": "gate",
    "severity": "severity",
    "criteria": "criteria",
    "crit": "criteria",
}

_REQUIRED_FIELDS: tuple[str, ...] = ("gate", "lane", "repo", "base", "subject")


class S3GateRemediationError(Exception):
    """A ``REVIEW_BLOCKER`` line was malformed or could not be sliced."""


def _is_full_sha(value: Any) -> bool:
    """True for a 40-hex-char full SHA (local copy, GLE-020)."""
    if not isinstance(value, str) or len(value) != 40:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


# ── Parsed blocker ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class S3GateBlocker:
    """One parsed ``REVIEW_BLOCKER`` fact from the S3-Gate.

    Carries exactly what the controller needs to slice and re-dispatch a
    correction: the gate that failed, the lane identity, the domain
    (``repo`` + ``base_sha``) that isolates its workspace, the frozen
    ``subject_sha`` under review and the criteria the gate reported failed.
    """

    gate: str
    lane_id: str
    repo: str
    base_sha: str
    subject_sha: str
    failed_criteria: tuple[str, ...] = ()
    severity: Severity = Severity.BLOCKER

    def validate(self) -> None:
        """Raise :class:`S3GateRemediationError` on any incomplete field."""
        if not self.gate:
            raise S3GateRemediationError("blocker must name the gate that failed")
        if not self.lane_id:
            raise S3GateRemediationError("blocker must name its lane")
        if not self.repo:
            raise S3GateRemediationError(
                f"blocker for lane {self.lane_id!r} must name its repo"
            )
        if not _is_full_sha(self.base_sha):
            raise S3GateRemediationError(
                f"blocker for lane {self.lane_id!r} base SHA {self.base_sha!r} "
                f"is not a full SHA"
            )
        if not _is_full_sha(self.subject_sha):
            raise S3GateRemediationError(
                f"blocker for lane {self.lane_id!r} subject SHA "
                f"{self.subject_sha!r} is not a full SHA"
            )
        if not isinstance(self.severity, Severity):
            raise S3GateRemediationError(
                f"blocker for lane {self.lane_id!r} has unknown severity "
                f"{self.severity!r}"
            )

    @property
    def domain(self) -> RemediationDomain:
        """The workspace-isolation domain this blocker belongs to."""
        return RemediationDomain(repo=self.repo, base=self.base_sha)

    @property
    def is_standard(self) -> bool:
        """True when this blocker resolves to the standard severities."""
        return self.severity in STANDARD_SEVERITIES

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "lane_id": self.lane_id,
            "repo": self.repo,
            "base_sha": self.base_sha,
            "subject_sha": self.subject_sha,
            "failed_criteria": list(self.failed_criteria),
            "severity": self.severity.value,
        }


# ── Parsing ──────────────────────────────────────────────────────────────────


def _split_criteria(tokens: Sequence[str]) -> tuple[str, ...]:
    criteria: list[str] = []
    for token in tokens:
        for part in token.split(","):
            part = part.strip()
            if part:
                criteria.append(part)
    return tuple(criteria)


def _parse_positional(fields: Sequence[str]) -> dict[str, Any]:
    if len(fields) < len(_REQUIRED_FIELDS):
        raise S3GateRemediationError(
            f"REVIEW_BLOCKER line needs at least {len(_REQUIRED_FIELDS)} fields "
            f"(gate, lane, repo, base, subject); got {len(fields)}: {list(fields)!r}"
        )
    gate, lane, repo, base, subject = fields[: len(_REQUIRED_FIELDS)]
    return {
        "gate": gate,
        "lane": lane,
        "repo": repo,
        "base": base,
        "subject": subject,
        "criteria": _split_criteria(fields[len(_REQUIRED_FIELDS):]),
    }


def _parse_key_value(fields: Sequence[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for token in fields:
        key, sep, value = token.partition("=")
        if not sep or not value:
            raise S3GateRemediationError(
                f"REVIEW_BLOCKER key/value field {token!r} is not of the form key=value"
            )
        canonical = _FIELD_ALIASES.get(key.strip().lower())
        if canonical is None:
            raise S3GateRemediationError(
                f"REVIEW_BLOCKER field {key!r} is not a known field; expected one "
                f"of {sorted(set(_FIELD_ALIASES.values()))}"
            )
        if canonical in parsed:
            raise S3GateRemediationError(
                f"REVIEW_BLOCKER field {canonical!r} was supplied more than once"
            )
        parsed[canonical] = value
    if "criteria" in parsed:
        parsed["criteria"] = _split_criteria([parsed["criteria"]])
    return parsed


def parse_review_blocker_line(line: str) -> Optional[S3GateBlocker]:
    """Parse one log line into an :class:`S3GateBlocker`, or ``None``.

    Returns ``None`` for a line that does not carry the ``REVIEW_BLOCKER``
    token (blank lines, ``REVIEW_FREIGABE`` passes, unrelated log output). A
    line that *does* carry the token but is malformed — too few fields, an
    unknown key, a non-full SHA — raises :class:`S3GateRemediationError`
    fail-closed rather than being silently dropped.
    """
    if not isinstance(line, str):
        raise S3GateRemediationError(f"gate log line must be a string, got {line!r}")
    tokens = line.strip().lstrip("-*•").split()
    if REVIEW_BLOCKER not in tokens:
        return None
    rest = tokens[tokens.index(REVIEW_BLOCKER) + 1:]
    if not rest:
        raise S3GateRemediationError(
            f"REVIEW_BLOCKER line carries no fields: {line!r}"
        )

    fields = _parse_key_value(rest) if any("=" in t for t in rest) else _parse_positional(rest)
    missing = [name for name in _REQUIRED_FIELDS if not fields.get(name)]
    if missing:
        raise S3GateRemediationError(
            f"REVIEW_BLOCKER line is missing required field(s) {missing}: {line!r}"
        )

    severity_raw = (fields.get("severity") or Severity.BLOCKER.value).strip().lower()
    try:
        severity = Severity(severity_raw)
    except ValueError as exc:
        raise S3GateRemediationError(
            f"REVIEW_BLOCKER line declares unknown severity {severity_raw!r}"
        ) from exc

    blocker = S3GateBlocker(
        gate=fields["gate"],
        lane_id=fields["lane"],
        repo=fields["repo"],
        base_sha=fields["base"],
        subject_sha=fields["subject"],
        failed_criteria=tuple(fields.get("criteria") or ()),
        severity=severity,
    )
    blocker.validate()
    return blocker


def parse_review_blocker_output(gate_output: str) -> list[S3GateBlocker]:
    """Parse every ``REVIEW_BLOCKER`` fact from an S3-Gate log blob.

    ``gate_output`` may be a whole log; only lines carrying the blocker token
    are consumed. Fails closed on the first malformed blocker line.
    """
    if not isinstance(gate_output, str):
        raise S3GateRemediationError(
            f"S3-Gate output must be a string, got {gate_output!r}"
        )
    blockers: list[S3GateBlocker] = []
    for line in gate_output.splitlines():
        blocker = parse_review_blocker_line(line)
        if blocker is not None:
            blockers.append(blocker)
    return blockers


# ── Plan ─────────────────────────────────────────────────────────────────────


@dataclass
class S3RemediationPlan:
    """A remediation plan sliced automatically from S3-Gate blockers.

    ``remediation`` is the disjoint :class:`RemediationPlan` the pure planner
    produced; ``blockers`` are the gate facts it was sliced from. The plan
    decides whether a human is required — it never launches anything.
    """

    blockers: tuple[S3GateBlocker, ...] = ()
    remediation: RemediationPlan = field(default_factory=RemediationPlan)
    failure_round: int = 0
    max_rounds: int = DEFAULT_MAX_ROUNDS

    def __post_init__(self) -> None:
        if not isinstance(self.failure_round, int) or self.failure_round < 0:
            raise S3GateRemediationError(
                f"failure round must be a non-negative integer, got "
                f"{self.failure_round!r}"
            )
        if not isinstance(self.max_rounds, int) or self.max_rounds < 1:
            raise S3GateRemediationError(
                f"max rounds must be a positive integer, got {self.max_rounds!r}"
            )

    @property
    def total_lanes(self) -> int:
        return self.remediation.total_lanes

    @property
    def single_domain(self) -> bool:
        return self.remediation.single_domain

    @property
    def multi_domain(self) -> bool:
        return self.remediation.multi_domain

    @property
    def budget_exhausted(self) -> bool:
        """True when no bounded correction round remains for these blockers."""
        return bool(self.blockers) and self.failure_round >= self.max_rounds

    def human_intervention_reasons(self) -> tuple[str, ...]:
        """The reasons, if any, this plan may not auto-spawn its lanes.

        A standard blocker with budget remaining yields no reasons — the
        controller spawns it. A non-standard severity or an exhausted budget
        yields a reason and the plan spawns nothing.
        """
        reasons: list[str] = []
        for blocker in self.blockers:
            if not blocker.is_standard:
                reasons.append(
                    f"lane {blocker.lane_id!r} has non-standard blocker severity "
                    f"{blocker.severity.value!r}"
                )
        if self.budget_exhausted:
            reasons.append(
                f"correction budget exhausted at round {self.failure_round} of "
                f"{self.max_rounds}"
            )
        return tuple(reasons)

    @property
    def requires_human_intervention(self) -> bool:
        return bool(self.human_intervention_reasons())

    def to_dict(self) -> dict[str, Any]:
        return {
            "blockers": [b.to_dict() for b in self.blockers],
            "remediation": self.remediation.to_dict(),
            "failure_round": self.failure_round,
            "max_rounds": self.max_rounds,
            "requires_human_intervention": self.requires_human_intervention,
            "human_intervention_reasons": list(self.human_intervention_reasons()),
        }


def plan_remediation_from_s3_gate(
    gate_output: str,
    *,
    failure_round: int = 0,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> S3RemediationPlan:
    """Slice S3-Gate output into disjoint remediation micro-lanes.

    Parses the ``REVIEW_BLOCKER`` facts, then delegates the slicing to the pure
    :func:`~skillweave.dispatch.remediation.plan_remediation` planner so each
    domain gets isolated lanes. Launches nothing.
    """
    blockers = parse_review_blocker_output(gate_output)
    failed_entries = [
        {"lane_id": b.lane_id, "repo": b.repo, "base": b.base_sha} for b in blockers
    ]
    remediation = plan_remediation(failed_entries, failure_round=failure_round)
    return S3RemediationPlan(
        blockers=tuple(blockers),
        remediation=remediation,
        failure_round=failure_round,
        max_rounds=max_rounds,
    )


# ── Spawn seam ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RemediationLaneSpawn:
    """One micro-lane the controller is about to start.

    Every field is a frozen fact: the identity and domain of the lane, the
    subject under correction, its failed criteria, the round it consumes and
    the role that authorized the spawn. ``requires_human_intervention`` records
    whether the controller may start it at all — a lane with a non-standard
    blocker or an exhausted budget is recorded but never started.
    """

    spawn_id: str
    lane_id: str
    domain: RemediationDomain
    base_sha: str
    subject_sha: str
    failed_criteria: tuple[str, ...]
    failure_round: int
    spawned_by: str
    requires_human_intervention: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "spawn_id": self.spawn_id,
            "lane_id": self.lane_id,
            "domain": {"repo": self.domain.repo, "base": self.domain.base},
            "base_sha": self.base_sha,
            "subject_sha": self.subject_sha,
            "failed_criteria": list(self.failed_criteria),
            "failure_round": self.failure_round,
            "spawned_by": self.spawned_by,
            "requires_human_intervention": self.requires_human_intervention,
        }


#: The provider-neutral seam a controller starts a remediation lane through.
#: It receives the frozen spawn and returns anything (a handle, a receipt); the
#: controller never inspects it. A seam that raises aborts the spawn fail-closed.
SpawnSeam = Callable[[RemediationLaneSpawn], Any]


def _spawn_id(lane_id: str, base_sha: str, subject_sha: str, failure_round: int) -> str:
    return content_id("s3_remediation_spawn", lane_id, base_sha, subject_sha, failure_round)


def _blocker_index(plan: S3RemediationPlan) -> dict[tuple[str, str], S3GateBlocker]:
    """Map each ``(lane, domain)`` to its blocker, failing closed on collision.

    The planner models a micro-lane by ``(lane_id, domain)`` alone, so two
    blockers that share both but differ in subject or criteria cannot be told
    apart when a spawn is built. Rather than let last-wins silently start a
    lane carrying the wrong frozen subject, refuse the ambiguous plan.
    """
    index: dict[tuple[str, str], S3GateBlocker] = {}
    for blocker in plan.blockers:
        key = (blocker.lane_id, blocker.domain.key)
        existing = index.get(key)
        if existing is not None:
            raise S3GateRemediationError(
                f"ambiguous S3-Gate output: lane {blocker.lane_id!r} in domain "
                f"{blocker.domain.key!r} has more than one REVIEW_BLOCKER "
                f"(subjects {existing.subject_sha!r} and {blocker.subject_sha!r}); "
                f"a micro-lane cannot be attributed to one of them"
            )
        index[key] = blocker
    return index


def build_remediation_spawns(
    plan: S3RemediationPlan,
    *,
    role: str = CONTROLLER_ROLE,
) -> tuple[RemediationLaneSpawn, ...]:
    """Turn a plan's disjoint groups into frozen, spawn-ready lane records.

    Spawn order follows the plan's group order, so multi-domain splits start as
    isolated lanes. Pure: no seam is called and no worker launches.
    """
    if not role:
        raise S3GateRemediationError("a spawn must record the role that authorized it")
    index = _blocker_index(plan)
    escalate = plan.requires_human_intervention
    spawns: list[RemediationLaneSpawn] = []
    for group in plan.remediation.groups:
        for micro_lane in group:
            blocker = _blocker_for(index, micro_lane, plan)
            spawns.append(
                RemediationLaneSpawn(
                    spawn_id=_spawn_id(
                        micro_lane.lane_id,
                        blocker.base_sha,
                        blocker.subject_sha,
                        plan.failure_round,
                    ),
                    lane_id=micro_lane.lane_id,
                    domain=micro_lane.domain,
                    base_sha=blocker.base_sha,
                    subject_sha=blocker.subject_sha,
                    failed_criteria=blocker.failed_criteria,
                    failure_round=plan.failure_round,
                    spawned_by=role,
                    requires_human_intervention=escalate,
                )
            )
    return tuple(spawns)


def _blocker_for(
    index: Mapping[tuple[str, str], S3GateBlocker],
    micro_lane: RemediationMicroLane,
    plan: S3RemediationPlan,
) -> S3GateBlocker:
    key = (micro_lane.lane_id, micro_lane.domain.key)
    blocker = index.get(key)
    if blocker is None:
        raise S3GateRemediationError(
            f"micro-lane {micro_lane.lane_id!r} in domain "
            f"{micro_lane.domain.key!r} has no matching S3-Gate blocker "
            f"(plan carries {len(plan.blockers)} blocker(s))"
        )
    return blocker


def spawn_remediation_lanes(
    plan: S3RemediationPlan,
    *,
    seam: Optional[SpawnSeam] = None,
    role: str = CONTROLLER_ROLE,
) -> tuple[RemediationLaneSpawn, ...]:
    """Start a plan's remediation lanes through the injected spawn seam.

    Every lane is started when the plan authorizes automatic remediation (a
    standard blocker with budget remaining). When the plan requires human
    intervention, no lane is started through the seam: the spawns are returned
    with ``requires_human_intervention=True`` for the operator to authorize
    first. ``seam=None`` records the intents without launching anything.
    """
    spawns = build_remediation_spawns(plan, role=role)
    if seam is None or plan.requires_human_intervention:
        return spawns
    for spawn in spawns:
        seam(spawn)
    return spawns


@dataclass(frozen=True)
class S3RemediationOutcome:
    """The controller's whole response to one S3-Gate failure report."""

    plan: S3RemediationPlan
    spawns: tuple[RemediationLaneSpawn, ...]

    @property
    def requires_human_intervention(self) -> bool:
        return self.plan.requires_human_intervention

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "spawns": [s.to_dict() for s in self.spawns],
            "requires_human_intervention": self.requires_human_intervention,
        }


def remediate_from_s3_gate(
    gate_output: str,
    *,
    seam: Optional[SpawnSeam] = None,
    failure_round: int = 0,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    role: str = CONTROLLER_ROLE,
) -> S3RemediationOutcome:
    """Controller entry point: parse, slice and start S3-Gate remediation.

    One call turns the S3-Gate's ``REVIEW_BLOCKER`` output into started
    micro-lanes. A standard blocker is spawned by the controller itself, with
    no human in the loop; a non-standard blocker or an exhausted budget yields
    spawns that no seam is called for, so an operator authorizes before any
    mutation starts.
    """
    plan = plan_remediation_from_s3_gate(
        gate_output, failure_round=failure_round, max_rounds=max_rounds
    )
    spawns = spawn_remediation_lanes(plan, seam=seam, role=role)
    return S3RemediationOutcome(plan=plan, spawns=spawns)


__all__ = [
    "REVIEW_BLOCKER",
    "REVIEW_FREIGABE",
    "STANDARD_SEVERITIES",
    "DEFAULT_MAX_ROUNDS",
    "S3GateRemediationError",
    "S3GateBlocker",
    "S3RemediationPlan",
    "RemediationLaneSpawn",
    "S3RemediationOutcome",
    "SpawnSeam",
    "parse_review_blocker_line",
    "parse_review_blocker_output",
    "plan_remediation_from_s3_gate",
    "build_remediation_spawns",
    "spawn_remediation_lanes",
    "remediate_from_s3_gate",
]
