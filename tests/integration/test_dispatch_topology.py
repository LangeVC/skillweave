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


# ── Live operator dispatcher: the authoritative topology gate ─────────────
#
# C3 (SW1311-TOPOLOGY-001): the topology/integration gate is consumed by the
# *real* operator dispatcher (``OperatorDispatchApplication.dispatch``) before
# any workspace is provisioned or worker fanned out. These tests drive the real
# application seam with an in-memory workspace and a fan-out recorder that reads
# each batch's per-child launch context (``subject_repo``) to identify which
# lane entered which batch — proving fail-closed manifest completeness, collision
# serialization, Integrator routing, serialized-lane isolation, eligibility, and
# non-mutating v1.3.10 compatibility.


import io  # noqa: E402

import yaml  # noqa: E402

from pathlib import Path as _Path  # noqa: E402

from skillweave.dispatch.application import (  # noqa: E402
    OperatorDispatchApplication,
    ProvisionedWorkspace,
    TopologyGateError,
    TopologyGateInput,
    WorkspaceSeam,
)
from skillweave.dispatch.topology import WorktreeState  # noqa: E402

_FIXTURES = _Path(__file__).resolve().parent.parent / "fixtures"
_PROFILE = _FIXTURES / "dispatch-profile.yaml"
_OP_SHA = "f" * 40


def _lane_id_from_repo(repo):
    return repo.rsplit("/", 1)[-1]


class _FakeWorkspace(WorkspaceSeam):
    def __init__(self):
        self.provisions = []

    def provision(self, lane, run_id):
        self.provisions.append(lane.id)
        return ProvisionedWorkspace(base_sha=lane.base or "", path=f"/tmp/{lane.id}")

    def release(self, lane, run_id):
        pass


class _RecordingFanout:
    """Records one fan-out batch per call, as the list of lane ids resolved from
    each child's ``subject_repo`` launch context."""

    def __init__(self):
        self.batches = []
        self.calls = 0

    def __call__(self, commands, **kwargs):
        self.calls += 1
        contexts = kwargs.get("launch_contexts") or []
        if contexts:
            ids = [_lane_id_from_repo(c.subject_repo) for c in contexts]
        else:
            ids = [_lane_id_from_repo(kwargs.get("subject_repo") or "")]
        self.batches.append(ids)
        return _FakeResult(children=[_FakeChild() for _ in commands])


class _FakeChild:
    succeeded = True


class _FakeResult:
    def __init__(self, children):
        self.children = children


def _governed_lane(
    lane_id,
    *,
    write_scope,
    policy="independent",
    depends_on=None,
    repo=None,
    branch=None,
    worktree=None,
    namespace=None,
):
    lane = {
        "id": lane_id,
        "role": "ops",
        "repo": repo or f"skillweave/{lane_id}",
        "base": _OP_SHA,
        "execution_model": "cold",
        "mutating": True,
        "write_scope": write_scope if isinstance(write_scope, list) else [write_scope],
        "worktree": worktree if worktree is not None else f"/tmp/{lane_id}",
        "branch": branch if branch is not None else f"branch-{lane_id}",
        "depends_on": depends_on or [],
        "integration_policy": policy,
    }
    if namespace is not None:
        lane["harness_state_namespace"] = namespace
    return lane


def _write_sequence(tmp_path, lanes):
    seq = {
        "session_boundary": "batch",
        "profile": {"path": str(_PROFILE), "required": True},
        "execution_model": "cold",
        "max_correction_rounds_per_wave": 0,
        "max_parallel": 8,
        "lanes": lanes,
    }
    path = tmp_path / "governed-sequence.yaml"
    path.write_text(yaml.safe_dump(seq), encoding="utf-8")
    return str(path)


def _dispatch(tmp_path, lanes, *, fanout, gate_input=None):
    seq = _write_sequence(tmp_path, lanes)
    ws = _FakeWorkspace()
    app = OperatorDispatchApplication(workspace_seam=ws, fanout_seam=fanout)
    run = app.dispatch(
        seq, str(_PROFILE), wave="0", sink=io.StringIO(), gate_input=gate_input
    )
    return run, ws


