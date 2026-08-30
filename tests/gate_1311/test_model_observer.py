"""Dispatch-order group 4 — "model policy and live/replay observer" (criteria 7, 8).

Criterion 7 proves the provider-neutral model policy and the canonical Council
namespace/attribution surfaces: risk-shaped allocation, bounded escalation,
technical-failure separation, exactly-once prefix translation, and truthful
requested/resolved/answering attribution.

Criterion 8 proves the live/replay projection and the read-only observer:
replaying the same ordered typed events yields an identical projection, the
semantic observer reports coverage gaps and the observer/view refuse every
forbidden runtime action and mutation.

All hermetic; no network, no wall clock, no mutation.
"""

from __future__ import annotations

import pytest

from skillweave.dispatch import model_policy as M
from skillweave.routing import faigate_adapter as F
from skillweave.trace.projection import Projector, ProjectionEvent, builds_identical_projection
from skillweave.trace.observer import observe_run, measured_fact, MeasuredFactKind
from skillweave.trace import view as V
from skillweave.trace import contracts as C

SHA_A = "a" * 40


# ── Criterion 7: model policy + Council namespace/attribution ───────────────


def test_criterion_07_model_policy_and_council_namespace_attribution():
    """Model policy risk-shapes allocation, Council translation is exactly-once
    and attribution is three-way and truthful."""
    # Provider-neutral declaration: no vendor/gateway prefix in the contract.
    decl = M.ModelPolicyDeclaration(minimum_tier=M.ModelTier.FLASH)
    assert decl.minimum_tier is M.ModelTier.FLASH

    # A forcing signal (architecture) requires Pro unless overridden.
    forced = M.AllocationSignals(task_kind="action", architecture=True)
    assert M.allocate(forced, decl).tier is M.ModelTier.PRO
    assert M.allocate(forced, decl).forced_pro

    # A bounded discovery lane without forcing signals stays Flash (size/coverage
    # never force a tier).
    discovery = M.AllocationSignals(task_kind="discovery", coverage=1000)
    assert M.allocate(discovery, decl).tier is M.ModelTier.FLASH

    # Only a reasoned override may lower a forced Pro.
    overridden = M.allocate(forced, decl, override_reason="bounded rework, low blast")
    assert overridden.override and overridden.tier is M.ModelTier.FLASH

    # Bounded escalation: after two non-progress cycles a Flash task escalates to
    # Pro when no ceiling; with a zero ceiling it blocks explicitly (never loops).
    esc = M.EscalationState(tier=M.ModelTier.FLASH)
    esc.record_non_progress().record_review_fail()
    esc.escalate(M.ModelPolicyDeclaration(minimum_tier=M.ModelTier.FLASH, cost_ceiling=None))
    assert esc.tier is M.ModelTier.PRO and not esc.blocked

    esc_block = M.EscalationState(tier=M.ModelTier.FLASH)
    esc_block.record_non_progress().record_review_fail()
    esc_block.escalate(M.ModelPolicyDeclaration(minimum_tier=M.ModelTier.FLASH, cost_ceiling=0))
    assert esc_block.blocked and esc_block.tier is M.ModelTier.FLASH

    # Technical failures are separated from review failures.
    for kind in ("provider_unavailable", "rate_limit", "launch_failure", "attribution_failure"):
        assert M.is_technical_failure(kind)

    # Exactly-once namespace translation, fail-closed.
    assert F.translate_model_id("deepseek-v4-pro") == "deepseek-v4-pro"
    assert F.translate_model_id("faigate/deepseek-v4-pro") == "deepseek-v4-pro"
    assert F.translate_model_id("faigate:deepseek-v4-pro") == "deepseek-v4-pro"
    with pytest.raises(F.ModelNamespaceError):
        F.translate_model_id("faigate/faigate/deepseek-v4-pro")  # doubled prefix
    with pytest.raises(F.ModelNamespaceError):
        F.translate_model_id("openrouter/deepseek-v4-pro")  # foreign prefix

    # Council profile data must be provider-native; a gateway prefix is refused.
    with pytest.raises(F.ModelNamespaceError):
        F.validate_council_model_ids(
            models=["faigate/deepseek-v4-pro", "deepseek-v4-flash"],
            chairman="deepseek-v4-pro",
        )
    F.validate_council_model_ids(
        models=["deepseek-v4-pro", "deepseek-v4-flash"], chairman="deepseek-v4-pro"
    )

    # The default roster holds >= 2 distinct provider-native seats (no defaulted
    # gateway prefix in the product contract).
    default = F.ROUTER_PROFILES["default"]
    assert len(set(default["models"])) >= 2

    # Truthful 3-way attribution: unknown stays unknown, never copied.
    att = M.ModelAttribution.of(requested="faigate/deepseek-v4-pro")
    assert att.answering is M.UNKNOWN
    full = M.ModelAttribution.of(
        requested="faigate/deepseek-v4-pro",
        resolved="deepseek-v4-pro",
        answering="deepseek-v4-pro",
    )
    assert full.to_dict() == {
        "requested": "faigate/deepseek-v4-pro",
        "resolved": "deepseek-v4-pro",
        "answering": "deepseek-v4-pro",
    }
    assert full.answering_known and full.resolved_known


