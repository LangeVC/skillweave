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
    decide_resolved,
    faigate_endpoint,
    resolve_reachable,
    RoutingDecision,
    Adjustment,
    rank_metrics,
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


# ── Criterion 3: auto reads the existing complexity ─────────────────────

def test_auto_consumes_the_single_complexity_number():
    # The consumed complexity is one non-negative number — the count that folds
    # points, criteria count, and dependency depth. auto reads that number and
    # maps it onto the tier axis; it does not invent a second measure.
    profile = _profile()
    assert decide(profile, MODE_AUTO, complexity=0).tier == TIER_FAST
    assert decide(profile, MODE_AUTO, complexity=1).tier == TIER_BALANCED
    assert decide(profile, MODE_AUTO, complexity=3).tier == TIER_DEEP


def test_auto_computes_no_second_complexity():
    # auto trusts the number it was handed. Feeding the same number always
    # yields the same tier regardless of the profile's own tier — the profile
    # tier is never consulted as a second complexity signal under auto.
    fast_profile = _profile(tier="deep")
    deep_profile = _profile(tier="fast")
    assert decide(fast_profile, MODE_AUTO, complexity=0).tier == TIER_FAST
    assert decide(deep_profile, MODE_AUTO, complexity=2).tier == TIER_DEEP


def test_auto_refuses_a_non_number_complexity():
    # A second, differing measure can only enter if auto accepts something it
    # did not compute. It does not: booleans and floats are refused, so the
    # only path in is the producer's own number (or a resolved tier name).
    profile = _profile()
    with pytest.raises(RoutingProfileError):
        decide(profile, MODE_AUTO, complexity=True)
    with pytest.raises(RoutingProfileError):
        decide(profile, MODE_AUTO, complexity=1.5)


# ── Criterion 4: pin decides nothing ────────────────────────────────────

def test_pin_runs_no_derivation_and_ignores_complexity():
    # Pin never reads the complexity nor derives a tier from it: the profile's
    # own tier is the decision, and a complexity handed alongside is dropped.
    profile = _profile(tier="deep")
    decision = decide(profile, MODE_PIN, complexity=0)  # would be fast under auto
    assert decision.tier == "deep"
    assert decision.input is None
    assert decision.adjustments == []
    assert decision.mode == MODE_PIN


def test_pin_is_never_improved_upon():
    # A pin is the operator's override. No bound, floor, ceiling, or automatic
    # adjustment modifies it — the profile tier is returned verbatim.
    profile = _hybrid_profile(floor="fast", ceiling="balanced", tier="deep")
    decision = decide(profile, MODE_PIN, complexity=TIER_FAST, role="reviewer")
    assert decision.tier == "deep"  # bounds ignored under pin
    assert decision.adjustments == []


# ── Criterion 4: the raw-metric-to-rank step is explicit and named ──────

def test_the_conversion_step_is_named_and_has_thresholds():
    # The translation from raw metrics to rank is a named, public function
    # (rank_metrics) with literal thresholds, so it is auditable and never an
    # undeclared jump between two number scales.
    assert rank_metrics(points=1, criteria=3, depth=0).rank == 0  # small on every axis
    assert rank_metrics(points=2, criteria=4, depth=1).rank == 0
    assert rank_metrics(points=3, criteria=5, depth=1).rank == 1  # between
    assert rank_metrics(points=6, criteria=3, depth=0).rank == 2  # heavy points
    assert rank_metrics(points=1, criteria=8, depth=0).rank == 2  # heavy criteria
    assert rank_metrics(points=1, criteria=3, depth=3).rank == 2  # heavy depth


def test_a_three_point_three_criteria_task_is_not_deep():
    # The measured defect: a 3-point / 3-criteria task must not route to the
    # most expensive tier. Under the explicit thresholds it is balanced.
    rank = rank_metrics(points=3, criteria=3, depth=0)
    assert rank.rank == 1
    decision = decide(_profile(), MODE_AUTO, complexity=rank)
    assert decision.tier == TIER_BALANCED


