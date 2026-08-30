"""Integration tests for integration eligibility (SW1311-TOPOLOGY-001, 4-9).

Covers the remaining acceptance criteria end to end through
:mod:`skillweave.dispatch.integration`:

4. Before integration a lane rebases onto the current full integration-tip SHA
   and reruns its controller verification.
5. Any rebase or integration that changes the candidate SHA invalidates the
   earlier review and requires a fresh cold review.
6. A multi-parent integration receipt records every reviewed parent full SHA and
   proves each parent outcome is present; a sibling omission fails even when
   tests pass.
7. A semantic conflict is assigned to an explicit Integrator role with a bounded
   write scope, test contract and receipt; the controller performs no product
   edit.
8. Reviewer/observer cache artifacts cannot enter an integration candidate or
   make a review worktree appear product-dirty.
9. A dependency-DAG fixture keeps a dependent lane pending until its required
   integrated parent is independently passed.
"""

import sys
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.dispatch.integration import (  # noqa: E402
    IntegrationError,
    IntegrationTip,
    IntegrationReceipt,
    ParentReceipt,
    ReceiptError,
    Review,
    ReviewInvalidatedError,
    SemanticConflictError,
    INTEGRATOR_ROLE,
    assign_semantic_conflict,
    build_dependency_graph,
    candidate_cache_artifacts,
    plan_rebase,
    product_paths,
    require_fresh_review,
    resolve_semantic_conflict,
    review_still_valid,
)
from skillweave.dispatch.topology import LaneTopology  # noqa: E402

_SHA = "d" * 40
_TIP = "e" * 40


def _lane(lane_id, *, depends_on=None):
    return LaneTopology(
        lane_id=lane_id,
        base=_SHA,
        depends_on=depends_on or [],
        write_scope=[f"/repo/{lane_id}/**"],
        worktree=f"/tmp/{lane_id}",
        branch=f"branch-{lane_id}",
        integration_policy="independent",
    )


# ── Criterion 4: rebase onto integration tip + re-verification ───────────────


def test_rebase_records_pre_and_post_sha_and_requires_reverification():
    lane = _lane("lane-a")
    result = plan_rebase(lane, candidate_sha=_SHA, tip=IntegrationTip(tip_sha=_TIP))
    assert result.pre_rebase_sha == _SHA
    assert result.post_rebase_sha == _TIP
    assert result.sha_changed is True
    # Re-verification did not run automatically: the plan only records that it
    # must. The caller invokes controller verification against post_rebase_sha.
    assert result.reran_verification is False


def test_rebase_onto_same_sha_keeps_sha_stable():
    lane = _lane("lane-a")
    result = plan_rebase(lane, candidate_sha=_SHA, tip=IntegrationTip(tip_sha=_SHA))
    assert result.sha_changed is False


def test_rebase_rejects_non_full_sha_candidate():
    lane = _lane("lane-a")
    with pytest.raises(IntegrationError):
        plan_rebase(lane, candidate_sha="main", tip=IntegrationTip(tip_sha=_TIP))


def test_rebase_rejects_non_full_sha_tip():
    lane = _lane("lane-a")
    with pytest.raises(IntegrationError):
        plan_rebase(lane, candidate_sha=_SHA, tip=IntegrationTip(tip_sha="main"))


# ── Criterion 5: SHA change invalidates review ───────────────────────────────


def test_review_still_valid_only_for_exact_sha():
    review = Review(lane_id="lane-a", reviewed_sha=_SHA, verdict="approved")
    assert review_still_valid(review, _SHA) is True
    assert review_still_valid(review, _TIP) is False


def test_rebase_that_changes_sha_requires_fresh_review():
    review = Review(lane_id="lane-a", reviewed_sha=_SHA, verdict="approved")
    # The candidate moved to the integration tip after rebase -> stale review.
    with pytest.raises(ReviewInvalidatedError):
        require_fresh_review(review, _TIP)


def test_rebase_without_change_keeps_review():
    review = Review(lane_id="lane-a", reviewed_sha=_SHA, verdict="approved")
    assert require_fresh_review(review, _SHA) is review


def test_missing_review_requires_fresh_review():
    with pytest.raises(ReviewInvalidatedError):
        require_fresh_review(None, _SHA)


# ── Criterion 6: multi-parent receipt, sibling omission fails ────────────────


def _receipt(parents, candidate_sha=_SHA):
    return IntegrationReceipt(
        lane_id="integrator", candidate_sha=candidate_sha,
        parents={pid: ParentReceipt(parent_sha=sha, outcome_present=present)
                 for pid, (sha, present) in parents.items()},
    )


