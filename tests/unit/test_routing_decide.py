"""Tests for the routing decision (SW-135-013, dispatch 1).

Dispatch 1 criteria:

1. Three modes exist and are declared, never inferred: `pin` uses the named
   profile and decides nothing; `auto` derives the tier from complexity;
   `hybrid` lets auto decide WITHIN bounds the profile declares (floor tier,
   ceiling tier, per-role pins), so the decision is free only where allowed.
2. Hybrid is precise enough to test: a per-role pin wins inside hybrid; a
   decision below the floor is raised to it; above the ceiling is lowered to
   it; and both adjustments are recorded as adjustments, not as the original
   decision.
"""
import pytest

from skillweave.routing import (
    RoutingProfile,
    from_dict,
    TIER_FAST,
    TIER_BALANCED,
    TIER_DEEP,
    RoutingProfileError,
)
from skillweave.routing.decide import (
    MODE_PIN,
    MODE_AUTO,
    MODE_HYBRID,
    VALID_MODES,
    decide,
    RoutingDecision,
    Adjustment,
)


def _profile(**overrides):
    data = {
        "name": "sw135",
        "tier": "balanced",
        "limits": {},
        "roles": {
            "ops": {"model": "sonnet"},
            "reviewer": {"model": "gpt-4o"},
            "worker": {"model": "deepseek-v4", "pin": "sonnet"},
        },
    }
    data.update(overrides)
    return from_dict(data)


# ── Criterion 1: three modes declared, never inferred ────────────────────

def test_only_three_modes_are_declared():
    assert set(VALID_MODES) == {MODE_PIN, MODE_AUTO, MODE_HYBRID}


def test_unknown_mode_is_refused_not_inferred():
    profile = _profile()
    with pytest.raises(RoutingProfileError):
        decide(profile, "guess")
    with pytest.raises(RoutingProfileError):
        decide(profile, "")
    with pytest.raises(RoutingProfileError):
        decide(profile, "automatic")


def test_pin_decides_nothing():
    # Pin uses the profile's own tier, reads no complexity, applies no bounds,
    # and records no adjustments.
    profile = _profile(tier="deep")
    decision = decide(profile, MODE_PIN, complexity=TIER_FAST)
    assert decision.mode == MODE_PIN
    assert decision.tier == "deep"
    assert decision.input is None
    assert decision.adjustments == []


def test_auto_derives_tier_from_complexity():
    profile = _profile()
    fast = decide(profile, MODE_AUTO, complexity=TIER_FAST)
    deep = decide(profile, MODE_AUTO, complexity=TIER_DEEP)
    assert fast.tier == TIER_FAST
    assert deep.tier == TIER_DEEP
    assert fast.adjustments == []
    # Under auto the profile's own tier is not consulted: complexity is what
    # drives, so a balanced profile under auto + fast complexity is fast.
    assert fast.tier != profile.tier


def test_auto_accepts_integer_rank():
    profile = _profile()
    assert decide(profile, MODE_AUTO, complexity=0).tier == TIER_FAST
    assert decide(profile, MODE_AUTO, complexity=1).tier == TIER_BALANCED
    assert decide(profile, MODE_AUTO, complexity=2).tier == TIER_DEEP
    assert decide(profile, MODE_AUTO, complexity=99).tier == TIER_DEEP


def test_auto_refuses_unknown_complexity():
    profile = _profile()
    with pytest.raises(RoutingProfileError):
        decide(profile, MODE_AUTO, complexity="warp")
    with pytest.raises(RoutingProfileError):
        decide(profile, MODE_AUTO, complexity=-1)


# ── Criterion 2: hybrid is precise enough to test ────────────────────────

def _hybrid_profile(floor=None, ceiling=None, **overrides):
    metadata = {}
    if floor is not None:
        metadata["floor_tier"] = floor
    if ceiling is not None:
        metadata["ceiling_tier"] = ceiling
    return _profile(metadata=metadata, **overrides)


