"""Typed operational handoffs and controller checkpoints (SW1311-HANDOFF-001).

This module owns the *transfer* layer of the dispatch trace — the contract that
turns prose-only "hand off this lane to so-and-so" notes into immutable, typed
records a cold controller can consume without a transcript. It is deliberately
decision-only and provider/harness-neutral, like its siblings
:mod:`skillweave.trace.contracts` and :mod:`skillweave.trace.review`: it names
no model, gateway or harness, performs no product edit and imports no optional
``skillweave.runtime`` subpackage (GLE-020).

It builds on, and never duplicates, the existing contracts:

* a handoff's ``source_receipt_id`` references a
  :class:`~skillweave.trace.contracts.JobRecord` already appended to the
  append-only receipt log (``contracts``), and its ``expected_receipt_type``
  names the :class:`~skillweave.trace.contracts.RoundKind` the destination must
  produce;
* the review *verdict* and *accepted finding ids* a controller checkpoint
  preserves come from :mod:`skillweave.trace.review`, never re-derived here;
* the destination ``base``/``subject`` SHAs and ``dependencies`` are the same
  topology facts :mod:`skillweave.dispatch.topology` enforces; a handoff does
  not re-serialize lanes, it only preserves those facts across a cold session.

Six concerns live here, one per acceptance criterion:

1. **Typed variants** (:class:`HandoffKind`) — ``ops``, ``review``,
   ``correction``, ``integration`` and ``controller_resume`` are distinct,
   immutable records with a stable content-addressed ``id`` and a required
   ``source_receipt_id`` (criterion 1).
2. **Complete destination contract** (:class:`Handoff`) — every handoff binds
   the destination role, exact base/subject SHAs, dependencies, allowed and
   forbidden scope, required inputs, criteria, commands, a correction budget and
   an expected receipt type (criterion 2). A variant that omits any of these
   fails closed.
3. **Fail-closed launch** (:func:`can_start`, :func:`assert_replace_role_can_start`) —
   a destination cannot start when the source receipt/artifact is missing, a
   base or subject differs, a digest is stale, or the requested role lacks
   authority (criterion 3).
4. **Controller checkpoint** (:class:`ControllerCheckpoint`) — preserves every
   frozen candidate SHA, base, the latest verdict, accepted finding ids,
   correction budgets, the current batch index and whether an external job is
   active (criterion 4).
5. **Cold reconstruction** (:func:`reconstruct_next_action`) — a cold controller
   derives the next legal action from the checkpoint and typed records alone,
   with no transcript; the result *explicitly* disclaims autonomous crash
   recovery and persistent observer resume (criterion 5).
6. **Projection-only logs** (:func:`handoff_log`, :func:`checkpoint_log`) — the
   human-readable form is a pure function of immutable state; editing it cannot
   mutate dispatch state (criterion 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from skillweave.trace.contracts import content_id
from skillweave.trace.review import ReviewVerdict


# ── Role and receipt vocabulary (aligned with contracts.review) ─────────────


#: The destination roles a handoff may bind. ``ops`` produces an ops handoff,
#: ``reviewer`` a review handoff, ``producer`` a correction handoff,
#: ``integrator`` an integration handoff and ``controller`` a controller-resume.
OPS_ROLE = "ops"
REVIEWER_ROLE = "reviewer"
PRODUCER_ROLE = "producer"
INTEGRATOR_ROLE = "integrator"
CONTROLLER_ROLE = "controller"

#: The role a cold controller resumes as; distinct from the roles above since a
#: resume is not a lane handoff but a controller re-entry.
RESUME_ROLE = "controller"

#: Receipt types a handoff may expect the destination to produce. These reuse
#: the append-only round kinds plus the ops/controller-resume terminal kinds.
RECEIPT_DISPATCH = "dispatch"
RECEIPT_CORRECTION = "correction"
RECEIPT_REVIEW = "review"
RECEIPT_INTEGRATION = "integration"
RECEIPT_OPS = "ops"
RECEIPT_CONTROLLER_RESUME = "controller_resume"

#: Destination roles supported by :func:`can_start`; a role not in this set lacks
#: launch authority fail-closed (criterion 3).
KNOWN_DESTINATION_ROLES = frozenset({
    OPS_ROLE, REVIEWER_ROLE, PRODUCER_ROLE, INTEGRATOR_ROLE, CONTROLLER_ROLE,
})

#: Required receipt types per destination role. A destination that would produce
#: a receipt kind outside its role's set is refused (separation of duties).
ROLE_RECEIPT_TYPES: dict[str, frozenset[str]] = {
    OPS_ROLE: frozenset({RECEIPT_OPS, RECEIPT_DISPATCH}),
    REVIEWER_ROLE: frozenset({RECEIPT_REVIEW}),
    PRODUCER_ROLE: frozenset({RECEIPT_CORRECTION, RECEIPT_DISPATCH}),
    INTEGRATOR_ROLE: frozenset({RECEIPT_INTEGRATION}),
    CONTROLLER_ROLE: frozenset({RECEIPT_CONTROLLER_RESUME}),
}


def _is_full_sha(value: Any) -> bool:
    """True for a 40-hex-char full SHA (local copy, GLE-020)."""
    if not isinstance(value, str) or len(value) != 40:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


# ── Exception hierarchy ──────────────────────────────────────────────────────


class HandoffError(Exception):
    """A handoff/checkpoint contract violation (raised fail-closed)."""


class HandoffBuildError(HandoffError):
    """A handoff omitted a required field of its destination contract."""


class HandoffStartError(HandoffError):
    """A destination's launch was blocked (criterion 3)."""


