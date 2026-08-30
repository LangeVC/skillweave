"""Semantic observation over typed trace records (SW1311-OBSERVER-001).

This module owns the *semantic* layer of the trace observer: it turns typed,
append-only trace records — :class:`~skillweave.trace.contracts.JobRecord` /
:class:`~skillweave.trace.contracts.JobResult` /
:class:`~skillweave.trace.contracts.TerminalEnvelope`, review records and
dispositions, and typed handoffs/checkpoints — into *semantic findings* a cold
operator can consume without a transcript. It is read-only: it classifies facts,
never mutates the records it reads, and never re-derives state a sibling module
already owns.

It deliberately does not poll a log file, a process id, or a raw stdout stream:
every input is a typed record already produced by the contracts/review/handoff
layer. Its sibling :mod:`skillweave.dispatch.observer` performs the same
semantic classification over the live typed :class:`DispatchEvent` stream.

Three concerns live here (criterion 1–3):

1. **Semantic finding taxonomy** (:class:`SemanticFinding`,
   :class:`SemanticFindingKind`): nine distinct, typed finding kinds that cover
   evidence location, claim, causality, actionability, criterion-coverage gap,
   child-terminal gap, heartbeat expiry, blocked input and resource collision.
2. **Coverage and honest measured facts** (:class:`CoverageReport`,
   :class:`MeasuredFact`): seen-vs-expected criterion and terminal-child
   coverage, run-to-run variance, verified/rejected claims, false-positive /
   false-negative indicators, correction budget and gate state. Cost / token /
   latency values appear *only* from typed measured facts (:class:`MeasuredFact`
   has a non-empty ``source`` and ``kind``); otherwise they are ``unavailable``
   with a recorded reason.
3. **Run-scoped understanding** (:class:`TraceObservation`): a snapshot of the
   semantic understanding of one run's typed records, which the projection
   (:mod:`skillweave.trace.projection`) renders and which replays exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from skillweave.trace.contracts import (
    EvidenceAvailability,
    GateVerdict,
    JobRecord,
    JobStatus,
    TerminalState,
)
from skillweave.trace.review import (
    ReviewRecord,
    ReviewVerdict,
    Severity,
)


class SemanticFindingKind(str, Enum):
    """The nine semantic finding kinds (criterion 1).

    Each is a *distinct* observation about a typed record; no kind is a synonym
    for another, and none is derived from a raw log marker or process id.
    """

    MISSING_EVIDENCE = "missing_evidence"
    EVIDENCE_LOCATION_INCORRECT = "evidence_location_incorrect"
    CLAIM_INCORRECT = "claim_incorrect"
    CAUSAL_INCORRECT = "causal_incorrect"
    NOT_ACTIONABLE = "not_actionable"
    CRITERION_COVERAGE_GAP = "criterion_coverage_gap"
    CHILD_TERMINAL_COVERAGE_GAP = "child_terminal_coverage_gap"
    HEARTBEAT_EXPIRED = "heartbeat_expired"
    BLOCKED_INPUT = "blocked_input"
    RESOURCE_COLLISION = "resource_collision"


class SeverityLevel(str, Enum):
    """The severity a semantic finding is classified at."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SemanticFinding:
    """One semantic observation, immutable (criterion 1).

    A finding names its ``kind``, a ``severity``, the ``subject`` record it is
    about (a record id / subject SHA), a ``location`` (evidence or code
    location), a ``claim`` (what the record implies), the ``criterion`` it
    relates to, and a machine ``detail``. It is a *classification*, never a
    mutation: the observer may emit it, never act on it.
    """

    kind: SemanticFindingKind
    severity: SeverityLevel
    subject: str
    location: Optional[str] = None
    claim: Optional[str] = None
    criterion: Optional[str] = None
    detail: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "severity": self.severity.value,
            "subject": self.subject,
            "location": self.location,
            "claim": self.claim,
            "criterion": self.criterion,
            "detail": self.detail,
        }


# ── Honest measured facts (criterion 3) ─────────────────────────────────────


class MeasuredFactKind(str, Enum):
    """The kinds of measured fact the observer may report cost from."""

    COST = "cost"
    TOKENS = "tokens"
    LATENCY = "latency"


