"""Integration tests for collision-safe topology (SW1311-TOPOLOGY-001, 1-3).

Covers the first three acceptance criteria end to end through the pure
decision seams in :mod:`skillweave.dispatch.topology`:

1. Every mutating lane declares a full base SHA, dependency set, write scope,
   exclusive worktree, branch and integration policy before dispatch.
2. Predicted overlapping write scopes, incompatible bases or shared harness
   state namespaces serialize before launch unless an explicit integration lane
   is declared.
3. A successful mutating lane is eligible only when its work is committed on the
   declared non-detached branch and the worktree is clean except for an explicit
   cache allowlist.

These are behavioral tests over real data structures, not text/source-presence
assertions.
"""

import sys
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.dispatch.topology import (  # noqa: E402
    ManifestError,
    LaneTopology,
    WorktreeState,
    assess_eligibility,
    build_serialization_plan,
    detect_collisions,
    is_eligible,
)

_BASE_A = "a" * 40
_BASE_B = "b" * 40


def _lane(lane_id, *, base=None, depends_on=None, write_scope=None,
          worktree=None, branch=None, policy="independent", namespace=None):
    return LaneTopology(
        lane_id=lane_id,
        base=base if base is not None else _BASE_A,
        depends_on=depends_on if depends_on is not None else [],
        write_scope=write_scope if write_scope is not None else [f"/repo/{lane_id}/**"],
        worktree=worktree if worktree is not None else f"/tmp/{lane_id}",
        branch=branch if branch is not None else f"branch-{lane_id}",
        integration_policy=policy,
        harness_state_namespace=namespace,
    )


# ── Criterion 1: complete manifest declared before dispatch ──────────────────


def test_valid_manifest_validates_without_error():
    lane = _lane("lane-a")
    lane.validate()  # must not raise


def test_missing_base_sha_is_rejected():
    lane = _lane("lane-a", base="main")  # branch name, not a full SHA
    with pytest.raises(ManifestError) as exc:
        lane.validate()
    assert "base" in str(exc.value)


def test_short_base_sha_is_rejected():
    lane = _lane("lane-a", base="a" * 7)
    with pytest.raises(ManifestError):
        lane.validate()


def test_missing_write_scope_is_rejected():
    lane = _lane("lane-a", write_scope=[])
    with pytest.raises(ManifestError) as exc:
        lane.validate()
    assert "write scope" in str(exc.value)


def test_missing_worktree_and_branch_are_rejected():
    lane = LaneTopology(
        lane_id="lane-a", base=_BASE_A, depends_on=[],
        write_scope=["/repo/lane-a/**"], worktree=None, branch=None,
        integration_policy="independent",
    )
    with pytest.raises(ManifestError) as exc:
        lane.validate()
    assert "worktree" in str(exc.value)


def test_detached_branch_is_rejected():
    lane = _lane("lane-a", branch="HEAD")
    with pytest.raises(ManifestError) as exc:
        lane.validate()
    assert "non-detached" in str(exc.value)


def test_unknown_integration_policy_is_rejected():
    lane = _lane("lane-a", policy="merge-anything")
    with pytest.raises(ManifestError) as exc:
        lane.validate()
    assert "integration_policy" in str(exc.value)


def test_missing_dependency_set_is_rejected():
    lane = LaneTopology(
        lane_id="lane-a", base=_BASE_A, depends_on=None,
        write_scope=["/repo/lane-a/**"], worktree="/tmp/lane-a",
        branch="branch-lane-a", integration_policy="independent",
    )
    with pytest.raises(ManifestError):
        lane.validate()


# ── Criterion 2: collisions serialize unless integrator declared ─────────────


def test_overlapping_write_scope_serializes():
    a = _lane("lane-a", write_scope=["/shared/**"])
    b = _lane("lane-b", write_scope=["/shared/sub/**"])
    plan = build_serialization_plan([a, b])
    assert plan.groups != [["lane-a", "lane-b"]], "overlapping scopes must not share a batch"
    assert "lane-a" in plan.serialized or "lane-b" in plan.serialized


def test_disjoint_write_scopes_share_a_batch():
    a = _lane("lane-a", write_scope=["/repo-a/**"])
    b = _lane("lane-b", write_scope=["/repo-b/**"])
    plan = build_serialization_plan([a, b])
    assert plan.groups == [["lane-a", "lane-b"]]


