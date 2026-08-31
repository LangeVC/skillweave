"""Unit tests for Council Profile Parser (DR-004).

Tests Acceptance Criteria:
1. Profiles define capabilities instead of IDs.
2. Parser extracts capability lists.
3. Backward compatibility (if a profile uses a hardcoded ID, it should still work).
"""

from pathlib import Path
import pytest

from skillweave.council.profile_parser import (
    CouncilProfile,
    extract_capabilities,
    extract_capabilities_from_model_id,
    get_profile,
    load_council_profiles,
    parse_profile,
    parse_profile_dict,
    parse_profile_file,
    parse_profile_markdown,
    parse_profile_section,
)
from skillweave.routing.policy import RoutingPolicyEngine


def test_parse_reference_council_profiles_file():
    """Verify that the official references/council-profiles.md parses properly with capabilities."""
    profiles = load_council_profiles()
    assert "default" in profiles
    assert "quick" in profiles
    assert "deep" in profiles
    assert "expert" in profiles

    default_prof = profiles["default"]
    assert default_prof.name == "default"
    assert "reasoning" in default_prof.capabilities
    assert "general" in default_prof.capabilities
    assert default_prof.chairman == "reasoning"
    assert default_prof.mode == "standard"
    assert default_prof.temperature == 0.5
    assert default_prof.is_capability_based is True

    quick_prof = profiles["quick"]
    assert quick_prof.name == "quick"
    assert "fast" in quick_prof.capabilities
    assert quick_prof.mode == "quick"
    assert quick_prof.temperature == 0.3

    deep_prof = profiles["deep"]
    assert deep_prof.name == "deep"
    assert "reasoning" in deep_prof.capabilities
    assert "analysis" in deep_prof.capabilities
    assert deep_prof.mode == "full"

    expert_prof = profiles["expert"]
    assert expert_prof.name == "expert"
    assert "expert" in expert_prof.capabilities
    assert expert_prof.mode == "full"


def test_parse_markdown_custom_capability_profiles():
    """AC 1: Profiles define capabilities instead of IDs."""
    md_content = """
# Custom Profiles

## code_review
- Capabilities: coding, reasoning, analysis
- Chairman: reasoning
- Mode: full
- Temperature: 0.2
- Use: In-depth code security and quality review
- Min Models: 3
- Max Cost: 0.10

## fast_qa
- Capabilities: fast, general
- Chairman: fast
- Mode: quick
- Temperature: 0.7
- Description: Rapid Q&A
"""
    profiles = parse_profile_markdown(md_content)
    assert len(profiles) == 2
    assert "code_review" in profiles
    assert "fast_qa" in profiles

    cr = profiles["code_review"]
    assert cr.capabilities == ["coding", "reasoning", "analysis"]
    assert cr.chairman == "reasoning"
    assert cr.chairman_capabilities == ["reasoning"]
    assert cr.mode == "full"
    assert cr.temperature == 0.2
    assert cr.use == "In-depth code security and quality review"
    assert cr.min_models_required == 3
    assert cr.max_cost == 0.10
    assert cr.is_capability_based is True


def test_extract_capabilities():
    """AC 2: Parser extracts capability lists."""
    # From CouncilProfile object
    prof = CouncilProfile(name="test", capabilities=["vision", "reasoning"])
    assert extract_capabilities(prof) == ["vision", "reasoning"]

    # From dict with capabilities
    dict_data = {"capabilities": ["coding", "tools"]}
    assert extract_capabilities(dict_data) == ["coding", "tools"]

    # From dict with comma-separated capabilities string
    dict_str = {"capabilities": "coding, tools, reasoning"}
    assert extract_capabilities(dict_str) == ["coding", "tools", "reasoning"]

    # From markdown text
    md = """
## sec_audit
- Capabilities: security, analysis, reasoning
- Mode: full
"""
    assert extract_capabilities(md) == ["security", "analysis", "reasoning"]

    # From list of strings
    assert extract_capabilities(["reasoning", "fast"]) == ["reasoning", "fast"]

    # Single capability keyword
    assert extract_capabilities("reasoning") == ["reasoning"]


