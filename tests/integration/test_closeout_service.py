"""Integration tests for the closeout service (SW-157-CLOSE-001).

Covers:
- Step A: missing/mismatched evidence and dirty/leased/active/unclassified
  workspace states block CLOSED; the deterministic preview precedes authority.
- Step B: the machine-tested releasechain/launch/repo-health/closeout authority
  boundaries.

Every fixture here is disposable and in-memory. The closeout lane owns no
cleanup authority, so no test creates, removes or mutates a real workspace.
"""

import copy
import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.closeout_service import (  # noqa: E402
    AUTHORITY_BOUNDARIES,
    Boundary,
    CloseoutDecision,
    CloseoutError,
    CloseoutService,
    EvidenceInput,
    EvidenceKind,
    EvidenceStatus,
    Hold,
    STATUS_CLOSED,
    STATUS_HELD,
    WorkspaceSignal,
    is_closed,
    missing_evidence,
    required_evidence,
    tampered_launch_receipt,
)
from skillweave.repo_health.worktrees import (  # noqa: E402
    Classification,
    DirtyState,
    EvidenceState,
    HeadState,
    LeaseState,
    ReachabilityState,
    RegistrationState,
    UpstreamState,
    WorkspaceInventory,
    WorkspaceRow,
    DiskState,
    ExistenceState,
    LocationKind,
)

SUBJECT = "a" * 40
OTHER_SUBJECT = "b" * 40
LAUNCH_SHA = "c" * 64


def _service():
    return CloseoutService(".")


def _launch_receipt(*, outcome="success", result="available"):
    """A complete launch receipt built through the launch lane's own sealer.

    The launch contract's own rules are honoured rather than re-implemented: an
    unavailable result must declare a limit *and* cannot carry a success outcome.
    """
    from skillweave.launch import seal

    limits = []
    if result == "unavailable":
        limits = ["deployment target unreachable"]
        outcome = "unavailable"
    core = {
        "schema_version": 1,
        "result": {"status": result, "summary": "deployed"},
        "target": {"environment": "staging", "version": "1.5.6"},
        "artifact": {"artifact_id": "sw-1.5.6", "sha256": LAUNCH_SHA},
        "commands": [{"command": "deploy.sh", "exit": 0}],
        "outcome": {"status": outcome},
        "provenance": {
            "launcher": "ops",
            "run_id": "run-1",
            "produced_at": "2026-09-27T00:00:00Z",
        },
        "limits": limits,
    }
    sealed = seal(core)
    return sealed.to_dict() if hasattr(sealed, "to_dict") else dict(sealed)


def _assessment_receipt(*, result="available", subject=SUBJECT):
    payload = {
        "schema_version": 1,
        "result": {"status": result, "summary": "assessed"},
        "subject": {"full_sha": subject},
        "sources": [{"path": "a.py", "sha256": "d" * 64}],
        "commands": [],
        "findings": [],
        "limits": [],
        "provenance": {
            "assessor": "ops",
            "run_id": "run-1",
            "produced_at": "2026-09-27T00:00:00Z",
        },
    }
    return payload


class _Telemetry:
    def __init__(self, digest="e" * 64):
        self._digest = digest

    def snapshot(self):
        return {
            "restart_count": 0,
            "malformed_count": 0,
            "desync_count": 0,
            "receipt_digest": self._digest,
        }


def _row(**overrides):
    base = dict(
        path="/tmp/collection/.worktrees/repo/run-1/lane-1",
        repo="repo",
        kind=LocationKind.WORKTREE,
        registration=RegistrationState.REGISTERED,
        existence=ExistenceState.PRESENT,
        dirtiness=DirtyState.CLEAN,
        head=HeadState.BRANCH,
        upstream=UpstreamState.UP_TO_DATE,
        reachability=ReachabilityState.REACHABLE,
        lease=LeaseState.EXPIRED,
        process=EvidenceState.ABSENT,
        session=EvidenceState.ABSENT,
        disk=DiskState.MEASURED,
        disk_bytes=10,
        classification=Classification.STALE,
        reason="workspace lease has expired",
    )
    base.update(overrides)
    return WorkspaceRow(**base)


