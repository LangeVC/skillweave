"""Tests for declarative routing profiles (SW-135 dispatch 1).

Covers the two acceptance criteria of the dispatch:
1. A RoutingProfile is declarable as data and carries all four parts:
   model choice per role, tier (fast/balanced/deep), limits, target tool.
2. Roles are DATA (not an enum); built-ins ops/reviewer/observer/chairman/worker
   plus declarable extras; observer is wired to the existing runtime observer.
"""
import pytest

from skillweave.routing import (
    RoutingProfile,
    RoleDefinition,
    ToolSpec,
    builtin_roles,
    from_dict,
    load_profiles,
    resolve_role,
    TIER_FAST,
    TIER_BALANCED,
    TIER_DEEP,
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
