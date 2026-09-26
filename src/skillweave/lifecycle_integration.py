"""The one contract through which lifecycle and routing read the onboarding profile.

Onboarding (SW-156-ONBOARD-001/002) produces two artifacts with very different
standing:

``skillweave.config/onboarding-profile.yaml``
    The *durable* operator profile: role, purpose, autonomy and risk boundary,
    each drawn from a closed vocabulary. This is authored input, and it exists
    only once someone has actually been onboarded.

``.skillweave/onboarding-state.yaml``
    The *generated* onboarding result. It is computed output that resolves every
    unset field from ``PROFILE_DEFAULTS``, so it always looks like a complete
    profile even on a project where no profile was ever declared.

Lifecycle and routing read the durable profile here, and only here. They
deliberately do not read the generated state as a profile: the generated state
cannot distinguish "the operator chose ``developer``" from "nobody answered and
the default filled in". A missing profile is therefore a first-class outcome --
:func:`read_profile` reports it and returns the onboarding guidance -- and never
a reason to synthesise an operator profile from the defaults.
"""

import os
from dataclasses import dataclass
from typing import Optional

import yaml

from .onboarding import OnboardingService
from .onboarding.service import DURABLE_PROFILE_PATH
from .onboarding_cli import PROFILE_CHOICES, load_onboarding_state
from .phase_detection import detect_phase
from .routing.decide import CEILING_KEY, FLOOR_KEY, MODE_HYBRID, decide
from .routing.profile import (
    RoutingProfile,
    TIER_BALANCED,
    TIER_DEEP,
    TIER_FAST,
)
from .workflow_recommendation import recommend

#: Directory holding the durable authored profile, relative to the project root.
CONFIG_DIR = "skillweave.config"

#: Guidance returned when no profile has been authored. Deliberately a single
#: string shared by lifecycle and routing: one contract, one answer to "what now".
MISSING_PROFILE_GUIDANCE = (
    "No onboarding profile has been authored at {path}. Run interactive "
    "onboarding (``skillweave onboard``) to declare a role, purpose, autonomy "
    "and risk boundary. Lifecycle and routing read that profile and will not "
    "invent an operator profile in its place."
)

# ── Profile -> lifecycle ────────────────────────────────────────────────────
#
# Purpose is the profile field that speaks to the lifecycle: it says what the
# operator is trying to do, and each purpose has a bundle whose phases are that
# work. The mapping is declared here, in the same place both readers meet the
# profile, rather than being recomputed from the generated state.
PURPOSE_TO_BUNDLE: dict[str, str] = {
    "build": "design-and-build",
    "review": "release-and-launch",
    "research": "discovery-to-blueprint",
    "operate": "post-release-improvement",
}

# ── Profile -> routing ──────────────────────────────────────────────────────
#
# The onboarding role vocabulary and the routing role vocabulary are different
# axes with confusingly similar names, so the reconciliation is written out
# rather than left to string identity. The routing roles are the built-ins from
# ``routing.profile``.
ROLE_TO_ROUTING_ROLE: dict[str, str] = {
    "operator": "ops",
    "developer": "worker",
    "reviewer": "reviewer",
    "researcher": "observer",
}

# Autonomy is the profile field that speaks to routing: it says how much should
# happen without confirmation, which is a depth-of-model question. Guided work
# is quick, autonomous work is deep.
AUTONOMY_TO_TIER: dict[str, str] = {
    "guided": TIER_FAST,
    "supervised": TIER_BALANCED,
    "autonomous": TIER_DEEP,
}

#: The declared baseline complexity the profile-derived route is computed from.
#: Rank 0 is "fast"; the profile's own tier then floors the hybrid decision, so
#: the result is the profile's tier and the clamp is visible as an adjustment.
_ROUTE_BASELINE_COMPLEXITY = 0


@dataclass(frozen=True)
class ProfileRead:
    """What the contract hands to lifecycle and routing.

    ``profile`` holds authored fields only, so it is empty whenever ``missing``
    is true -- there is no default-filled shape to mistake for a choice.
    """

    profile: dict[str, str]
    missing: bool
    source: str  # "durable" | "absent" | "empty" | "invalid"
    guidance: Optional[str]
    profile_path: str

    @property
    def configured(self) -> bool:
        return not self.missing


def profile_path(project_root: str = ".") -> str:
    """Path of the durable authored profile under ``project_root``."""
    return os.path.join(str(project_root), CONFIG_DIR, DURABLE_PROFILE_PATH)


def _valid_authored_fields(raw: dict) -> dict[str, str]:
    """Keep only the four profile fields carrying a declared choice.

    A value outside the closed vocabulary is dropped rather than trusted: the
    vocabularies are closed by design (see ``onboarding_cli``), so an
    off-vocabulary value is not a profile field we know how to act on.
    """
    profile: dict[str, str] = {}
    for field, choices in PROFILE_CHOICES.items():
        value = raw.get(field)
        if isinstance(value, str) and value in choices:
            profile[field] = value
    return profile