class CheckpointError(HandoffError):
    """A controller checkpoint was malformed or inconsistent."""


class ReconstructionError(HandoffError):
    """A cold controller could not derive a legal next action."""


# ── Criterion 1: typed variants ──────────────────────────────────────────────


class HandoffKind(str, Enum):
    """The five distinct, immutable handoff variants (criterion 1)."""

    OPS = "ops"
    REVIEW = "review"
    CORRECTION = "correction"
    INTEGRATION = "integration"
    CONTROLLER_RESUME = "controller_resume"


@dataclass(frozen=True)
class Scope:
    """The allowed/forbidden scope a handoff binds (criterion 2).

    ``allowed_paths`` are the paths the destination may mutate; ``forbidden_paths``
    are the paths it must not touch. Both are exact, not defaults: a handoff
    without an explicit allowed scope fails closed.
    """

    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_paths": list(self.allowed_paths),
            "forbidden_paths": list(self.forbidden_paths),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Scope":
        return cls(
            allowed_paths=tuple(data.get("allowed_paths") or ()),
            forbidden_paths=tuple(data.get("forbidden_paths") or ()),
        )


@dataclass(frozen=True)
class Handoff:
    """One immutable typed transfer (criteria 1, 2).

    Every handoff binds the full destination contract: destination role, exact
    base and subject SHAs, dependencies, allowed/forbidden scope, required
    inputs, criteria, commands, a correction budget and the expected receipt
    type. ``id`` is a stable content-addressed id; ``source_receipt_id`` names
    the append-only receipt this handoff was issued from. The record is frozen:
    once produced it cannot be rewritten.
    """

    id: str
    kind: HandoffKind
    source_receipt_id: str
    destination_role: str
    base_sha: str
    subject_sha: str
    dependencies: tuple[str, ...]
    scope: Scope
    required_inputs: tuple[str, ...]
    criteria: tuple[str, ...]
    commands: tuple[str, ...]
    correction_budget: int
    expected_receipt_type: str
    digest: str

    def validate(self) -> None:
        """Raise :class:`HandoffBuildError` on any missing/inconsistent field."""
        if not self.id:
            raise HandoffBuildError("handoff id must be non-empty")
        if not self.source_receipt_id:
            raise HandoffBuildError("handoff must bind a source receipt id")
        if self.destination_role not in KNOWN_DESTINATION_ROLES:
            raise HandoffBuildError(
                f"destination role {self.destination_role!r} is not a known role"
            )
        if not _is_full_sha(self.base_sha):
            raise HandoffBuildError(
                f"base SHA {self.base_sha!r} is not a full SHA"
            )
        if not _is_full_sha(self.subject_sha):
            raise HandoffBuildError(
                f"subject SHA {self.subject_sha!r} is not a full SHA"
            )
        if not self.scope.allowed_paths:
            raise HandoffBuildError(
                "handoff must declare a non-empty allowed scope"
            )
        if not self.required_inputs:
            raise HandoffBuildError("handoff must declare required inputs")
        if not self.criteria:
            raise HandoffBuildError("handoff must declare criteria")
        if not self.commands:
            raise HandoffBuildError("handoff must declare commands")
        if not isinstance(self.correction_budget, int) or self.correction_budget < 0:
            raise HandoffBuildError(
                "correction budget must be a non-negative integer"
            )
        role_types = ROLE_RECEIPT_TYPES.get(self.destination_role, frozenset())
        if self.expected_receipt_type not in role_types:
            raise HandoffBuildError(
                f"expected receipt type {self.expected_receipt_type!r} is not "
                f"available to role {self.destination_role!r}"
            )
        if not self.digest:
            raise HandoffBuildError("handoff must carry a digest")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "source_receipt_id": self.source_receipt_id,
            "destination_role": self.destination_role,
            "base_sha": self.base_sha,
            "subject_sha": self.subject_sha,
            "dependencies": list(self.dependencies),
            "scope": self.scope.to_dict(),
            "required_inputs": list(self.required_inputs),
            "criteria": list(self.criteria),
            "commands": list(self.commands),
            "correction_budget": self.correction_budget,
            "expected_receipt_type": self.expected_receipt_type,
            "digest": self.digest,
        }