def test_incompatible_bases_serialize():
    a = _lane("lane-a", base=_BASE_A, write_scope=["/repo-a/**"])
    b = _lane("lane-b", base=_BASE_B, write_scope=["/repo-b/**"])
    plan = build_serialization_plan([a, b])
    assert "lane-a" in plan.serialized or "lane-b" in plan.serialized


def test_shared_harness_state_namespace_serializes():
    a = _lane("lane-a", write_scope=["/repo-a/**"], namespace="shared-state")
    b = _lane("lane-b", write_scope=["/repo-b/**"], namespace="shared-state")
    plan = build_serialization_plan([a, b])
    assert "lane-a" in plan.serialized or "lane-b" in plan.serialized


def test_detect_collisions_reports_reasons():
    a = _lane("lane-a", write_scope=["/shared/**"])
    b = _lane("lane-b", write_scope=["/shared/sub/**"])
    collisions = detect_collisions([a, b])
    assert any(c.reason == "write_scope_overlap" for c in collisions)


def test_detect_collisions_reports_incompatible_base():
    a = _lane("lane-a", base=_BASE_A, write_scope=["/a/**"])
    b = _lane("lane-b", base=_BASE_B, write_scope=["/b/**"])
    collisions = detect_collisions([a, b])
    assert any(c.reason == "incompatible_base" for c in collisions)


def test_explicit_integration_lane_absorbs_collision():
    a = _lane("lane-a", write_scope=["/shared/**"], policy="requires_integrator")
    b = _lane("integrator", write_scope=["/shared/**"], policy="requires_integrator")
    plan = build_serialization_plan([a, b], integration_lanes=["integrator"])
    # The integrator is permitted to fold the conflict; the two may share a
    # batch only because one is an explicit integration lane.
    assert plan.groups == [["integrator", "lane-a"]]


def test_two_plain_lanes_never_fold_by_fiat():
    a = _lane("lane-a", write_scope=["/shared/**"])
    b = _lane("lane-b", write_scope=["/shared/**"])
    plan = build_serialization_plan([a, b])  # no integration_lanes declared
    assert plan.groups != [["lane-a", "lane-b"]]


# ── Criterion 3: commit + clean (except allowlist) eligibility ───────────────


def _committed(lane, sha=None, on_branch=None):
    return WorktreeState(
        committed_sha=sha or lane.base,
        detached=False,
        on_branch=on_branch or lane.branch,
        dirty_paths=[],
    )


def test_committed_on_declared_branch_clean_eligible():
    lane = _lane("lane-a")
    state = WorktreeState(
        committed_sha="c" * 40, detached=False,
        on_branch=lane.branch, dirty_paths=[],
    )
    assert assess_eligibility(lane, state) == []
    assert is_eligible(lane, state)


def test_detached_head_not_eligible():
    lane = _lane("lane-a")
    state = WorktreeState(
        committed_sha="c" * 40, detached=True,
        on_branch=None, dirty_paths=[],
    )
    reasons = assess_eligibility(lane, state)
    assert any("detached" in r for r in reasons)


def test_dirty_path_not_eligible():
    lane = _lane("lane-a")
    state = WorktreeState(
        committed_sha="c" * 40, detached=False,
        on_branch=lane.branch, dirty_paths=["src/skillweave/dispatch/topology.py"],
    )
    reasons = assess_eligibility(lane, state)
    assert any("product-dirty" in r for r in reasons)


def test_cache_artifact_does_not_make_worktree_dirty():
    lane = _lane("lane-a")
    state = WorktreeState(
        committed_sha="c" * 40, detached=False,
        on_branch=lane.branch,
        dirty_paths=["src/skillweave/dispatch/__pycache__/topology.cpython-312.pyc"],
    )
    assert assess_eligibility(lane, state) == []
    assert is_eligible(lane, state)


def test_wrong_branch_not_eligible():
    lane = _lane("lane-a")
    state = WorktreeState(
        committed_sha="c" * 40, detached=False,
        on_branch="some-other-branch", dirty_paths=[],
    )
    reasons = assess_eligibility(lane, state)
    assert any("not the declared" in r for r in reasons)


def test_custom_allowlist_only_excludes_declared_cache():
    lane = _lane("lane-a")
    state = WorktreeState(
        committed_sha="c" * 40, detached=False,
        on_branch=lane.branch, dirty_paths=["__pycache__/x.pyc"],
    )
    # Not in the default allowlist unless the caller passes it; here the
    # default allowlist DOES include __pycache__ so it stays eligible.
    assert is_eligible(lane, state)

    # A narrow allowlist excluding __pycache__ makes the same path dirty.
    state2 = WorktreeState(
        committed_sha="c" * 40, detached=False,
        on_branch=lane.branch, dirty_paths=["__pycache__/x.pyc"],
    )
    assert not is_eligible(lane, state2, cache_allowlist=())