# F6: incomplete/absent mutating topology manifest fails closed before launch.
def test_operator_dispatcher_fails_closed_on_partial_manifest(tmp_path):
    bad = {
        "id": "lane-a",
        "role": "ops",
        "repo": "skillweave/lane-a",
        "base": _OP_SHA,
        "execution_model": "cold",
        "mutating": True,
        "write_scope": ["/repo/lane-a/**"],
        # worktree and branch omitted -> incomplete manifest.
    }
    fanout = _RecordingFanout()
    with pytest.raises(TopologyGateError):
        _dispatch(tmp_path, [bad], fanout=fanout)
    assert fanout.calls == 0, "no worker may start on an incomplete manifest"


# F6: a detached branch name is not a governable manifest.
def test_operator_dispatcher_rejects_detached_branch_in_manifest(tmp_path):
    bad = _governed_lane("lane-a", write_scope="/repo/a/**", branch="HEAD")
    fanout = _RecordingFanout()
    with pytest.raises(TopologyGateError):
        _dispatch(tmp_path, [bad], fanout=fanout)
    assert fanout.calls == 0


# Criterion 2: overlapping write scope serializes (never one batch).
def test_operator_dispatcher_serializes_overlapping_write_scope(tmp_path):
    a = _governed_lane("lane-a", write_scope="/shared/**")
    b = _governed_lane("lane-b", write_scope="/shared/sub/**")
    fanout = _RecordingFanout()
    run, _ = _dispatch(tmp_path, [a, b], fanout=fanout)
    assert fanout.batches == [["lane-a"], ["lane-b"]], (
        f"colliding lanes must never share a fan-out batch, got {fanout.batches}"
    )
    assert run.halted is False


# Criterion 2: shared harness state namespace serializes.
def test_operator_dispatcher_serializes_shared_namespace(tmp_path):
    a = _governed_lane("lane-a", write_scope="/a/**", namespace="shared")
    b = _governed_lane("lane-b", write_scope="/b/**", namespace="shared")
    fanout = _RecordingFanout()
    _dispatch(tmp_path, [a, b], fanout=fanout)
    assert fanout.batches == [["lane-a"], ["lane-b"]]


# F3: requires_integrator without an explicit eligible integrator refuses.
def test_operator_dispatcher_requires_integrator_fails_closed(tmp_path):
    a = _governed_lane(
        "lane-a", write_scope="/repo/a/**", policy="requires_integrator"
    )
    fanout = _RecordingFanout()
    with pytest.raises(TopologyGateError) as exc:
        _dispatch(tmp_path, [a], fanout=fanout, gate_input=TopologyGateInput())
    assert "requires_integrator" in str(exc.value)
    assert fanout.calls == 0


# F3 (green): an explicit distinct integrator lane satisfies requires_integrator.
def test_operator_dispatcher_requires_integrator_with_integrator_passes(tmp_path):
    a = _governed_lane(
        "lane-a", write_scope="/repo/a/**", policy="requires_integrator"
    )
    integrator = _governed_lane("integrator", write_scope="/repo/integrator/**")
    fanout = _RecordingFanout()
    run, _ = _dispatch(
        tmp_path,
        [a, integrator],
        fanout=fanout,
        gate_input=TopologyGateInput(integration_lanes=["integrator"]),
    )
    # Both lanes are disjoint; the requires_integrator lane is released by the
    # explicit integrator lane, so they share one collision-safe batch.
    assert len(fanout.batches) == 1
    assert sorted(fanout.batches[0]) == ["integrator", "lane-a"]
    assert run.halted is False


# F3 (red): naming only itself as the integrator does not satisfy the policy.
def test_operator_dispatcher_requires_integrator_not_own_integrator(tmp_path):
    a = _governed_lane(
        "lane-a", write_scope="/repo/a/**", policy="requires_integrator"
    )
    fanout = _RecordingFanout()
    with pytest.raises(TopologyGateError) as exc:
        _dispatch(
            tmp_path, [a], fanout=fanout,
            gate_input=TopologyGateInput(integration_lanes=["lane-a"]),
        )
    assert "requires_integrator" in str(exc.value)
    assert fanout.calls == 0


