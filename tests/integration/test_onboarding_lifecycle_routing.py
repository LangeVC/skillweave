"""Lifecycle and routing consume the onboarding profile (SW-156-ONBOARD-003).

Covers the three acceptance criteria:

1. **One contract** -- lifecycle and routing both read the profile through
   :func:`skillweave.lifecycle_integration.read_profile`, and both see the same
   authored fields.
2. **A profile change changes a route or recommendation** -- changing the
   authored profile changes the route/recommendation lifecycle and routing
   produce.
3. **A missing profile triggers onboarding guidance** -- no profile means the
   guidance, never an operator profile invented from ``PROFILE_DEFAULTS``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.lifecycle_integration import (
    MISSING_PROFILE_GUIDANCE,
    get_lifecycle_context,
    lifecycle_profile_context,
    read_profile,
    recommended_route,
)
from skillweave.onboarding import OnboardingService
from skillweave.onboarding_cli import PROFILE_DEFAULTS


# ── Helpers ──────────────────────────────────────────────────────────────────


def _durable_profile_path(root: Path) -> Path:
    return root / "skillweave.config" / "onboarding-profile.yaml"


def _author(root: Path, **profile: str) -> None:
    """Write an authored profile directly, as onboarding would persist it."""
    path = _durable_profile_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(profile, sort_keys=False))


# ── Criterion 1: lifecycle and routing read through one contract ─────────────


def test_lifecycle_and_routing_read_one_contract(tmp_path):
    """Both readers observe the same authored fields, from the same file."""
    _author(tmp_path, role="researcher", purpose="research",
            autonomy="autonomous", risk_boundary="medium")

    read = read_profile(str(tmp_path))
    lifecycle = lifecycle_profile_context(str(tmp_path))
    route = recommended_route(str(tmp_path))

    assert read.configured is True
    # Lifecycle and routing agree with the contract, field for field.
    assert lifecycle["profile"] == read.profile
    assert route["rendered_role"] == read.profile["role"]
    assert lifecycle["missing"] is False
    assert route["missing"] is False
    # And the contract reads exactly what was authored -- nothing added.
    assert read.profile == {
        "role": "researcher",
        "purpose": "research",
        "autonomy": "autonomous",
        "risk_boundary": "medium",
    }


def test_service_written_profile_is_what_the_contract_reads(tmp_path):
    """The profile onboarding persists is the profile the contract reads."""
    OnboardingService(tmp_path).apply(
        role="reviewer", purpose="review", autonomy="supervised",
        risk_boundary="conservative",
    )

    read = read_profile(str(tmp_path))
    assert read.source == "durable"
    assert read.profile == {
        "role": "reviewer",
        "purpose": "review",
        "autonomy": "supervised",
        "risk_boundary": "conservative",
    }


def test_lifecycle_context_carries_the_profile(tmp_path):
    """The lifecycle context surfaces the declared profile and its bundle."""
    _author(tmp_path, role="operator", purpose="operate",
            autonomy="guided", risk_boundary="medium")

    ctx = get_lifecycle_context(str(tmp_path))
    assert ctx["profile_configured"] is True
    assert ctx["profile"]["purpose"] == "operate"
    assert ctx["onboarding_guidance"] is None


# ── Criterion 2: a changed profile changes a recommendation or route ─────────


@pytest.mark.parametrize(
    "purpose,expected_bundle",
    [
        ("build", "design-and-build"),
        ("review", "release-and-launch"),
        ("research", "discovery-to-blueprint"),
        ("operate", "post-release-improvement"),
    ],
)
def test_changed_purpose_changes_recommended_bundle(tmp_path, purpose, expected_bundle):
    """Each authored purpose yields its own bundle recommendation."""
    _author(tmp_path, role="operator", purpose=purpose,
            autonomy="guided", risk_boundary="medium")

    ctx = lifecycle_profile_context(str(tmp_path))
    assert ctx["active_bundle"] == expected_bundle


def test_differential_purpose_changes_the_bundle(tmp_path):
    """The same project, two profiles, two different bundles."""
    _author(tmp_path, role="operator", purpose="build",
            autonomy="guided", risk_boundary="medium")
    build_bundle = lifecycle_profile_context(str(tmp_path))["active_bundle"]

    _author(tmp_path, role="operator", purpose="operate",
            autonomy="guided", risk_boundary="medium")
    operate_bundle = lifecycle_profile_context(str(tmp_path))["active_bundle"]

    assert build_bundle != operate_bundle


@pytest.mark.parametrize(
    "autonomy,expected_tier",
    [("guided", "fast"), ("supervised", "balanced"), ("autonomous", "deep")],
)
def test_changed_autonomy_changes_the_route_tier(tmp_path, autonomy, expected_tier):
    """Each authored autonomy yields its own route tier, via routing.decide."""
    _author(tmp_path, role="developer", purpose="build",
            autonomy=autonomy, risk_boundary="medium")

    route = recommended_route(str(tmp_path))
    assert route["tier"] == expected_tier
    assert route["decision"]["tier"] == expected_tier


def test_differential_profile_changes_the_route(tmp_path):
    """Changing the profile changes the route routing produces."""
    _author(tmp_path, role="developer", purpose="build",
            autonomy="guided", risk_boundary="conservative")
    guided = recommended_route(str(tmp_path))

    _author(tmp_path, role="developer", purpose="build",
            autonomy="autonomous", risk_boundary="conservative")
    autonomous = recommended_route(str(tmp_path))

    assert guided["tier"] != autonomous["tier"]


def test_changed_role_changes_the_route_role_mapping(tmp_path):
    """The onboarding role maps to a different routing role per choice."""
    _author(tmp_path, role="reviewer", purpose="review", autonomy="guided",
            risk_boundary="conservative")
    reviewer = recommended_route(str(tmp_path))

    _author(tmp_path, role="operator", purpose="review", autonomy="guided",
            risk_boundary="conservative")
    operator = recommended_route(str(tmp_path))

    assert reviewer["routing_role"] == "reviewer"
    assert operator["routing_role"] == "ops"
    assert reviewer["routing_role"] != operator["routing_role"]


# ── Criterion 3: a missing profile triggers onboarding guidance ──────────────


def test_absent_profile_reports_missing_not_defaults(tmp_path):
    """No profile file: the contract reports missing and never defaults."""
    read = read_profile(str(tmp_path))

    assert read.missing is True
    assert read.configured is False
    assert read.source == "absent"
    assert read.profile == {}
    assert read.guidance is not None
    assert MISSING_PROFILE_GUIDANCE.format(path=str(_durable_profile_path(tmp_path))) == read.guidance


def test_missing_profile_guides_instead_of_inventing_a_bundle(tmp_path):
    """Lifecycle offers no bundle and the guidance when nothing is authored."""
    ctx = lifecycle_profile_context(str(tmp_path))

    assert ctx["active_bundle"] is None
    assert ctx["configured"] is False
    assert ctx["profile"] == {}
    assert ctx["guidance"] is not None


def test_missing_profile_guides_instead_of_inventing_a_route(tmp_path):
    """Routing derives no route and the guidance when nothing is authored."""
    route = recommended_route(str(tmp_path))

    assert route["missing"] is True
    assert route["decision"] is None
    assert route["tier"] is None
    assert route["rendered_role"] is None
    assert route["guidance"] is not None


def test_no_default_profile_is_ever_invented(tmp_path):
    """The defaults never appear as resolved values when nothing is authored."""
    read = read_profile(str(tmp_path))
    route = recommended_route(str(tmp_path))
    ctx = lifecycle_profile_context(str(tmp_path))

    default_values = set(PROFILE_DEFAULTS.values())
    assert default_values.isdisjoint(read.profile.values())
    assert route["tier"] is None
    assert route["rendered_role"] is None
    assert ctx["active_bundle"] is None


@pytest.mark.parametrize("content", ["", "not: a profile", "role: wizard\n"])
def test_empty_corrupt_and_off_vocabulary_profiles_are_missing(tmp_path, content):
    """An unusable profile is missing, it is not silently repaired."""
    path = _durable_profile_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)

    read = read_profile(str(tmp_path))
    assert read.missing is True
    assert read.profile == {}
    assert read.guidance is not None

    route = recommended_route(str(tmp_path))
    assert route["missing"] is True
    assert route["tier"] is None


def test_corrupt_yaml_does_not_raise(tmp_path):
    """Unparseable YAML is a missing profile, not an exception."""
    path = _durable_profile_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("::: not yaml :::\n\t- broken")

    read = read_profile(str(tmp_path))
    assert read.missing is True
    assert read.source == "invalid"


def test_lifecycle_context_guides_when_profile_absent(tmp_path):
    """The lifecycle context carries the guidance for an unconfigured project."""
    ctx = get_lifecycle_context(str(tmp_path))

    assert ctx["profile_configured"] is False
    assert ctx["profile"] == {}
    assert ctx["onboarding_guidance"] is not None
