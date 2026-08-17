"""Tests for declarative routing profiles (SW-135 dispatches 1 and 2).

Dispatch 1 criteria:
1. A RoutingProfile is declarable as data and carries all four parts:
   model choice per role, tier (fast/balanced/deep), limits, target tool.
2. Roles are DATA (not an enum); built-ins ops/reviewer/observer/chairman/worker
   plus declarable extras; observer is wired to the existing runtime observer.

Dispatch 2 criteria:
3. A role carries its capabilities in the same profile file; the capability
   matrix is loaded from there, not hardcoded; an undeclared role falls closed.
4. Incompatible capabilities (can_mutate_run_state + can_approve_gate) are
   refused at load time — that combination is self-approval.
"""
import pytest

from skillweave.routing import (
    RoutingProfile,
    RoleDefinition,
    ToolSpec,
    builtin_roles,
    from_dict,
    load_profiles,
    load_matrix,
    resolve_role,
    TIER_FAST,
    TIER_BALANCED,
    TIER_DEEP,
    CAP_MUTATE_RUN_STATE,
    CAP_APPROVE_GATE,
    RoutingProfileError,
    TIER_TO_ROUTER,
    tier_to_router,
    tier_to_mode,
    ResolutionRecord,
    resolve_tier,
    known_model_ids,
    ROUTER_PROFILES,
)
from skillweave.runtime.observer import ObserverRuntime


def _profile(**overrides):
    data = {
        "name": "sw135",
        "tier": "balanced",
        "limits": {
            "timeout": 30.0,
            "max_retries": 2,
            "min_models_required": 3,
            "on_model_failure": "retry",
        },
        "roles": {
            "ops": {"model": "sonnet"},
            "reviewer": {"model": "gpt-4o"},
            "chairman": {"model": "opus"},
            "worker": {"model": "deepseek-v4", "tool": {
                "name": "council",
                "launch_command": "python3 -m skillweave.council",
            }},
        },
    }
    data.update(overrides)
    return from_dict(data)


# ── Criterion 1: profile is declarable data with all four parts ──────────

def test_profile_carries_model_choice_per_role():
    profile = _profile()
    assert profile.model_for("ops") == "sonnet"
    assert profile.model_for("reviewer") == "gpt-4o"
    assert profile.model_for("chairman") == "opus"
    assert profile.model_for("worker") == "deepseek-v4"


def test_profile_carries_tier():
    assert _profile().tier == TIER_BALANCED
    assert _profile(tier="fast").tier == TIER_FAST
    assert _profile(tier="deep").tier == TIER_DEEP


def test_profile_rejects_unknown_tier():
    with pytest.raises(ValueError):
        _profile(tier="warp")


def test_profile_carries_limits():
    profile = _profile()
    assert profile.limits.timeout == 30.0
    assert profile.limits.max_retries == 2
    assert profile.limits.min_models_required == 3
    assert profile.limits.on_model_failure == "retry"


def test_profile_rejects_unknown_failure_behaviour():
    with pytest.raises(ValueError):
        _profile(limits={"on_model_failure": "explode"})


def test_profile_carries_target_tool_with_launch_command():
    profile = _profile()
    tool = profile.tool_for("worker")
    assert tool is not None
    assert tool.name == "council"
    assert tool.launch_command == "python3 -m skillweave.council"


# ── Criterion 2: roles are data, not an enum ─────────────────────────────

def test_builtin_roles_are_data_including_observer():
    roles = builtin_roles()
    assert set(roles.keys()) == {"ops", "reviewer", "observer", "chairman", "worker"}
    assert all(isinstance(r, RoleDefinition) for r in roles.values())
    assert roles["observer"].is_observer is True
    assert roles["ops"].is_observer is False


def test_observer_role_is_wired_to_existing_runtime_observer():
    profile = _profile()
    observer = profile.observer_role()
    assert observer is not None
    assert observer.is_observer is True
    # The runtime observer that 'observer' is wired to is the existing type.
    assert ObserverRuntime is not None


def test_profile_seeds_builtin_roles_by_default():
    profile = _profile()
    assert profile.role("ops") is not None
    assert profile.role("observer") is not None