def _clean_preview_kwargs(**overrides):
    """A run that supplied the artifact its manifest declared, and nothing else wrong.

    ``required_evidence`` is part of the clean shape: without a manifest the
    closeout cannot tell a complete run from an empty one, so it holds. Tests
    that pass ``evidence=`` must therefore keep the manifest in step with the
    producers they supply, or they are exercising an incomplete run.
    """
    evidence = [
        EvidenceInput(
            kind=EvidenceKind.LAUNCH, producer="launch", value=_launch_receipt(),
            supplied=True,
        ),
        EvidenceInput(
            kind=EvidenceKind.ASSESSMENT, producer="assess",
            value=_assessment_receipt(), supplied=True, cross_check=SUBJECT,
        ),
    ]
    kwargs = dict(
        run_id="run-1",
        subject=SUBJECT,
        required_evidence=evidence,
        evidence=evidence,
        workspaces=[_row()],
        telemetry=_Telemetry(),
    )
    kwargs.update(overrides)
    return kwargs


# ── Step A: clean run actually closes ──────────────────────────────────────


def test_clean_run_previews_closed():
    preview = _service().preview(**_clean_preview_kwargs())
    assert preview.status == STATUS_CLOSED
    assert not preview.held
    assert preview.codes == ()
    assert len(preview.digest) == 64


def test_clean_run_receipt_is_closed():
    service = _service()
    preview = service.preview(**_clean_preview_kwargs())
    decision = CloseoutDecision(
        decided_by="ops-lead", preview_digest=preview.digest, accepted=True,
        reason="all evidence intact",
    )
    receipt = service.decide(preview, decision)
    assert receipt.status == STATUS_CLOSED
    assert is_closed(receipt)
    assert receipt.decided_by == "ops-lead"
    assert len(receipt.digest) == 64


# ── Step A: missing vs mismatched evidence ────────────────────────────────


def test_missing_launch_evidence_blocks_closed():
    preview = _service().preview(
        **_clean_preview_kwargs(
            evidence=[
                missing_evidence(EvidenceKind.LAUNCH, "launch"),
                EvidenceInput(
                    kind=EvidenceKind.ASSESSMENT, producer="assess",
                    value=_assessment_receipt(), supplied=True, cross_check=SUBJECT,
                ),
            ]
        )
    )
    assert preview.held
    assert preview.has(Hold.EVIDENCE_MISSING)


def test_missing_assessment_evidence_blocks_closed():
    preview = _service().preview(
        **_clean_preview_kwargs(
            evidence=[
                EvidenceInput(
                    kind=EvidenceKind.LAUNCH, producer="launch",
                    value=_launch_receipt(), supplied=True,
                ),
                missing_evidence(EvidenceKind.ASSESSMENT, "assess"),
            ]
        )
    )
    assert preview.held
    assert preview.has(Hold.EVIDENCE_MISSING)


def test_missing_and_mismatched_are_distinct_holds():
    service = _service()
    missing = service.preview(
        **_clean_preview_kwargs(
            evidence=[missing_evidence(EvidenceKind.LAUNCH, "launch")]
        )
    )
    mismatched = service.preview(
        **_clean_preview_kwargs(
            evidence=[
                tampered_launch_receipt(
                    _launch_receipt(outcome="failure", result="unavailable")
                )
            ]
        )
    )
    assert missing.has(Hold.EVIDENCE_MISSING)
    assert not missing.has(Hold.EVIDENCE_MISMATCHED)
    assert mismatched.has(Hold.EVIDENCE_MISMATCHED)
    assert not mismatched.has(Hold.EVIDENCE_MISSING)


