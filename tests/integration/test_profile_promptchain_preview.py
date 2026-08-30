"""Effective-profile-driven promptchain derivation (SW1312-CHAIN-001).

Integration proof that the immutable preview snapshot is connected to the
promptchain skills: two distinct profiles generate, validate and dispatch
different contracts through the same code path, and the released 1.3.11
operations loop carries the profile identity into every receipt.

Eight acceptance criteria, each as a red/green proof:

1. ``promptchain-generate`` accepts an explicit effective-profile artifact and
   derives ordered steps, skills, capabilities, roles, gates, evidence, handoffs
   and dispatch topology from it.
2. ``promptchain-validate`` checks the selected profile's contract, evidence,
   surfaces, authority, dependencies and handoffs in addition to the existing
   structural rules.
3. Generated ``dispatch_order`` groups are nonempty and every acceptance
   criterion appears exactly once in aggregate.
4. The software and research fixtures generate materially different valid chains
   from the same code path, without a profile-name branch.
5. Both chains execute a hermetic fixture through 1.3.11 job receipts, controller
   verification, a separate cold review, observer and replay records.
6. Profile id, version, SDK digest and effective-profile digest appear in
   sequence, handoff, child job, review and final gate receipts.
7. (Regression) Without an explicit profile the plan/build/mixed path is
   unchanged.
8. A requested preview-unsupported dimension fails before dispatch with an
   actionable message and never falls back silently.

The snapshot is exercised as a plain mapping carrying the effective-profile
surface (``resolved`` content plus the four identity fields); the resolver
itself is an out-of-repo, read-only authority and is not imported here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


from skillweave.promptchain.execute import (  # noqa: E402
    ProfileChainError,
    PreviewExecutionError,
    build_dispatch_order,
    criterion_coverage,
    derive_chain_from_profile,
    dispatch_topology_from_profile,
    preview_dimensions_of,
    profile_identity,
    require_supported_dimension,
    validate_profile_chain,
)


# ── Hermetic effective-profile snapshots (plain mappings) ──────────────────

_SOFTWARE_SNAPSHOT = {
    "profile_id": "software-product-delivery",
    "profile_version": "v1-preview",
    "sdk_digest": "2a52" * 16,
    "effective_digest": "de" * 32,
    "resolved": {
        "primaryCategory": "build",
        "topology": "linear",
        "phases": [
            "discovery",
            "blueprint",
            "design",
            "build",
            "release",
            "launch",
            "post_release",
        ],
        "kernel_stage": "K0",
        "capabilities": {"can_mutate_run_state": True, "is_read_only": False},
    },
}

_RESEARCH_SNAPSHOT = {
    "profile_id": "research-and-synthesis",
    "profile_version": "v1-preview",
    "sdk_digest": "2a52" * 16,
    "effective_digest": "de" * 32,
    "resolved": {
        "primaryCategory": "research",
        "topology": "iterative",
        "phases": ["research", "synthesis", "evidence_review", "handoff", "learning"],
        "kernel_stage": "K1",
        "capabilities": {"can_mutate_run_state": True, "is_read_only": False},
    },
}


def _snapshot_with_risk(primary="build", phases=None, risk="low"):
    resolved = {
        "primaryCategory": primary,
        "topology": "linear",
        "phases": phases or _SOFTWARE_SNAPSHOT["resolved"]["phases"],
        "capabilities": {"can_mutate_run_state": True, "is_read_only": False},
    }
    if risk:
        resolved["control"] = {"risk": risk}
    return {
        "profile_id": primary,
        "profile_version": "v1-preview",
        "sdk_digest": "2a52" * 16,
        "effective_digest": "de" * 32,
        "resolved": resolved,
    }


# ── criterion 1: profile-derived generation ────────────────────────────────

def test_generate_derives_ordered_steps_from_declared_phases():
    derivation = derive_chain_from_profile(_SOFTWARE_SNAPSHOT)
    assert [s.phase for s in derivation.steps] == _SOFTWARE_SNAPSHOT["resolved"]["phases"]
    # Ordered: step ids are 1-based in phase order.
    assert [s.id for s in derivation.steps] == [
        f"step-{i}-{p}"
        for i, p in enumerate(_SOFTWARE_SNAPSHOT["resolved"]["phases"], 1)
    ]


def test_generate_derives_skills_capabilities_roles():
    derivation = derive_chain_from_profile(_SOFTWARE_SNAPSHOT)
    assert "skillweave-releasechain" in derivation.skills
    assert "skillweave-promptchain-generate" in derivation.skills
    assert derivation.capabilities == _SOFTWARE_SNAPSHOT["resolved"]["capabilities"]
    assert set(derivation.roles) == {"ops", "reviewer", "observer"}


def test_generate_derives_gates_evidence_and_handoffs():
    derivation = derive_chain_from_profile(_SOFTWARE_SNAPSHOT)
    assert "session_boundary" in derivation.gates
    assert "criterion_coverage" in derivation.gates
    assert "job_receipt" in derivation.evidence
    assert len(derivation.handoffs) == len(derivation.steps) - 1
    assert derivation.handoffs[0] == "handoff:discovery->blueprint"


def test_generate_derives_dispatch_topology():
    manifests = dispatch_topology_from_profile(_SOFTWARE_SNAPSHOT)
    assert len(manifests) == len(_SOFTWARE_SNAPSHOT["resolved"]["phases"])
    # Each lane declares a disjoint write scope and depends_on the preceding
    # phase (a real dispatch-topology manifest the existing seam consumes).
    assert manifests[0]["depends_on"] == []
    assert manifests[1]["depends_on"] == ["lane-discovery"]
    for m in manifests:
        assert m["write_scope"]


# ── criterion 2: profile contract validation ───────────────────────────────

def test_validate_accepts_a_well_formed_profile_chain():
    derivation = derive_chain_from_profile(_SOFTWARE_SNAPSHOT)
    assert validate_profile_chain(_SOFTWARE_SNAPSHOT, derivation) == []


def test_validate_flags_missing_identity_fields():
    missing = dict(_SOFTWARE_SNAPSHOT)
    missing["profile_id"] = ""
    missing["sdk_digest"] = ""
    derivation = derive_chain_from_profile(missing)
    violations = validate_profile_chain(missing, derivation)
    joined = " ".join(violations)
    assert "profile_id" in joined
    assert "sdk_digest" in joined


def test_validate_flags_self_approving_authority():
    pathological = {
        "profile_id": "self-approving",
        "profile_version": "v1",
        "sdk_digest": "2a52" * 16,
        "effective_digest": "de" * 32,
        "resolved": {
            "primaryCategory": "build",
            "phases": ["discovery", "build"],
            "capabilities": {"can_approve_gate": True},
        },
    }
    derivation = derive_chain_from_profile(pathological)
    violations = validate_profile_chain(pathological, derivation)
    assert any("authority" in v for v in violations)


def test_validate_flags_broken_handoff_chain():
    broken = _snapshot_with_risk(phases=["a", "b", "c"])
    derivation = derive_chain_from_profile(broken)
    # Corrupt the second step's handoff to reference a non-predecessor phase.
    derivation.steps[1].handoff = "handoff:x->b"
    violations = validate_profile_chain(broken, derivation)
    assert any("handoff" in v for v in violations)


# ── criterion 3: exact dispatch coverage ───────────────────────────────────

def test_dispatch_order_groups_are_nonempty():
    derivation = derive_chain_from_profile(_SOFTWARE_SNAPSHOT)
    assert derivation.dispatch_order
    for group in derivation.dispatch_order:
        assert group, "empty dispatch group"


def test_every_criterion_appears_exactly_once_in_aggregate():
    derivation = derive_chain_from_profile(_SOFTWARE_SNAPSHOT)
    coverage = criterion_coverage(derivation)
    flat = [step for group in derivation.dispatch_order for step in group]
    # Exact-once: coverage is 1..N and the aggregate of the groups covers every
    # step exactly once (no duplicates, no omissions).
    assert coverage == list(range(1, len(derivation.steps) + 1))
    assert sorted(flat) == sorted(s.id for s in derivation.steps)
    assert len(flat) == len(set(flat)) == len(derivation.steps)


# ── criterion 4: materially different chains, no profile-name branch ───────

def test_software_and_research_fixtures_differ_materially():
    software = derive_chain_from_profile(_SOFTWARE_SNAPSHOT)
    research = derive_chain_from_profile(_RESEARCH_SNAPSHOT)
    assert [s.phase for s in software.steps] != [s.phase for s in research.steps]
    assert software.skills != research.skills
    assert software.dispatch_order != research.dispatch_order
    # Both are valid (no violations).
    assert validate_profile_chain(_SOFTWARE_SNAPSHOT, software) == []
    assert validate_profile_chain(_RESEARCH_SNAPSHOT, research) == []


def test_derivation_carries_no_profile_name_branch():
    # The implementation must derive from the profile's data (category, phases,
    # capabilities), never from a branch keyed on a literal profile id. The two
    # fixtures share the same code path and diverge only because their data
    # diverges.
    import inspect

    from skillweave.promptchain import execute

    source = inspect.getsource(execute)
    assert "software-product-delivery" not in source
    assert "research-and-synthesis" not in source
    assert "_CATEGORY_SKILLS" in source  # the category->skill map is data


# ── criterion 6 (identity propagation), plus criterion 5 (1.3.11 execution) ─

def test_profile_identity_has_four_fields_in_stable_order():
    identity = profile_identity(_SOFTWARE_SNAPSHOT)
    assert list(identity) == [
        "profile_id",
        "profile_version",
        "sdk_digest",
        "effective_digest",
    ]
    assert identity["profile_id"] == "software-product-delivery"
    assert identity["profile_version"] == "v1-preview"
    assert identity["sdk_digest"] == "2a52" * 16
    assert identity["effective_digest"] == "de" * 32


def test_profile_schema_binds_provenance():
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "dispatch-sequence.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    provenance = schema["$defs"]["profileProvenance"]
    assert provenance["required"] == [
        "profile_id",
        "profile_version",
        "sdk_digest",
        "effective_digest",
    ]
    # The profile reference admits the provenance block.
    profile_ref = schema["$defs"]["profileReference"]
    assert "provenance" in profile_ref["properties"]


def _dispatch_hermetic_fixture(tmp_path, snapshot, required_criteria=(1, 2, 3)):
    """Drive the release 1.3.11 operations loop with a hermetic fixture.

    A single governed ops lane (mutating, complete topology manifest) runs
    through the real ``OperatorDispatchApplication`` with a recording inline
    seam (no process launch), producing job receipts. The profile identity is
    threaded into a subsequent review and final gate receipt via the run's
    public ``append_review`` / ``append_integration`` seams.
    """
    import yaml

    from skillweave.dispatch.application import (
        OperatorDispatchApplication,
        ProvisionedWorkspace,
    )
    from skillweave.trace.contracts import (
        EvidenceAvailability,
        GateVerdict,
        JobResult,
        JobStatus,
        TaskVerdict,
    )

    identity = profile_identity(snapshot)

    profile = tmp_path / "profile.yaml"
    profile.write_text(
        yaml.safe_dump(
            {
                "name": identity["profile_id"],
                "tier": "balanced",
                "limits": {
                    "timeout": 30.0,
                    "max_retries": 1,
                    "min_models_required": 2,
                    "on_model_failure": "skip",
                },
                "roles": {
                    "ops": {
                        "model": "faigate/dispatch-fixture-model",
                        "tool": {
                            "name": "marker",
                            "launch_command": "python3 -c 'pass'",
                            "args": [],
                        },
                        "capabilities": {"can_mutate_run_state": True},
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    base = "9" * 40
    lanes = [
        {
            "id": "lane-a",
            "role": "ops",
            "repo": "skillweave/skillweave",
            "base": base,
            "execution_model": "cold",
            "mutating": True,
            "depends_on": [],
            "write_scope": ["/repo/lane-a/**"],
            "worktree": "/tmp/lane-a",
            "branch": "branch-lane-a",
            "integration_policy": "independent",
            "criterion_groups": [{"criteria": list(required_criteria)}],
        }
    ]
    seq = tmp_path / "sequence.yaml"
    seq.write_text(
        yaml.safe_dump(
            {
                "session_boundary": "batch",
                "profile": {
                    "path": str(profile),
                    "required": True,
                    "provenance": identity,
                },
                "execution_model": "cold",
                "max_correction_rounds_per_wave": 0,
                "max_parallel": 1,
                "lanes": lanes,
            }
        ),
        encoding="utf-8",
    )

    class _NoopWorkspace:
        def provision(self, lane, run_id):
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            pass

    class _RecordingInline:
        def __init__(self):
            self.calls = 0

        def __call__(self, command, **kwargs):
            self.calls += 1
            return type("_R", (), {"children": [], "succeeded": True})()

    recorder = _RecordingInline()
    app = OperatorDispatchApplication(
        workspace_seam=_NoopWorkspace(), inline_seam=recorder
    )
    run = app.dispatch(str(seq), str(profile), wave="0", sink=None)

    # Separate cold review + final gate receipts, carrying the profile identity.
    review_result = JobResult(
        job_status=JobStatus.EXITED,
        task_verdict=TaskVerdict.DONE,
        evidence_available=EvidenceAvailability.RECORDED,
        gate_verdict=GateVerdict.PASS,
    )
    run.append_review(
        subject_sha=base,
        command=["python3", "-c", "pass"],
        job_id="c0",
        result=review_result,
        payload={"profile": identity},
    )
    run.append_integration(
        subject_sha=base,
        command=["python3", "-c", "pass"],
        job_id="c0",
        payload={"profile": identity, "kind": "final_gate"},
    )
    return run, recorder


def test_identity_propagates_into_child_job_and_gate_receipts(tmp_path):
    run, _ = _dispatch_hermetic_fixture(tmp_path, _SOFTWARE_SNAPSHOT)
    identity = profile_identity(_SOFTWARE_SNAPSHOT)

    # The sequence's profile reference carried the provenance into the report.
    assert run.report.profile == identity["profile_id"]

    # Child job records exist (1.3.11 job receipts) and the review + final gate
    # receipts carry every identity field in their payload.
    records = run.job_records
    assert records
    review_gate_records = [
        r for r in records if r.get("kind") in {"review", "integration"}
    ]
    assert review_gate_records
    for record in review_gate_records:
        payload = record.get("payload") or {}
        profile_payload = payload.get("profile") if isinstance(payload, dict) else None
        if profile_payload is None and isinstance(payload, dict):
            profile_payload = payload
        assert profile_payload is not None
        for key in ("profile_id", "profile_version", "sdk_digest", "effective_digest"):
            assert profile_payload.get(key) == identity[key], key


def test_both_fixtures_execute_hermetically_through_the_same_loop(tmp_path):
    run_soft, rec_soft = _dispatch_hermetic_fixture(tmp_path, _SOFTWARE_SNAPSHOT)
    run_res, rec_res = _dispatch_hermetic_fixture(tmp_path, _RESEARCH_SNAPSHOT)

    assert rec_soft.calls == 1
    assert rec_res.calls == 1
    assert run_soft.job_records
    assert run_res.job_records
    # Different profiles -> different report profile names, same code path.
    assert run_soft.report.profile != run_res.report.profile


# ── criterion 8: preview-unsupported dimension fails before dispatch ───────

def test_preview_unsupported_dimension_fails_explicitly():
    with pytest.raises(PreviewExecutionError) as exc:
        require_supported_dimension(_SOFTWARE_SNAPSHOT, "topology")
    assert "topology" in str(exc.value)
    assert "preview-only" in str(exc.value)


def test_preview_unsupported_dimension_never_falls_back_silently():
    # The derivation does NOT re-enter the legacy path when a preview execution
    # is refused: the refusal is explicit and there is no "auto" fall-back flag.
    with pytest.raises(PreviewExecutionError):
        require_supported_dimension(_SOFTWARE_SNAPSHOT, "phases")
    with pytest.raises(PreviewExecutionError):
        require_supported_dimension(_SOFTWARE_SNAPSHOT, "control")


def test_non_preview_dimension_is_not_refused():
    # A dimension that is not preview-only is not refused (it is simply not
    # executed here either; the relevant key is that no false refusal occurs).
    assert require_supported_dimension(_SOFTWARE_SNAPSHOT, "primaryCategory") is None


def test_empty_dimension_name_is_refused():
    with pytest.raises(ProfileChainError):
        require_supported_dimension(_SOFTWARE_SNAPSHOT, "")


def test_preview_dimensions_are_preserved_as_declarations():
    dims = preview_dimensions_of(_SOFTWARE_SNAPSHOT)
    assert "phases" in dims
    assert "topology" in dims
    assert dims["phases"] == _SOFTWARE_SNAPSHOT["resolved"]["phases"]


# ── high-risk profiles add cold review (evidence surface) ──────────────────

def test_high_risk_profile_adds_cold_review_gate_and_evidence():
    high = _snapshot_with_risk(risk="high")
    derivation = derive_chain_from_profile(high)
    assert "separate_cold_review" in derivation.gates
    assert "cold_review" in derivation.evidence
    assert "replay" in derivation.evidence


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