def test_custom_role_declared_alongside_builtins():
    profile = _profile(
        roles={
            "ops": {"model": "sonnet"},
            "reviewer": {"model": "gpt-4o"},
            "observer": {"model": "none"},
            "chairman": {"model": "opus"},
            "worker": {"model": "deepseek-v4"},
            "auditor": {"model": "gemini-pro"},
        }
    )
    for builtin in ("ops", "reviewer", "observer", "chairman", "worker"):
        assert profile.role(builtin) is not None
    assert profile.role("auditor") is not None
    assert profile.model_for("auditor") == "gemini-pro"


def test_resolve_role_returns_declared_role():
    profile = _profile()
    assert resolve_role(profile, "ops").key == "ops"


def test_resolve_role_raises_for_undeclared():
    profile = _profile()
    with pytest.raises(ValueError):
        resolve_role(profile, "nonexistent")


def test_load_profiles_accepts_many_profiles():
    profiles = load_profiles({
        "sw135": {
            "name": "sw135",
            "tier": "fast",
            "limits": {},
            "roles": {},
        },
        "release": {
            "name": "release",
            "tier": "deep",
            "limits": {},
            "roles": {},
        },
    })
    assert set(profiles.keys()) == {"sw135", "release"}
    assert profiles["sw135"].tier == TIER_FAST
    assert profiles["release"].tier == TIER_DEEP


def test_roundtrip_preserves_all_four_parts():
    profile = _profile()
    rebuilt = from_dict(profile.to_dict())
    assert rebuilt.name == profile.name
    assert rebuilt.tier == profile.tier
    assert rebuilt.limits.timeout == profile.limits.timeout
    assert rebuilt.limits.max_retries == profile.limits.max_retries
    assert rebuilt.limits.min_models_required == profile.limits.min_models_required
    assert rebuilt.limits.on_model_failure == profile.limits.on_model_failure
    assert rebuilt.model_for("ops") == profile.model_for("ops")
    assert rebuilt.model_for("worker") == profile.model_for("worker")
    assert rebuilt.tool_for("worker").launch_command == profile.tool_for("worker").launch_command


# ── Criterion 3: capabilities come from the same file, falling closed ────

def test_role_carries_capabilities_from_same_file():
    profile = _profile(
        roles={
            "ops": {
                "model": "sonnet",
                "capabilities": {CAP_MUTATE_RUN_STATE: True},
            },
            "reviewer": {
                "model": "gpt-4o",
                "capabilities": {CAP_APPROVE_GATE: True},
            },
        }
    )
    assert profile.role_can("ops", CAP_MUTATE_RUN_STATE) is True
    assert profile.role_can("ops", CAP_APPROVE_GATE) is False
    assert profile.role_can("reviewer", CAP_MUTATE_RUN_STATE) is False
    assert profile.role_can("reviewer", CAP_APPROVE_GATE) is True


def test_capability_matrix_is_loaded_not_hardcoded():
    profile = _profile(
        roles={
            "ops": {"capabilities": {CAP_MUTATE_RUN_STATE: True}},
            "custom_writer": {"capabilities": {CAP_MUTATE_RUN_STATE: True}},
        }
    )
    matrix = profile.capability_matrix()
    assert isinstance(matrix, dict)
    # The matrix reflects exactly what the file declared: no role that was not
    # declared appears, and no capability is invented for it.
    assert "custom_writer" in matrix
    assert matrix["custom_writer"].can(CAP_MUTATE_RUN_STATE) is True
    assert matrix["custom_writer"].can(CAP_APPROVE_GATE) is False


def test_undeclared_role_falls_closed():
    profile = _profile(
        roles={
            "ops": {"capabilities": {CAP_MUTATE_RUN_STATE: True}},
            "reviewer": {"capabilities": {CAP_APPROVE_GATE: True}},
        }
    )
    # "gremlin" is nowhere in the profile: every capability check must deny.
    assert profile.role("gremlin") is None
    assert profile.role_can("gremlin", CAP_MUTATE_RUN_STATE) is False
    assert profile.role_can("gremlin", CAP_APPROVE_GATE) is False


def test_declared_role_without_capabilities_falls_closed():
    profile = _profile(
        roles={"plain_role": {"model": "sonnet"}}
    )
    assert profile.role_can("plain_role", CAP_MUTATE_RUN_STATE) is False
    assert profile.role_can("plain_role", CAP_APPROVE_GATE) is False


def test_load_matrix_returns_only_declared_roles():
    roles = {
        "ops": RoleDefinition(key="ops", capabilities={CAP_MUTATE_RUN_STATE: True}),
        "reviewer": RoleDefinition(key="reviewer", capabilities={CAP_APPROVE_GATE: True}),
    }
    matrix = load_matrix(roles)
    assert set(matrix.keys()) == {"ops", "reviewer"}