def test_no_committed_work_not_eligible():
    lane = _lane("lane-a")
    state = WorktreeState(
        committed_sha=None, detached=False,
        on_branch=lane.branch, dirty_paths=[],
    )
    reasons = assess_eligibility(lane, state)
    assert any("no committed work" in r for r in reasons)


# ── Live execution seam: topology is enforced before any worker launch ──────
#
# The decision helpers above are not enough on their own: the contract is that
# the PromptChain execution seam (``skillweave.promptchain.execute``) refuses or
# serializes invalid topology before a fan-out worker ever starts. These tests
# exercise that entry point, not the helper modules in isolation.


def _seq_decl(parallel_lanes, serialized_lanes=None):
    """Build a minimal promptchain sequence declaration for the executor."""
    from skillweave.promptchain.execute import load_sequence

    phases = []
    if parallel_lanes:
        phases.append({"phase": "build", "parallel_lanes": parallel_lanes})
    if serialized_lanes:
        phases.append({"phase": "build", "serialized_lanes": serialized_lanes})
    return load_sequence({"session_boundary": "batch", "phases": phases})


def _topo_lane(lane_id, *, write_scope, base=_BASE_A, namespace=None, depends_on=None):
    """A parallel lane declaration carrying the topology manifest fields."""
    lane = {
        "id": lane_id,
        "base": base,
        "depends_on": depends_on or [],
        "write_scope": write_scope
        if isinstance(write_scope, list)
        else [write_scope],
        "worktree": f"/tmp/{lane_id}",
        "branch": f"branch-{lane_id}",
        "integration_policy": "independent",
    }
    if namespace is not None:
        lane["harness_state_namespace"] = namespace
    return lane


def test_execute_seam_serializes_overlapping_write_scope_before_fanout():
    from skillweave.promptchain.execute import execute_sequence

    a = _topo_lane("lane-a", write_scope="/shared/**")
    b = _topo_lane("lane-b", write_scope="/shared/sub/**")
    batches = []

    def fake_fanout(lane_ids):
        batches.append(list(lane_ids))

    plan = execute_sequence(_seq_decl([a, b]), fanout=fake_fanout)
    # Overlapping scopes must never share a batch: two fan-out calls.
    assert len(batches) == 2, f"colliding lanes must serialize, got {batches}"
    assert batches == [["lane-a"], ["lane-b"]]
    assert plan.modes() == ["subagent", "subagent"]


def test_execute_seam_keeps_disjoint_lanes_in_one_batch():
    from skillweave.promptchain.execute import execute_sequence

    a = _topo_lane("lane-a", write_scope="/repo-a/**")
    b = _topo_lane("lane-b", write_scope="/repo-b/**")
    batches = []

    def fake_fanout(lane_ids):
        batches.append(list(lane_ids))

    execute_sequence(_seq_decl([a, b]), fanout=fake_fanout)
    assert batches == [["lane-a", "lane-b"]]


def test_execute_seam_fails_closed_on_incomplete_manifest_before_fanout():
    from skillweave.promptchain.execute import TopologyGateError, execute_sequence

    # A topology-governed lane missing its write scope is incomplete.
    bad = {
        "id": "lane-a",
        "base": _BASE_A,
        "depends_on": [],
        "worktree": "/tmp/lane-a",
        "branch": "branch-lane-a",
        "integration_policy": "independent",
        # write_scope omitted -> incomplete manifest
    }
    called = []

    def fake_fanout(lane_ids):
        called.append(list(lane_ids))

    try:
        execute_sequence(_seq_decl([bad]), fanout=fake_fanout)
        assert False, "expected TopologyGateError"
    except TopologyGateError as exc:
        assert "write scope" in str(exc)
    assert called == [], "no worker may start after an invalid topology declaration"


def test_execute_seam_without_topology_fields_preserves_single_batch():
    # No lane is topology-governed: the pre-existing single-batch behavior is
    # preserved (one fan-out call with all parallel lane ids).
    from skillweave.promptchain.execute import execute_sequence

    a = {"id": "T1"}
    b = {"id": "T2"}
    batches = []

    def fake_fanout(lane_ids):
        batches.append(list(lane_ids))

    execute_sequence(_seq_decl([a, b]), fanout=fake_fanout)
    assert batches == [["T1", "T2"]]