def _digest_of(*, kind: HandoffKind, base_sha: str, subject_sha: str,
               destination_role: str, expected_receipt_type: str,
               correction_budget: int) -> str:
    """The content digest a handoff's binding fields hash to."""
    return content_id(
        "handoff", kind.value, destination_role, base_sha, subject_sha,
        expected_receipt_type, correction_budget,
    )


def build_handoff(
    *,
    kind: HandoffKind,
    source_receipt_id: str,
    destination_role: str,
    base_sha: str,
    subject_sha: str,
    allowed_paths: Sequence[str],
    forbidden_paths: Sequence[str] = (),
    dependencies: Sequence[str] = (),
    required_inputs: Sequence[str],
    criteria: Sequence[str],
    commands: Sequence[str],
    correction_budget: int = 0,
    expected_receipt_type: str,
) -> Handoff:
    """Build and validate a typed handoff, deriving a stable content id.

    The ``id`` is content-addressed over the kind, role, SHAs, expected receipt
    type and budget, so an identical transfer derives an identical id. The
    ``digest`` covers the same binding fields and is checked at start time.
    """
    digest = _digest_of(
        kind=kind,
        base_sha=base_sha,
        subject_sha=subject_sha,
        destination_role=destination_role,
        expected_receipt_type=expected_receipt_type,
        correction_budget=correction_budget,
    )
    handoff = Handoff(
        id=content_id(
            kind.value, destination_role, base_sha, subject_sha,
            expected_receipt_type, correction_budget,
        ),
        kind=kind,
        source_receipt_id=source_receipt_id,
        destination_role=destination_role,
        base_sha=base_sha,
        subject_sha=subject_sha,
        dependencies=tuple(dependencies),
        scope=Scope(
            allowed_paths=tuple(allowed_paths),
            forbidden_paths=tuple(forbidden_paths),
        ),
        required_inputs=tuple(required_inputs),
        criteria=tuple(criteria),
        commands=tuple(commands),
        correction_budget=correction_budget,
        expected_receipt_type=expected_receipt_type,
        digest=digest,
    )
    handoff.validate()
    return handoff


def build_ops_handoff(
    *, source_receipt_id: str, base_sha: str, subject_sha: str,
    allowed_paths: Sequence[str], required_inputs: Sequence[str],
    criteria: Sequence[str], commands: Sequence[str],
    forbidden_paths: Sequence[str] = (),
    dependencies: Sequence[str] = (),
) -> Handoff:
    """Build an ``ops`` handoff."""
    return build_handoff(
        kind=HandoffKind.OPS,
        source_receipt_id=source_receipt_id,
        destination_role=OPS_ROLE,
        base_sha=base_sha,
        subject_sha=subject_sha,
        allowed_paths=allowed_paths,
        forbidden_paths=forbidden_paths,
        dependencies=dependencies,
        required_inputs=required_inputs,
        criteria=criteria,
        commands=commands,
        correction_budget=0,
        expected_receipt_type=RECEIPT_OPS,
    )


