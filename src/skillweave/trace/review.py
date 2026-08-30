"""Review policy (SW1311-REVIEW-001): findings, dispositions, adjudication, gates.

This module owns the *review* layer of the dispatch trace — the contract that
turns a reviewer's observations into a fail-closed decision a controller can
consume. It is deliberately decision-only and provider/harness-neutral: it
names no model, gateway or harness, performs no product edit and imports no
optional ``skillweave.runtime`` subpackage (GLE-020), mirroring the sibling
:mod:`skillweave.trace.contracts` module.

It builds on, and never duplicates, the existing trace contracts: a review is a
:class:`~skillweave.trace.contracts.RoundKind.REVIEW` round appended onto the
same append-only receipt log, and its outcome is carried in the record payload.
What lives here is the *policy* that the receipt alone does not express:

1. **Findings** (:class:`Finding`) — a reviewer's observation carries a stable
   id, a criterion *or* code location, a severity, an evidence reference, the
   reviewer identity and the exact full subject SHA (criterion 1).
2. **Dispositions** (:class:`Disposition`) — before any correction is generated,
   every finding receives exactly one accepted/rejected decision with a
   rationale and the disposing actor; a duplicate or conflicting disposition
   fails closed (criterion 2).
3. **Controller adjudication** (:func:`adjudicate`) — the controller *separately*
   verifies location, reachable state, causal chain and impact, and may uphold,
   narrow or reject individual findings while the immutable reviewer record is
   preserved. It can never synthesize ``REVIEW_PASS`` (criterion 3).
4. **Freeze** (:class:`CandidateReviewState`) — a controller verification
   failure or a ``REVIEW_FAIL`` freezes the exact candidate SHA and blocks
   dependent-lane readiness (criterion 4).
5. **Correction handoff** (:class:`CorrectionHandoff`) — carries all-and-only
   accepted finding ids, consumes a bounded correction round, and requires a
   subsequent controller verification plus a fresh cold review (criterion 5).
6. **Subject change** (:func:`invalidate_on_subject_change`) — a changed subject
   SHA invalidates the prior verdict and dispositions unless an explicit
   finding-by-finding :class:`CarryForwardRule` applies (criterion 6).
7. **Separation** (:func:`validate_producer_reviewer_separation`,
   :func:`assert_reviewer_authority`) — producer and reviewer must be distinct
   sessions, roles and worktrees, and a reviewer's mutation/repair authority
   fails before execution (criterion 7).
8. **Critical final gate** (:func:`evaluate_critical_gate`) — two *diverse*
   reviewers are dispatched concurrently against one immutable subject; both
   must return ``REVIEW_PASS``, and material disagreement routes to targeted
   evidence adjudication rather than majority voting (criterion 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from skillweave.trace.contracts import content_id


# ── Roles and authority vocabulary (aligned with runtime.authority) ──────────

#: The producer role — the actor that authored the subject under review.
PRODUCER_ROLE = "producer"

#: The reviewer role — a read-only actor that produces findings and a verdict.
REVIEWER_ROLE = "reviewer"

#: The controller role — adjudicates findings, verifies candidates, never edits.
CONTROLLER_ROLE = "controller"

#: Actions a reviewer may never perform. A reviewer is read-only: mutation,
#: repair, write, commit, push, merge, release and tag all fail before execution.
REVIEWER_FORBIDDEN_ACTIONS: frozenset[str] = frozenset({
    "mutate", "repair", "write", "commit", "push", "merge", "release", "tag",
})


def _is_full_sha(value: Any) -> bool:
    """True for a 40-hex-char full subject SHA (local copy, GLE-020)."""
    if not isinstance(value, str) or len(value) != 40:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


# ── Exception hierarchy ──────────────────────────────────────────────────────


class ReviewPolicyError(Exception):
    """A review-policy contract violation (raised fail-closed)."""


class DispositionError(ReviewPolicyError):
    """A finding received a duplicate/conflicting (or missing) disposition."""


class AdjudicationError(ReviewPolicyError):
    """A controller adjudication was malformed or unauthorized."""


class CorrectionHandoffError(ReviewPolicyError):
    """A correction handoff violated the bounded-round or accepted-id contract."""


class ReviewGateError(ReviewPolicyError):
    """A review gate (freeze, readiness, critical gate) was violated."""


class ReviewAuthorityError(ReviewPolicyError):
    """A role/session/worktree separation or reviewer-authority rule failed."""


class CriticalGateError(ReviewGateError):
    """The critical final gate could not be satisfied (diversity or verdict)."""


# ── Enums ────────────────────────────────────────────────────────────────────


class Severity(str, Enum):
    """The severity of a finding (classification, not a decision)."""

    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"


class DispositionDecision(str, Enum):
    """The single accepted/rejected decision a finding receives (criterion 2)."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