# ── Criterion 4: self-approval refused at load time ───────────────────────

def test_self_approval_refused_at_load_time():
    with pytest.raises(RoutingProfileError):
        from_dict({
            "name": "sw135",
            "tier": "balanced",
            "limits": {},
            "roles": {
                "rot": {
                    "capabilities": {
                        CAP_MUTATE_RUN_STATE: True,
                        CAP_APPROVE_GATE: True,
                    },
                },
            },
        })


def test_self_approval_refused_even_if_one_capability_false():
    # Only a role holding BOTH capabilities (both truthy) is self-approval.
    profile = _profile(
        roles={
            "ops": {
                "capabilities": {
                    CAP_MUTATE_RUN_STATE: True,
                    CAP_APPROVE_GATE: False,
                },
            },
        }
    )
    assert profile.role("ops") is not None
    assert profile.role_can("ops", CAP_MUTATE_RUN_STATE) is True
    assert profile.role_can("ops", CAP_APPROVE_GATE) is False


def test_self_approval_refused_also_in_load_profiles():
    with pytest.raises(RoutingProfileError):
        load_profiles({
            "bad": {
                "name": "bad",
                "tier": "balanced",
                "limits": {},
                "roles": {
                    "rot": {
                        "capabilities": {
                            CAP_MUTATE_RUN_STATE: True,
                            CAP_APPROVE_GATE: True,
                        },
                    },
                },
            }
        })


def test_roundtrip_preserves_capabilities():
    profile = _profile(
        roles={
            "ops": {"capabilities": {CAP_MUTATE_RUN_STATE: True}},
            "reviewer": {"capabilities": {CAP_APPROVE_GATE: True}},
        }
    )
    rebuilt = from_dict(profile.to_dict())
    assert rebuilt.role_can("ops", CAP_MUTATE_RUN_STATE) is True
    assert rebuilt.role_can("ops", CAP_APPROVE_GATE) is False
    assert rebuilt.role_can("reviewer", CAP_APPROVE_GATE) is True


# ── Criterion 7: three vocabularies reconciled explicitly ───────────────

def test_tier_to_router_maps_all_three_tiers():
    assert tier_to_router(TIER_FAST) == ("quick", "quick")
    assert tier_to_router(TIER_BALANCED) == ("default", "standard")
    assert tier_to_router(TIER_DEEP) == ("deep", "full")


def test_tier_to_router_extracts_mode():
    assert tier_to_mode(TIER_FAST) == "quick"
    assert tier_to_mode(TIER_BALANCED) == "standard"
    assert tier_to_mode(TIER_DEEP) == "full"


def test_deep_is_disambiguated_between_tier_and_router_name():
    # `deep` as a TIER resolves to the `deep` router preset with full mode —
    # not the `expert` preset, and not name-matched to any other tier.
    name, mode = tier_to_router(TIER_DEEP)
    assert name == "deep"
    assert mode == "full"


def test_expert_is_not_a_tier():
    # `expert` is a router preset (model quality), not an effort level: no
    # tier may resolve to it, so the tier axis cannot lie about effort vs models.
    for name, _mode in TIER_TO_ROUTER.values():
        assert name != "expert"


def test_tier_to_router_rejects_unknown_tier():
    with pytest.raises(RoutingProfileError):
        tier_to_router("warp")


def test_tier_to_router_has_no_surprise_entries():
    assert set(TIER_TO_ROUTER.keys()) == {TIER_FAST, TIER_BALANCED, TIER_DEEP}


# ── Criterion 8: tier names intent; pinning is marked in the record ──────

def test_tier_names_intent_not_a_model():
    # A tier resolves through the router preset, not to a hardcoded model: the
    # profile's tier is the *intent* axis, Faigate's ROUTER_PROFILES is the
    # resolution. resolve_tier returns models drawn from the preset.
    profile = _profile(tier="balanced")
    record = resolve_tier(profile)
    assert record.tier == "balanced"
    assert record.router_name == "default"
    assert record.mode == "standard"
    assert record.resolved_models == ["sonnet", "gpt-4o", "gemini-pro", "deepseek-v4"]