def build_review_handoff(
    *, source_receipt_id: str, base_sha: str, subject_sha: str,
    allowed_paths: Sequence[str], required_inputs: Sequence[str],
    criteria: Sequence[str], commands: Sequence[str],
    forbidden_paths: Sequence[str] = (),
    dependencies: Sequence[str] = (),
) -> Handoff:
    """Build a ``review`` handoff."""
    return build_handoff(
        kind=HandoffKind.REVIEW,
        source_receipt_id=source_receipt_id,
        destination_role=REVIEWER_ROLE,
        base_sha=base_sha,
        subject_sha=subject_sha,
        allowed_paths=allowed_paths,
        forbidden_paths=forbidden_paths,
        dependencies=dependencies,
        required_inputs=required_inputs,
        criteria=criteria,
        commands=commands,
        correction_budget=0,
        expected_receipt_type=RECEIPT_REVIEW,
    )


def build_correction_handoff(
    *, source_receipt_id: str, base_sha: str, subject_sha: str,
    allowed_paths: Sequence[str], required_inputs: Sequence[str],
    criteria: Sequence[str], commands: Sequence[str],
    correction_budget: int,
    forbidden_paths: Sequence[str] = (),
    dependencies: Sequence[str] = (),
) -> Handoff:
    """Build a ``correction`` handoff with a bounded correction budget."""
    return build_handoff(
        kind=HandoffKind.CORRECTION,
        source_receipt_id=source_receipt_id,
        destination_role=PRODUCER_ROLE,
        base_sha=base_sha,
        subject_sha=subject_sha,
        allowed_paths=allowed_paths,
        forbidden_paths=forbidden_paths,
        dependencies=dependencies,
        required_inputs=required_inputs,
        criteria=criteria,
        commands=commands,
        correction_budget=correction_budget,
        expected_receipt_type=RECEIPT_CORRECTION,
    )


def build_integration_handoff(
    *, source_receipt_id: str, base_sha: str, subject_sha: str,
    allowed_paths: Sequence[str], required_inputs: Sequence[str],
    criteria: Sequence[str], commands: Sequence[str],
    forbidden_paths: Sequence[str] = (),
    dependencies: Sequence[str] = (),
) -> Handoff:
    """Build an ``integration`` handoff."""
    return build_handoff(
        kind=HandoffKind.INTEGRATION,
        source_receipt_id=source_receipt_id,
        destination_role=INTEGRATOR_ROLE,
        base_sha=base_sha,
        subject_sha=subject_sha,
        allowed_paths=allowed_paths,
        forbidden_paths=forbidden_paths,
        dependencies=dependencies,
        required_inputs=required_inputs,
        criteria=criteria,
        commands=commands,
        correction_budget=0,
        expected_receipt_type=RECEIPT_INTEGRATION,
    )


def build_controller_resume_handoff(
    *, source_receipt_id: str, base_sha: str, subject_sha: str,
    allowed_paths: Sequence[str], required_inputs: Sequence[str],
    criteria: Sequence[str], commands: Sequence[str],
    forbidden_paths: Sequence[str] = (),
    dependencies: Sequence[str] = (),
) -> Handoff:
    """Build a ``controller_resume`` handoff."""
    return build_handoff(
        kind=HandoffKind.CONTROLLER_RESUME,
        source_receipt_id=source_receipt_id,
        destination_role=CONTROLLER_ROLE,
        base_sha=base_sha,
        subject_sha=subject_sha,
        allowed_paths=allowed_paths,
        forbidden_paths=forbidden_paths,
        dependencies=dependencies,
        required_inputs=required_inputs,
        criteria=criteria,
        commands=commands,
        correction_budget=0,
        expected_receipt_type=RECEIPT_CONTROLLER_RESUME,
    )


# ── Criterion 3: fail-closed launch ──────────────────────────────────────────


def _receipt_missing(receipts: Mapping[str, Any], receipt_id: str) -> bool:
    return receipt_id not in receipts


def can_start(
    handoff: Handoff,
    *,
    receipts: Mapping[str, Any],
    current_base_sha: Optional[str] = None,
    current_subject_sha: Optional[str] = None,
    role: Optional[str] = None,
) -> bool:
    """Return ``True`` only when the destination may start (criterion 3).

    A destination is blocked — ``False`` — when any of:

    * the source receipt/artifact is missing from ``receipts``;
    * ``current_base_sha`` differs from the handoff's exact base;
    * ``current_subject_sha`` differs from the handoff's exact subject;
    * the handoff's binding digest is stale (its fields no longer hash to the
      recorded digest);
    * ``role`` (the actor attempting the start) lacks authority for the
      destination role.

    The first blocking reason is available via :func:`start_blocking_reason`.
    """
    return start_blocking_reason(
        handoff,
        receipts=receipts,
        current_base_sha=current_base_sha,
        current_subject_sha=current_subject_sha,
        role=role,
    ) is None