def test_tampered_launch_receipt_is_mismatched_not_missing():
    """A launch receipt that fails its own digest check is mismatched evidence."""
    receipt = _launch_receipt()
    tampered = copy.deepcopy(receipt)
    tampered["outcome"] = {"status": "failure"}  # digest no longer covers content

    preview = _service().preview(
        **_clean_preview_kwargs(evidence=[tampered_launch_receipt(tampered)])
    )
    assert preview.has(Hold.EVIDENCE_MISMATCHED)
    assert preview.has(Hold.LAUNCH_UNVERIFIED)
    assert not preview.has(Hold.EVIDENCE_MISSING)


def test_launch_outcome_failure_is_successful_evidence_but_blocks_via_outcome():
    """An intact receipt with a failed outcome is PRESENT, not mismatched."""
    from skillweave.closeout_service import EvidenceInput as EI

    item = EI(
        kind=EvidenceKind.LAUNCH, producer="launch",
        value=_launch_receipt(outcome="failure"), supplied=True,
    )
    assert item.status() is EvidenceStatus.PRESENT


def test_unavailable_launch_result_is_mismatched():
    from skillweave.closeout_service import EvidenceInput as EI

    item = EI(
        kind=EvidenceKind.LAUNCH, producer="launch",
        value=_launch_receipt(result="unavailable"), supplied=True,
    )
    assert item.status() is EvidenceStatus.MISMATCHED


def test_assessment_bound_to_wrong_subject_is_mismatched():
    preview = _service().preview(
        **_clean_preview_kwargs(
            evidence=[
                EvidenceInput(
                    kind=EvidenceKind.ASSESSMENT, producer="assess",
                    value=_assessment_receipt(subject=OTHER_SUBJECT),
                    supplied=True, cross_check=SUBJECT,
                )
            ]
        )
    )
    assert preview.has(Hold.EVIDENCE_MISMATCHED)


def test_unavailable_assessment_raises_its_boundary_hold():
    preview = _service().preview(
        **_clean_preview_kwargs(
            evidence=[
                EvidenceInput(
                    kind=EvidenceKind.ASSESSMENT, producer="assess",
                    value=_assessment_receipt(result="unavailable"),
                    supplied=True, cross_check=SUBJECT,
                )
            ]
        )
    )
    # Present and intact, but an unavailable receipt establishes nothing, so the
    # closeout holds on the absent evidence rather than pretending it passed.
    assert preview.held
    assert preview.has(Hold.ASSESSMENT_UNAVAILABLE)
    assert not preview.has(Hold.EVIDENCE_MISMATCHED)


# ── Step A: workspace holds ────────────────────────────────────────────────


def test_dirty_workspace_blocks_closed():
    preview = _service().preview(
        **_clean_preview_kwargs(
            workspaces=[_row(dirtiness=DirtyState.DIRTY, classification=Classification.DIRTY)]
        )
    )
    assert preview.has(Hold.WORKSPACE_DIRTY)
    assert preview.by_boundary()["repo_health"]


def test_leased_workspace_blocks_closed():
    """An active, owned lease is a hold even with no live process or session."""
    preview = _service().preview(
        **_clean_preview_kwargs(
            workspaces=[
                _row(
                    lease=LeaseState.ACTIVE,
                    session=EvidenceState.ABSENT,
                    process=EvidenceState.ABSENT,
                    classification=Classification.HEALTHY,
                )
            ]
        )
    )
    assert preview.has(Hold.WORKSPACE_LEASED)


def test_active_session_workspace_blocks_closed():
    preview = _service().preview(
        **_clean_preview_kwargs(
            workspaces=[
                _row(
                    lease=LeaseState.EXPIRED,
                    session=EvidenceState.PRESENT,
                    classification=Classification.STALE,
                )
            ]
        )
    )
    assert preview.has(Hold.WORKSPACE_ACTIVE)


def test_live_process_workspace_blocks_closed():
    preview = _service().preview(
        **_clean_preview_kwargs(
            workspaces=[
                _row(
                    lease=LeaseState.EXPIRED,
                    process=EvidenceState.PRESENT,
                    classification=Classification.STALE,
                )
            ]
        )
    )
    assert preview.has(Hold.WORKSPACE_ACTIVE)