class AdjudicationDecision(str, Enum):
    """The controller's per-finding decision (criterion 3).

    The controller may uphold, narrow or reject a finding — never pass a review.
    """

    UPHOLD = "uphold"
    NARROW = "narrow"
    REJECT = "reject"


class ReviewVerdict(str, Enum):
    """The binary verdict a reviewer returns for a subject (criteria 4, 8).

    ``REVIEW_PASS`` is produced *only* by a reviewer — a controller can never
    synthesize it (criterion 3).
    """

    REVIEW_PASS = "REVIEW_PASS"
    REVIEW_FAIL = "REVIEW_FAIL"


# ── Criterion 1: findings ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    """One reviewer observation, immutable (criterion 1).

    A finding is identified by a stable ``id``, and must name a criterion *or* a
    code location, a ``severity``, an evidence reference, the ``reviewer_id``
    that produced it and the exact full ``subject_sha`` it was raised against.
    It is frozen: once produced it is the immutable reviewer record the
    controller adjudicates against (criterion 3).
    """

    id: str
    severity: Severity
    evidence_ref: str
    reviewer_id: str
    subject_sha: str
    criterion: Optional[str] = None
    code_location: Optional[str] = None

    def validate(self) -> None:
        """Raise :class:`ReviewPolicyError` on any incomplete field."""
        if not self.id:
            raise ReviewPolicyError("finding id must be non-empty")
        if not (self.criterion or self.code_location):
            raise ReviewPolicyError(
                f"finding '{self.id}' must name a criterion or code location"
            )
        if not self.evidence_ref:
            raise ReviewPolicyError(f"finding '{self.id}' must reference evidence")
        if not self.reviewer_id:
            raise ReviewPolicyError(f"finding '{self.id}' must name its reviewer")
        if not _is_full_sha(self.subject_sha):
            raise ReviewPolicyError(
                f"finding '{self.id}' subject SHA {self.subject_sha!r} is not a full SHA"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "severity": self.severity.value,
            "evidence_ref": self.evidence_ref,
            "reviewer_id": self.reviewer_id,
            "subject_sha": self.subject_sha,
            "criterion": self.criterion,
            "code_location": self.code_location,
        }


def new_finding(
    *,
    reviewer_id: str,
    subject_sha: str,
    severity: Severity,
    evidence_ref: str,
    criterion: Optional[str] = None,
    code_location: Optional[str] = None,
    finding_id: Optional[str] = None,
) -> Finding:
    """Build a finding, deriving a stable content-addressed id when not supplied.

    The id is content-addressed over the reviewer, subject, severity, evidence
    and location so the same observation derives the same id; a caller needing
    two distinct findings that otherwise coincide may pass ``finding_id``.
    """
    if finding_id is None:
        finding_id = content_id(
            "finding", reviewer_id, subject_sha, severity.value,
            evidence_ref, criterion, code_location,
        )
    finding = Finding(
        id=finding_id,
        severity=severity,
        evidence_ref=evidence_ref,
        reviewer_id=reviewer_id,
        subject_sha=subject_sha,
        criterion=criterion,
        code_location=code_location,
    )
    finding.validate()
    return finding


# ── Criterion 2: dispositions ────────────────────────────────────────────────


@dataclass(frozen=True)
class Disposition:
    """The single accepted/rejected decision a finding receives (criterion 2).

    Carries the ``finding_id`` it disposes, the binary ``decision``, a
    ``rationale`` and the ``actor_id`` that disposed it. Frozen so a decision,
    once recorded, cannot be silently rewritten.
    """

    finding_id: str
    decision: DispositionDecision
    rationale: str
    actor_id: str

    def validate(self) -> None:
        if not self.finding_id:
            raise DispositionError("disposition must name its finding")
        if not self.rationale:
            raise DispositionError(
                f"disposition for '{self.finding_id}' must carry a rationale"
            )
        if not self.actor_id:
            raise DispositionError(
                f"disposition for '{self.finding_id}' must name its actor"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "decision": self.decision.value,
            "rationale": self.rationale,
            "actor_id": self.actor_id,
        }


class DispositionRegister:
    """A fail-closed register of one disposition per finding (criterion 2).

    Recording a second disposition for the same finding raises
    :class:`DispositionError` (duplicate/conflicting disposition fails closed).
    """

    def __init__(self) -> None:
        self._by_finding: dict[str, Disposition] = {}

    def __len__(self) -> int:
        return len(self._by_finding)

    def record(self, disposition: Disposition) -> Disposition:
        """Record a disposition, refusing a duplicate/conflicting one."""
        disposition.validate()
        existing = self._by_finding.get(disposition.finding_id)
        if existing is not None:
            raise DispositionError(
                f"finding '{disposition.finding_id}' already has a "
                f"{existing.decision.value} disposition; a duplicate or "
                "conflicting disposition fails closed"
            )
        self._by_finding[disposition.finding_id] = disposition
        return disposition

    def get(self, finding_id: str) -> Optional[Disposition]:
        return self._by_finding.get(finding_id)

    def decision(self, finding_id: str) -> Optional[DispositionDecision]:
        d = self._by_finding.get(finding_id)
        return d.decision if d is not None else None

    def accepted_finding_ids(self) -> list[str]:
        """The finding ids disposed ``accepted``, in stable order."""
        return sorted(
            fid for fid, d in self._by_finding.items()
            if d.decision is DispositionDecision.ACCEPTED
        )

    def rejected_finding_ids(self) -> list[str]:
        """The finding ids disposed ``rejected``, in stable order."""
        return sorted(
            fid for fid, d in self._by_finding.items()
            if d.decision is DispositionDecision.REJECTED
        )

    def finding_ids(self) -> list[str]:
        """Every disposed finding id, in stable order."""
        return sorted(self._by_finding)

    def require_all(self, findings: Sequence[Finding]) -> None:
        """Fail closed unless every finding has exactly one disposition.

        A finding missing a disposition, or a disposition naming a finding that
        does not exist, raises :class:`DispositionError` (criterion 2).
        """
        finding_ids = {f.id for f in findings}
        missing = sorted(fid for fid in finding_ids if fid not in self._by_finding)
        if missing:
            raise DispositionError(
                f"findings missing a disposition: {missing}"
            )
        orphan = sorted(fid for fid in self._by_finding if fid not in finding_ids)
        if orphan:
            raise DispositionError(
                f"dispositions reference unknown findings: {orphan}"
            )


# ── Criterion 3: controller adjudication ─────────────────────────────────────


def _downgrade(severity: Severity) -> Severity:
    return {
        Severity.BLOCKER: Severity.MAJOR,
        Severity.MAJOR: Severity.MINOR,
        Severity.MINOR: Severity.MINOR,
    }[severity]


@dataclass(frozen=True)
class Adjudication:
    """The controller's per-finding decision (criterion 3).

    Records the four *separately verified* dimensions — location, reachable
    state, causal chain and impact — and the resulting ``decision``
    (uphold/narrow/reject). ``narrowed_severity`` is set only when the finding
    is narrowed. There is no verdict field here: an adjudication is about a
    single finding and can never synthesize ``REVIEW_PASS``.
    """

    finding_id: str
    decision: AdjudicationDecision
    actor_id: str
    verified_location: bool
    verified_reachable: bool
    verified_causal: bool
    verified_impact: bool
    narrowed_severity: Optional[Severity] = None
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "decision": self.decision.value,
            "actor_id": self.actor_id,
            "verified_location": self.verified_location,
            "verified_reachable": self.verified_reachable,
            "verified_causal": self.verified_causal,
            "verified_impact": self.verified_impact,
            "narrowed_severity": (
                self.narrowed_severity.value if self.narrowed_severity else None
            ),
            "rationale": self.rationale,
        }


def adjudicate(
    finding: Finding,
    *,
    actor_id: str,
    location_verified: bool,
    reachable_verified: bool,
    causal_verified: bool,
    impact_verified: bool,
    narrowed_severity: Optional[Severity] = None,
) -> Adjudication:
    """Adjudicate one finding, verifying the four dimensions separately.

    The decision is fail-closed and binary in effect (criterion 3):

    * a finding whose location, reachable state or causal chain cannot be
      verified is **rejected**;
    * a finding whose impact cannot be verified (severity overstated) is
      **narrowed** to the next lower severity;
    * a finding that verifies on all four dimensions is **upheld**.

    The immutable reviewer record (the frozen :class:`Finding`) is never
    modified; the result is a separate :class:`Adjudication`. This function
    returns an :class:`Adjudication`, never a :class:`ReviewVerdict`, so the
    controller cannot synthesize ``REVIEW_PASS``.
    """
    finding.validate()
    if not actor_id:
        raise AdjudicationError("adjudication must name its actor")
    if not (location_verified and reachable_verified and causal_verified):
        decision = AdjudicationDecision.REJECT
        narrowed = None
    elif not impact_verified:
        decision = AdjudicationDecision.NARROW
        narrowed = narrowed_severity or _downgrade(finding.severity)
    else:
        decision = AdjudicationDecision.UPHOLD
        narrowed = None
    return Adjudication(
        finding_id=finding.id,
        decision=decision,
        actor_id=actor_id,
        verified_location=location_verified,
        verified_reachable=reachable_verified,
        verified_causal=causal_verified,
        verified_impact=impact_verified,
        narrowed_severity=narrowed,
    )


# ── Review records and verdicts (criteria 4, 8) ──────────────────────────────


@dataclass(frozen=True)
class ReviewRecord:
    """A reviewer's verdict bound to one immutable subject (criteria 4, 8).

    ``verdict`` is ``REVIEW_PASS`` or ``REVIEW_FAIL``; ``findings`` are the
    reviewer's observations for that subject. Only a reviewer produces this —
    the controller's adjudication is per-finding, never a review verdict.
    """

    reviewer_id: str
    subject_sha: str
    verdict: ReviewVerdict
    findings: tuple[Finding, ...] = ()

    def validate(self) -> None:
        if not self.reviewer_id:
            raise ReviewPolicyError("review must name its reviewer")
        if not _is_full_sha(self.subject_sha):
            raise ReviewPolicyError(
                f"review subject SHA {self.subject_sha!r} is not a full SHA"
            )
        for finding in self.findings:
            finding.validate()
            if finding.subject_sha != self.subject_sha:
                raise ReviewPolicyError(
                    f"finding '{finding.id}' subject SHA does not match the review"
                )
            if finding.reviewer_id != self.reviewer_id:
                raise ReviewPolicyError(
                    f"finding '{finding.id}' reviewer does not match the review"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer_id": self.reviewer_id,
            "subject_sha": self.subject_sha,
            "verdict": self.verdict.value,
            "findings": [f.to_dict() for f in self.findings],
        }


def review_pass(
    reviewer_id: str,
    subject_sha: str,
    findings: Sequence[Finding] = (),
) -> ReviewRecord:
    """Return a ``REVIEW_PASS`` record (a reviewer's verdict, never a controller's)."""
    record = ReviewRecord(
        reviewer_id=reviewer_id,
        subject_sha=subject_sha,
        verdict=ReviewVerdict.REVIEW_PASS,
        findings=tuple(findings),
    )
    record.validate()
    return record


def review_fail(
    reviewer_id: str,
    subject_sha: str,
    findings: Sequence[Finding] = (),
) -> ReviewRecord:
    """Return a ``REVIEW_FAIL`` record (a reviewer's verdict, never a controller's)."""
    record = ReviewRecord(
        reviewer_id=reviewer_id,
        subject_sha=subject_sha,
        verdict=ReviewVerdict.REVIEW_FAIL,
        findings=tuple(findings),
    )
    record.validate()
    return record


# ── Criterion 4: freeze and dependent readiness ──────────────────────────────


@dataclass
class CandidateReviewState:
    """The review state of one candidate subject (criterion 4).

    A ``REVIEW_FAIL`` or a controller verification failure freezes the exact
    ``subject_sha`` and blocks dependent-lane readiness. A candidate is ready
    for its dependents only when the controller verified it, its verdict is
    ``REVIEW_PASS`` and it is not frozen.
    """

    subject_sha: str
    verdict: Optional[ReviewVerdict] = None
    controller_verified: bool = False
    frozen: bool = False
    freeze_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if not _is_full_sha(self.subject_sha):
            raise ReviewPolicyError(
                f"candidate subject SHA {self.subject_sha!r} is not a full SHA"
            )

    def _freeze(self, reason: str) -> None:
        self.frozen = True
        self.freeze_reason = reason

    def record_review(self, review: ReviewRecord) -> None:
        """Record a review verdict, freezing the candidate on ``REVIEW_FAIL``."""
        review.validate()
        if review.subject_sha != self.subject_sha:
            raise ReviewPolicyError(
                f"review subject {review.subject_sha!r} does not match candidate "
                f"{self.subject_sha!r}"
            )
        self.verdict = review.verdict
        if review.verdict is ReviewVerdict.REVIEW_FAIL:
            self._freeze("REVIEW_FAIL")

    def record_controller_verification(self, verified: bool) -> None:
        """Record the controller's verification; failure freezes the candidate."""
        self.controller_verified = verified
        if not verified:
            self._freeze("controller verification failed")

    def frozen_subject_sha(self) -> Optional[str]:
        """The exact frozen candidate SHA, or ``None`` when not frozen."""
        return self.subject_sha if self.frozen else None

    def dependent_ready(self) -> bool:
        """True only when verified, passed and not frozen (criterion 4)."""
        return (
            self.controller_verified
            and self.verdict is ReviewVerdict.REVIEW_PASS
            and not self.frozen
        )