def test_rank_is_named_in_the_record():
    # When raw metrics are converted here, the decision record names which raw
    # values produced which rank, so the translation is visible in the record.
    rank = rank_metrics(points=3, criteria=3, depth=0)
    decision = decide(_profile(), MODE_AUTO, complexity=rank)
    assert decision.rank is not None
    assert decision.rank.points == 3
    assert decision.rank.criteria == 3
    assert decision.rank.depth == 0
    assert decision.rank.rank == 1
    data = decision.to_dict()
    assert data["rank"] == {"points": 3, "criteria": 3, "depth": 0, "rank": 1}


def test_bare_rank_from_producer_has_no_conversion_named():
    # If the producer already emitted a rank, this module converted nothing, so
    # the record carries no rank mapping — and a bare rank is NOT treated as a
    # raw metric that silently lands on deep.
    decision = decide(_profile(), MODE_AUTO, complexity=1)
    assert decision.tier == TIER_BALANCED
    assert decision.rank is None


def test_raw_metrics_refuse_negative_values():
    with pytest.raises(RoutingProfileError):
        rank_metrics(points=-1, criteria=3, depth=0)
    with pytest.raises(RoutingProfileError):
        rank_metrics(points=1, criteria=-3, depth=0)
    with pytest.raises(RoutingProfileError):
        rank_metrics(points=1, criteria=3, depth=-1)


# ── Criterion 6: the decision is recorded, with what Faigate resolved ────

def test_decision_records_every_driver():
    # The record carries mode, profile, tier, the input that drove the tier,
    # the rank (when raw metrics were converted here), and the adjustments that
    # clamped it — six fields, no prose.
    rank = rank_metrics(points=3, criteria=3, depth=1)
    decision = decide(_hybrid_profile(floor="balanced"), MODE_HYBRID, complexity=rank)
    assert decision.mode == MODE_HYBRID
    assert decision.profile == "sw135"
    assert decision.tier == TIER_BALANCED
    assert decision.input is rank
    assert decision.rank is rank
    assert len(decision.adjustments) == 0


def test_decide_resolved_attaches_faigate_resolution():
    # decide_resolved records what Faigate turned the decision into: the
    # ResolutionRecord names the router preset, council mode, and model ids.
    decision = decide_resolved(_profile(), MODE_AUTO, complexity=TIER_FAST)
    assert decision.resolution is not None
    assert decision.resolution.tier == TIER_FAST
    assert decision.resolution.router_name == "quick"
    assert decision.resolution.mode == "quick"
    assert decision.resolution.resolved_models  # Faigate named concrete models
    # The resolution must match the decided tier, not the profile's default.
    assert decision.tier == TIER_FAST


def test_decide_resolved_records_adjusted_tier():
    # Under hybrid a below-floor decision is clamped to the floor, and the
    # Faigate resolution must reflect the clamped tier, not the raw complexity.
    decision = decide_resolved(
        _hybrid_profile(floor="deep"),
        MODE_HYBRID,
        complexity=TIER_FAST,
    )
    assert decision.tier == TIER_DEEP
    assert decision.resolution.tier == TIER_DEEP
    assert decision.resolution.router_name == "deep"
    assert decision.resolution.mode == "full"


def test_pin_resolution_has_no_automatic_improvement():
    # Under pin, no automatic decision runs and the resolution reflects the
    # operator's override verbatim: the profile's own tier is what Faigate
    # resolves, never an improvement on it.
    decision = decide_resolved(_profile(tier="deep"), MODE_PIN, complexity=TIER_FAST)
    assert decision.tier == TIER_DEEP
    assert decision.input is None
    assert decision.adjustments == []
    assert decision.resolution.tier == TIER_DEEP


# ── Determinism: same task, same profile, same mode → same decision ──────

def test_decide_is_deterministic():
    # The same task, profile, and mode produce the same decision, held by a
    # test not a docstring. Repeated calls yield byte-identical records.
    profile = _hybrid_profile(floor="balanced", ceiling="deep")
    rank = rank_metrics(points=3, criteria=5, depth=1)
    first = decide(profile, MODE_HYBRID, complexity=rank).to_dict()
    for _ in range(5):
        assert decide(profile, MODE_HYBRID, complexity=rank).to_dict() == first