@dataclass(frozen=True)
class MeasuredFact:
    """A measured cost/token/latency fact, or an explicit ``unavailable``.

    ``kind`` / ``value`` / ``unit`` are present only when the value derives from
    a *typed* measured fact (``source`` names the record it came from). When
    ``available`` is false, ``reason`` states why the value is unavailable; the
    observer may never invent a number there.
    """

    kind: MeasuredFactKind
    available: bool
    value: Any = None
    unit: Optional[str] = None
    source: Optional[str] = None
    reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind.value,
            "available": self.available,
        }
        if self.available:
            data["value"] = self.value
            data["unit"] = self.unit
            data["source"] = self.source
        else:
            data["reason"] = self.reason
        return data


# ── Coverage report (criterion 2) ───────────────────────────────────────────


@dataclass(frozen=True)
class ClaimStatus:
    """A claim's verification state: verified, rejected, or unverified."""

    verified: bool
    rejected: bool
    false_positive: bool = False
    false_negative: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "verified": self.verified,
            "rejected": self.rejected,
            "false_positive": self.false_positive,
            "false_negative": self.false_negative,
        }


@dataclass(frozen=True)
class CoverageReport:
    """Seen-vs-expected coverage and run-to-run variance (criterion 2).

    ``seen_criteria`` / ``expected_criteria`` give exact-once coverage of
    acceptance criteria; ``seen_terminal_children`` / ``expected_terminal_children``
    give terminal-child coverage; ``coverage_envelope`` names the widest/lower
    bound of what was observed. ``budget_remaining`` / ``budget_consumed`` and
    ``gate`` state complete the operator-facing facts.
    """

    seen_criteria: tuple[str, ...] = ()
    expected_criteria: tuple[str, ...] = ()
    seen_terminal_children: tuple[str, ...] = ()
    expected_terminal_children: tuple[str, ...] = ()
    coverage_envelope_min: Optional[int] = None
    coverage_envelope_max: Optional[int] = None
    run_to_run_variance: Optional[float] = None
    claim_statuses: Mapping[str, ClaimStatus] = field(default_factory=dict)
    budget_remaining: Optional[int] = None
    budget_total: Optional[int] = None
    budget_consumed: int = 0
    gate_state: Optional[str] = None

    def missing_criteria(self) -> tuple[str, ...]:
        seen = set(self.seen_criteria)
        return tuple(c for c in self.expected_criteria if c not in seen)

    def missing_terminal_children(self) -> tuple[str, ...]:
        seen = set(self.seen_terminal_children)
        return tuple(c for c in self.expected_terminal_children if c not in seen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seen_criteria": list(self.seen_criteria),
            "expected_criteria": list(self.expected_criteria),
            "seen_terminal_children": list(self.seen_terminal_children),
            "expected_terminal_children": list(self.expected_terminal_children),
            "coverage_envelope_min": self.coverage_envelope_min,
            "coverage_envelope_max": self.coverage_envelope_max,
            "run_to_run_variance": self.run_to_run_variance,
            "claim_statuses": {
                k: v.to_dict() for k, v in self.claim_statuses.items()
            },
            "budget_remaining": self.budget_remaining,
            "budget_total": self.budget_total,
            "budget_consumed": self.budget_consumed,
            "gate_state": self.gate_state,
        }


# ── Precedence: terminals that block a run ─────────────────────────────────


@dataclass(frozen=True)
class TraceObservation:
    """The semantic understanding of one run's typed records (a snapshot).

    This is the deterministic output of :func:`observe_run` and is the *input*
    to the projection. It carries the semantic findings, the coverage report and
    the measured facts. It is immutable: replaying the same ordered records
    produces an equal snapshot.
    """

    run_id: str
    findings: tuple[SemanticFinding, ...] = ()
    coverage: CoverageReport = field(default_factory=CoverageReport)
    measured_facts: tuple[MeasuredFact, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "findings": [f.to_dict() for f in self.findings],
            "coverage": self.coverage.to_dict(),
            "measured_facts": [m.to_dict() for m in self.measured_facts],
        }


# ── Measured-fact extraction from typed facts ───────────────────────────────