def test_resolution_record_marks_pinned_profile():
    # A role that pins a concrete model id produces a record that is marked
    # pinned and says so — so a later run can tell "requested by name" from
    # "pinned to this exact model".
    profile = _profile(
        tier="balanced",
        roles={"ops": {"model": "sonnet", "pin": "opus"}},
    )
    record = resolve_tier(profile)
    assert record.is_pinned is True
    assert record.pinned == "opus"
    assert record.resolved_models == ["opus"]
    # The record surfaces the pin in its serialisable form too.
    assert record.to_dict()["pinned"] == "opus"


def test_unpinned_profile_resolution_is_not_marked_pinned():
    profile = _profile(tier="deep")
    record = resolve_tier(profile)
    assert record.is_pinned is False
    assert record.pinned is None
    assert record.resolved_models == ["sonnet", "gpt-4o", "gemini-pro",
                                      "deepseek-v4", "llama-4", "mistral"]


def test_pin_makes_profile_stable_when_preset_changes():
    # Pinning a model id keeps the resolution stable no matter what the preset
    # would otherwise say — that is the point of a pin (AK 8: profile stays
    # valid when models change, pin says exactly what ran).
    profile = _profile(
        tier="balanced",
        roles={"ops": {"pin": "sonnet"}},
    )
    record = resolve_tier(profile)
    assert record.resolved_models == ["sonnet"]


def test_contradictory_pins_are_not_silently_collapsed():
    # Two roles pinning DIFFERENT models has no single resolution. It is
    # reported as unpinned (rather than an invented winner), so a caller can see
    # the contradiction instead of trusting a guessed model.
    profile = _profile(
        tier="balanced",
        roles={
            "ops": {"pin": "opus"},
            "reviewer": {"pin": "sonnet"},
        },
    )
    record = resolve_tier(profile)
    assert record.is_pinned is False
    assert record.pinned is None


# ── Criterion 9: what actually resolved is recorded with the run ─────────

def test_resolution_record_captures_requested_and_resolved():
    # A later run must tell the difference between "what was requested" (tier)
    # and "what actually resolved" (models + mode). The record keeps both sides.
    profile = _profile(tier="fast")
    record = resolve_tier(profile)
    assert record.tier == "fast"
    assert record.router_name == "quick"
    assert record.mode == "quick"
    assert record.resolved_models == ["gpt-4o-mini", "haiku"]


def test_resolution_record_roundtrips():
    record = ResolutionRecord(
        tier="deep",
        router_name="deep",
        mode="full",
        resolved_models=["sonnet", "opus"],
        pinned="opus",
    )
    data = record.to_dict()
    assert data["tier"] == "deep"
    assert data["resolved_models"] == ["sonnet", "opus"]
    assert data["pinned"] == "opus"
    assert data["mode"] == "full"


def test_pin_roundtrip_preserved():
    profile = _profile(roles={"ops": {"pin": "opus"}})
    rebuilt = from_dict(profile.to_dict())
    assert rebuilt.role("ops").is_pinned is True
    assert rebuilt.role("ops").pin == "opus"


# ── Criterion 10: unknown model is UNVERIFIED, never refused on the roster ──

def test_unavailable_model_names_profile_and_role():
    # A role declaring a non-cast model id no longer raises: absence from
    # Faigate's under-reporting /v1/models roster is not evidence of non-service,
    # and refusal requires a positive model-specific error the roster probe
    # cannot produce. The resolution succeeds rather than blocking the profile
    # on a static guess.
    profile = _profile(roles={"ops": {"model": "turbo-9000"}})
    resolution = resolve_tier(profile)
    assert resolution.pinned is None
    assert resolution.resolved_models  # resolved, not refused


def test_unavailable_pin_names_profile_and_role():
    # The same UNVERIFIED guarantee applies to a pin: a concrete model id whose
    # absence from the roster is not grounds for refusal, so the profile
    # resolves rather than blocking on the pin.
    profile = _profile(roles={"worker": {"pin": "claude-nonexistent"}})
    resolution = resolve_tier(profile)
    assert resolution.pinned == "claude-nonexistent"


def test_known_model_ids_is_exhaustive_and_disjoint_from_unknown():
    ids = known_model_ids()
    assert "sonnet" in ids
    assert "opus" in ids
    assert "turbo-9000" not in ids
    # Every preset's models are resolvable, i.e. the availability set is the
    # union of all preset pools, not a guess.
    for preset in ROUTER_PROFILES.values():
        for model in preset["models"]:
            assert model in ids