# ── Live integration gate: enforced by the execute seam before fan-out ─────
#
# C1 wired manifest validation and collision serialization into the seam. The
# remaining acceptance behaviors (4-9) must be *reachable* from the same live
# entry point, not left as decision helpers in ``dispatch.integration``. These
# tests drive ``execute_sequence`` (and its immediate ``gate_integration``) with
# a typed ``IntegrationGateInput`` and prove fail-closed refusal before any
# fan-out worker starts.


_SHA = "c" * 40
_TIP = "d" * 40


def _integrating_lane(lane_id, *, base=_SHA, depends_on=None):
    """A topology-governed parallel lane used as the integration subject."""
    return _topo_lane(
        lane_id,
        write_scope=f"/repo/{lane_id}/**",
        base=base,
        depends_on=depends_on,
    )


def _gate_input(**kwargs):
    from skillweave.promptchain.execute import IntegrationGateInput

    defaults = dict(lane_id="lane-a")
    defaults.update(kwargs)
    return IntegrationGateInput(**defaults)


def test_execute_seam_refuses_missing_post_rebase_verification():
    # Criterion 4: rebase happened (SHA changed) but the controller did not
    # rerun verification -> refuse before fan-out.
    from skillweave.promptchain.execute import TopologyGateError, execute_sequence

    a = _integrating_lane("lane-a")
    called = []

    def fake_fanout(lane_ids):
        called.append(list(lane_ids))

    with pytest.raises(TopologyGateError) as exc:
        execute_sequence(
            _seq_decl([a]),
            fanout=fake_fanout,
            integration_input=_gate_input(
                candidate_sha=_SHA,
                integration_tip_sha=_TIP,
                reran_verification=False,
                verification_passed=True,
            ),
        )
    assert "verification" in str(exc.value)
    assert called == [], "no worker may start without a post-rebase verification"


def test_execute_seam_refuses_failed_post_rebase_verification():
    from skillweave.promptchain.execute import TopologyGateError, execute_sequence

    a = _integrating_lane("lane-a")
    called = []

    def fake_fanout(lane_ids):
        called.append(list(lane_ids))

    with pytest.raises(TopologyGateError):
        execute_sequence(
            _seq_decl([a]),
            fanout=fake_fanout,
            integration_input=_gate_input(
                candidate_sha=_SHA,
                integration_tip_sha=_TIP,
                reran_verification=True,
                verification_passed=False,
            ),
        )
    assert called == []


def test_execute_seam_refuses_stale_review_on_changed_sha():
    # Criterion 5: the candidate moved to _TIP; a review bound to the old SHA is
    # stale and refuses before any fan-out.
    from skillweave.dispatch.integration import Review
    from skillweave.promptchain.execute import TopologyGateError, execute_sequence

    a = _integrating_lane("lane-a")
    called = []

    def fake_fanout(lane_ids):
        called.append(list(lane_ids))

    with pytest.raises(TopologyGateError) as exc:
        execute_sequence(
            _seq_decl([a]),
            fanout=fake_fanout,
            integration_input=_gate_input(
                candidate_sha=_SHA,
                integration_tip_sha=_TIP,
                reran_verification=True,
                verification_passed=True,
                review=Review(lane_id="lane-a", reviewed_sha=_SHA, verdict="approved"),
            ),
        )
    assert "review" in str(exc.value)
    assert called == []


def test_execute_seam_refuses_sibling_omission_in_receipt():
    # Criterion 6: parent-b is expected but omitted from the receipt -> refuse.
    from skillweave.dispatch.integration import (
        IntegrationReceipt,
        ParentReceipt,
    )
    from skillweave.promptchain.execute import TopologyGateError, execute_sequence

    a = _integrating_lane("lane-a")
    receipt = IntegrationReceipt(
        lane_id="lane-a",
        candidate_sha=_SHA,
        parents={"parent-a": ParentReceipt(parent_sha=_SHA, outcome_present=True)},
    )
    called = []

    def fake_fanout(lane_ids):
        called.append(list(lane_ids))

    with pytest.raises(TopologyGateError) as exc:
        execute_sequence(
            _seq_decl([a]),
            fanout=fake_fanout,
            integration_input=_gate_input(
                receipt=receipt,
                expected_parents=["parent-a", "parent-b"],
            ),
        )
    assert "parent-b" in str(exc.value)
    assert called == []