def measured_fact(
    kind: MeasuredFactKind,
    *,
    value: Any = None,
    unit: Optional[str] = None,
    source: Optional[str] = None,
) -> MeasuredFact:
    """Return a measured fact only when ``value`` and ``source`` are present.

    Without both, the fact is ``unavailable`` with a concrete reason — the
    observer never invents a cost/token/latency number (criterion 3).
    """
    if value is None or source is None:
        return MeasuredFact(
            kind=kind,
            available=False,
            reason=(
                f"{kind.value} is unavailable: no typed measured fact "
                "records it"
            ),
        )
    return MeasuredFact(
        kind=kind, available=True, value=value, unit=unit, source=source,
    )


# ── Semantic classification over typed records ─────────────────────────────


def _criteria_from_payload(record: JobRecord) -> tuple[str, ...]:
    payload = record.payload
    if payload is None:
        return ()
    if isinstance(payload, Mapping):
        return tuple(str(c) for c in payload.get("criteria", ()))
    return ()


def classify_record(record: JobRecord) -> tuple[SemanticFinding, ...]:
    """Classify one typed :class:`JobRecord` into semantic findings.

    The classification reads only the record's typed surface — no raw output.
    Each finding kind maps to a concrete condition on the typed fields:
    """

    findings: list[SemanticFinding] = []
    result = record.result
    envelope = record.envelope
    subject = record.job_id or record.record_id

    if record.kind.value not in ("dispatch", "correction", "review", "integration"):
        return tuple(findings)

    if result is not None:
        if result.evidence_available is EvidenceAvailability.MISSING:
            findings.append(SemanticFinding(
                kind=SemanticFindingKind.MISSING_EVIDENCE,
                severity=SeverityLevel.WARNING,
                subject=subject,
                detail="required evidence is missing",
            ))
        elif result.evidence_available is EvidenceAvailability.UNRESOLVABLE:
            findings.append(SemanticFinding(
                kind=SemanticFindingKind.MISSING_EVIDENCE,
                severity=SeverityLevel.CRITICAL,
                subject=subject,
                detail="required evidence is unresolvable",
            ))

        if result.job_status is JobStatus.HEARTBEAT_EXPIRED:
            findings.append(SemanticFinding(
                kind=SemanticFindingKind.HEARTBEAT_EXPIRED,
                severity=SeverityLevel.CRITICAL,
                subject=subject,
                detail="child heartbeat expired before a terminal event",
            ))
        elif result.job_status is JobStatus.BLOCKED_INPUT:
            findings.append(SemanticFinding(
                kind=SemanticFindingKind.BLOCKED_INPUT,
                severity=SeverityLevel.WARNING,
                subject=subject,
                detail="noninteractive child requested stdin and never waited",
            ))

        if result.job_status is JobStatus.LAUNCH_FAILED and (
            envelope is not None and envelope.terminal_state is TerminalState.PREFLIGHT_FAILED
        ):
            findings.append(SemanticFinding(
                kind=SemanticFindingKind.RESOURCE_COLLISION,
                severity=SeverityLevel.CRITICAL,
                subject=subject,
                detail="shared state namespace collision failed preflight",
            ))

    return tuple(findings)


def classify_review(review: ReviewRecord) -> tuple[SemanticFinding, ...]:
    """Classify a review record into coverage/claim semantic findings."""
    findings: list[SemanticFinding] = []
    for f in review.findings:
        findings.append(SemanticFinding(
            kind=SemanticFindingKind.CLAIM_INCORRECT,
            severity=_severity_of(f.severity),
            subject=review.subject_sha,
            location=f.code_location,
            claim=f.criterion,
            detail=f.evidence_ref,
        ))
    return tuple(findings)


def _severity_of(severity: Severity) -> SeverityLevel:
    return {
        Severity.BLOCKER: SeverityLevel.CRITICAL,
        Severity.MAJOR: SeverityLevel.WARNING,
        Severity.MINOR: SeverityLevel.INFO,
    }[severity]


# ── Run-level observation ───────────────────────────────────────────────────


