"""Model allocation and escalation policy integration test (SW1311-MODEL-001).

Proves the provider-neutral allocation/escalation/attribution/receipt policy end
to end against the core module (``skillweave.dispatch.model_policy``) and the
dispatched profile resolution seam (``skillweave.dispatch.profile_resolution``):

* Criterion 1 — a product contract declares capability/minimum tier,
  architectural risk, cost ceiling and fallback with no vendor/gateway prefix.
* Criterion 2 — requested, gateway-resolved and answering model stay separate;
  unknown attribution stays unknown.
* Criterion 4 — allocation weighs the risk dimensions, never file count alone.
* Criterion 5 — Flash only for bounded low-risk work; the forcing signals
  require Pro unless an explicit, reasoned override is recorded.
* Criterion 6 — after two non-progress/accepted review-fail cycles Flash
  escalates to Pro if budget permits, else blocks explicitly.
* Criterion 7 — provider unavailable/rate limit/launch/attribution failures are
  technical, consume no correction round and never become a review verdict.
* Criterion 8 — tokens/latency/cost are receipt-bound; transfer observations
  cannot mutate policy.

The provider-neutral core names no vendor, gateway or product model: ``flash``
and ``pro`` are capability classes.
"""

import sys
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.dispatch.model_policy import (  # noqa: E402
    AllocationError,
    AllocationSignals,
    ESCALATION_THRESHOLD,
    EscalationState,
    ModelAttribution,
    ModelPolicyDeclaration,
    ModelReceipt,
    ModelTier,
    TechnicalFailureError,
    TransferObservation,
    UNKNOWN,
    allocate,
    apply_transfer_observation,
    is_technical_failure,
)


# ── Criterion 1: provider-neutral product contract ─────────────────────────

def test_model_policy_declaration_has_no_vendor_prefix():
    decl = ModelPolicyDeclaration(
        minimum_tier=ModelTier.PRO,
        architectural_risk="high",
        cost_ceiling=1000.0,
        fallback="block",
    )
    d = decl.to_dict()
    assert d["minimum_tier"] == "pro"
    assert d["architectural_risk"] == "high"
    assert d["cost_ceiling"] == 1000.0
    assert d["fallback"] == "block"
    # No vendor/gateway prefix appears in the declaration surface.
    assert "/" not in d["minimum_tier"]
    assert ":" not in d["minimum_tier"]


def test_model_policy_declaration_roundtrips_from_dict():
    decl = ModelPolicyDeclaration.from_dict(
        {
            "minimum_tier": "pro",
            "architectural_risk": "critical",
            "cost_ceiling": 42.0,
            "fallback": "escalate",
            "requires": {"security": True},
        }
    )
    assert decl.minimum_tier is ModelTier.PRO
    assert decl.architectural_risk == "critical"
    assert decl.cost_ceiling == 42.0
    assert decl.fallback == "escalate"
    assert decl.requires == {"security": True}


def test_model_policy_declaration_refuses_unknown_tier():
    with pytest.raises(AllocationError):
        ModelPolicyDeclaration.from_dict({"minimum_tier": "quad"})


def test_model_policy_declaration_refuses_unknown_risk():
    with pytest.raises(AllocationError):
        ModelPolicyDeclaration(architectural_risk="catastrophic")


def test_model_policy_declaration_refuses_unknown_fallback():
    with pytest.raises(AllocationError):
        ModelPolicyDeclaration(fallback="crash")


# ── Criterion 2: three separate attribution facts, unknown stays unknown ───

def test_requested_resolved_answering_are_separate():
    a = ModelAttribution.of(
        requested="req", resolved="gateway-chosen", answering="actual"
    )
    assert a.requested == "req"
    assert a.resolved == "gateway-chosen"
    assert a.answering == "actual"
    assert a.requested != a.resolved
    assert a.resolved != a.answering


