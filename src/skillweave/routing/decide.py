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
    Derive the tier from complexity: either the raw metrics (points, criteria
    count, dependency depth) converted here via the named :func:`rank_metrics`
    step, or a rank the producer already emitted. There is exactly one measure
    of complexity, and the conversion between the raw scale and the rank scale
    is explicit with its thresholds written down — never two disagreeing
    measures, never an undeclared translation between two number scales.

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

from dataclasses import dataclass, field, replace
from typing import Any, Optional

from skillweave.routing.faigate_adapter import resolve_tier

from skillweave.routing.profile import (
    ResolutionRecord,
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

# The rank is what decide() consumes: 0 = fast, 1 = balanced, >=2 = deep.
# promptchain-generate emits raw metrics (points, criteria count, dependency
# depth); this module owns the named step that turns those into a rank so the
# thresholds are written down in exactly one place.
RANK_FAST = 0
RANK_BALANCED = 1
RANK_DEEP = 2

# Raw-metric ranges measured from complexity-analysis.md on 2026-08-16, so the
# thresholds below are calibrated to data, not invented symmetry.
MEASURED_POINTS = (1, 8)
MEASURED_CRITERIA = (3, 10)
MEASURED_DEPTH = (0, 5)

# The single named conversion: raw metrics -> rank. A task is "fast" only when
# it is small on every axis; "deep" as soon as any axis is heavy; "balanced"
# in between. The thresholds are literals so the translation is auditable and
# cannot drift silently between two number scales.
FAST_MAX_POINTS = 2
FAST_MAX_CRITERIA = 4
FAST_MAX_DEPTH = 1
DEEP_MIN_POINTS = 6
DEEP_MIN_CRITERIA = 8
DEEP_MIN_DEPTH = 3


@dataclass(frozen=True)
class ComplexityRank:
    """The named raw-metric-to-rank step, with its source values kept.

    ``points``, ``criteria``, and ``depth`` are the raw metrics
    promptchain-generate measured. ``rank`` is the value ``decide`` consumes.
    This dataclass exists so the conversion is explicit and anywhere a decision
    is recorded, the record can name which raw values produced which rank —
    an undeclared translation between the two scales is how a routing layer
    silently overspends.
    """

    points: int
    criteria: int
    depth: int
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "points": self.points,
            "criteria": self.criteria,
            "depth": self.depth,
            "rank": self.rank,
        }


