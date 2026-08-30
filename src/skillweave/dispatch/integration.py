"""Integration eligibility, rebase, review invalidation, and the Integrator role.

Topology (:mod:`skillweave.dispatch.topology`) decides *which* lanes may touch
*which* paths in *which* order. This module owns what happens at the *moment of
integration*: rebasing a lane onto the integration tip, deciding when a rebase
invalidates a prior review, and recording a multi-parent integration receipt
that proves every reviewed parent actually landed.

It is decision-only: no ``git`` I/O, no model/provider/gateway/harness default,
no product edit by the controller. The controller supplies observed facts
(SHAs, worktree states) and receives a verdict; the *Integrator* — an explicit,
bounded role — is the only actor that resolves a semantic conflict.

Concerns:

* **Rebase + re-verification** — before integration a lane rebases onto the full
  integration-tip SHA and reruns its controller verification (criterion 4).
* **Review invalidation** — any rebase or integration that changes the candidate
  SHA invalidates the earlier review and requires a fresh cold review
  (criterion 5).
* **Multi-parent receipts** — an integration receipt records every reviewed
  parent full SHA and proves each parent outcome is present; a sibling omission
  fails even when every included parent passes (criterion 6).
* **Semantic conflicts** — assigned to an explicit Integrator role with a bounded
  write scope, test contract, and receipt; the controller performs no product
  edit (criterion 7).
* **Cache exclusion** — reviewer/observer cache artifacts (``__pycache__`` etc.)
  cannot enter an integration candidate or make a review worktree appear
  product-dirty (criterion 8).
* **Dependent gating** — a dependency-DAG keeps a dependent lane pending until
  its required integrated parent is independently passed (criterion 9).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Sequence

from skillweave.dispatch.topology import (
    LaneTopology,
    TopologyError,
    _is_full_sha,
    default_cache_allowlist,
    _is_cache_path,
)

#: The explicit integrator role name. This is the only actor permitted to
#: resolve a semantic conflict; it is distinct from ops/reviewer/observer.
INTEGRATOR_ROLE = "integrator"

#: A semantic conflict cannot be resolved by the controller: it is a named
#: state the Integrator must own.
SEMANTIC_CONFLICT = "semantic_conflict"


class IntegrationError(TopologyError):
    """An integration eligibility or receipt check failed."""


class ReviewInvalidatedError(IntegrationError):
    """A rebase/integration changed the candidate SHA, invalidating the review."""


class ReceiptError(IntegrationError):
    """A multi-parent integration receipt is incomplete or inconsistent."""


class SemanticConflictError(IntegrationError):
    """A semantic conflict surfaced; only the Integrator may resolve it."""


@dataclass
class IntegrationTip:
    """The integration target a lane rebases onto.

    ``tip_sha`` is the current full integration-tip SHA. A lane must rebase onto
    this exact SHA before its work is eligible to integrate.
    """

    tip_sha: str


@dataclass
class RebaseResult:
    """The outcome of rebasing a lane's candidate onto the integration tip."""

    lane_id: str
    pre_rebase_sha: str
    post_rebase_sha: str
    reran_verification: bool = False
    verification_passed: bool = False

    @property
    def sha_changed(self) -> bool:
        return self.pre_rebase_sha != self.post_rebase_sha


def plan_rebase(
    lane: LaneTopology,
    candidate_sha: str,
    tip: IntegrationTip,
) -> RebaseResult:
    """Record the rebase a lane must perform before integration (criterion 4).

    The rebase lands the candidate on ``tip.tip_sha``; ``candidate_sha`` is the
    lane's current head. The returned result records both SHAs so a caller can
    later decide whether the prior review still holds. Re-verification is the
    caller's invocation of the controller verification; ``plan_rebase`` records
    only that it *must* happen, not that it ran.
    """
    if not _is_full_sha(candidate_sha):
        raise IntegrationError(
            f"lane '{lane.lane_id}' candidate SHA {candidate_sha!r} is not a full SHA",
            field=f"{lane.lane_id}.candidate_sha",
        )
    if not _is_full_sha(tip.tip_sha):
        raise IntegrationError(
            f"integration tip SHA {tip.tip_sha!r} is not a full SHA", field="tip_sha"
        )
    return RebaseResult(
        lane_id=lane.lane_id,
        pre_rebase_sha=candidate_sha,
        post_rebase_sha=tip.tip_sha,
    )


@dataclass
class Review:
    """A cold review bound to a specific candidate SHA.

    ``reviewed_sha`` is the exact full SHA the review applied to. A review is
    only valid for that SHA; once the candidate moves, the review is stale.
    """

    lane_id: str
    reviewed_sha: str
    verdict: str = "pending"