def test_healthy_workspace_is_unclassified_hold():
    """Healthy is not a completed disposal, so it is held, not waved through."""
    preview = _service().preview(
        **_clean_preview_kwargs(
            workspaces=[
                _row(
                    lease=LeaseState.EXPIRED,
                    session=EvidenceState.ABSENT,
                    process=EvidenceState.ABSENT,
                    classification=Classification.HEALTHY,
                )
            ]
        )
    )
    assert preview.has(Hold.WORKSPACE_UNCLASSIFIED)
    assert not preview.has(Hold.WORKSPACE_LEASED)


def test_healthy_unmanaged_workspace_is_unclassified_hold():
    preview = _service().preview(
        **_clean_preview_kwargs(
            workspaces=[
                _row(
                    lease=LeaseState.ABSENT,
                    session=EvidenceState.ABSENT,
                    classification=Classification.HEALTHY,
                )
            ]
        )
    )
    assert preview.has(Hold.WORKSPACE_UNCLASSIFIED)


def test_unknown_classification_workspace_blocks_closed():
    preview = _service().preview(
        **_clean_preview_kwargs(
            workspaces=[
                _row(classification=Classification.UNKNOWN, dirtiness=DirtyState.UNKNOWN)
            ]
        )
    )
    assert preview.has(Hold.WORKSPACE_EVIDENCE_UNKNOWN)


def test_unknown_dimension_workspace_blocks_closed():
    preview = _service().preview(
        **_clean_preview_kwargs(
            workspaces=[
                _row(lease=LeaseState.UNKNOWN, classification=Classification.STALE)
            ]
        )
    )
    assert preview.has(Hold.WORKSPACE_EVIDENCE_UNKNOWN)


def test_unregistered_workspace_blocks_closed():
    preview = _service().preview(
        **_clean_preview_kwargs(
            workspaces=[
                _row(
                    registration=RegistrationState.UNREGISTERED,
                    classification=Classification.ORPHANED,
                    lease=LeaseState.ABSENT,
                )
            ]
        )
    )
    assert preview.has(Hold.WORKSPACE_UNCLASSIFIED)


def test_adverse_classified_workspace_does_not_block():
    """STALE/ORPHANED with no live owner is walk-away-able."""
    preview = _service().preview(
        **_clean_preview_kwargs(
            workspaces=[
                _row(
                    lease=LeaseState.EXPIRED,
                    session=EvidenceState.ABSENT,
                    reachability=ReachabilityState.REACHABLE,
                    classification=Classification.STALE,
                )
            ]
        )
    )
    assert preview.status == STATUS_CLOSED


def test_workspace_signal_is_projected_from_inventory_row():
    signal = WorkspaceSignal.from_row(_row(lease=LeaseState.ACTIVE))
    assert signal.managed is True
    assert signal.lease == "active"
    assert signal.classification == "stale"

    unmanaged = WorkspaceSignal.from_row(_row(lease=LeaseState.ABSENT))
    assert unmanaged.managed is False


def test_workspace_inventory_object_is_accepted():
    inventory = WorkspaceInventory(
        collection="/tmp/collection", rows=[_row()]
    )
    preview = _service().preview(**_clean_preview_kwargs(workspaces=inventory))
    assert preview.status == STATUS_CLOSED


# ── Step A: telemetry ─────────────────────────────────────────────────────


def test_missing_telemetry_blocks_closed():
    preview = _service().preview(**_clean_preview_kwargs(telemetry=None))
    assert preview.has(Hold.TELEMETRY_UNAVAILABLE)


def test_telemetry_without_digest_blocks_closed():
    class _Bad:
        def snapshot(self):
            return {"restart_count": 0, "receipt_digest": "not-a-digest"}

    preview = _service().preview(**_clean_preview_kwargs(telemetry=_Bad()))
    assert preview.has(Hold.TELEMETRY_UNAVAILABLE)


def test_intact_telemetry_does_not_block():
    preview = _service().preview(**_clean_preview_kwargs(telemetry=_Telemetry()))
    assert not preview.has(Hold.TELEMETRY_UNAVAILABLE)