def start_blocking_reason(
    handoff: Handoff,
    *,
    receipts: Mapping[str, Any],
    current_base_sha: Optional[str] = None,
    current_subject_sha: Optional[str] = None,
    role: Optional[str] = None,
) -> Optional[str]:
    """Return the first launch-blocking reason, or ``None`` when unblocked."""
    handoff.validate()
    if _receipt_missing(receipts, handoff.source_receipt_id):
        return f"source receipt '{handoff.source_receipt_id}' is missing"
    expected = _digest_of(
        kind=handoff.kind,
        base_sha=handoff.base_sha,
        subject_sha=handoff.subject_sha,
        destination_role=handoff.destination_role,
        expected_receipt_type=handoff.expected_receipt_type,
        correction_budget=handoff.correction_budget,
    )
    if expected != handoff.digest:
        return "handoff digest is stale"
    if current_base_sha is not None and current_base_sha != handoff.base_sha:
        return (
            f"base differs: expected {handoff.base_sha!r}, got {current_base_sha!r}"
        )
    if current_subject_sha is not None and current_subject_sha != handoff.subject_sha:
        return (
            f"subject differs: expected {handoff.subject_sha!r}, "
            f"got {current_subject_sha!r}"
        )
    if role is not None and role != handoff.destination_role:
        return (
            f"role {role!r} lacks authority to start a "
            f"{handoff.destination_role!r} handoff"
        )
    return None


def assert_can_start(
    handoff: Handoff,
    *,
    receipts: Mapping[str, Any],
    current_base_sha: Optional[str] = None,
    current_subject_sha: Optional[str] = None,
    role: Optional[str] = None,
) -> None:
    """Raise :class:`HandoffStartError` unless the destination may start."""
    reason = start_blocking_reason(
        handoff,
        receipts=receipts,
        current_base_sha=current_base_sha,
        current_subject_sha=current_subject_sha,
        role=role,
    )
    if reason is not None:
        raise HandoffStartError(reason)


# ── Criterion 4: controller checkpoint ───────────────────────────────────────


@dataclass(frozen=True)
class FrozenCandidate:
    """One frozen candidate preserved in the checkpoint (criterion 4)."""

    candidate_sha: str
    base_sha: str

    def validate(self) -> None:
        if not _is_full_sha(self.candidate_sha):
            raise CheckpointError(
                f"frozen candidate SHA {self.candidate_sha!r} is not a full SHA"
            )
        if not _is_full_sha(self.base_sha):
            raise CheckpointError(
                f"frozen base SHA {self.base_sha!r} is not a full SHA"
            )

    def to_dict(self) -> dict[str, Any]:
        return {"candidate_sha": self.candidate_sha, "base_sha": self.base_sha}


@dataclass(frozen=True)
class ControllerCheckpoint:
    """A complete frozen controller checkpoint (criterion 4).

    Preserves the frozen candidate SHAs and their bases, the latest verdict,
    the accepted finding ids, the correction budgets per lane, the current batch
    index and whether an external job is active. A cold controller reconstructs
    its next action from this alone — no transcript.
    """

    checkpoint_id: str
    frozen_candidates: tuple[FrozenCandidate, ...]
    latest_verdict: Optional[ReviewVerdict]
    accepted_finding_ids: tuple[str, ...]
    correction_budgets: Mapping[str, int]
    current_batch: int
    active_job: bool

    def validate(self) -> None:
        if not self.checkpoint_id:
            raise CheckpointError("checkpoint id must be non-empty")
        for candidate in self.frozen_candidates:
            candidate.validate()
        for lane, budget in self.correction_budgets.items():
            if not isinstance(budget, int) or budget < 0:
                raise CheckpointError(
                    f"correction budget for lane {lane!r} must be a non-negative "
                    f"integer, got {budget!r}"
                )
        if not isinstance(self.current_batch, int) or self.current_batch < 0:
            raise CheckpointError(
                f"current batch must be a non-negative integer, got "
                f"{self.current_batch!r}"
            )
        if not isinstance(self.active_job, bool):
            raise CheckpointError("active job must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "frozen_candidates": [c.to_dict() for c in self.frozen_candidates],
            "latest_verdict": (
                self.latest_verdict.value if self.latest_verdict is not None else None
            ),
            "accepted_finding_ids": list(self.accepted_finding_ids),
            "correction_budgets": dict(self.correction_budgets),
            "current_batch": self.current_batch,
            "active_job": self.active_job,
        }