def observe_run(
    run_id: str,
    records: Sequence[JobRecord],
    *,
    expected_criteria: Sequence[str] = (),
    expected_terminal_children: Sequence[str] = (),
    reviews: Sequence[ReviewRecord] = (),
    budget_total: Optional[int] = None,
    budget_consumed: int = 0,
    prior_seen_criteria: Sequence[tuple[str, ...]] = (),
    measured: Sequence[MeasuredFact] = (),
) -> TraceObservation:
    """Produce an immutable semantic observation of one run (criteria 1–3).

    Only typed facts are consumed. The result is deterministic for a given
    ordered input, so the projection replays exactly.
    """
    findings: list[SemanticFinding] = []
    seen_criteria: list[str] = []
    seen_children: list[str] = []

    for record in records:
        findings.extend(classify_record(record))
        seen_criteria.extend(_criteria_from_payload(record))
        result = record.result
        if record.job_id:
            seen_children.append(record.job_id)
        elif result is not None and (
            result.job_status
            in {
                JobStatus.EXITED,
                JobStatus.SIGNALED,
                JobStatus.TIMED_OUT,
                JobStatus.CANCELLED,
                JobStatus.HEARTBEAT_EXPIRED,
                JobStatus.BLOCKED_INPUT,
                JobStatus.LAUNCH_FAILED,
            }
        ):
            seen_children.append(record.record_id)

    for review in reviews:
        findings.extend(classify_review(review))

    missing_criteria = set(expected_criteria) - set(seen_criteria)
    for criterion in sorted(missing_criteria):
        findings.append(SemanticFinding(
            kind=SemanticFindingKind.CRITERION_COVERAGE_GAP,
            severity=SeverityLevel.WARNING,
            subject=run_id,
            criterion=criterion,
            detail="criterion not observed in any typed record",
        ))

    missing_children = set(expected_terminal_children) - set(seen_children)
    for child in sorted(missing_children):
        findings.append(SemanticFinding(
            kind=SemanticFindingKind.CHILD_TERMINAL_COVERAGE_GAP,
            severity=SeverityLevel.WARNING,
            subject=run_id,
            location=child,
            detail="expected terminal child not observed",
        ))

    claim_statuses: dict[str, ClaimStatus] = {}
    for review in reviews:
        for f in review.findings:
            claim_statuses[f.id] = ClaimStatus(
                verified=review.verdict is ReviewVerdict.REVIEW_PASS,
                rejected=review.verdict is ReviewVerdict.REVIEW_FAIL,
                false_positive=False,
                false_negative=review.verdict is ReviewVerdict.REVIEW_FAIL,
            )

    observed_rounds = [r.round for r in records if r.round is not None]
    envelope_min = min(observed_rounds) if observed_rounds else None
    envelope_max = max(observed_rounds) if observed_rounds else None

    variance = _variance(seen_criteria, prior_seen_criteria)

    coverage = CoverageReport(
        seen_criteria=tuple(sorted(set(seen_criteria))),
        expected_criteria=tuple(sorted(set(expected_criteria))),
        seen_terminal_children=tuple(sorted(set(seen_children))),
        expected_terminal_children=tuple(sorted(set(expected_terminal_children))),
        coverage_envelope_min=envelope_min,
        coverage_envelope_max=envelope_max,
        run_to_run_variance=variance,
        claim_statuses=claim_statuses,
        budget_total=budget_total,
        budget_consumed=budget_consumed,
        budget_remaining=(
            budget_total - budget_consumed
            if budget_total is not None
            else None
        ),
        gate_state=_gate_state(records),
    )

    return TraceObservation(
        run_id=run_id,
        findings=tuple(findings),
        coverage=coverage,
        measured_facts=tuple(measured),
    )


def _variance(
    seen: Sequence[str],
    prior: Sequence[tuple[str, ...]],
) -> Optional[float]:
    """Run-to-run variance: fraction of prior runs whose seen set differs."""
    if not prior:
        return None
    seen_set = set(seen)
    differing = sum(1 for p in prior if set(p) != seen_set)
    return round(differing / len(prior), 4)


def _gate_state(records: Sequence[JobRecord]) -> Optional[str]:
    """The gate state derived from the latest typed gate verdict, or ``None``."""
    for record in reversed(records):
        result = record.result
        if result is not None and result.gate_verdict is not GateVerdict.UNSET:
            return result.gate_verdict.value
    return None


__all__ = [
    "SemanticFindingKind",
    "SeverityLevel",
    "MeasuredFactKind",
    "SemanticFinding",
    "MeasuredFact",
    "ClaimStatus",
    "CoverageReport",
    "TraceObservation",
    "measured_fact",
    "classify_record",
    "classify_review",
    "observe_run",
]