def test_hybrid_per_role_pin_wins():
    # Inside hybrid a per-role pin wins: the deciding role's pinned model is
    # used, and no floor/ceiling adjustment applies because there is no free
    # decision left to clamp.
    profile = _hybrid_profile(
        floor="balanced",
        ceiling="deep",
        roles={"worker": {"model": "deepseek-v4", "pin": "sonnet"}},
    )
    decision = decide(profile, MODE_HYBRID, complexity=TIER_FAST, role="worker")
    assert decision.pinned == "sonnet"
    assert decision.adjustments == []
    # A complexity that would otherwise fall below the floor is not clamped
    # when a pin wins: the pin replaces the tier decision entirely.


def test_hybrid_decision_below_floor_is_raised():
    profile = _hybrid_profile(floor="balanced")
    decision = decide(profile, MODE_HYBRID, complexity=TIER_FAST)
    assert decision.tier == TIER_BALANCED
    assert len(decision.adjustments) == 1
    adjustment = decision.adjustments[0]
    assert adjustment.kind == "floor"
    assert adjustment.from_tier == TIER_FAST
    assert adjustment.to_tier == TIER_BALANCED


def test_hybrid_decision_above_ceiling_is_lowered():
    profile = _hybrid_profile(ceiling="balanced")
    decision = decide(profile, MODE_HYBRID, complexity=TIER_DEEP)
    assert decision.tier == TIER_BALANCED
    assert len(decision.adjustments) == 1
    adjustment = decision.adjustments[0]
    assert adjustment.kind == "ceiling"
    assert adjustment.from_tier == TIER_DEEP
    assert adjustment.to_tier == TIER_BALANCED


def test_hybrid_inside_bounds_is_not_adjusted():
    profile = _hybrid_profile(floor="fast", ceiling="deep")
    decision = decide(profile, MODE_HYBRID, complexity=TIER_BALANCED)
    assert decision.tier == TIER_BALANCED
    assert decision.adjustments == []


def test_hybrid_both_bounds_can_fire_on_one_side_only():
    # A decision below the floor is raised to the floor; it is then inside the
    # ceiling, so exactly one adjustment fires. A decision above the ceiling
    # behaves the same way in the other direction.
    profile = _hybrid_profile(floor="balanced", ceiling="deep")
    low = decide(profile, MODE_HYBRID, complexity=TIER_FAST)
    assert low.tier == TIER_BALANCED
    assert [a.kind for a in low.adjustments] == ["floor"]

    profile2 = _hybrid_profile(floor="fast", ceiling="balanced")
    high = decide(profile2, MODE_HYBRID, complexity=TIER_DEEP)
    assert high.tier == TIER_BALANCED
    assert [a.kind for a in high.adjustments] == ["ceiling"]


def test_adjustments_are_recorded_not_presented_as_original():
    # The adjustment record keeps from_tier (what auto decided) distinct from
    # to_tier (what the bound forced). The decision's `tier` is the adjusted
    # value, and the adjustment tells the original — so the clamp is never
    # rewritten to look like the intended decision.
    profile = _hybrid_profile(floor="deep")
    decision = decide(profile, MODE_HYBRID, complexity=TIER_FAST)
    assert decision.tier == TIER_DEEP  # the adjusted value
    assert decision.adjustments[0].from_tier == TIER_FAST  # the original decision
    assert decision.adjustments[0].to_tier == TIER_DEEP


def test_hybrid_bounds_are_declared_not_inferred():
    # Without declared bounds, hybrid simply is auto: no floor, no ceiling.
    profile = _profile()
    decision = decide(profile, MODE_HYBRID, complexity=TIER_FAST)
    assert decision.tier == TIER_FAST
    assert decision.adjustments == []


def test_hybrid_rejects_invalid_declared_bound():
    profile = _hybrid_profile(floor="warp")
    with pytest.raises(RoutingProfileError):
        decide(profile, MODE_HYBRID, complexity=TIER_FAST)


def test_decision_roundtrips_to_dict():
    decision = decide(
        _hybrid_profile(floor="balanced"),
        MODE_HYBRID,
        complexity=TIER_FAST,
    )
    data = decision.to_dict()
    assert data["mode"] == MODE_HYBRID
    assert data["tier"] == TIER_BALANCED
    assert data["adjustments"] == [
        {"kind": "floor", "from_tier": TIER_FAST, "to_tier": TIER_BALANCED}
    ]


def test_decision_record_names_profile():
    decision = decide(_profile(), MODE_PIN)
    assert decision.profile == "sw135"