def test_full_receipt_with_all_parents_present_validates():
    r = _receipt({"parent-a": (_SHA, True), "parent-b": (_TIP, True)})
    r.validate(expected_parents=["parent-a", "parent-b"])  # must not raise


def test_sibling_omission_fails_even_when_other_parents_pass():
    # parent-b is entirely absent, parent-a passes -> still a failure.
    r = _receipt({"parent-a": (_SHA, True)})
    with pytest.raises(ReceiptError) as exc:
        r.validate(expected_parents=["parent-a", "parent-b"])
    assert "parent-b" in str(exc.value)


def test_parent_without_outcome_fails_even_when_tests_pass():
    r = _receipt({"parent-a": (_SHA, True), "parent-b": (_TIP, False)})
    with pytest.raises(ReceiptError) as exc:
        r.validate(expected_parents=["parent-a", "parent-b"])
    assert "outcome is not present" in str(exc.value)


def test_parent_sha_must_be_full_sha():
    r = _receipt({"parent-a": ("main", True)})
    with pytest.raises(ReceiptError):
        r.validate(expected_parents=["parent-a"])


# ── Criterion 7: semantic conflict -> Integrator role ────────────────────────


def test_semantic_conflict_bound_to_integrator_with_scope_and_contract():
    lane = _lane("lane-a")
    assignment = assign_semantic_conflict(
        lane,
        conflict="overlapping semantics in src/foo.py",
        write_scope=["/repo/lane-a/src/foo.py"],
        test_contract=["tests/test_foo.py::test_resolution"],
    )
    assert assignment.integrator == INTEGRATOR_ROLE
    assert assignment.write_scope == ["/repo/lane-a/src/foo.py"]
    assert assignment.test_contract
    assert assignment.conflict


def test_assignment_refuses_unbounded_scope():
    lane = _lane("lane-a")
    with pytest.raises(SemanticConflictError):
        assign_semantic_conflict(lane, conflict="x", write_scope=[], test_contract=["t"])


def test_assignment_refuses_missing_test_contract():
    lane = _lane("lane-a")
    with pytest.raises(SemanticConflictError):
        assign_semantic_conflict(lane, conflict="x", write_scope=["/a"], test_contract=[])


def test_resolution_yields_receipt_not_controller_edit():
    lane = _lane("lane-a")
    assignment = assign_semantic_conflict(
        lane, conflict="x", write_scope=["/repo/lane-a/x.py"], test_contract=["t"],
    )
    receipt = resolve_semantic_conflict(
        assignment, candidate_sha=_SHA,
        parents={"parent-a": ParentReceipt(parent_sha=_SHA, outcome_present=True)},
    )
    assert isinstance(receipt, IntegrationReceipt)
    assert receipt.candidate_sha == _SHA
    receipt.validate(expected_parents=["parent-a"])
    # The controller performed no product edit: the receipt is a record, not a
    # mutation of write scope or paths.
    assert assignment.write_scope == ["/repo/lane-a/x.py"]


# ── Criterion 8: cache artifacts excluded from candidate ─────────────────────


def test_cache_artifacts_are_identified_and_product_paths_split():
    paths = [
        "src/skillweave/__pycache__/dispatch.cpython-312.pyc",
        "src/skillweave/dispatch/topology.py",
        ".pytest_cache/v/cache/nodeids",
        "tests/integration/test_dispatch_topology.py",
    ]
    cache = candidate_cache_artifacts(paths)
    assert "src/skillweave/dispatch/topology.py" not in cache
    assert any("__pycache__" in p for p in cache)
    assert "src/skillweave/dispatch/topology.py" in product_paths(paths)
    assert "src/skillweave/__pycache__/dispatch.cpython-312.pyc" not in product_paths(paths)


# ── Criterion 9: dependency-DAG gating ───────────────────────────────────────


def test_dependent_lane_pending_until_parent_independently_passed():
    a = _lane("lane-a")
    b = _lane("lane-b", depends_on=["lane-a"])
    c = _lane("lane-c", depends_on=["lane-b"])
    graph = build_dependency_graph([a, b, c])

    # Nothing passed -> both dependents pending.
    assert graph.dependents_pending(passed=[]) == ["lane-b", "lane-c"]

    # Only lane-a passed -> lane-b is released (its parent passed), but lane-c
    # is still pending because lane-b is not yet integrated.
    assert graph.dependents_pending(passed=["lane-a"]) == ["lane-c"]

    # lane-a and lane-b passed -> lane-c released.
    assert graph.dependents_pending(passed=["lane-a", "lane-b"]) == []

    # All three passed -> nothing pending.
    assert graph.dependents_pending(passed=["lane-a", "lane-b", "lane-c"]) == []