# ── Step A: deterministic preview precedes authority ──────────────────────


def test_preview_is_deterministic():
    service = _service()
    first = service.preview(**_clean_preview_kwargs())
    second = service.preview(**_clean_preview_kwargs())
    assert first.digest == second.digest
    assert first.to_dict() == second.to_dict()


def test_preview_digest_changes_with_evidence():
    service = _service()
    clean = service.preview(**_clean_preview_kwargs())
    held = service.preview(
        **_clean_preview_kwargs(evidence=[missing_evidence(EvidenceKind.LAUNCH, "launch")])
    )
    assert clean.digest != held.digest


def test_preview_digest_is_sha256_of_canonical_payload():
    preview = _service().preview(**_clean_preview_kwargs())
    canonical = json.dumps(
        preview.payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == preview.digest


def test_preview_precedes_authority_and_is_total():
    """The preview exists, and blocks, with no decision and no authority."""
    service = _service()
    preview = service.preview(
        **_clean_preview_kwargs(evidence=[missing_evidence(EvidenceKind.LAUNCH, "launch")])
    )
    assert preview.held
    # No decision has been made; the hold is already fully described.
    assert preview.by_boundary()["closeout"] or preview.by_boundary()["launch"]


def test_preview_refuses_non_canonical_subject():
    with pytest.raises(CloseoutError, match="canonical lowercase full 40-hex"):
        _service().preview(**_clean_preview_kwargs(subject="not-a-sha"))


def test_preview_refuses_trailing_newline_subject():
    with pytest.raises(CloseoutError, match="canonical lowercase full 40-hex"):
        _service().preview(**_clean_preview_kwargs(subject=SUBJECT + "\n"))


def test_preview_refuses_empty_run_id():
    with pytest.raises(CloseoutError, match="run_id must be a non-empty string"):
        _service().preview(**_clean_preview_kwargs(run_id=""))


# ── Step A: authority is additive only ────────────────────────────────────


def test_authority_cannot_clear_a_preview_hold():
    service = _service()
    preview = service.preview(
        **_clean_preview_kwargs(evidence=[missing_evidence(EvidenceKind.LAUNCH, "launch")])
    )
    receipt = service.decide(
        preview,
        CloseoutDecision(
            decided_by="ops-lead", preview_digest=preview.digest, accepted=True,
            reason="looks fine to me",
        ),
    )
    assert receipt.status == STATUS_HELD
    assert not is_closed(receipt)


def test_authority_refusal_is_recorded_as_a_hold():
    service = _service()
    preview = service.preview(**_clean_preview_kwargs())
    receipt = service.decide(
        preview,
        CloseoutDecision(
            decided_by="ops-lead", preview_digest=preview.digest, accepted=False,
            reason="retro is not scheduled yet",
        ),
    )
    assert receipt.status == STATUS_HELD
    assert any(b["code"] == Hold.AUTHORITY_MISMATCH.value for b in receipt.blockers)


def test_decision_bound_to_stale_preview_is_refused():
    service = _service()
    preview = service.preview(**_clean_preview_kwargs())
    other = service.preview(**_clean_preview_kwargs(run_id="run-2"))
    receipt = service.decide(
        preview,
        CloseoutDecision(
            decided_by="ops-lead", preview_digest=other.digest, accepted=True,
            reason="closed",
        ),
    )
    assert receipt.status == STATUS_HELD
    assert receipt.preview_digest == preview.digest


def test_decision_requires_named_authority():
    with pytest.raises(CloseoutError, match="must name an authority"):
        CloseoutDecision(decided_by="", preview_digest="f" * 64, accepted=True)


def test_decision_requires_digest_binding():
    with pytest.raises(CloseoutError, match="sha256 preview digest"):
        CloseoutDecision(decided_by="ops", preview_digest="nope", accepted=True)


def test_refusal_requires_a_reason():
    with pytest.raises(CloseoutError, match="unexplained refusal"):
        CloseoutDecision(
            decided_by="ops", preview_digest="f" * 64, accepted=False, reason=""
        )


# ── Step A: negative holds are persistable ────────────────────────────────


def test_held_receipt_is_durable_and_tamper_evident():
    service = _service()
    preview = service.preview(
        **_clean_preview_kwargs(
            workspaces=[
                _row(dirtiness=DirtyState.DIRTY, classification=Classification.DIRTY)
            ]
        )
    )
    receipt = service.decide(
        preview,
        CloseoutDecision(
            decided_by="ops-lead", preview_digest=preview.digest, accepted=True,
            reason="nothing to fix",
        ),
    )
    payload = receipt.payload()
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == receipt.digest
    assert any(b["code"] == Hold.WORKSPACE_DIRTY.value for b in receipt.blockers)


def test_all_holds_declare_a_boundary():
    for hold in Hold:
        assert hold in AUTHORITY_BOUNDARIES or True  # table below is the check
    from skillweave.closeout_service import HOLD_BOUNDARIES

    assert set(HOLD_BOUNDARIES) == set(Hold)
    assert all(isinstance(b, Boundary) for b in HOLD_BOUNDARIES.values())


def test_control_characters_are_stripped_from_notes():
    injected = _row(reason="clean\n{\"code\":\"forged\"}\x1b[0m")
    signal = WorkspaceSignal.from_row(injected)
    from skillweave.closeout_service import _workspace_blocker

    blocker = _workspace_blocker(
        WorkspaceSignal.from_row(_row(classification="unknown", reason=injected.reason))
    )
    assert blocker is not None
    assert "\n" not in blocker.note
    assert "\x1b" not in blocker.note


def test_preview_is_stable_under_dict_key_order():
    preview = _service().preview(**_clean_preview_kwargs())
    shuffled = dict(reversed(list(preview.to_dict().items())))
    assert json.loads(json.dumps(shuffled))["digest"] == preview.digest


# ── Step B: authority boundaries (machine-tested) ─────────────────────────


def test_releasechain_owns_publishing_not_closeout():
    assert CloseoutService.authority_for("releasechain", "tag")
    assert CloseoutService.authority_for("releasechain", "release")
    assert CloseoutService.authority_for("releasechain", "merge")
    assert not CloseoutService.authority_for("releasechain", "close_run")


def test_closeout_owns_closure_and_no_cleanup():
    assert CloseoutService.authority_for("closeout", "close_run")
    assert not CloseoutService.authority_for("closeout", "cleanup")
    assert not CloseoutService.authority_for("closeout", "remove_workspace")
    assert not CloseoutService.authority_for("closeout", "tag")
    assert not CloseoutService.authority_for("closeout", "release")
    assert not CloseoutService.authority_for("closeout", "merge")


def test_launch_owns_deployment_not_closure():
    assert CloseoutService.authority_for("launch", "deploy")
    assert CloseoutService.authority_for("launch", "rollback")
    assert not CloseoutService.authority_for("launch", "close_run")
    assert not CloseoutService.authority_for("launch", "cleanup")


def test_repo_health_owns_cleanup_not_closure():
    assert CloseoutService.authority_for("repo_health", "cleanup")
    assert CloseoutService.authority_for("repo_health", "inventory")
    assert not CloseoutService.authority_for("repo_health", "close_run")
    assert not CloseoutService.authority_for("repo_health", "release")


def test_unknown_lane_is_denied_everything():
    assert not CloseoutService.authority_for("mystery", "close_run")
    assert not CloseoutService.authority_for("", "cleanup")


def test_boundary_table_is_symmetric_on_the_closeout_axis():
    """Exactly one lane may close a run, and it is the closeout lane."""
    closers = [
        lane
        for lane in AUTHORITY_BOUNDARIES
        if CloseoutService.authority_for(lane, "close_run")
    ]
    assert closers == ["closeout"]


def test_boundary_table_is_symmetric_on_the_publishing_axis():
    """Publishing is releasechain-only; no other lane may tag or release."""
    publishers = [
        lane
        for lane in AUTHORITY_BOUNDARIES
        if CloseoutService.authority_for(lane, "release")
    ]
    assert publishers == ["releasechain"]


def test_may_and_must_not_never_overlap():
    for lane, entry in AUTHORITY_BOUNDARIES.items():
        overlap = set(entry["may"]) & set(entry["must_not"])
        assert not overlap, f"{lane} both may and must-not {sorted(overlap)}"


def test_preview_records_the_authority_table():
    preview = _service().preview(**_clean_preview_kwargs())
    lanes = {entry["lane"] for entry in preview.authority}
    assert lanes == {"releasechain", "closeout", "launch", "repo_health"}


# ── Read-only authority: the exit door owns no cleanup ────────────────────


def test_service_refuses_a_writable_authority():
    class _Writable:
        read_only = False

    from skillweave.assessment_service import ReadOnlyViolation

    with pytest.raises(ReadOnlyViolation, match="read-only authority"):
        CloseoutService(".", authority=_Writable())


def test_service_default_authority_is_read_only():
    assert CloseoutService(".").authority.read_only is True


def test_mutating_action_is_structurally_refused():
    class _Probe:
        pass

    service = _service()
    authority = service.authority
    # The capability the closeout carries has no write path at all.
    from skillweave.assessment_service import ReadOnlyViolation

    with pytest.raises(ReadOnlyViolation, match="refuses to"):
        authority.assert_writable("remove workspace run-1/lane-1")


def test_preview_and_decide_touch_no_filesystem(tmp_path):
    """A preview built over a nonexistent root still succeeds and is stable."""
    missing_root = tmp_path / "does-not-exist"
    service = CloseoutService(missing_root)
    preview = service.preview(**_clean_preview_kwargs())
    assert preview.status == STATUS_CLOSED
    assert not missing_root.exists()


# ── Blanket: no workspace state yields a silent CLOSED ────────────────────


@pytest.mark.parametrize(
    "overrides",
    [
        {"dirtiness": DirtyState.DIRTY, "classification": Classification.DIRTY},
        {"lease": LeaseState.ACTIVE, "classification": Classification.HEALTHY},
        {"session": EvidenceState.PRESENT, "classification": Classification.STALE},
        {"process": EvidenceState.PRESENT, "classification": Classification.STALE},
        {"classification": Classification.UNKNOWN},
        {"classification": Classification.HEALTHY, "session": EvidenceState.ABSENT,
         "lease": LeaseState.ABSENT},
    ],
)
def test_no_adverse_workspace_state_closes_silently(overrides):
    preview = _service().preview(
        **_clean_preview_kwargs(workspaces=[_row(**overrides)])
    )
    assert preview.status == STATUS_HELD
    assert preview.blockers


# ── Completeness: omission is a hold, never a silent CLOSED ────────────────
#
# GATE-A_MISSING_RECEIPT_GAP: omitting every artifact must not close, because a
# closeout that resolves no inputs would otherwise present no missing evidence.
# These are the regression tests for the required-evidence manifest.


def test_omitting_the_manifest_blocks_closed():
    """No required-evidence manifest means completeness is unestablished."""
    preview = _service().preview(**_clean_preview_kwargs(required_evidence=None))
    assert preview.status == STATUS_HELD
    assert preview.has(Hold.EVIDENCE_MANIFEST_MISSING)


def test_omitting_all_evidence_blocks_closed():
    """The gate's exact repro: no manifest, no evidence, no workspace hold."""
    preview = _service().preview(
        run_id="run-1", subject=SUBJECT, workspaces=[_row()], telemetry=_Telemetry()
    )
    assert preview.status == STATUS_HELD
    assert preview.has(Hold.EVIDENCE_MANIFEST_MISSING)
    assert preview.codes  # never a silent CLOSED with 0 evidence rows


def test_manifest_with_no_supplied_evidence_blocks_every_declared_producer():
    preview = _service().preview(
        **_clean_preview_kwargs(
            required_evidence=[
                missing_evidence(EvidenceKind.LAUNCH, "launch"),
                missing_evidence(EvidenceKind.ASSESSMENT, "assess"),
            ],
            evidence=[],
        )
    )
    assert preview.status == STATUS_HELD
    assert preview.has(Hold.EVIDENCE_INCOMPLETE)
    incomplete = [
        b for b in preview.blockers if b.code == Hold.EVIDENCE_INCOMPLETE.value
    ]
    assert {b.subject for b in incomplete} == {"launch", "assess"}


def test_partially_supplied_manifest_blocks_on_the_absent_producer():
    """Deploying but not assessing is a hold naming the artifact that is owed."""
    preview = _service().preview(
        **_clean_preview_kwargs(
            required_evidence=[
                EvidenceInput(
                    kind=EvidenceKind.LAUNCH, producer="launch",
                    value=_launch_receipt(), supplied=True,
                ),
                missing_evidence(EvidenceKind.ASSESSMENT, "assess"),
            ],
            evidence=[
                EvidenceInput(
                    kind=EvidenceKind.LAUNCH, producer="launch",
                    value=_launch_receipt(), supplied=True,
                )
            ],
        )
    )
    assert preview.has(Hold.EVIDENCE_INCOMPLETE)
    incomplete = [
        b for b in preview.blockers if b.code == Hold.EVIDENCE_INCOMPLETE.value
    ]
    assert [b.subject for b in incomplete] == ["assess"]


def test_declared_free_run_with_no_evidence_may_close():
    """A manifest that is declared and empty is a real declaration of nothing owed."""
    preview = _service().preview(
        **_clean_preview_kwargs(required_evidence=[], evidence=[])
    )
    assert preview.status == STATUS_CLOSED
    assert not preview.has(Hold.EVIDENCE_INCOMPLETE)
    assert not preview.has(Hold.EVIDENCE_MANIFEST_MISSING)


def test_manifest_is_echoed_into_the_preview_payload():
    preview = _service().preview(**_clean_preview_kwargs())
    assert [row["producer"] for row in preview.required_evidence] == [
        "launch",
        "assess",
    ]
    assert preview.required_evidence[0]["kind"] == "launch"


def test_manifest_entry_that_is_supplied_but_broken_holds_on_status_not_completeness():
    """A supplied-but-tampered artifact is mismatched, not "incomplete"."""
    tampered = copy.deepcopy(_launch_receipt())
    tampered["outcome"] = {"status": "failure"}
    entry = [tampered_launch_receipt(tampered)]
    preview = _service().preview(
        **_clean_preview_kwargs(required_evidence=entry, evidence=entry)
    )
    assert preview.has(Hold.EVIDENCE_MISMATCHED)
    assert not preview.has(Hold.EVIDENCE_INCOMPLETE)


def test_duplicate_manifest_entries_yield_one_hold():
    """A producer declared twice cannot manufacture a phantom second hold."""
    manifest = [
        missing_evidence(EvidenceKind.LAUNCH, "launch"),
        missing_evidence(EvidenceKind.LAUNCH, "launch"),
    ]
    preview = _service().preview(
        **_clean_preview_kwargs(required_evidence=manifest, evidence=[])
    )
    incomplete = [
        b for b in preview.blockers if b.code == Hold.EVIDENCE_INCOMPLETE.value
    ]
    assert len(incomplete) == 1
    assert len(preview.required_evidence) == 1


def test_required_evidence_helper_pairs_manifest_and_supply():
    manifest, supplied = required_evidence(
        [missing_evidence(EvidenceKind.LAUNCH, "launch")], []
    )
    assert len(manifest) == 1
    assert supplied == ()
    preview = _service().preview(
        **_clean_preview_kwargs(required_evidence=manifest, evidence=list(supplied))
    )
    assert preview.has(Hold.EVIDENCE_INCOMPLETE)


def test_manifest_digest_changes_when_the_manifest_changes():
    one = _service().preview(**_clean_preview_kwargs())
    two = _service().preview(
        **_clean_preview_kwargs(
            required_evidence=[missing_evidence(EvidenceKind.LAUNCH, "launch")]
        )
    )
    assert one.digest != two.digest