def test_execute_seam_refuses_parent_outcome_absence_in_receipt():
    from skillweave.dispatch.integration import (
        IntegrationReceipt,
        ParentReceipt,
    )
    from skillweave.promptchain.execute import TopologyGateError, execute_sequence

    a = _integrating_lane("lane-a")
    receipt = IntegrationReceipt(
        lane_id="lane-a",
        candidate_sha=_SHA,
        parents={
            "parent-a": ParentReceipt(parent_sha=_SHA, outcome_present=True),
            "parent-b": ParentReceipt(parent_sha=_TIP, outcome_present=False),
        },
    )
    called = []

    def fake_fanout(lane_ids):
        called.append(list(lane_ids))

    with pytest.raises(TopologyGateError) as exc:
        execute_sequence(
            _seq_decl([a]),
            fanout=fake_fanout,
            integration_input=_gate_input(
                receipt=receipt,
                expected_parents=["parent-a", "parent-b"],
            ),
        )
    assert "outcome" in str(exc.value)
    assert called == []


def test_execute_seam_refuses_unready_dependency():
    # Criterion 9: lane-b depends on lane-a, but lane-a is not passed -> refuse.
    from skillweave.promptchain.execute import TopologyGateError, execute_sequence

    b = _integrating_lane("lane-b", depends_on=["lane-a"])
    called = []

    def fake_fanout(lane_ids):
        called.append(list(lane_ids))

    with pytest.raises(TopologyGateError) as exc:
        execute_sequence(
            _seq_decl([b]),
            fanout=fake_fanout,
            integration_input=_gate_input(
                lane_id="lane-b",
                passed_lane_ids=[],
            ),
        )
    assert "pending" in str(exc.value)
    assert called == []


def test_gate_integration_yields_bounded_integrator_assignment():
    # Criterion 7: a semantic conflict routes to an explicit Integrator with a
    # bounded write scope, test contract and receipt — never a controller edit.
    from skillweave.dispatch.integration import (
        INTEGRATOR_ROLE,
        IntegrationReceipt,
        ParentReceipt,
        resolve_semantic_conflict,
    )
    from skillweave.promptchain.execute import gate_integration

    a = _integrating_lane("lane-a")
    declaration = _seq_decl([a])
    result = gate_integration(
        declaration,
        _gate_input(
            semantic_conflict="overlapping semantics in src/foo.py",
            conflict_write_scope=["/repo/lane-a/src/foo.py"],
            conflict_test_contract=["tests/test_foo.py::test_resolution"],
        ),
    )
    assignment = result.integrator_assignment
    assert assignment is not None
    assert assignment.integrator == INTEGRATOR_ROLE
    assert assignment.write_scope == ["/repo/lane-a/src/foo.py"]
    assert assignment.test_contract == ["tests/test_foo.py::test_resolution"]
    assert assignment.conflict

    # The controller records a resolution as a receipt; it performs no product
    # edit — the write scope stays bounded to the conflict path.
    receipt = resolve_semantic_conflict(
        assignment,
        candidate_sha=_SHA,
        parents={"parent-a": ParentReceipt(parent_sha=_SHA, outcome_present=True)},
    )
    assert isinstance(receipt, IntegrationReceipt)
    receipt.validate(expected_parents=["parent-a"])
    assert assignment.write_scope == ["/repo/lane-a/src/foo.py"]


def test_execute_seam_permits_complete_valid_integration_input():
    # Criterion 4+6 combined: a complete, valid integration input permits the
    # next action (fan-out runs exactly once for the non-colliding lane).
    from skillweave.dispatch.integration import Review
    from skillweave.promptchain.execute import execute_sequence

    a = _integrating_lane("lane-a")
    batches = []

    def fake_fanout(lane_ids):
        batches.append(list(lane_ids))

    # Rebase moves candidate _SHA -> _TIP; the review is already bound to _TIP
    # (fresh) and verification reran and passed.
    plan = execute_sequence(
        _seq_decl([a]),
        fanout=fake_fanout,
        integration_input=_gate_input(
            candidate_sha=_SHA,
            integration_tip_sha=_TIP,
            reran_verification=True,
            verification_passed=True,
            review=Review(lane_id="lane-a", reviewed_sha=_TIP, verdict="approved"),
        ),
    )
    assert plan.modes() == ["subagent"]
    assert batches == [["lane-a"]]