# ── Criterion 5: correction handoff ──────────────────────────────────────────


@dataclass(frozen=True)
class CorrectionHandoff:
    """A bounded correction handoff to the producer (criterion 5).

    Carries *all and only* the accepted finding ids, the ``correction_round`` it
    consumes (bounded by ``max_rounds``), and the follow-up obligations — a
    subsequent controller verification and a fresh cold review — that must be
    satisfied before the correction is complete.
    """

    subject_sha: str
    finding_ids: tuple[str, ...]
    correction_round: int
    max_rounds: int
    requires_controller_verification: bool = True
    requires_fresh_review: bool = True

    def validate(self) -> None:
        if not _is_full_sha(self.subject_sha):
            raise CorrectionHandoffError(
                f"correction subject SHA {self.subject_sha!r} is not a full SHA"
            )
        if not (1 <= self.correction_round <= self.max_rounds):
            raise CorrectionHandoffError(
                f"correction round {self.correction_round} is outside the bounded "
                f"range 1..{self.max_rounds}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_sha": self.subject_sha,
            "finding_ids": list(self.finding_ids),
            "correction_round": self.correction_round,
            "max_rounds": self.max_rounds,
            "requires_controller_verification": self.requires_controller_verification,
            "requires_fresh_review": self.requires_fresh_review,
        }