def test_decide_resolved_is_deterministic():
    # Adding the Faigate resolution must not break determinism: identical input
    # yields an identical resolution record.
    profile = _hybrid_profile(floor="balanced", ceiling="deep")
    rank = rank_metrics(points=6, criteria=4, depth=0)
    first = decide_resolved(profile, MODE_HYBRID, complexity=rank).to_dict()
    for _ in range(5):
        assert decide_resolved(profile, MODE_HYBRID, complexity=rank).to_dict() == first


# ── Criterion 8: Faigate unreachable is a defined state ──────────────────

def test_faigate_endpoint_names_a_concrete_address():
    # The error path always names a concrete endpoint, never a blank.
    endpoint = faigate_endpoint()
    assert endpoint.startswith("http://")
    assert "/v1" in endpoint


def test_unreachable_without_fallback_raises_naming_endpoint():
    # When Faigate does not answer and no fallback is declared, the run fails
    # with a message naming the endpoint — it never silently uses another model.
    profile = _profile()
    with pytest.raises(RoutingProfileError) as exc:
        resolve_reachable(
            profile, MODE_AUTO, complexity=TIER_FAST,
            reachability=lambda ep: False,
        )
    assert faigate_endpoint() in str(exc.value)
    assert "unreachable" in str(exc.value).lower()


def test_unreachable_with_declared_fallback_uses_it():
    # Only a *declared* fallback profile is applied; it is never invented.
    profile = _profile(tier="balanced")
    fallback = _profile(name="fallback", tier="deep")
    decision = resolve_reachable(
        profile, MODE_PIN,
        reachability=lambda ep: False,
        fallback_profile=fallback,
    )
    assert decision.profile == "fallback"
    assert decision.tier == "deep"
    assert decision.resolution is not None
    assert decision.resolution.tier == "deep"


def test_reachable_resolves_normally():
    # The happy path behaves like decide_resolved; no fallback is consulted.
    profile = _profile(tier="balanced")
    decision = resolve_reachable(
        profile, MODE_AUTO, complexity=TIER_FAST,
        reachability=lambda ep: True,
    )
    assert decision.resolution is not None
    assert decision.resolution.tier == TIER_FAST
    assert decision.profile == "sw135"


def test_unreachable_resolution_is_deterministic():
    # The declared-fallback path is deterministic too: same input, same record.
    profile = _profile()
    fallback = _profile(name="fallback", tier="deep")
    first = resolve_reachable(
        profile, MODE_PIN, reachability=lambda ep: False, fallback_profile=fallback,
    ).to_dict()
    for _ in range(5):
        again = resolve_reachable(
            profile, MODE_PIN, reachability=lambda ep: False, fallback_profile=fallback,
        ).to_dict()
        assert again == first


# ── Criterion 9: red proof across all three modes ────────────────────────

def test_red_auto_different_complexity_different_tiers():
    # Two tasks of different complexity must route to different tiers under
    # auto, or the complexity axis measures nothing.
    low = decide(_profile(), MODE_AUTO, complexity=rank_metrics(points=1, criteria=1, depth=0))
    high = decide(_profile(), MODE_AUTO, complexity=rank_metrics(points=6, criteria=6, depth=2))
    assert low.tier != high.tier


def test_red_pin_ignores_complexity():
    # The same task under pin routes to the pinned profile regardless of
    # complexity: a fast complexity still returns the profile's deep tier.
    profile = _profile(tier="deep")
    decision = decide(profile, MODE_PIN, complexity=TIER_FAST)
    assert decision.tier == "deep"
    # And a deep complexity under a fast-profile pin still returns fast.
    fast = _profile(tier="fast")
    assert decide(fast, MODE_PIN, complexity=TIER_DEEP).tier == "fast"


def test_red_hybrid_below_floor_is_raised_and_recorded():
    # A task whose complexity would pick a tier below the floor is raised, and
    # the adjustment is visible in the record.
    profile = _hybrid_profile(floor="balanced")
    decision = decide(profile, MODE_HYBRID, complexity=TIER_FAST)
    assert decision.tier == TIER_BALANCED
    assert decision.adjustments
    assert decision.adjustments[0].from_tier == TIER_FAST
    assert decision.adjustments[0].to_tier == TIER_BALANCED


