"""Routing decision: the three declared modes, and nothing inferred.

``profile.py`` (lane 012) declares what a profile *is*: per-role model choice,
a tier, limits, and a target tool. This module declares how a run *chooses*
among profiles, and it does so explicitly, never by guessing.

Three modes exist, and only these three:

``pin``
    Use the named profile. Decide nothing. ``complexity`` is never read, no
    bounds are applied, and no automatic tier is derived. A pinned profile is
    the operator's override and is never silently improved upon.

``auto``
    Derive the tier from complexity. The complexity value is what
    promptchain-generate already computed (points, criteria count, dependency
    depth) — this module consumes it, it does not compute a second measure of
    its own. Resolving those raw measures into the declared complexity value is
    the upstream producer's job (dispatch 3); here the value drives the tier
    directly.

``hybrid``
    Let ``auto`` decide, but only WITHIN bounds the profile declares. The
    bounds are read from the profile's own metadata (``floor_tier`` and
    ``ceiling_tier``), plus any per-role pin. The decision is free only where
    it was allowed to be free: outside the bounds it is clamped, and every
    clamp is recorded as an adjustment, not presented as the original decision.

The modes are the point. ``decide`` refuses an unknown mode with an error that
names it, so a caller can never pass a free-form string and have it treated as
"close enough" — the same discipline profile.py applies to tiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from skillweave.routing.profile import (
    RoutingProfile,
    RoutingProfileError,
    RoleDefinition,
    TIER_FAST,
    TIER_BALANCED,
    TIER_DEEP,
    VALID_TIERS,
)

MODE_PIN = "pin"
MODE_AUTO = "auto"
MODE_HYBRID = "hybrid"

VALID_MODES = frozenset({MODE_PIN, MODE_AUTO, MODE_HYBRID})

# Ordering over the tier axis, used only to decide "below the floor" and
# "above the ceiling" inside hybrid. It is an ordinal, not a value judgement.
TIER_ORDER = {
    TIER_FAST: 0,
    TIER_BALANCED: 1,
    TIER_DEEP: 2,
}

# Metadata keys a profile may carry to declare hybrid bounds.
FLOOR_KEY = "floor_tier"
CEILING_KEY = "ceiling_tier"

ADJUST_FLOOR = "floor"
ADJUST_CEILING = "ceiling"


@dataclass
class Adjustment:
    """A bound that clamped a hybrid decision.

    ``kind`` is ``floor`` (decision raised up to the floor) or ``ceiling``
    (decision lowered down to it). ``from_tier`` is what auto decided;
    ``to_tier`` is the tier actually used after clamping. The two are always
    different, which is what makes an adjustment visible in the record instead
    of silently swallowing the clamp.
    """

    kind: str
    from_tier: str
    to_tier: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "from_tier": self.from_tier,
            "to_tier": self.to_tier,
        }


@dataclass
class RoutingDecision:
    """What ``decide`` produced: the declared mode, the resolved tier, any pin,
    and any bound adjustments that fired.

    A later run can reconstruct the whole story from this single record: which
    mode was declared, which tier resulted, what complexity input drove it (if
    any), and exactly which floor/ceiling bounds adjusted it along the way.
    """

    mode: str
    profile: str
    tier: str
    adjustments: list[Adjustment] = field(default_factory=list)
    pinned: Optional[str] = None
    input: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "profile": self.profile,
            "tier": self.tier,
            "pinned": self.pinned,
            "input": self.input,
            "adjustments": [a.to_dict() for a in self.adjustments],
        }


def _tier_from_complexity(complexity: Any) -> str:
    """Map the declared complexity value onto a tier.

    ``complexity`` is either a tier name directly (``fast``/``balanced``/
    ``deep``) or a non-negative integer rank resolved against the three ordered
    tiers (0 -> fast, 1 -> balanced, >=2 -> deep). An unknown value is refused
    loudly, mirroring profile.py's tier guard. This is the consumption half:
    it does not compute points/criteria/depth, it trusts whatever the producer
    already resolved into this value.
    """
    if isinstance(complexity, str):
        if complexity not in VALID_TIERS:
            raise RoutingProfileError(
                f"unknown complexity '{complexity}' "
                f"(expected one of {sorted(VALID_TIERS)})"
            )
        return complexity
    if isinstance(complexity, int) and not isinstance(complexity, bool):
        if complexity < 0:
            raise RoutingProfileError(
                f"complexity rank must be non-negative, got {complexity}"
            )
        ordered = [TIER_FAST, TIER_BALANCED, TIER_DEEP]
        return ordered[min(complexity, len(ordered) - 1)]
    raise RoutingProfileError(
        f"complexity must be a tier name or a non-negative integer, got "
        f"{complexity!r}"
    )


def _role_pin(profile: RoutingProfile, role: Optional[str]) -> Optional[str]:
    """Return the pin for ``role``, or None when there is no such pinned role.

    A pin is per-role data (``RoleDefinition.pin``). Inside hybrid a per-role
    pin wins: when the deciding role pins a model, that model is used and no
    bound adjustment applies, because there is no free decision left to clamp.
    """
    if role is None:
        return None
    definition: Optional[RoleDefinition] = profile.role(role)
    if definition is None or not definition.is_pinned:
        return None
    return definition.pin


def _hybrid_bounds(profile: RoutingProfile) -> tuple[Optional[str], Optional[str]]:
    """Read hybrid bounds from the profile's own metadata.

    Returns ``(floor_tier, ceiling_tier)``; either may be None to mean "no
    bound on that side". A declared bound that is not a valid tier is refused
    loudly, the same as any other malformed profile field.
    """
    floor = profile.metadata.get(FLOOR_KEY)
    ceiling = profile.metadata.get(CEILING_KEY)
    for label, value in ((FLOOR_KEY, floor), (CEILING_KEY, ceiling)):
        if value is not None and value not in VALID_TIERS:
            raise RoutingProfileError(
                f"profile '{profile.name}' declares {label} '{value}' "
                f"which is not a valid tier ({sorted(VALID_TIERS)})"
            )
    return floor, ceiling


def decide(
    profile: RoutingProfile,
    mode: str,
    complexity: Any = None,
    role: Optional[str] = None,
) -> RoutingDecision:
    """Choose a routing decision for ``profile`` under the declared ``mode``.

    ``mode`` must be one of :data:`MODE_PIN`, :data:`MODE_AUTO`, :data:`MODE_HYBRID`.
    Any other value raises :class:`RoutingProfileError` — modes are declared,
    never inferred. ``complexity`` is the value ``auto`` (and ``hybrid``, which
    is auto-with-bounds) derives the tier from; ``role`` is the per-role pin
    scope relevant only inside hybrid.

    Returns a :class:`RoutingDecision` carrying the mode, profile, final tier,
    any pin, and any adjustments. Adjustments only ever appear under hybrid and
    are always recorded separately from the tier they adjusted, so a floor or
    ceiling clamp is visible rather than presented as the original decision.
    """
    if mode not in VALID_MODES:
        raise RoutingProfileError(
            f"unknown routing mode '{mode}' "
            f"(expected one of {sorted(VALID_MODES)})"
        )

    if mode == MODE_PIN:
        # Decide nothing: the profile's own tier stands, complexity is ignored,
        # and no automatic decision runs at all. A pin is the operator's
        # override, never improved upon.
        pinned = _role_pin(profile, role)
        return RoutingDecision(
            mode=mode,
            profile=profile.name,
            tier=profile.tier,
            pinned=pinned,
            input=None,
            adjustments=[],
        )

    # auto and hybrid both derive the tier from complexity. hybrid then clamps
    # that tier inside declared bounds; auto does not.
    tier = _tier_from_complexity(complexity)

    if mode == MODE_AUTO:
        return RoutingDecision(
            mode=mode,
            profile=profile.name,
            tier=tier,
            pinned=None,
            input=complexity,
            adjustments=[],
        )

    # mode == MODE_HYBRID
    pinned = _role_pin(profile, role)
    adjustments: list[Adjustment] = []

    if pinned is None:
        floor, ceiling = _hybrid_bounds(profile)
        if floor is not None and TIER_ORDER[tier] < TIER_ORDER[floor]:
            adjustments.append(Adjustment(ADJUST_FLOOR, from_tier=tier, to_tier=floor))
            tier = floor
        if ceiling is not None and TIER_ORDER[tier] > TIER_ORDER[ceiling]:
            adjustments.append(Adjustment(ADJUST_CEILING, from_tier=tier, to_tier=ceiling))
            tier = ceiling

    return RoutingDecision(
        mode=mode,
        profile=profile.name,
        tier=tier,
        pinned=pinned,
        input=complexity,
        adjustments=adjustments,
    )
