"""SkillWeave promptchain execution surface.

``execute`` is the executor for ``sequences/*.yaml`` orchestration files: it
loads a sequence, refuses one that does not declare ``session_boundary``, and
turns lanes marked ``parallel_lanes`` into subagent dispatches while leaving
``serialized_lanes`` inline.

This package also owns the **contract-derived promptchain** (SW-160-VERT-004):
one generator turns a :class:`ContractInput` — the role, scope, target repo,
full base SHA, acceptance criteria and settled decisions a brief settles — into
a :class:`ContractDerivedChain` of :class:`ContractArtifact` records.

* Every generated artifact carries the contract's role, scope, target repo,
  full base SHA, criteria and settled decisions (criterion 1).
* An artifact's digest is content-addressed over those contract fields *and*
  the typed handoff's digest *and* the review subject, so the handoff and the
  review subject are bound to the contract input rather than reconstructed
  later (criterion 2).
* The generator branches on the contract's *data* (its category, scope,
  criteria, decisions), never on a profile name, so two verticals
  (``software-delivery.v2`` build and ``research-synthesis.v1`` research) run
  the same code path and diverge only because their data diverges (criterion 3).
* :func:`dispatch_contract_chain` re-derives those digests before the first
  worker starts; a brief that was tampered with after generation is refused
  with :class:`TamperedBriefError` and starts zero workers (criterion 4).

Nothing here imports an optional ``skillweave.runtime`` subpackage (GLE-020):
it builds on the *contracts* layer only (``skillweave.trace.contracts`` and
``skillweave.trace.handoff``), which is core.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, Optional, Sequence

from skillweave.trace.contracts import content_id
from skillweave.trace.handoff import (
    OPS_ROLE,
    REVIEWER_ROLE,
    Handoff,
    build_ops_handoff,
    build_review_handoff,
    start_blocking_reason,
)

from .execute import (
    SequenceDeclaration,
    Lane,
    DispatchPlan,
    DispatchEntry,
    SUBAGENT,
    INLINE,
    MissingSessionBoundaryError,
    load_sequence,
    build_dispatch_plan,
    execute_sequence,
    BatchCommand,
    SessionState,
    SessionRun,
    Session,
    SessionConsumedError,
    SessionExecutionError,
    load_state_file,
)


# ── Exception hierarchy ──────────────────────────────────────────────────────


class ContractPromptChainError(Exception):
    """A contract-derived promptchain violation (raised fail-closed)."""


class ContractInputError(ContractPromptChainError):
    """The contract input is incomplete or inconsistent with its contract."""


class TamperedBriefError(ContractPromptChainError):
    """The brief no longer matches the generated chain.

    Raised by :func:`dispatch_contract_chain` *before* the first worker starts:
    a brief that was edited after its chain was generated must be regenerated,
    never dispatched.
    """


def _is_full_sha(value: Any) -> bool:
    """True for a 40-hex-char full SHA (local copy, GLE-020)."""
    if not isinstance(value, str) or len(value) != 40:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


# ── Criterion 1: the contract input ──────────────────────────────────────────


@dataclass(frozen=True)
class ContractInput:
    """The settled contract a promptchain is derived from.

    Every field is an input the brief settles *before* any prompt is generated:
    the producing ``role``, the mutable ``scope``, the ``target_repo``, the full
    ``base_sha``, the acceptance ``criteria`` and the decisions the chain must
    carry forward. ``category`` names the lifecycle category (build, research,
    ...); ``reviewer_role`` names the separate, read-only reviewing role.

    The record is frozen: once settled, an edit produces a *different* contract
    (a different :meth:`digest`), which is exactly what the pre-start gate in
    :func:`dispatch_contract_chain` detects.
    """

    role: str
    scope: tuple[str, ...]
    target_repo: str
    base_sha: str
    criteria: tuple[str, ...]
    settled_decisions: tuple[str, ...] = ()
    category: str = ""
    reviewer_role: str = REVIEWER_ROLE

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", tuple(self.scope))
        object.__setattr__(self, "criteria", tuple(self.criteria))
        object.__setattr__(self, "settled_decisions", tuple(self.settled_decisions))

    def digest(self) -> str:
        """The content-addressed identity of the settled contract.

        A single settled decision changing yields a different digest, so the
        digest is the tamper baseline the generated chain is bound to.
        """
        return content_id(
            "contract-input",
            self.role,
            list(self.scope),
            self.target_repo,
            self.base_sha,
            list(self.criteria),
            list(self.settled_decisions),
            self.category,
            self.reviewer_role,
        )

    def validate(self) -> None:
        """Raise :class:`ContractInputError` on any missing/inconsistent field."""
        if self.role != OPS_ROLE:
            raise ContractInputError(
                f"contract role {self.role!r} must be the producing role "
                f"{OPS_ROLE!r}"
            )
        if self.reviewer_role != REVIEWER_ROLE:
            raise ContractInputError(
                f"contract reviewer role {self.reviewer_role!r} must be the "
                f"reviewing role {REVIEWER_ROLE!r}"
            )
        if not str(self.target_repo).strip():
            raise ContractInputError("contract must name a target repo")
        if not _is_full_sha(self.base_sha):
            raise ContractInputError(
                f"contract base SHA {self.base_sha!r} is not a full SHA"
            )
        if not self.scope:
            raise ContractInputError("contract must declare a non-empty scope")
        if not self.criteria:
            raise ContractInputError("contract must declare acceptance criteria")
        for decision in self.settled_decisions:
            if not str(decision).strip():
                raise ContractInputError("settled decisions must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "scope": list(self.scope),
            "target_repo": self.target_repo,
            "base_sha": self.base_sha,
            "criteria": list(self.criteria),
            "settled_decisions": list(self.settled_decisions),
            "category": self.category,
            "reviewer_role": self.reviewer_role,
        }


# ── Criterion 1/2: generated artifacts ───────────────────────────────────────


def _artifact_digest(
    *,
    contract_digest: str,
    role: str,
    scope: Sequence[str],
    target_repo: str,
    base_sha: str,
    criteria: Sequence[str],
    settled_decisions: Sequence[str],
    handoff_digest: str,
    review_subject_sha: str,
) -> str:
    """Content-address an artifact over its contract fields, handoff and subject.

    The digest is a *single* binding: the contract identity, every carried
    contract field, the typed handoff's own digest and the review subject all
    feed it, so an artifact cannot be re-issued against a different contract,
    handoff or subject without changing this digest (criterion 2).
    """
    return content_id(
        "contract-artifact",
        contract_digest,
        role,
        list(scope),
        target_repo,
        base_sha,
        list(criteria),
        list(settled_decisions),
        handoff_digest,
        review_subject_sha,
    )


@dataclass(frozen=True)
class ContractArtifact:
    """One generated artifact carrying its contract and its binding digest.

    The artifact carries the contract's role, scope, target repo, full base SHA,
    criteria and settled decisions (criterion 1) plus the typed :class:`Handoff`
    the destination consumes and the review subject SHA its review will bind to.
    ``digest`` binds all of those back to the contract input (criterion 2).
    """

    id: str
    contract_digest: str
    role: str
    scope: tuple[str, ...]
    target_repo: str
    base_sha: str
    criteria: tuple[str, ...]
    settled_decisions: tuple[str, ...]
    category: str
    handoff: Handoff
    review_subject_sha: str
    digest: str

    def recompute_digest(self) -> str:
        """Re-derive the artifact digest from the fields it carries."""
        return _artifact_digest(
            contract_digest=self.contract_digest,
            role=self.role,
            scope=self.scope,
            target_repo=self.target_repo,
            base_sha=self.base_sha,
            criteria=self.criteria,
            settled_decisions=self.settled_decisions,
            handoff_digest=self.handoff.digest,
            review_subject_sha=self.review_subject_sha,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "contract_digest": self.contract_digest,
            "role": self.role,
            "scope": list(self.scope),
            "target_repo": self.target_repo,
            "base_sha": self.base_sha,
            "criteria": list(self.criteria),
            "settled_decisions": list(self.settled_decisions),
            "category": self.category,
            "handoff": self.handoff.to_dict(),
            "review_subject_sha": self.review_subject_sha,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class ContractDerivedChain:
    """The ordered artifacts one contract input derives into.

    ``contract_digest`` is the identity of the contract that produced the chain;
    ``artifacts`` is the ordered producer → reviewer chain; :meth:`digest` binds
    the whole chain to its contract and every artifact digest.
    """

    contract_digest: str
    category: str
    artifacts: tuple[ContractArtifact, ...]

    def digest(self) -> str:
        """The content-addressed identity of the chain under its contract."""
        return content_id(
            "contract-chain",
            self.contract_digest,
            [artifact.digest for artifact in self.artifacts],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_digest": self.contract_digest,
            "category": self.category,
            "digest": self.digest(),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


# ── Criterion 3: profile data -> contract input (no name branch) ─────────────


def _role_with_capability(
    roles: Mapping[str, Any], capability: str, fallback: str
) -> str:
    """The first role whose declared capabilities carry ``capability``.

    Data-driven: the role is read from the profile's own ``capabilities``
    mapping, never from a literal profile or role name.
    """
    for name, spec in roles.items():
        caps = spec.get("capabilities") if isinstance(spec, Mapping) else None
        if isinstance(caps, Mapping) and caps.get(capability):
            return str(name)
    return fallback


def contract_input_from_profile(
    profile: Mapping[str, Any],
    *,
    target_repo: str,
    base_sha: str,
    criteria: Sequence[str],
    settled_decisions: Sequence[str] = (),
) -> ContractInput:
    """Compose a :class:`ContractInput` from a WorkProfile's contract *data*.

    The role, scope and category come from the profile's declared data
    (``changeSurfaces``, ``capabilities``, ``category``); the target repo, base
    SHA, criteria and settled decisions come from the run brief. The same code
    path serves every vertical: two profiles diverge here only because their
    declared data diverges, never because of a branch on their name.
    """
    if not isinstance(profile, Mapping):
        raise ContractInputError("a profile mapping is required to derive a contract")

    category = str(profile.get("category") or profile.get("primaryCategory") or "")
    surfaces = profile.get("changeSurfaces") or profile.get("change_surfaces") or ()
    scope = [f"/{str(surface).strip('/')}/**" for surface in surfaces if str(surface).strip()]
    if not scope:
        raise ContractInputError(
            "profile declares no changeSurfaces to derive a write scope from"
        )

    roles = profile.get("roles")
    roles = roles if isinstance(roles, Mapping) else {}
    producer = _role_with_capability(roles, "can_mutate_run_state", "")
    reviewer = _role_with_capability(roles, "can_approve_gate", "")
    if producer != OPS_ROLE or reviewer != REVIEWER_ROLE:
        raise ContractInputError(
            "profile must declare a separate producing role holding "
            "can_mutate_run_state and a reviewing role holding can_approve_gate"
        )

    return ContractInput(
        role=OPS_ROLE,
        scope=tuple(scope),
        target_repo=target_repo,
        base_sha=base_sha,
        criteria=tuple(criteria),
        settled_decisions=tuple(settled_decisions),
        category=category,
        reviewer_role=REVIEWER_ROLE,
    )


# ── The one generator (criterion 1/2/3) ──────────────────────────────────────


def generate_contract_promptchain(contract: ContractInput) -> ContractDerivedChain:
    """Derive the ordered artifact chain from one contract input.

    Produces a producer artifact (an ``ops`` handoff bound to the base SHA) and
    a review artifact (a ``review`` handoff whose subject is the contract's
    frozen review subject). Both carry every contract field, and both digests
    bind the handoff and the review subject back to the contract input. The
    function reads only the contract's data — the two verticals take this same
    path and diverge only because their contracts differ (criterion 3).
    """
    contract.validate()
    contract_digest = contract.digest()
    # The review subject is a full SHA derived from the contract input, so the
    # review is bound to the settled contract, not to a caller-supplied value.
    review_subject_sha = contract_digest[:40]

    producer_handoff = build_ops_handoff(
        source_receipt_id=contract_digest,
        base_sha=contract.base_sha,
        subject_sha=contract.base_sha,
        allowed_paths=contract.scope,
        required_inputs=contract.criteria,
        criteria=contract.criteria,
        commands=(f"produce:{contract.target_repo}",),
    )
    producer = _seal_artifact(
        contract,
        contract_digest=contract_digest,
        role=contract.role,
        handoff=producer_handoff,
        review_subject_sha=review_subject_sha,
    )

    reviewer_handoff = build_review_handoff(
        source_receipt_id=producer.digest,
        base_sha=contract.base_sha,
        subject_sha=review_subject_sha,
        allowed_paths=contract.scope,
        required_inputs=(producer.digest,),
        criteria=contract.criteria,
        commands=("review",),
    )
    reviewer = _seal_artifact(
        contract,
        contract_digest=contract_digest,
        role=contract.reviewer_role,
        handoff=reviewer_handoff,
        review_subject_sha=review_subject_sha,
    )

    return ContractDerivedChain(
        contract_digest=contract_digest,
        category=contract.category,
        artifacts=(producer, reviewer),
    )


def _seal_artifact(
    contract: ContractInput,
    *,
    contract_digest: str,
    role: str,
    handoff: Handoff,
    review_subject_sha: str,
) -> ContractArtifact:
    """Build one artifact and seal it with its contract-bound digest."""
    artifact = ContractArtifact(
        id=content_id("contract-artifact-id", contract_digest, role),
        contract_digest=contract_digest,
        role=role,
        scope=tuple(contract.scope),
        target_repo=contract.target_repo,
        base_sha=contract.base_sha,
        criteria=tuple(contract.criteria),
        settled_decisions=tuple(contract.settled_decisions),
        category=contract.category,
        handoff=handoff,
        review_subject_sha=review_subject_sha,
        digest="",
    )
    return replace(artifact, digest=artifact.recompute_digest())


# ── Validation (criterion 1/2) ───────────────────────────────────────────────


def validate_contract_chain(chain: ContractDerivedChain) -> list[str]:
    """Check a derived chain carries its contract and its bindings.

    Returns the list of violations (empty means valid). Fails closed on a
    missing artifact, a missing contract digest, an artifact that drops a
    contract field, an invalid handoff, or an artifact whose stored digest no
    longer matches the fields it carries.
    """
    violations: list[str] = []
    if not chain.artifacts:
        violations.append("chain carries no artifacts")
    if not chain.contract_digest:
        violations.append("chain omits the contract digest")
    for index, artifact in enumerate(chain.artifacts):
        if not artifact.role:
            violations.append(f"artifact {index} carries no role")
        if not artifact.target_repo:
            violations.append(f"artifact {index} carries no target repo")
        if not _is_full_sha(artifact.base_sha):
            violations.append(f"artifact {index} base SHA is not a full SHA")
        if not artifact.scope:
            violations.append(f"artifact {index} carries no scope")
        if not artifact.criteria:
            violations.append(f"artifact {index} carries no criteria")
        if not artifact.contract_digest:
            violations.append(f"artifact {index} omits the contract digest")
        if not artifact.review_subject_sha:
            violations.append(f"artifact {index} carries no review subject")
        try:
            artifact.handoff.validate()
        except Exception as exc:  # noqa: BLE001
            violations.append(f"artifact {index} handoff invalid: {exc}")
        if artifact.digest != artifact.recompute_digest():
            violations.append(
                f"artifact {index} digest does not match its contract-bound bytes"
            )
    return violations


# ── Criterion 4: the pre-start tamper gate ───────────────────────────────────


def validate_brief(
    contract: ContractInput, chain: ContractDerivedChain
) -> list[str]:
    """Return the reasons the brief and chain disagree (empty means intact).

    Re-derives the contract digest and every artifact digest and compares them
    to the generated chain, then applies the canonical fail-closed launch check
    (:func:`start_blocking_reason`) to each handoff. Any mismatch means the
    brief was tampered with after generation.
    """
    reasons: list[str] = []
    contract_digest = contract.digest()
    if contract_digest != chain.contract_digest:
        reasons.append(
            "contract digest mismatch: the brief was changed after its chain "
            "was generated"
        )
    for index, artifact in enumerate(chain.artifacts):
        if artifact.contract_digest != contract_digest:
            reasons.append(
                f"artifact {index} is bound to a different contract digest"
            )
        if artifact.digest != artifact.recompute_digest():
            reasons.append(
                f"artifact {index} digest does not match its contract-bound bytes"
            )

    receipts: dict[str, Any] = {contract_digest: chain}
    for artifact in chain.artifacts:
        receipts[artifact.digest] = artifact
    for index, artifact in enumerate(chain.artifacts):
        reason = start_blocking_reason(artifact.handoff, receipts=receipts)
        if reason is not None:
            reasons.append(f"artifact {index} cannot start: {reason}")
    return reasons


def dispatch_contract_chain(
    chain: ContractDerivedChain,
    contract: ContractInput,
    *,
    on_worker_start: Optional[Callable[[ContractArtifact], Any]] = None,
) -> list[str]:
    """Gate the chain on the brief, then start its workers.

    The brief is re-validated *before* the first worker starts: if the contract
    digest or any artifact digest no longer matches, :class:`TamperedBriefError`
    is raised and ``on_worker_start`` is never invoked — zero workers start.
    Only an intact chain invokes ``on_worker_start`` once per artifact, in
    order, and returns the started artifact ids.
    """
    reasons = validate_brief(contract, chain)
    if reasons:
        raise TamperedBriefError("; ".join(reasons))
    started: list[str] = []
    for artifact in chain.artifacts:
        if on_worker_start is not None:
            on_worker_start(artifact)
        started.append(artifact.id)
    return started


__all__ = [
    "SequenceDeclaration",
    "Lane",
    "DispatchPlan",
    "DispatchEntry",
    "SUBAGENT",
    "INLINE",
    "MissingSessionBoundaryError",
    "load_sequence",
    "build_dispatch_plan",
    "execute_sequence",
    "BatchCommand",
    "SessionState",
    "SessionRun",
    "Session",
    "SessionConsumedError",
    "SessionExecutionError",
    "load_state_file",
    "ContractPromptChainError",
    "ContractInputError",
    "TamperedBriefError",
    "ContractInput",
    "ContractArtifact",
    "ContractDerivedChain",
    "contract_input_from_profile",
    "generate_contract_promptchain",
    "validate_contract_chain",
    "validate_brief",
    "dispatch_contract_chain",
]