def build_correction_handoff(
    findings: Sequence[Finding],
    dispositions: DispositionRegister,
    *,
    subject_sha: str,
    correction_round: int,
    max_rounds: int,
) -> CorrectionHandoff:
    """Build a correction handoff from the accepted findings (criterion 5).

    Fails closed when any finding lacks a disposition, when the correction round
    is outside the bound, or when the subject SHA is not a full SHA. The
    returned handoff carries exactly the accepted finding ids — never a rejected
    one, and never one the register did not dispose.
    """
    if not _is_full_sha(subject_sha):
        raise CorrectionHandoffError(
            f"correction subject SHA {subject_sha!r} is not a full SHA"
        )
    dispositions.require_all(findings)
    if not (1 <= correction_round <= max_rounds):
        raise CorrectionHandoffError(
            f"correction round {correction_round} is outside the bounded "
            f"range 1..{max_rounds}"
        )
    return CorrectionHandoff(
        subject_sha=subject_sha,
        finding_ids=tuple(dispositions.accepted_finding_ids()),
        correction_round=correction_round,
        max_rounds=max_rounds,
    )


def correction_complete(
    handoff: CorrectionHandoff,
    *,
    controller_verified: bool,
    fresh_review: Optional[ReviewRecord],
) -> bool:
    """True only when the correction's follow-ups are satisfied (criterion 5).

    A correction is complete when the controller verified the corrected subject
    *and* a fresh cold ``REVIEW_PASS`` review is bound to it. A missing or
    ``REVIEW_FAIL`` fresh review, or a failed verification, keeps it incomplete.
    """
    handoff.validate()
    if not controller_verified:
        return False
    if fresh_review is None:
        return False
    fresh_review.validate()
    if fresh_review.subject_sha != handoff.subject_sha:
        raise ReviewPolicyError(
            f"fresh review subject {fresh_review.subject_sha!r} does not match "
            f"correction subject {handoff.subject_sha!r}"
        )
    return fresh_review.verdict is ReviewVerdict.REVIEW_PASS


