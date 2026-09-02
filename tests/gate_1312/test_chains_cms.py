"""Dispatch-order group 3 — profile chains and CMS through 1.3.11 contracts (criterion 4).

Both profile chains (software-product-delivery and research-and-synthesis) and
all four CMS scenarios execute through the *released 1.3.11* contracts:

* **receipt** — ``skillweave.trace.contracts`` append-only receipts;
* **review** — ``skillweave.trace.review`` dual-review authority / disposition;
* **observer** — ``skillweave.dispatch.observer`` read-only negative authority;
* **replay** — ``skillweave.trace.projection`` deterministic replay;
* **authority** — ``skillweave.runtime.authority`` role capability matrix.

No CMS scenario introduces a Core branch; the CMS pack and its four scenarios
are data resolved through the shared routing-profile and dispatch contracts.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
import yaml

from tests.gate_1312 import _sibling as sib
from tests.gate_1312._sibling import require

SCENARIOS = (
    "cms-landing-page",
    "cms-recurring-maintenance",
    "cms-content-seo",
    "cms-incident-rollback",
)

PRODUCER_FORBIDDEN = {"self_approve", "publish"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _sequence(name: str) -> dict:
    return _load(sib.cms_scenarios_dir() / name / "sequence.yaml")


def _dispatch_profile(name: str) -> dict:
    return _load(sib.cms_scenarios_dir() / name / "dispatch-profile.yaml")


def test_criterion_04_chains_and_cms_through_1_3_11_contracts():
    """Profile chains + every CMS scenario resolve through the released 1.3.11
    receipt / review / observer / replay / authority contracts, with no CMS
    special-casing in Core.
    """
    require(sib.cms_scenarios_dir, name="skillweave-packs-pro")
    require(sib.cms_pack_dir, name="skillweave-packs-pro")
    # --- Receipt contract -------------------------------------------------------
    from skillweave.trace import contracts as C

    log = C.AppendOnlyReceiptLog()
    r = C.new_append_only_round(
        log, parent_id=None, round_=1, kind=C.RoundKind.DISPATCH, job_id="job-1",
        result=C.JobResult(
            job_status=C.JobStatus.EXITED,
            task_verdict=C.TaskVerdict.DONE,
            evidence_available=C.EvidenceAvailability.RECORDED,
            gate_verdict=C.GateVerdict.PASS,
        ),
    )
    assert log.resolve_id(r.record_id) is r
    assert r.digest

    # --- Review contract (dual-review authority, fail-closed) -------------------
    from skillweave.trace import review as R
    from skillweave.runtime.authority import Role

    # Producer and reviewer are distinct roles; reviewer is read-only.
    # REVIEWER cannot mutate run state; OPS cannot approve a gate.
    from skillweave.runtime.authority import (
        can_mutate_run_state,
        can_approve_gate,
        is_read_only,
    )
    assert can_mutate_run_state(Role.OPS.value) is True
    assert can_approve_gate(Role.OPS.value) is False
    assert can_mutate_run_state(Role.REVIEWER.value) is False
    assert can_approve_gate(Role.REVIEWER.value) is True
    assert is_read_only(Role.REVIEWER.value) is True
    assert R.ReviewVerdict.REVIEW_PASS.value == "REVIEW_PASS"

    # --- Observer contract (read-only negative authority) -----------------------
    from skillweave.dispatch.observer import assert_observer_authority
    assert_observer_authority("observe")
    for forbidden in ("dispatch", "cancel", "write", "mutate", "commit", "release"):
        with pytest.raises(Exception):
            assert_observer_authority(forbidden)

    # --- Replay contract (deterministic projection) ------------------------------
    from skillweave.trace.projection import Projector

    projector = Projector(run_id="run-1")
    projection = projector.projection()
    assert projection.run.run_id == "run-1"

    # --- Every CMS sequence resolves through the dispatch + profile contracts ---
    import skillweave.dispatch.contracts as dc
    import skillweave.dispatch.profile_resolution as pr

    for name in SCENARIOS:
        seq = _sequence(name)
        decl = dc.load_sequence(seq)
        assert decl.profile.required is True
        dc.validate_for_dispatch(decl, decl.mutating_lanes()[0].criteria_covered())

        profile_path = sib.cms_scenarios_dir() / name / "dispatch-profile.yaml"
        resolved = pr.resolve_dispatch_profile(
            str(profile_path), ["ops", "reviewer", "observer"]
        )
        assert {"ops", "reviewer", "observer"} <= set(resolved.roles)
        for key, role in resolved.roles.items():
            assert role.profile == resolved.profile_name
            assert role.limits is not None

    # --- No CMS branch / subject / role in Core vocabulary ----------------------
    for module in (dc, pr):
        low = inspect.getsource(module).lower()
        assert "cms" not in low

    # --- CMS pack roles dissolve onto documented packs-pro authority ------------
    pack_process = _load(sib.cms_pack_dir() / "process.yaml")["process"]
    role_ids = {r["id"] for r in pack_process["roles"]}
    assert role_ids == {"decision-owner", "cms-ops-producer", "independent-reviewer",
                        "publish-approver", "observer"}
    producer = next(r for r in pack_process["roles"] if r["id"] == "cms-ops-producer")
    assert set(producer["cannot"]) == PRODUCER_FORBIDDEN
    assert producer["mutates"] is True
    publish = next(r for r in pack_process["roles"] if r["id"] == "publish-approver")
    assert publish["distinctFrom"] == ["cms-ops-producer"]


def test_both_profile_chains_validate_against_preview_schema():
    """Both OSS profile chains stay valid previews against the pinned SDK schema."""
    require(sib.base_profiles_dir, name="skillweave-profiles")
    require(sib.sdk_validator_module, name="skillweave-sdk")
    validator = sib.sdk_validator_module()
    schemas = sib.sdk_schemas_dir()
    work = "https://skillweave.dev/schemas/work-profile/0.1.0"
    life = "https://skillweave.dev/schemas/lifecycle-profile/0.1.0"
    for pid in ("software-product-delivery", "research-and-synthesis"):
        doc = _load(sib.base_profiles_dir() / f"{pid}.v1-preview.yaml")
        assert validator.validate(doc["workProfile"], work, schemas) == []
        assert validator.validate(doc["lifecycleProfile"], life, schemas) == []
        assert validator.lifecycle_profile_errors(doc["lifecycleProfile"]) == []


def test_cms_pack_is_not_a_third_base_profile():
    """The CMS pack declares itself special/domain, never a third base profile."""
    require(sib.cms_pack_dir, name="skillweave-packs-pro")
    pack = _load(sib.cms_pack_dir() / "pack.yaml")["pack"]
    assert pack["declaresNot"]["lifecycleProfile"] is True
    assert pack["declaresNot"]["coreExtension"] is True
    assert pack["packType"] == "domain"
    assert pack["providerBound"] is True