# F2: a semantic conflict is removed from normal fan-out and routed to the
# bounded Integrator — the controller launches no worker for the conflicted lane.
def test_operator_dispatcher_routes_semantic_conflict_to_integrator(tmp_path):
    a = _governed_lane("lane-a", write_scope="/repo/a/**")
    b = _governed_lane("lane-b", write_scope="/repo/b/**")
    fanout = _RecordingFanout()
    run, _ = _dispatch(
        tmp_path,
        [a, b],
        fanout=fanout,
        gate_input=TopologyGateInput(
            semantic_conflict="lane-a",
            conflict_write_scope=["/repo/a/src/foo.py"],
            conflict_test_contract=["tests/test_foo.py::test_resolution"],
        ),
    )
    # Only lane-b reached normal fan-out; lane-a was routed to the Integrator.
    assert fanout.batches == [["lane-b"]], (
        f"conflicted lane must not enter fan-out, got {fanout.batches}"
    )
    assignment = run.integrator_assignment
    assert assignment is not None
    assert assignment.integrator == "integrator"
    assert assignment.lane_id == "lane-a"
    assert assignment.write_scope == ["/repo/a/src/foo.py"]
    assert assignment.test_contract == ["tests/test_foo.py::test_resolution"]


# F5: dirty / detached candidates are refused before integration.
def test_operator_dispatcher_refuses_ineligible_worktrees(tmp_path):
    a = _governed_lane("lane-a", write_scope="/repo/a/**")
    fanout = _RecordingFanout()

    dirty = WorktreeState(
        committed_sha="c" * 40, detached=False, on_branch="branch-lane-a",
        dirty_paths=["src/x.py"],
    )
    with pytest.raises(TopologyGateError) as exc:
        _dispatch(
            tmp_path, [a], fanout=fanout,
            gate_input=TopologyGateInput(eligibility={"lane-a": dirty}),
        )
    assert "not eligible" in str(exc.value)
    assert fanout.calls == 0

    detached = WorktreeState(
        committed_sha="c" * 40, detached=True, on_branch=None, dirty_paths=[]
    )
    with pytest.raises(TopologyGateError):
        _dispatch(
            tmp_path, [a], fanout=fanout,
            gate_input=TopologyGateInput(eligibility={"lane-a": detached}),
        )
    assert fanout.calls == 0


def test_operator_dispatcher_refuses_committed_but_wrong_branch(tmp_path):
    a = _governed_lane("lane-a", write_scope="/repo/a/**")
    fanout = _RecordingFanout()
    wrong_branch = WorktreeState(
        committed_sha="c" * 40, detached=False,
        on_branch="some-other-branch", dirty_paths=[],
    )
    with pytest.raises(TopologyGateError) as exc:
        _dispatch(
            tmp_path, [a], fanout=fanout,
            gate_input=TopologyGateInput(eligibility={"lane-a": wrong_branch}),
        )
    assert "not eligible" in str(exc.value)
    assert fanout.calls == 0


# green: valid fully governed lanes run exactly once.
def test_operator_dispatcher_valid_governed_lanes_run_once(tmp_path):
    a = _governed_lane("lane-a", write_scope="/repo-a/**")
    b = _governed_lane("lane-b", write_scope="/repo-b/**")
    fanout = _RecordingFanout()
    run, ws = _dispatch(tmp_path, [a, b], fanout=fanout)
    assert fanout.batches == [["lane-a", "lane-b"]], (
        f"disjoint governed lanes run in one batch, got {fanout.batches}"
    )
    assert run.halted is False
    assert set(ws.provisions) == {"lane-a", "lane-b"}


# v1.3.10 compatibility: a non-mutating lane never enters the gate and never
# launches.
def test_operator_dispatcher_non_mutating_lane_is_not_governed(tmp_path):
    non_mutating = {
        "id": "observer",
        "role": "observer",
        "repo": "skillweave/observer",
        "base": _OP_SHA,
        "execution_model": "cold",
        # mutating omitted -> False; no topology fields declared.
    }
    fanout = _RecordingFanout()
    run, ws = _dispatch(tmp_path, [non_mutating], fanout=fanout)
    assert ws.provisions == []
    assert fanout.calls == 0
    assert run.halted is False