def review_still_valid(review: Review, candidate_sha: str) -> bool:
    """True when the review still applies to the current candidate SHA.

    Acceptance criterion 5: any rebase/integration that changed the candidate
    SHA invalidates the earlier review. A review survives only while the
    candidate SHA is unchanged.
    """
    return _is_full_sha(candidate_sha) and review.reviewed_sha == candidate_sha


def require_fresh_review(
    review: Optional[Review],
    candidate_sha: str,
) -> Review:
    """Return the review if still valid, else raise :class:`ReviewInvalidatedError`.

    When the candidate SHA differs from the reviewed SHA (or no review exists),
    a fresh cold review is required — never satisfied by an in-place edit.
    """
    if review is None:
        raise ReviewInvalidatedError(
            f"no review present for candidate {candidate_sha!r}; a fresh cold "
            "review is required", field="review",
        )
    if not review_still_valid(review, candidate_sha):
        raise ReviewInvalidatedError(
            f"review for {review.reviewed_sha!r} no longer applies to candidate "
            f"{candidate_sha!r}; a fresh cold review is required", field="review",
        )
    return review


@dataclass
class ParentReceipt:
    """One reviewed parent folded into an integration.

    ``parent_sha`` is the full reviewed SHA of the parent; ``outcome_present``
    proves the parent's outcome actually landed in the candidate (e.g. the
    parent's trees/patches are discoverable in the merged tree).
    """

    parent_sha: str
    outcome_present: bool


@dataclass
class IntegrationReceipt:
    """A multi-parent integration receipt (criterion 6).

    Records the integration tip, the resulting candidate SHA, and every reviewed
    parent. ``parents`` is keyed by parent lane id; a parent whose outcome is
    absent fails the receipt even when every other parent passes.
    """

    lane_id: str
    candidate_sha: str
    parents: dict[str, ParentReceipt] = field(default_factory=dict)

    @property
    def reviewed_parent_shas(self) -> list[str]:
        return [p.parent_sha for p in self.parents.values()]

    def validate(self, expected_parents: Sequence[str]) -> None:
        """Raise :class:`ReceiptError` unless every expected parent is present and passed.

        ``expected_parents`` is the full set of parent lane ids that must be
        reviewed. A sibling omission (a parent id listed in ``expected_parents``
        but missing from the receipt, or present without ``outcome_present``)
        fails the receipt — even when every included parent passed its test.
        """
        if not _is_full_sha(self.candidate_sha):
            raise ReceiptError(
                f"integrator '{self.lane_id}' candidate SHA {self.candidate_sha!r} "
                "is not a full SHA", field="candidate_sha",
            )
        missing = [p for p in expected_parents if p not in self.parents]
        if missing:
            raise ReceiptError(
                f"integrator '{self.lane_id}' receipt is missing reviewed parents: "
                f"{sorted(missing)}", field="parents",
            )
        for parent_id, receipt in self.parents.items():
            if not _is_full_sha(receipt.parent_sha):
                raise ReceiptError(
                    f"parent '{parent_id}' SHA {receipt.parent_sha!r} is not a full SHA",
                    field=f"parents.{parent_id}",
                )
            if not receipt.outcome_present:
                raise ReceiptError(
                    f"parent '{parent_id}' outcome is not present in the candidate",
                    field=f"parents.{parent_id}.outcome_present",
                )


@dataclass
class IntegratorAssignment:
    """A semantic conflict handed to the explicit Integrator role (criterion 7).

    The integrator gets a *bounded* ``write_scope`` (paths it may touch to
    resolve the conflict), a ``test_contract`` naming the tests that must pass,
    and a ``receipt`` proving the resolution. The controller performs no product
    edit: it only produces this assignment.
    """

    integrator: str
    lane_id: str
    conflict: str
    write_scope: List[str] = field(default_factory=list)
    test_contract: List[str] = field(default_factory=list)
    receipt: Optional[IntegrationReceipt] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "integrator": self.integrator,
            "lane_id": self.lane_id,
            "conflict": self.conflict,
            "write_scope": list(self.write_scope),
            "test_contract": list(self.test_contract),
            "receipt": self.receipt.candidate_sha if self.receipt else None,
        }