def rank_metrics(points: int, criteria: int, depth: int) -> ComplexityRank:
    """Convert the three raw complexity metrics into a declared rank.

    The thresholds are the literals above: a task is fast only if it is small
    on every axis (``points <= FAST_MAX_POINTS`` and ``criteria <=
    FAST_MAX_CRITERIA`` and ``depth <= FAST_MAX_DEPTH``); deep as soon as any
    axis is heavy (``points >= DEEP_MIN_POINTS`` or ``criteria >=
    DEEP_MIN_CRITERIA`` or ``depth >= DEEP_MIN_DEPTH``); balanced otherwise.
    """
    if points < 0 or criteria < 0 or depth < 0:
        raise RoutingProfileError(
            f"raw metrics must be non-negative, got "
            f"points={points} criteria={criteria} depth={depth}"
        )
    small = (
        points <= FAST_MAX_POINTS
        and criteria <= FAST_MAX_CRITERIA
        and depth <= FAST_MAX_DEPTH
    )
    heavy = (
        points >= DEEP_MIN_POINTS
        or criteria >= DEEP_MIN_CRITERIA
        or depth >= DEEP_MIN_DEPTH
    )
    if small:
        rank = RANK_FAST
    elif heavy:
        rank = RANK_DEEP
    else:
        rank = RANK_BALANCED
    return ComplexityRank(points=points, criteria=criteria, depth=depth, rank=rank)


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
    any), which floor/ceiling bounds adjusted it along the way, and — when a
    resolution was attached — what Faigate resolved the request to.

    ``resolution`` is the :class:`~skillweave.routing.profile.ResolutionRecord`
    Faigate produced from the decision's tier. It is optional: ``decide`` only
    *attaches* a resolution it was handed, it never performs one. That split
    keeps ``decide`` pure — a decision is a function of its declared mode,
    profile, and complexity, and is therefore deterministic — while a separate
    step (``decide_resolved``) records what the router actually turned the
    decision into.
    """

    mode: str
    profile: str
    tier: str
    adjustments: list[Adjustment] = field(default_factory=list)
    pinned: Optional[str] = None
    input: Any = None
    rank: Optional[ComplexityRank] = None
    resolution: Optional[ResolutionRecord] = None

    def to_dict(self) -> dict[str, Any]:
        rank = self.rank.to_dict() if self.rank is not None else None
        resolution = self.resolution.to_dict() if self.resolution is not None else None
        return {
            "mode": self.mode,
            "profile": self.profile,
            "tier": self.tier,
            "pinned": self.pinned,
            "input": self.input,
            "rank": rank,
            "resolution": resolution,
            "adjustments": [a.to_dict() for a in self.adjustments],
        }


def _tier_from_complexity(complexity: Any) -> tuple[str, Optional[ComplexityRank]]:
    """Resolve the consumed complexity value onto a tier, naming its rank.

    ``complexity`` is one of:

    * a :class:`ComplexityRank` — raw metrics with the conversion already done
      here, so the returned rank is named in the record;
    * a bare non-negative integer rank (0 -> fast, 1 -> balanced, >=2 -> deep)
      the producer emitted directly;
    * a tier name (``fast``/``balanced``/``deep``) the producer resolved.

    Only the first form carries raw values, so only then is a rank named in the
    record. The bare-integer and tier-name forms are the producer's own rank,
    not a conversion this module performed. Everything else is refused loudly.

    Returns ``(tier, rank_or_none)``: the rank is non-None exactly when raw
    metrics were converted here, so the decision record can state which raw
    value produced which rank.
    """
    if isinstance(complexity, ComplexityRank):
        rank = complexity.rank
        tier = _tier_name_from_rank(rank)
        return tier, complexity
    if isinstance(complexity, str):
        if complexity not in VALID_TIERS:
            raise RoutingProfileError(
                f"unknown complexity '{complexity}' "
                f"(expected one of {sorted(VALID_TIERS)})"
            )
        return complexity, None
    if isinstance(complexity, int) and not isinstance(complexity, bool):
        if complexity < 0:
            raise RoutingProfileError(
                f"complexity must be non-negative, got {complexity}"
            )
        return _tier_name_from_rank(complexity), None
    raise RoutingProfileError(
        f"complexity must be a ComplexityRank, a tier name, or a non-negative "
        f"integer, got {complexity!r}"
    )


def _tier_name_from_rank(rank: int) -> str:
    """Map a non-negative rank onto the named tier axis.

    This is the shared tail of the conversion: 0 -> fast, 1 -> balanced,
    >=2 -> deep. The rank is already validated non-negative by its callers.
    """
    ordered = [TIER_FAST, TIER_BALANCED, TIER_DEEP]
    return ordered[min(rank, len(ordered) - 1)]


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
    never inferred. ``complexity`` is what ``auto`` (and ``hybrid``, which is
    auto-with-bounds) derive the tier from: a :class:`ComplexityRank` (raw
    metrics converted here, whose raw values and rank are named in the record),
    a bare rank the producer already emitted, or a resolved tier name.
    ``role`` is the per-role pin scope relevant only inside hybrid.

    Under ``pin`` no automatic decision runs at all: ``complexity`` is not
    read, the tier is not derived, no bound is consulted — the pin is the
    operator's override and is never silently ignored or improved upon.

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
    tier, rank = _tier_from_complexity(complexity)

    if mode == MODE_AUTO:
        return RoutingDecision(
            mode=mode,
            profile=profile.name,
            tier=tier,
            pinned=None,
            input=complexity,
            rank=rank,
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
        rank=rank,
        adjustments=adjustments,
    )


def decide_resolved(
    profile: RoutingProfile,
    mode: str,
    complexity: Any = None,
    role: Optional[str] = None,
) -> RoutingDecision:
    """Decide, then record what Faigate resolved the decision to.

    This is the recording step for the whole story (AK 6): ``decide`` computes
    the decision, then the decision's final tier is resolved through Faigate
    (:func:`~skillweave.routing.faigate_adapter.resolve_tier`) and the resulting
    :class:`~skillweave.routing.profile.ResolutionRecord` is attached to the
    record. A later run needs only this single record to reconstruct mode,
    profile, tier, the input that drove it, every bound that adjusted it, and
    what Faigate resolved it to.

    The decision itself is unchanged by the resolution: the record is what
    gains the resolution field, not the decision, so the determinism of
    ``decide`` is preserved and the "what really ran" answer rides alongside
    "what was decided" instead of replacing it.
    """
    decision = decide(profile, mode, complexity=complexity, role=role)
    # resolve_tier derives from profile.tier; the decision's tier may differ
    # (auto/hybrid derive from complexity), so resolve against a profile copy
    # carrying the decided tier. Faigate sees only the tier — the copy is not
    # persisted, so no profile data is altered by the recording step.
    tiered = replace(profile, tier=decision.tier)
    resolution = resolve_tier(tiered)
    return RoutingDecision(
        mode=decision.mode,
        profile=decision.profile,
        tier=decision.tier,
        adjustments=decision.adjustments,
        pinned=decision.pinned,
        input=decision.input,
        rank=decision.rank,
        resolution=resolution,
    )