def build_checkpoint(
    *,
    frozen_candidates: Sequence[FrozenCandidate],
    latest_verdict: Optional[ReviewVerdict],
    accepted_finding_ids: Sequence[str],
    correction_budgets: Mapping[str, int],
    current_batch: int,
    active_job: bool,
    checkpoint_id: Optional[str] = None,
) -> ControllerCheckpoint:
    """Build and validate a controller checkpoint, deriving a stable id.

    The id is content-addressed over the frozen candidates, verdict, accepted
    finding ids and current batch, so an identical checkpoint derives an
    identical id (idempotent re-entry).
    """
    if checkpoint_id is None:
        checkpoint_id = content_id(
            "controller_checkpoint",
            [c.to_dict() for c in frozen_candidates],
            latest_verdict.value if latest_verdict is not None else None,
            sorted(accepted_finding_ids),
            current_batch,
        )
    checkpoint = ControllerCheckpoint(
        checkpoint_id=checkpoint_id,
        frozen_candidates=tuple(frozen_candidates),
        latest_verdict=latest_verdict,
        accepted_finding_ids=tuple(accepted_finding_ids),
        correction_budgets=dict(correction_budgets),
        current_batch=current_batch,
        active_job=active_job,
    )
    checkpoint.validate()
    return checkpoint


# ── Criterion 5: cold reconstruction ─────────────────────────────────────────


@dataclass(frozen=True)
class NextAction:
    """The next legal action a cold controller derived (criterion 5).

    ``action`` is one of ``integrate``, ``correct``, ``dispatch_next_batch``,
    ``await_job``, ``review`` or ``complete``. ``disclaims_autonomous_recovery``
    and ``disclaims_persistent_observer_resume`` are always true: the result
    never claims the controller can auto-recover from a crash or that an
    observer's persistent resume state can be trusted blindly — those are human
    decisions, outside the derived action.
    """

    action: str
    next_batch: int
    rationale: str
    disclaims_autonomous_recovery: bool = True
    disclaims_persistent_observer_resume: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "next_batch": self.next_batch,
            "rationale": self.rationale,
            "disclaims_autonomous_recovery": self.disclaims_autonomous_recovery,
            "disclaims_persistent_observer_resume": (
                self.disclaims_persistent_observer_resume
            ),
        }


def reconstruct_next_action(
    checkpoint: ControllerCheckpoint,
    handoffs: Sequence[Handoff],
) -> NextAction:
    """Derive the next legal action from a checkpoint and typed records alone.

    The controller has no transcript, only the checkpoint and handoffs. The
    derivation is fail-closed and deterministic (criterion 5):

    * if an external job is active, the controller must ``await_job``;
    * if the latest verdict is ``REVIEW_FAIL``, the next action is ``correct``
      (a correction handoff exists and carries the accepted finding ids);
    * if accepted findings exist but there is no passing verdict, ``correct``;
    * if the latest verdict passed, with no more batches, ``integrate`` then
      ``complete``;
    * otherwise ``dispatch_next_batch`` (a review follows when needed).

    The returned :class:`NextAction` always disclaims autonomous crash recovery
    and persistent observer resume — the controller re-derives state, it does
    not trust a stale observer's self-resume.
    """
    checkpoint.validate()
    for handoff in handoffs:
        handoff.validate()

    if checkpoint.active_job:
        return NextAction(
            action="await_job",
            next_batch=checkpoint.current_batch,
            rationale="an external job is active; the controller must await its "
                      "receipt before proceeding",
        )

    pending = bool(checkpoint.accepted_finding_ids)
    if checkpoint.latest_verdict is ReviewVerdict.REVIEW_FAIL or pending:
        return NextAction(
            action="correct",
            next_batch=checkpoint.current_batch,
            rationale="a fail verdict or accepted findings remain; the next "
                      "legal action is a bounded correction",
        )

    if checkpoint.latest_verdict is ReviewVerdict.REVIEW_PASS:
        if checkpoint.current_batch == 0:
            return NextAction(
                action="complete",
                next_batch=checkpoint.current_batch,
                rationale="the only batch has passed review; integration and "
                          "completion are the remaining actions",
            )
        return NextAction(
            action="integrate",
            next_batch=checkpoint.current_batch,
            rationale="the current batch passed review; integrate then advance "
                      "to completion",
        )

    return NextAction(
        action="dispatch_next_batch",
        next_batch=checkpoint.current_batch + 1,
        rationale="no verdict yet and no active job; dispatch the next legal batch",
    )