def assign_semantic_conflict(
    lane: LaneTopology,
    *,
    conflict: str,
    write_scope: Sequence[str],
    test_contract: Sequence[str],
    integrator: str = INTEGRATOR_ROLE,
) -> IntegratorAssignment:
    """Bind a semantic conflict to a bounded Integrator assignment.

    The returned assignment is *not* a controller edit: it is the handoff of the
    conflict to the explicit Integrator, with a bounded write scope and a test
    contract. A resolved conflict yields an :class:`IntegrationReceipt` recorded
    by the integrator, never by the controller.
    """
    if not conflict:
        raise SemanticConflictError(
            "a semantic conflict must name its subject", field="conflict",
        )
    if not write_scope:
        raise SemanticConflictError(
            f"integrator assignment for lane '{lane.lane_id}' must carry a bounded "
            "write scope (the controller may not edit product paths)",
            field="write_scope",
        )
    if not test_contract:
        raise SemanticConflictError(
            f"integrator assignment for lane '{lane.lane_id}' must carry a test "
            "contract", field="test_contract",
        )
    return IntegratorAssignment(
        integrator=integrator,
        lane_id=lane.lane_id,
        conflict=conflict,
        write_scope=list(write_scope),
        test_contract=list(test_contract),
    )


def resolve_semantic_conflict(
    assignment: IntegratorAssignment,
    candidate_sha: str,
    *,
    parents: Optional[Mapping[str, ParentReceipt]] = None,
) -> IntegrationReceipt:
    """Record the integrator's resolution as an integration receipt.

    The controller does not edit product paths: this merely *records* the
    integrator's bounded resolution and returns the receipt that proves it.
    """
    if not _is_full_sha(candidate_sha):
        raise ReceiptError(
            f"integrator '{assignment.integrator}' candidate SHA {candidate_sha!r} "
            "is not a full SHA", field="candidate_sha",
        )
    return IntegrationReceipt(
        lane_id=assignment.lane_id,
        candidate_sha=candidate_sha,
        parents=dict(parents or {}),
    )


# --- Category 8: cache-artifact exclusion ------------------------------------

CANDIDATE_CACHE_PATTERNS = default_cache_allowlist()


def candidate_cache_artifacts(
    paths: Sequence[str],
    *,
    allowlist: Optional[Sequence[str]] = None,
) -> list[str]:
    """Return the subset of ``paths`` that are cache artifacts (excluded).

    Reviewer/observer cache artifacts such as ``__pycache__`` must not enter an
    integration candidate; this helper identifies them so a producer can filter
    them before the candidate is assembled (criterion 8).
    """
    allowlist = allowlist if allowlist is not None else CANDIDATE_CACHE_PATTERNS
    return [p for p in paths if _is_cache_path(p, allowlist)]


def product_paths(
    paths: Sequence[str],
    *,
    allowlist: Optional[Sequence[str]] = None,
) -> list[str]:
    """Return the subset of ``paths`` that are product paths (not cache)."""
    cache = set(candidate_cache_artifacts(paths, allowlist=allowlist))
    return [p for p in paths if p not in cache]


# --- Category 9: dependency-DAG gating ---------------------------------------


@dataclass
class DependencyGraph:
    """A dependency DAG over lanes.

    ``parents`` maps a lane id to the set of lane ids it depends on. ``gates``
    maps a lane id to a gate name whose independent pass releases it.
    """

    parents: dict[str, list[str]] = field(default_factory=dict)
    gates: dict[str, str] = field(default_factory=dict)

    def dependents_pending(self, passed: Sequence[str]) -> list[str]:
        """Return the lane ids still pending because a required parent is not integrated.

        A lane is pending when any of its parents is not in ``passed`` (the set
        of independently-passed, integrated parents). Criterion 9: a dependent
        stays pending until its required integrated parent is *independently*
        passed.
        """
        return sorted(
            lid for lid, deps in self.parents.items()
            if any(d not in passed for d in deps)
        )


def build_dependency_graph(lanes: Sequence[LaneTopology]) -> DependencyGraph:
    """Derive a dependency DAG from topology manifests (``depends_on``)."""
    return DependencyGraph(
        parents={t.lane_id: list(t.depends_on) for t in lanes},
        gates={t.lane_id: t.lane_id for t in lanes},
    )


__all__ = [
    "IntegrationError",
    "ReviewInvalidatedError",
    "ReceiptError",
    "SemanticConflictError",
    "INTEGRATOR_ROLE",
    "SEMANTIC_CONFLICT",
    "IntegrationTip",
    "RebaseResult",
    "Review",
    "ParentReceipt",
    "IntegrationReceipt",
    "IntegratorAssignment",
    "DependencyGraph",
    "plan_rebase",
    "review_still_valid",
    "require_fresh_review",
    "assign_semantic_conflict",
    "resolve_semantic_conflict",
    "candidate_cache_artifacts",
    "product_paths",
    "build_dependency_graph",
    "CANDIDATE_CACHE_PATTERNS",
]