# ── Criterion 6: subject-change invalidation ─────────────────────────────────


@dataclass(frozen=True)
class CarryForwardRule:
    """An explicit finding-by-finding carry-forward across a subject change.

    ``finding_id`` names the one finding that survives to ``new_subject_sha``;
    a finding without a rule does not carry forward (criterion 6).
    """

    finding_id: str
    new_subject_sha: str


@dataclass(frozen=True)
class SubjectChangeResult:
    """The outcome of applying a subject change (criterion 6).

    ``verdict_invalidated`` is always true when the SHA changed (a verdict is
    bound to a SHA and never carries forward). ``invalidated_finding_ids`` are
    the dispositions dropped; ``carried_forward_finding_ids`` are those an
    explicit rule preserved.
    """

    verdict_invalidated: bool
    invalidated_finding_ids: tuple[str, ...]
    carried_forward_finding_ids: tuple[str, ...]


def invalidate_on_subject_change(
    review: ReviewRecord,
    dispositions: DispositionRegister,
    *,
    new_subject_sha: str,
    carry_forward: Sequence[CarryForwardRule] = (),
) -> SubjectChangeResult:
    """Invalidate a verdict and dispositions when the subject SHA changes.

    The prior verdict is always invalidated (it is bound to the old SHA). Each
    disposition is invalidated unless an explicit :class:`CarryForwardRule`
    names its finding for the *exact* new SHA — carry-forward is
    finding-by-finding, never wholesale (criterion 6).
    """
    review.validate()
    if not _is_full_sha(new_subject_sha):
        raise ReviewPolicyError(
            f"new subject SHA {new_subject_sha!r} is not a full SHA"
        )
    if review.subject_sha == new_subject_sha:
        raise ReviewPolicyError(
            "subject SHA is unchanged; nothing to invalidate"
        )

    carried = {
        rule.finding_id
        for rule in carry_forward
        if rule.new_subject_sha == new_subject_sha
    }
    # A carry-forward rule for a finding this review never disposed is refused.
    known_ids = set(dispositions.finding_ids())
    stray = sorted(fid for fid in carried if fid not in known_ids)
    if stray:
        raise ReviewPolicyError(
            f"carry-forward rules name findings without a disposition: {stray}"
        )

    invalidated = tuple(
        sorted(fid for fid in known_ids if fid not in carried)
    )
    return SubjectChangeResult(
        verdict_invalidated=True,
        invalidated_finding_ids=invalidated,
        carried_forward_finding_ids=tuple(sorted(carried)),
    )


