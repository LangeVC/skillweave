"""Dispatch-order group 2 — "parallel and integration safety" (criteria 3, 4).

Proves real disjoint jobs overlap in time while conflicting write scopes
serialize, and that integration eligibility fails closed on every declared
defect. Uses the decision-only ``skillweave.dispatch.topology`` and
``skillweave.dispatch.integration`` surfaces plus the real ``fan_out_dispatch``
for the overlap half.

Mutates nothing: topology/integration are pure decision models; the fan-out half
writes only to a temporary directory.
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

import pytest

from skillweave.dispatch import topology as T
from skillweave.dispatch import integration as I
from skillweave.fanout.dispatch import fan_out_dispatch
from skillweave.routing.modelspec import concrete

SHA_A = "a" * 40
SHA_B = "b" * 40


def _lane(lane_id, *, base=SHA_A, scope=("src/",), deps=()):
    return T.LaneTopology(
        lane_id=lane_id, base=base, depends_on=list(deps),
        write_scope=list(scope), worktree=f"/tmp/{lane_id}",
        branch=f"ops/{lane_id}",
    )


# ── Criterion 3: disjoint jobs overlap, conflicting scopes serialize ─────────


def test_criterion_03_disjoint_jobs_overlap_conflicting_scopes_serialize():
    """Two real disjoint jobs overlap; two conflicting scopes serialize.

    The overlap half runs two real child processes (in a temp dir) through
    ``fan_out_dispatch`` and requires them to overlap in wall-clock time. The
    serialize half builds a serialization plan over two lanes with overlapping
    write scopes and requires they land in separate batches, while two lanes
    with disjoint scopes share a batch.
    """
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp)
        script = (
            "import sys, time, pathlib\n"
            "p = pathlib.Path(sys.argv[1]) / sys.argv[2]\n"
            "p.write_text(str(time.time() * 1000))\n"
            "time.sleep(0.25)\n"
            "(p.parent / (p.name + '.end')).write_text(str(time.time() * 1000))\n"
            "print('done')\n"
        )
        cmds = [
            [sys.executable, "-c", script, str(marker), "a"],
            [sys.executable, "-c", script, str(marker), "b"],
        ]
        result = fan_out_dispatch(
            cmds, run_id="gate-1311-overlap", subject_repo="skillweave",
            subject_commit=SHA_A, tool="opencode",
            model=concrete("faigate/deepseek-v4-flash"),
            created_at="2026-08-29T00:00:00Z",
        )
        assert result.overlapped
        assert result.succeeded, result.child_outcomes()
        a_start = float((marker / "a").read_text())
        a_end = float((marker / "a.end").read_text())
        b_start = float((marker / "b").read_text())
        b_end = float((marker / "b.end").read_text())
        # Each job started before the other finished.
        assert a_end > b_start and b_end > a_start

    # Conflicting write scopes serialize: both lanes touch "src/" -> separate.
    lane_x = _lane("lane-x", scope=("src/skillweave/dispatch/",))
    lane_y = _lane("lane-y", scope=("src/skillweave/dispatch/",))
    plan_conflict = T.build_serialization_plan([lane_x, lane_y])
    assert [lid for g in plan_conflict.groups for lid in g].count("lane-x") == 1
    assert not any("lane-x" in g and "lane-y" in g for g in plan_conflict.groups)
    assert set(plan_conflict.serialized) == {"lane-x", "lane-y"}

    # Disjoint scopes do NOT serialize.
    lane_p = _lane("lane-p", scope=("src/skillweave/dispatch/",))
    lane_q = _lane("lane-q", scope=("src/skillweave/trace/",))
    plan_parallel = T.build_serialization_plan([lane_p, lane_q])
    assert any("lane-p" in g and "lane-q" in g for g in plan_parallel.groups)

    # Collision detection reports the correct reason.
    collisions = T.detect_collisions([lane_x, lane_y])
    assert any(c.reason == "write_scope_overlap" for c in collisions)


# ── Criterion 4: integration eligibility fails closed ───────────────────────


def test_criterion_04_integration_eligibility_fails_closed():
    """Missing commit, detached HEAD, dirty state, stale base, sibling
    omission and changed-after-review SHA each fail integration eligibility.
    """
    lane = _lane("lane-1")

    # detached HEAD -> ineligible.
    detached = T.WorktreeState(
        committed_sha=SHA_A, detached=True, on_branch=None, dirty_paths=[]
    )
    assert not T.is_eligible(lane, detached)
    assert any("detached" in r for r in T.assess_eligibility(lane, detached))

    # missing commit -> ineligible.
    no_commit = T.WorktreeState(
        committed_sha=None, detached=False, on_branch=lane.branch, dirty_paths=[]
    )
    assert not T.is_eligible(lane, no_commit)

    # dirty non-allowlisted state -> ineligible.
    dirty = T.WorktreeState(
        committed_sha=SHA_A, detached=False, on_branch=lane.branch,
        dirty_paths=["src/skillweave/dispatch/topology.py"],
    )
    assert not T.is_eligible(lane, dirty)

    # cache-only dirt is allowed (allowlist).
    cache_only = T.WorktreeState(
        committed_sha=SHA_A, detached=False, on_branch=lane.branch,
        dirty_paths=["__pycache__/topology.cpython-312.pyc"],
    )
    assert T.is_eligible(lane, cache_only)

    # committed on the wrong branch -> ineligible.
    wrong_branch = T.WorktreeState(
        committed_sha=SHA_A, detached=False, on_branch="main", dirty_paths=[]
    )
    assert not T.is_eligible(lane, wrong_branch)

    # clean committed state -> eligible.
    clean = T.WorktreeState(
        committed_sha=SHA_A, detached=False, on_branch=lane.branch, dirty_paths=[]
    )
    assert T.is_eligible(lane, clean)

    # stale base: two lanes with disjoint scopes but different bases collide on
    # an incompatible base.
    lane_stale = _lane("lane-stale", base=SHA_B, scope=("docs/",))
    lane_docs = _lane("lane-docs", base=SHA_A, scope=("skills/",))
    collisions = T.detect_collisions([lane_docs, lane_stale])
    assert any(c.reason == "incompatible_base" for c in collisions)

    # sibling omission: a multi-parent receipt missing a reviewed parent fails
    # even though the included parent passed.
    receipt = I.IntegrationReceipt(
        lane_id="integrator-1", candidate_sha=SHA_A,
        parents={
            "parent-a": I.ParentReceipt(parent_sha=SHA_A, outcome_present=True),
        },
    )
    with pytest.raises(I.ReceiptError):
        receipt.validate(expected_parents=["parent-a", "parent-b"])

    # changed-after-review SHA invalidates a prior review (fresh cold required).
    review = I.Review(lane_id="lane-1", reviewed_sha=SHA_A, verdict="REVIEW_PASS")
    assert I.review_still_valid(review, SHA_A)
    assert not I.review_still_valid(review, SHA_B)
    with pytest.raises(I.ReviewInvalidatedError):
        I.require_fresh_review(review, SHA_B)