def test_unknown_attribution_stays_unknown():
    a = ModelAttribution.of(requested="req")
    assert a.requested == "req"
    assert a.resolved == UNKNOWN
    assert a.answering == UNKNOWN
    d = a.to_dict()
    # Every key is present so a later reader can tell "unset" from "unknown".
    assert d == {"requested": "req", "resolved": UNKNOWN, "answering": UNKNOWN}


def test_unknown_attribution_is_not_synthesised():
    # An empty/None answering model must not be filled from the requested id.
    a = ModelAttribution.of(requested="req", answering=None)
    assert a.answering == UNKNOWN
    assert a.answering != a.requested


def test_answering_known_flag():
    assert ModelAttribution.of(answering="x").answering_known is True
    assert ModelAttribution.of().answering_known is False


# ── Criterion 4: allocation is risk-shaped, not size-shaped ────────────────

def test_coverage_alone_does_not_force_pro():
    # Large coverage (size) with no forcing signal stays on the declared floor.
    signals = AllocationSignals(task_kind="discovery", coverage=100000)
    decl = ModelPolicyDeclaration(minimum_tier=ModelTier.FLASH)
    result = allocate(signals, decl)
    assert result.tier is ModelTier.FLASH
    assert result.forced_pro is False


def test_forcing_signal_forces_pro():
    for signal_name, kwarg in [
        ("architecture", {"architecture": True}),
        ("high_blast_radius", {"high_blast_radius": True}),
        ("migration", {"migration": True}),
        ("security", {"security": True}),
        ("causal_verification", {"causal_verification": True}),
        ("ambiguous_rework", {"ambiguous_rework": True}),
        ("critical_review", {"critical_review": True}),
    ]:
        signals = AllocationSignals(**kwarg)
        result = allocate(signals, ModelPolicyDeclaration())
        assert result.tier is ModelTier.PRO, f"{signal_name} must force Pro"
        assert result.forced_pro is True


def test_declared_pro_floor_forces_pro_even_without_signals():
    decl = ModelPolicyDeclaration(minimum_tier=ModelTier.PRO)
    result = allocate(AllocationSignals(), decl)
    assert result.tier is ModelTier.PRO


# ── Criterion 5: Flash only for low-risk, Pro requires explicit override ───

def test_bounded_low_risk_discovery_may_use_flash():
    signals = AllocationSignals(task_kind="discovery", task_type="bug-hunt")
    decl = ModelPolicyDeclaration(minimum_tier=ModelTier.FLASH)
    result = allocate(signals, decl)
    assert result.tier is ModelTier.FLASH


def test_architecture_requires_pro_unless_reasoned_override():
    signals = AllocationSignals(architecture=True)
    decl = ModelPolicyDeclaration(minimum_tier=ModelTier.FLASH)
    # No override: Pro.
    result = allocate(signals, decl)
    assert result.tier is ModelTier.PRO
    # Explicit, reasoned override lowers to the declared floor — and records it.
    overridden = allocate(signals, decl, override_reason="isolated, fully reversible")
    assert overridden.tier is ModelTier.FLASH
    assert overridden.override is True
    assert overridden.override_reason == "isolated, fully reversible"


def test_blank_override_does_not_lower_a_forced_pro():
    signals = AllocationSignals(security=True)
    decl = ModelPolicyDeclaration(minimum_tier=ModelTier.FLASH)
    result = allocate(signals, decl, override_reason="   ")
    assert result.tier is ModelTier.PRO
    assert result.override is False


# ── Criterion 6: bounded escalation ────────────────────────────────────────

def test_flash_escalates_to_pro_after_two_cycles_with_budget():
    state = EscalationState(tier=ModelTier.FLASH)
    state.record_non_progress()
    state.record_review_fail()
    assert state.cycles == 2
    assert state.cycles >= ESCALATION_THRESHOLD
    # Budget permits (no ceiling) → escalate to Pro.
    decl = ModelPolicyDeclaration(cost_ceiling=None)
    state.escalate(decl)
    assert state.tier is ModelTier.PRO
    assert state.blocked is False


