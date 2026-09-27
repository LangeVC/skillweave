"""Remediation planner: splits multi-domain failures into disjoint micro-lanes.

A pure planner (SW-PLAN-003 Step A). It takes a set of failed lanes, groups
them by their domain (repo + base), and produces a remediation plan:

- Multi-domain failures are split into disjoint micro-lanes — each lane is
  isolated in its own remediation group so one domain's correction never
  serializes with another domain's.
- Single-domain failures are kept bounded — all lanes in the same domain are
  grouped together since they share the same workspace constraints.

Nothing here launches a worker. The planner is a pure function: it receives
failed-lane facts and returns a plan, with zero side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence


@dataclass(frozen=True)
class RemediationDomain:
    """A domain identified by its (repo, base) pair.

    Two lanes share a domain when they operate on the same repo at the same
    base commit. A domain is the workspace-isolation unit: corrections in
    different domains must never serialize together.
    """

    repo: str
    base: str

    @property
    def key(self) -> str:
        return f"{self.repo}@{self.base}"


@dataclass
class RemediationMicroLane:
    """One failed lane, attributed to its domain and failure round.

    A micro-lane carries exactly enough context for the controller to
    re-dispatch a correction: the lane identity, the domain it belongs to,
    and the round in which it failed.
    """

    lane_id: str
    domain: RemediationDomain
    failure_round: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "domain": {"repo": self.domain.repo, "base": self.domain.base},
            "failure_round": self.failure_round,
        }


@dataclass
class RemediationPlan:
    """The output of the remediation planner.

    ``groups`` are the disjoint remediation groups. Each group contains one or
    more micro-lanes that can be corrected together (same domain). Groups are
    ordered so that multi-domain splits appear first, followed by bounded
    single-domain groups.

    ``single_domain`` is True when all failed lanes share one domain.
    ``multi_domain`` is True when failed lanes span multiple domains.
    """

    groups: list[list[RemediationMicroLane]] = field(default_factory=list)
    single_domain: bool = False
    multi_domain: bool = False

    @property
    def total_lanes(self) -> int:
        return sum(len(g) for g in self.groups)

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": [[ml.to_dict() for ml in group] for group in self.groups],
            "single_domain": self.single_domain,
            "multi_domain": self.multi_domain,
            "total_lanes": self.total_lanes,
        }


def plan_remediation(
    failed_lanes: Sequence[Mapping[str, Any]],
    *,
    failure_round: int = 0,
) -> RemediationPlan:
    """Plan remediation for a set of failed lanes.

    Groups failed lanes by domain (repo, base). Multi-domain failures are
    split into disjoint micro-lanes — each lane becomes its own group so
    corrections in different domains never serialize together.
    Single-domain failures are kept bounded in one group.

    Args:
        failed_lanes: Each entry is a mapping with at least ``lane_id``,
            ``repo``, and ``base`` keys.
        failure_round: The correction round in which these lanes failed.

    Returns:
        A :class:`RemediationPlan` with disjoint groups.
    """
    if not failed_lanes:
        return RemediationPlan()

    # Group by domain
    domain_groups: dict[str, list[RemediationMicroLane]] = {}
    for entry in failed_lanes:
        lane_id = entry["lane_id"]
        repo = entry.get("repo", "")
        base = entry.get("base", "")
        domain = RemediationDomain(repo=repo, base=base)
        micro_lane = RemediationMicroLane(
            lane_id=lane_id,
            domain=domain,
            failure_round=failure_round,
        )
        domain_groups.setdefault(domain.key, []).append(micro_lane)

    domains = list(domain_groups.keys())
    is_multi = len(domains) > 1

    groups: list[list[RemediationMicroLane]] = []
    if is_multi:
        # Multi-domain: split each lane into its own disjoint group so
        # corrections in different domains never serialize together.
        for domain_key in domains:
            for micro_lane in domain_groups[domain_key]:
                groups.append([micro_lane])
    else:
        # Single-domain: keep bounded — one group with all lanes.
        groups.append(list(domain_groups[domains[0]]))

    return RemediationPlan(
        groups=groups,
        single_domain=not is_multi and len(failed_lanes) > 0,
        multi_domain=is_multi,
    )