# ── Criterion 7: separation and reviewer authority ───────────────────────────


@dataclass(frozen=True)
class ActorBinding:
    """The session/role/worktree binding of one actor (criterion 7)."""

    actor_id: str
    role: str
    session_id: str
    worktree: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_id": self.actor_id,
            "role": self.role,
            "session_id": self.session_id,
            "worktree": self.worktree,
        }


def validate_producer_reviewer_separation(
    producer: ActorBinding,
    reviewer: ActorBinding,
) -> None:
    """Refuse a producer/reviewer pair that is not fully separated (criterion 7).

    Producer and reviewer must be distinct roles, distinct sessions and
    distinct worktrees; any collision raises :class:`ReviewAuthorityError`.
    """
    if producer.role != PRODUCER_ROLE:
        raise ReviewAuthorityError(
            producer.role, "produce", f"producer role is {producer.role!r}, "
            f"expected {PRODUCER_ROLE!r}"
        )
    if reviewer.role != REVIEWER_ROLE:
        raise ReviewAuthorityError(
            reviewer.role, "review", f"reviewer role is {reviewer.role!r}, "
            f"expected {REVIEWER_ROLE!r}"
        )
    if producer.session_id == reviewer.session_id:
        raise ReviewAuthorityError(
            reviewer.role, "review",
            "producer and reviewer must run in separate sessions",
        )
    if producer.worktree == reviewer.worktree:
        raise ReviewAuthorityError(
            reviewer.role, "review",
            "producer and reviewer must use separate worktrees",
        )