def read_profile(project_root: str = ".") -> ProfileRead:
    """Read the durable onboarding profile -- the single contract.

    Absent, empty, corrupt and off-vocabulary profiles all resolve to
    ``missing=True`` with the onboarding guidance. The one thing this never does
    is fill the gaps from ``PROFILE_DEFAULTS`` and present the result as an
    operator profile.
    """
    path = profile_path(project_root)

    # The read goes through the onboarding service -- the same durable-profile
    # loader the skill and CLI use -- so there is one implementation of "what
    # the authored profile is", not a second YAML reader.
    raw = OnboardingService(project_root).load_durable_profile()
    if raw is None:
        # Absent and unreadable both come back as None; the file's existence is
        # what tells the two apart.
        return _missing(path, "absent" if not os.path.exists(path) else "invalid")

    profile = _valid_authored_fields(raw)
    if not profile:
        # Either an empty file, or one whose every value is off-vocabulary.
        return _missing(path, "empty" if not raw else "invalid")

    return ProfileRead(
        profile=profile,
        missing=False,
        source="durable",
        guidance=None,
        profile_path=path,
    )


def _missing(path: str, source: str) -> ProfileRead:
    return ProfileRead(
        profile={},
        missing=True,
        source=source,
        guidance=MISSING_PROFILE_GUIDANCE.format(path=path),
        profile_path=path,
    )


def lifecycle_profile_context(project_root: str = ".") -> dict:
    """Lifecycle's read of the profile: the bundle the declared purpose implies.

    Returns ``active_bundle=None`` and the guidance when no profile is authored,
    so an unconfigured project is steered to onboarding instead of being handed
    the bundle a default profile would have implied.
    """
    read = read_profile(project_root)
    bundle = None
    if read.configured:
        bundle = PURPOSE_TO_BUNDLE.get(read.profile.get("purpose", ""))

    return {
        "profile": dict(read.profile),
        "configured": read.configured,
        "missing": read.missing,
        "source": read.source,
        "active_bundle": bundle,
        "guidance": read.guidance,
        "profile_path": read.profile_path,
    }


def recommended_route(project_root: str = ".") -> dict:
    """Routing's read of the profile: a route derived from role and autonomy.

    The decision itself is made by ``routing.decide`` -- this function only
    supplies the profile-derived inputs, so the routing rules stay in one place.
    With no profile authored there is no route to derive and the guidance is
    returned instead.
    """
    read = read_profile(project_root)
    if read.missing:
        return {
            "decision": None,
            "tier": None,
            "rendered_role": None,
            "routing_role": None,
            "missing": True,
            "source": read.source,
            "guidance": read.guidance,
        }

    rendered_role = read.profile.get("role")
    tier = AUTONOMY_TO_TIER.get(read.profile.get("autonomy", ""), TIER_BALANCED)

    # The profile's tier is both floor and ceiling: it is a declaration, not a
    # suggestion, so the hybrid decision is pinned to it while still being made
    # by ``decide`` and recorded as an adjustment.
    routing_profile = RoutingProfile(
        name="onboarding-profile",
        tier=tier,
        metadata={FLOOR_KEY: tier, CEILING_KEY: tier},
    )
    decision = decide(
        routing_profile,
        MODE_HYBRID,
        complexity=_ROUTE_BASELINE_COMPLEXITY,
    )

    return {
        "decision": decision.to_dict(),
        "tier": decision.tier,
        "rendered_role": rendered_role,
        "routing_role": ROLE_TO_ROUTING_ROLE.get(rendered_role or ""),
        "missing": False,
        "source": read.source,
        "guidance": None,
    }


def enrich_config(project_root: str = "."):
    config_path = os.path.join(project_root, ".skillweave", "config.yaml")
    if not os.path.exists(config_path):
        return None

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    changed = False
    lifecycle = config.setdefault("lifecycle", {})

    if "current_phase" not in lifecycle:
        phase, confidence = detect_phase(project_root)
        lifecycle["current_phase"] = phase
        lifecycle["phase_confidence"] = round(confidence, 2)
        changed = True

    if "active_bundle" not in lifecycle:
        # The authored profile is the first source: it states the purpose, and
        # the purpose implies the bundle. The generated onboarding state and the
        # phase-based recommendation remain as fallbacks for projects that have
        # no authored profile yet.
        profile_ctx = lifecycle_profile_context(project_root)
        if profile_ctx["active_bundle"]:
            lifecycle["active_bundle"] = profile_ctx["active_bundle"]
        else:
            ob_state = load_onboarding_state(project_root)
            if ob_state and ob_state.get("recommended_bundle"):
                lifecycle["active_bundle"] = ob_state["recommended_bundle"]
            else:
                rec = recommend(project_root=project_root)
                if rec.get("recommended_bundle"):
                    lifecycle["active_bundle"] = rec["recommended_bundle"]
        changed = True

    if changed:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

    return config


def get_lifecycle_context(project_root: str = ".") -> dict:
    config_path = os.path.join(project_root, ".skillweave", "config.yaml")
    context = {
        "phase_system_configured": False,
        "current_phase": None,
        "active_bundle": None,
        "phase_confidence": None,
    }

    if os.path.exists(config_path):
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        lifecycle = config.get("lifecycle", {})
        if lifecycle:
            context["phase_system_configured"] = True
            context["current_phase"] = lifecycle.get("current_phase")
            context["active_bundle"] = lifecycle.get("active_bundle")
            context["phase_confidence"] = lifecycle.get("phase_confidence")

    # The profile travels with the lifecycle context so a caller sees the
    # declared purpose alongside the bundle it produced -- and sees the guidance
    # rather than a fabricated bundle when nothing was declared.
    profile_ctx = lifecycle_profile_context(project_root)
    context["profile"] = profile_ctx["profile"]
    context["profile_configured"] = profile_ctx["configured"]
    context["onboarding_guidance"] = profile_ctx["guidance"]

    return context