def test_backward_compatibility_hardcoded_model_ids():
    """AC 3: Backward compatibility (if a profile uses a hardcoded ID, it should still work)."""
    legacy_md = """
## legacy_standard
- Models: deepseek-v4-pro, deepseek-v4-flash
- Chairman: deepseek-v4-pro
- Mode: standard
- Temperature: 0.5
- Use: Legacy model-based deliberation
"""
    profiles = parse_profile_markdown(legacy_md)
    assert "legacy_standard" in profiles
    legacy = profiles["legacy_standard"]

    # Hardcoded IDs are preserved
    assert legacy.models == ["deepseek-v4-pro", "deepseek-v4-flash"]
    assert legacy.chairman == "deepseek-v4-pro"
    assert legacy.mode == "standard"

    # Resolving models directly returns the hardcoded IDs
    resolved_models = legacy.resolve_models()
    assert resolved_models == ["deepseek-v4-pro", "deepseek-v4-flash"]

    # Resolving chairman returns the hardcoded chairman ID
    resolved_chairman = legacy.resolve_chairman()
    assert resolved_chairman == "deepseek-v4-pro"

    # Extracting capabilities from legacy profile derives capabilities from models
    caps = extract_capabilities(legacy)
    assert len(caps) > 0


def test_backward_compatibility_dict_format():
    """Verify legacy dict format with 'models' works seamlessly."""
    legacy_dict = {
        "models": ["gpt-4o", "claude-3-5-sonnet"],
        "chairman": "claude-3-5-sonnet",
        "mode": "full",
        "temperature": 0.4,
    }
    profile = parse_profile_dict(legacy_dict, name="legacy_dict")
    assert isinstance(profile, CouncilProfile)
    assert profile.name == "legacy_dict"
    assert profile.models == ["gpt-4o", "claude-3-5-sonnet"]
    assert profile.chairman == "claude-3-5-sonnet"
    assert profile.resolve_models() == ["gpt-4o", "claude-3-5-sonnet"]
    assert profile.resolve_chairman() == "claude-3-5-sonnet"


def test_dynamic_resolution_with_policy_engine():
    """Verify integration between CouncilProfile capabilities and RoutingPolicyEngine."""
    adapter_cache = {
        "deepseek-v4-pro": {"capabilities": ["reasoning", "coding"], "cost": 0.02},
        "deepseek-v4-flash": {"capabilities": ["fast", "general"], "cost": 0.005},
        "vision-expert": {"capabilities": ["vision", "reasoning"], "cost": 0.03},
    }
    engine = RoutingPolicyEngine(adapter_cache)

    prof = CouncilProfile(
        name="reasoning_team",
        capabilities=["reasoning"],
        chairman="reasoning",
        max_cost=0.05,
    )

    resolved = prof.resolve_models(policy_engine=engine)
    # Both deepseek-v4-pro and vision-expert have "reasoning"
    assert "deepseek-v4-pro" in resolved
    assert "vision-expert" in resolved
    assert "deepseek-v4-flash" not in resolved  # lacks "reasoning"

    chairman = prof.resolve_chairman(policy_engine=engine)
    assert chairman in ["deepseek-v4-pro", "vision-expert"]


def test_has_capability_helper():
    prof = CouncilProfile(name="test", capabilities=["Reasoning", "Coding"])
    assert prof.has_capability("reasoning") is True
    assert prof.has_capability("coding") is True
    assert prof.has_capability("vision") is False


def test_to_dict_roundtrip():
    original = CouncilProfile(
        name="expert_custom",
        capabilities=["reasoning", "analysis"],
        chairman="reasoning",
        mode="full",
        temperature=0.4,
        use="Custom expert profile",
        min_models_required=3,
        max_cost=0.08,
    )
    d = original.to_dict()
    reconstructed = CouncilProfile.from_dict(d)
    assert reconstructed.name == original.name
    assert reconstructed.capabilities == original.capabilities
    assert reconstructed.chairman == original.chairman
    assert reconstructed.mode == original.mode
    assert reconstructed.temperature == original.temperature
    assert reconstructed.use == original.use
    assert reconstructed.min_models_required == original.min_models_required
    assert reconstructed.max_cost == original.max_cost


def test_get_profile_fallback():
    # Known profile
    prof = get_profile("default")
    assert prof.name == "default"

    # Unknown profile falls back to default
    unknown = get_profile("non_existent_profile_xyz")
    assert unknown.name == "default"


def test_universal_parse_profile():
    # Pass CouncilProfile
    p = CouncilProfile(name="p1", capabilities=["fast"])
    assert parse_profile(p) is p

    # Pass dict
    d = {"name": "p2", "capabilities": ["coding"]}
    res = parse_profile(d)
    assert isinstance(res, CouncilProfile)
    assert res.name == "p2"

    # Pass markdown string
    md = "## p3\n- Capabilities: vision\n"
    res_md = parse_profile(md)
    assert isinstance(res_md, dict)
    assert "p3" in res_md