# ── Criterion 8: live/replay projection + observer authority ────────────────


def _events():
    return [
        ProjectionEvent(sequence=0, payload={
            "event_type": "dispatch", "wave": "W1", "lane_id": "lane-1",
            "job_id": "job-1", "criterion_group": [1, 2],
            "receipt_refs": ["r1"], "timestamp": "2026-08-29T00:00:00+00:00",
        }),
        ProjectionEvent(sequence=1, payload={
            "event_type": "heartbeat", "job_id": "job-1",
            "timestamp": "2026-08-29T00:00:05+00:00",
        }),
        ProjectionEvent(sequence=2, payload={
            "event_type": "state", "job_id": "job-1", "job_state": "exited",
            "gate_state": "pass", "disposition": "accepted",
            "rounds_remaining": 1, "integration_eligible": True,
            "timestamp": "2026-08-29T00:00:10+00:00",
        }),
    ]


def test_criterion_08_live_replay_projection_and_observer_authority():
    """Replay yields an identical projection; observer is read-only and reports
    coverage; intervened actions are refused."""
    # Replaying the same ordered typed events from zero yields an equal projection.
    p1 = Projector(run_id="run-1")
    for e in _events():
        p1.project(e)
    p2 = Projector(run_id="run-1")
    for e in _events():
        p2.project(e)

    proj1 = p1.projection()
    proj2 = p2.projection()
    assert builds_identical_projection(proj1, proj2)
    # Deterministic under any wall clock: re-fold in a fresh projector.
    assert proj1.run.run_id == "run-1"
    assert "lane-1" in {l.lane_id for l in proj1.lanes}
    assert proj1.gate_state == "pass"

    # Semantic observer reports seen coverage and missing-criterion gaps.
    records = [
        C.new_append_only_round(
            C.AppendOnlyReceiptLog(), parent_id=None, round_=1, kind=C.RoundKind.DISPATCH,
            job_id="job-1",
            result=C.JobResult(job_status=C.JobStatus.EXITED,
                               task_verdict=C.TaskVerdict.DONE,
                               evidence_available=C.EvidenceAvailability.RECORDED,
                               gate_verdict=C.GateVerdict.PASS),
            payload={"criteria": ["1"]},
        )
    ]
    obs = observe_run(
        "run-1", records, expected_criteria=("1", "2"),
        measured=[measured_fact(MeasuredFactKind.TOKENS, value=1234, unit="tokens",
                                source="job-1")],
    )
    kinds = {f.kind.value for f in obs.findings}
    assert "criterion_coverage_gap" in kinds
    assert obs.coverage.seen_criteria == ("1",)
    assert "2" in obs.coverage.expected_criteria  # expected is declared

    # Observer honesty: an unavailable fact carries a reason, never a number.
    unavailable = measured_fact(MeasuredFactKind.COST)
    assert not unavailable.available and unavailable.reason

    # Observer/view refuse every runtime action and mutation.
    for action in V.FORBIDDEN_RUNTIME_ACTIONS:
        with pytest.raises(V.ObserverAuthorityError):
            V.assert_observer_authority(action)
    for action in V.FORBIDDEN_MUTATIONS:
        with pytest.raises(V.ObserverAuthorityError):
            V.assert_observer_authority(action)

    # A read-only intervention request is emitted for liveness/non-progress.
    req = V.InterventionRequest(
        kind=V.InterventionKind.NON_PROGRESS, reason="no progress", threshold=1.0,
        action="request operator attention",
    )
    assert req.kind is V.InterventionKind.NON_PROGRESS
    assert "attention" in req.action  # a request, never a performed action