def assert_reviewer_authority(reviewer: ActorBinding, action: str) -> None:
    """Fail before execution when a reviewer attempts a forbidden action.

    A reviewer is read-only: ``mutate``, ``repair``, ``write``, ``commit``,
    ``push``, ``merge``, ``release`` and ``tag`` all raise
    :class:`ReviewAuthorityError` *before* the action runs (criterion 7).
    """
    if reviewer.role != REVIEWER_ROLE:
        raise ReviewAuthorityError(
            reviewer.role, action, f"expected a {REVIEWER_ROLE!r} binding"
        )
    if action in REVIEWER_FORBIDDEN_ACTIONS:
        raise ReviewAuthorityError(
            reviewer.role, action,
            f"reviewer '{reviewer.actor_id}' is read-only and may not {action}",
        )


# ── Criterion 8: critical final gate ─────────────────────────────────────────


@dataclass(frozen=True)
class CriticalReviewer:
    """One reviewer of the critical final gate (criterion 8).

    ``kind`` distinguishes reviewers (e.g. distinct models/perspectives) so the
    gate can require *diverse* reviewers, not two runs of the same reviewer.
    """

    reviewer_id: str
    kind: str


@dataclass(frozen=True)
class EvidenceAdjudication:
    """A targeted evidence-adjudication handoff for a material disagreement.

    Names only the disputed findings — the controller re-verifies *those* against
    their evidence, never re-votes the whole review (criterion 8).
    """

    subject_sha: str
    disputed_finding_ids: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_sha": self.subject_sha,
            "disputed_finding_ids": list(self.disputed_finding_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CriticalGateResult:
    """The verdict of the critical final gate (criterion 8).

    ``passed`` is true only when both diverse reviewers returned ``REVIEW_PASS``
    with no material disagreement. A material disagreement routes to
    :attr:`evidence_adjudication` — targeted, never majority voting.
    """

    passed: bool
    reviews: tuple[ReviewRecord, ...] = ()
    evidence_adjudication: Optional[EvidenceAdjudication] = None
    failed_reason: Optional[str] = None


def validate_critical_reviewers(reviewers: Sequence[CriticalReviewer]) -> None:
    """Refuse a critical gate that is not two *diverse* reviewers (criterion 8)."""
    if len(reviewers) != 2:
        raise CriticalGateError(
            f"critical gate requires exactly two reviewers, got {len(reviewers)}"
        )
    if len({r.reviewer_id for r in reviewers}) != 2:
        raise CriticalGateError("critical gate requires two distinct reviewers")
    if len({r.kind for r in reviewers}) != 2:
        raise CriticalGateError(
            "critical gate requires two diverse reviewers (distinct kinds)"
        )


def dispatch_critical_gate(
    subject_sha: str,
    reviewers: Sequence[CriticalReviewer],
    dispatcher: Any,
) -> Any:
    """Dispatch two diverse reviewers concurrently against one immutable subject.

    ``dispatcher`` is the injected seam (provider/harness-neutral) that receives
    *both* reviewers in a single call — a concurrent, not sequential, dispatch.
    The module validates diversity and the immutable full subject SHA first, so
    a non-diverse or non-full subject refuses before the dispatcher runs.
    """
    validate_critical_reviewers(reviewers)
    if not _is_full_sha(subject_sha):
        raise CriticalGateError(
            f"critical gate subject SHA {subject_sha!r} is not a full SHA"
        )
    return dispatcher(list(reviewers))


def _disputed_finding_ids(reviews: Sequence[ReviewRecord]) -> list[str]:
    """The finding ids the reviewers materially disagree on (criterion 8).

    Material disagreement is (a) differing verdicts — the failing reviewer's
    findings are disputed — or (b) the same criterion/code location raised at
    conflicting severities by the two reviewers.
    """
    verdicts = {r.verdict for r in reviews}
    if len(verdicts) != 1:
        return sorted(
            f.id for r in reviews if r.verdict is ReviewVerdict.REVIEW_FAIL
            for f in r.findings
        )
    by_key: dict[str, Finding] = {}
    disputed: list[str] = []
    for review in reviews:
        for finding in review.findings:
            key = finding.criterion or finding.code_location
            if key is None:
                continue
            existing = by_key.get(key)
            if existing is not None and existing.severity != finding.severity:
                disputed.extend([existing.id, finding.id])
            else:
                by_key.setdefault(key, finding)
    return sorted(set(disputed))


def evaluate_critical_gate(
    subject_sha: str,
    reviews: Sequence[ReviewRecord],
) -> CriticalGateResult:
    """Evaluate the critical final gate (criterion 8).

    Both reviews must be bound to the same immutable subject and produced by two
    distinct reviewers. The gate passes only when both return ``REVIEW_PASS``
    and there is no material disagreement; material disagreement routes to
    targeted evidence adjudication (never majority voting), and anything short
    of two passes fails.
    """
    if len(reviews) != 2:
        raise CriticalGateError(
            f"critical gate requires exactly two reviews, got {len(reviews)}"
        )
    for review in reviews:
        review.validate()
        if review.subject_sha != subject_sha:
            raise CriticalGateError(
                f"review subject {review.subject_sha!r} does not match gate "
                f"subject {subject_sha!r}"
            )
    if len({r.reviewer_id for r in reviews}) != 2:
        raise CriticalGateError("critical gate requires two distinct reviewers")

    disputed = _disputed_finding_ids(reviews)
    if disputed:
        return CriticalGateResult(
            passed=False,
            reviews=tuple(reviews),
            evidence_adjudication=EvidenceAdjudication(
                subject_sha=subject_sha,
                disputed_finding_ids=tuple(disputed),
                reason="material disagreement between reviewers; route to "
                       "targeted evidence adjudication",
            ),
        )

    both_pass = all(r.verdict is ReviewVerdict.REVIEW_PASS for r in reviews)
    if both_pass:
        return CriticalGateResult(passed=True, reviews=tuple(reviews))
    return CriticalGateResult(
        passed=False,
        reviews=tuple(reviews),
        failed_reason="both reviewers must return REVIEW_PASS",
    )


__all__ = [
    "PRODUCER_ROLE",
    "REVIEWER_ROLE",
    "CONTROLLER_ROLE",
    "REVIEWER_FORBIDDEN_ACTIONS",
    "ReviewPolicyError",
    "DispositionError",
    "AdjudicationError",
    "CorrectionHandoffError",
    "ReviewGateError",
    "ReviewAuthorityError",
    "CriticalGateError",
    "Severity",
    "DispositionDecision",
    "AdjudicationDecision",
    "ReviewVerdict",
    "Finding",
    "new_finding",
    "Disposition",
    "DispositionRegister",
    "Adjudication",
    "adjudicate",
    "ReviewRecord",
    "review_pass",
    "review_fail",
    "CandidateReviewState",
    "CorrectionHandoff",
    "build_correction_handoff",
    "correction_complete",
    "CarryForwardRule",
    "SubjectChangeResult",
    "invalidate_on_subject_change",
    "ActorBinding",
    "validate_producer_reviewer_separation",
    "assert_reviewer_authority",
    "CriticalReviewer",
    "EvidenceAdjudication",
    "CriticalGateResult",
    "validate_critical_reviewers",
    "dispatch_critical_gate",
    "evaluate_critical_gate",
]
