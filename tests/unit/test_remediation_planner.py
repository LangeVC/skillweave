"""Tests for the remediation planner (SW-PLAN-003 Step A).

Covers:
- Single-domain failures are kept bounded (one group with all lanes).
- Multi-domain failures are split into disjoint micro-lanes (one group per lane).
- Empty input produces an empty plan.
"""

import pytest

from skillweave.dispatch.remediation import (
    RemediationDomain,
    RemediationMicroLane,
    RemediationPlan,
    plan_remediation,
)


class TestSingleDomain:
    """Single-domain failures are kept bounded in one group."""

    def test_one_lane(self):
        plan = plan_remediation([
            {"lane_id": "a", "repo": "r", "base": "sha1"},
        ])
        assert plan.single_domain is True
        assert plan.multi_domain is False
        assert len(plan.groups) == 1
        assert len(plan.groups[0]) == 1
        assert plan.groups[0][0].lane_id == "a"

    def test_multiple_lanes_same_domain(self):
        plan = plan_remediation([
            {"lane_id": "a", "repo": "r", "base": "sha1"},
            {"lane_id": "b", "repo": "r", "base": "sha1"},
        ])
        assert plan.single_domain is True
        assert plan.multi_domain is False
        assert len(plan.groups) == 1
        assert len(plan.groups[0]) == 2
        ids = {ml.lane_id for ml in plan.groups[0]}
        assert ids == {"a", "b"}

    def test_different_repo_same_base_is_different_domain(self):
        plan = plan_remediation([
            {"lane_id": "a", "repo": "r1", "base": "sha1"},
            {"lane_id": "b", "repo": "r2", "base": "sha1"},
        ])
        assert plan.multi_domain is True
        assert len(plan.groups) == 2
        # Each lane in its own disjoint group
        all_lanes = {ml.lane_id for g in plan.groups for ml in g}
        assert all_lanes == {"a", "b"}

    def test_same_repo_different_base_is_different_domain(self):
        plan = plan_remediation([
            {"lane_id": "a", "repo": "r", "base": "sha1"},
            {"lane_id": "b", "repo": "r", "base": "sha2"},
        ])
        assert plan.multi_domain is True
        assert len(plan.groups) == 2


class TestMultiDomain:
    """Multi-domain failures are split into disjoint micro-lanes."""

    def test_each_lane_isolated_in_own_group(self):
        plan = plan_remediation([
            {"lane_id": "a", "repo": "r1", "base": "sha1"},
            {"lane_id": "b", "repo": "r2", "base": "sha2"},
            {"lane_id": "c", "repo": "r3", "base": "sha3"},
        ])
        assert plan.multi_domain is True
        assert plan.single_domain is False
        assert len(plan.groups) == 3
        # Each group contains exactly one micro-lane
        for group in plan.groups:
            assert len(group) == 1
        all_lanes = {g[0].lane_id for g in plan.groups}
        assert all_lanes == {"a", "b", "c"}

    def test_mixed_same_and_different_domains(self):
        # a and b share a domain; c is in a different domain
        plan = plan_remediation([
            {"lane_id": "a", "repo": "r", "base": "sha1"},
            {"lane_id": "b", "repo": "r", "base": "sha1"},
            {"lane_id": "c", "repo": "r2", "base": "sha2"},
        ])
        assert plan.multi_domain is True
        # Multi-domain: every lane gets its own group
        assert len(plan.groups) == 3
        all_lanes = {ml.lane_id for g in plan.groups for ml in g}
        assert all_lanes == {"a", "b", "c"}

    def test_failure_round_preserved(self):
        plan = plan_remediation([
            {"lane_id": "a", "repo": "r", "base": "sha1"},
        ], failure_round=3)
        assert plan.groups[0][0].failure_round == 3


class TestEmpty:
    """Empty input produces an empty plan."""

    def test_empty_list(self):
        plan = plan_remediation([])
        assert plan.single_domain is False
        assert plan.multi_domain is False
        assert plan.groups == []
        assert plan.total_lanes == 0


class TestRemediationPlanDict:
    """The plan can be serialized to dict."""

    def test_to_dict(self):
        plan = plan_remediation([
            {"lane_id": "a", "repo": "r1", "base": "sha1"},
            {"lane_id": "b", "repo": "r2", "base": "sha2"},
        ])
        d = plan.to_dict()
        assert d["multi_domain"] is True
        assert d["single_domain"] is False
        assert d["total_lanes"] == 2
        assert len(d["groups"]) == 2
        assert d["groups"][0][0]["lane_id"] in ("a", "b")


class TestRemediationMicroLaneDict:
    """Micro-lanes serialize with domain attribution."""

    def test_to_dict(self):
        ml = RemediationMicroLane(
            lane_id="x",
            domain=RemediationDomain(repo="r", base="sha"),
            failure_round=2,
        )
        d = ml.to_dict()
        assert d["lane_id"] == "x"
        assert d["domain"]["repo"] == "r"
        assert d["domain"]["base"] == "sha"
        assert d["failure_round"] == 2


class TestRemediationDomain:
    """Domain identifies by (repo, base)."""

    def test_key(self):
        d = RemediationDomain(repo="r", base="sha1")
        assert d.key == "r@sha1"

    def test_equality(self):
        d1 = RemediationDomain(repo="r", base="sha1")
        d2 = RemediationDomain(repo="r", base="sha1")
        d3 = RemediationDomain(repo="r", base="sha2")
        assert d1 == d2
        assert d1 != d3