def test_flash_escalates_with_positive_ceiling():
    state = EscalationState(tier=ModelTier.FLASH)
    state.record_non_progress()
    state.record_non_progress()
    decl = ModelPolicyDeclaration(cost_ceiling=500.0)
    state.escalate(decl)
    assert state.tier is ModelTier.PRO


def test_flash_blocks_explicitly_when_budget_forbids_escalation():
    state = EscalationState(tier=ModelTier.FLASH)
    state.record_review_fail()
    state.record_non_progress()
    # A zero ceiling means "Flash-only budget": escalation is not permitted.
    decl = ModelPolicyDeclaration(cost_ceiling=0.0)
    state.escalate(decl)
    assert state.blocked is True
    assert "escalation" in state.blocked_reason
    assert state.tier is ModelTier.FLASH  # did not silently jump to Pro


def test_only_one_cycle_does_not_escalate():
    state = EscalationState(tier=ModelTier.FLASH)
    state.record_non_progress()
    decl = ModelPolicyDeclaration(cost_ceiling=None)
    state.escalate(decl)
    assert state.tier is ModelTier.FLASH
    assert state.blocked is False


def test_pro_never_escalates_or_blocks():
    state = EscalationState(tier=ModelTier.PRO)
    state.record_non_progress()
    state.record_non_progress()
    state.record_non_progress()
    decl = ModelPolicyDeclaration(cost_ceiling=0.0)
    state.escalate(decl)
    assert state.tier is ModelTier.PRO
    assert state.blocked is False


def test_escalation_is_bounded_not_infinite():
    # Even after many cycles, the state is either Pro or blocked — never keeps
    # incrementing into an unbounded loop.
    state = EscalationState(tier=ModelTier.FLASH)
    for _ in range(20):
        state.record_non_progress()
    decl = ModelPolicyDeclaration(cost_ceiling=0.0)
    state.escalate(decl)
    assert state.blocked is True
    assert state.tier is ModelTier.FLASH


# ── Criterion 7: technical failures consume no correction round ────────────

@pytest.mark.parametrize(
    "kind",
    ["provider_unavailable", "rate_limit", "launch_failure", "attribution_failure"],
)
def test_technical_failure_kinds_are_technical(kind):
    assert is_technical_failure(kind) is True
    err = TechnicalFailureError(f"{kind} occurred", kind=kind)
    assert err.consume_correction is False
    # Never a review verdict: a technical failure carries no review verdict
    # field and is not a review error type.
    assert not hasattr(err, "verdict")
    assert isinstance(err, AllocationError)
    assert err.kind == kind


def test_review_failure_is_not_technical():
    # A review verdict is a task outcome, not a provider failure.
    assert is_technical_failure("review_fail") is False
    assert is_technical_failure("REVIEW_FAIL") is False


# ── Criterion 8: receipt-bound metrics, transfer cannot mutate policy ──────

def test_receipt_is_bound_to_measured_values():
    r = ModelReceipt(tokens=1234, latency_ms=9.5, cost=0.0042)
    d = r.to_dict()
    assert d["tokens"] == 1234
    assert d["latency_ms"] == 9.5
    assert d["cost"] == 0.0042
    assert r.unavailable_fields() == []


def test_receipt_unavailable_has_a_reason():
    r = ModelReceipt.unavailable("no telemetry exposed")
    assert r.tokens is None
    assert r.latency_ms is None
    assert r.cost is None
    assert set(r.unavailable_fields()) == {"tokens", "latency_ms", "cost"}
    assert r.to_dict() == {"reason": "no telemetry exposed"}


def test_transfer_observation_cannot_mutate_policy():
    decl = ModelPolicyDeclaration(
        minimum_tier=ModelTier.PRO, fallback="block", cost_ceiling=100.0
    )
    observation = TransferObservation(
        subject="observed-a-flash-was-fine",
        note="flash handled this fine",
        confidence="high",
    )
    result = apply_transfer_observation(decl, observation)
    assert result is decl
    assert result.minimum_tier is ModelTier.PRO
    assert result.fallback == "block"
    assert result.cost_ceiling == 100.0


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