def requires_review(checkpoint: ControllerCheckpoint) -> bool:
    """True when the next legal action mandates a fresh (cold) review.

    A correction or an advance to the next batch must be followed by a fresh
    review; a pass with no more batches does not (it integrates/completes).
    """
    checkpoint.validate()
    if checkpoint.latest_verdict is ReviewVerdict.REVIEW_FAIL:
        return True
    return bool(checkpoint.accepted_finding_ids)


# ── Criterion 6: projection-only logs ────────────────────────────────────────


def handoff_log(handoff: Handoff) -> str:
    """Render a handoff as a human-readable projection (criterion 6).

    This is a pure projection of immutable state: editing the returned string
    cannot mutate the :class:`Handoff` it was derived from, and a re-render from
    the same handoff always produces the same string.
    """
    lines = [
        f"handoff {handoff.id} [{handoff.kind.value}]",
        f"  source_receipt: {handoff.source_receipt_id}",
        f"  destination_role: {handoff.destination_role}",
        f"  base: {handoff.base_sha}",
        f"  subject: {handoff.subject_sha}",
        f"  dependencies: {', '.join(handoff.dependencies) or '(none)'}",
        f"  allowed_scope: {', '.join(handoff.scope.allowed_paths)}",
        f"  forbidden_scope: {', '.join(handoff.scope.forbidden_paths) or '(none)'}",
        f"  required_inputs: {', '.join(handoff.required_inputs)}",
        f"  criteria: {', '.join(handoff.criteria)}",
        f"  commands: {', '.join(handoff.commands)}",
        f"  correction_budget: {handoff.correction_budget}",
        f"  expected_receipt_type: {handoff.expected_receipt_type}",
    ]
    return "\n".join(lines)


def checkpoint_log(checkpoint: ControllerCheckpoint) -> str:
    """Render a checkpoint as a human-readable projection (criterion 6)."""
    frozen = ", ".join(
        f"{c.candidate_sha}@{c.base_sha}" for c in checkpoint.frozen_candidates
    ) or "(none)"
    verdict = (
        checkpoint.latest_verdict.value
        if checkpoint.latest_verdict is not None else "(none)"
    )
    budgets = ", ".join(
        f"{lane}:{budget}"
        for lane, budget in sorted(checkpoint.correction_budgets.items())
    ) or "(none)"
    lines = [
        f"checkpoint {checkpoint.checkpoint_id}",
        f"  frozen_candidates: {frozen}",
        f"  latest_verdict: {verdict}",
        f"  accepted_finding_ids: {', '.join(checkpoint.accepted_finding_ids) or '(none)'}",
        f"  correction_budgets: {budgets}",
        f"  current_batch: {checkpoint.current_batch}",
        f"  active_job: {checkpoint.active_job}",
    ]
    return "\n".join(lines)


__all__ = [
    "OPS_ROLE",
    "REVIEWER_ROLE",
    "PRODUCER_ROLE",
    "INTEGRATOR_ROLE",
    "CONTROLLER_ROLE",
    "RESUME_ROLE",
    "RECEIPT_DISPATCH",
    "RECEIPT_CORRECTION",
    "RECEIPT_REVIEW",
    "RECEIPT_INTEGRATION",
    "RECEIPT_OPS",
    "RECEIPT_CONTROLLER_RESUME",
    "KNOWN_DESTINATION_ROLES",
    "ROLE_RECEIPT_TYPES",
    "HandoffError",
    "HandoffBuildError",
    "HandoffStartError",
    "CheckpointError",
    "ReconstructionError",
    "HandoffKind",
    "Scope",
    "Handoff",
    "build_handoff",
    "build_ops_handoff",
    "build_review_handoff",
    "build_correction_handoff",
    "build_integration_handoff",
    "build_controller_resume_handoff",
    "can_start",
    "start_blocking_reason",
    "assert_can_start",
    "FrozenCandidate",
    "ControllerCheckpoint",
    "build_checkpoint",
    "NextAction",
    "reconstruct_next_action",
    "requires_review",
    "handoff_log",
    "checkpoint_log",
]
