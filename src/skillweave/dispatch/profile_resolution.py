"""Authoritative dispatch profile resolution (SW138-PROFILE-001).

``contracts.py`` (SW138-CONTRACT-001) owns the *declaration*: a
``SequenceDeclaration`` names an explicit profile path and per-lane roles, and
``validate_for_dispatch`` fails closed before any worker-start callback. This
module owns the *resolution*: turning that declaration into a concrete,
launchable intent per role, with one authoritative answer for every question.

It is the single seam between the dispatch contract and the routing profile
(:mod:`skillweave.routing.profile`). Nothing else under ``dispatch/`` may
re-resolve a profile; any consumer that wants to know "what tool does this role
launch, with which model, under which limits" goes through here.

The module is authoritative in five ways, matching the five acceptance criteria:

1. **An explicit profile path is required.** ``resolve_dispatch_profile`` takes
   the profile path as a required argument with no default. There is no
   repository-wide implicit default directory or file: a mutating dispatch that
   does not name a path is refused *before* any process launch, with the missing
   path named.

2. **The resolved intent is derivable from the profile alone.** The child
   launch command comes from the role's ``ToolSpec.launch_command`` and args;
   the model comes from the role's declared ``model``. A resolution keeps the
   requested model and the resolved model beside each other, so a receipt that
   later reports "what ran" is changed by nothing except the profile itself.

3. **Every required role resolves to exactly one of two explicit outcomes.**
   A role carrying a ``ToolSpec`` resolves to an explicit launch; a role without
   one resolves to explicit *in-place* mode. A required role that is absent
   from the profile is refused, naming the role — it never silently becomes an
   implicit in-place worker or a skipped slot.

4. **The four limits use one documented precedence chain.** ``timeout``,
   ``max_retries``, ``min_models_required`` and ``on_model_failure`` are each
   resolved through a single chain (explicit override, then the profile's
   declared limits, then the documented default), written down in exactly one
   place. They are never looked up from a side table.

5. **No literal harness or model name appears here.** The module names no
   concrete harness and no concrete model: those belong to profile *data*,
   which this module reads but never hard-codes.

Carry-forward (Contract review): the ``execution_model`` enum enforcement
(``cold``/``warm``/``resume``) belongs at the eventual live dispatch consumer.
This module therefore does **not** add a model or harness default, and does not
validate ``execution_model``: it resolves the profile, nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Sequence

from skillweave.routing.harness import load_profiles_from_location
from skillweave.routing.profile import (
    Limits,
    RoleDefinition,
    RoutingProfile,
    ToolSpec,
)

# ── Errors ─────────────────────────────────────────────────────────────────

class ProfileResolutionError(ValueError):
    """A dispatch profile could not be resolved to a launchable intent.

    Raised before any process launch. The offending field (a path or a role) is
    named via ``field`` so the failure is attributable, never a bare refusal.
    """

    def __init__(self, message: str, *, field: Optional[str] = None):
        super().__init__(message)
        self.field = field


# ── Resolved model receipt ────────────────────────────────────────────────

@dataclass
class ResolvedModel:
    """The model a role resolves to, keeping request and product beside it.

    ``requested`` is the model the profile's role declared. ``resolved`` is the
    concrete id the role actually runs. For a concrete declared model the two
    coincide; they are kept as separate fields so a receipt never lets a later
    reader mistake "what was asked for" for "what ran" (the same split
    ``faigate_adapter.ModelResolution`` keeps for fan-out specs).
    """

    requested: str
    resolved: str

    def to_dict(self) -> dict[str, Any]:
        return {"requested": self.requested, "resolved": self.resolved}


# ── Resolved role ─────────────────────────────────────────────────────────

@dataclass
class ResolvedRole:
    """One role resolved to an explicit launch or explicit in-place intent.

    Exactly one of the two outcomes holds, and it is distinguishable afterwards:

    * a role whose profile declares a ``ToolSpec`` carries ``tool`` (a launch);
    * a role without a tool carries ``in_place=True`` (runs in the current
      harness), never a silently missing entry.

    ``model`` is the resolved model receipt (requested + resolved). ``profile``
    names the profile the role came from, so a record can be re-traced to its
    source without a second load.
    """

    role: str
    profile: str
    model: Optional[ResolvedModel] = None
    tool: Optional[ToolSpec] = None
    in_place: bool = False
    limits: Optional[Limits] = None

    def is_launch(self) -> bool:
        return self.tool is not None and not self.in_place

    def launch_command(self) -> Optional[str]:
        """The child launch command, or ``None`` for an in-place role."""
        return self.tool.launch_command if self.tool is not None else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "profile": self.profile,
            "model": self.model.to_dict() if self.model is not None else None,
            "tool": (
                {
                    "name": self.tool.name,
                    "launch_command": self.tool.launch_command,
                    "args": list(self.tool.args),
                }
                if self.tool is not None
                else None
            ),
            "in_place": self.in_place,
        }


# ── Resolved limits: the single documented precedence chain ───────────────

# The one precedence chain for the four limits. Written down exactly once; no
# other table or mapping may shadow it. Higher entries win:
#
#   1. explicit override (the caller's per-dispatch argument),
#   2. the profile's declared ``limits``,
#   3. the documented default (the ``Limits`` dataclass defaults).
#
# Behavioural limits (``on_model_failure``) and the three numeric limits
# (``timeout``, ``max_retries``, ``min_models_required``) all travel the same
# chain. There is deliberately no side table keyed by role or harness: adding a
# limit value is a data change in the profile, never a new branch here.


def resolve_limits(
    profile_limits: Optional[Limits],
    override: Optional[Limits],
) -> Limits:
    """Apply the single documented precedence chain to the four limits.

    ``override`` (the caller's explicit per-dispatch value) wins where set;
    otherwise the profile's declared ``profile_limits``; otherwise the
    documented ``Limits`` defaults. Each of the four fields resolves
    independently through that same chain — there is no side table and no
    role-specific lookup.
    """
    base = profile_limits if profile_limits is not None else Limits()
    if override is None:
        return base
    # Prefer the override field when it is meaningfully set, else the base. The
    # ``on_model_failure`` name is validated upstream by ``Limits.from_dict``;
    # here we only carry whichever value won the chain.
    return Limits(
        timeout=override.timeout if _is_set(override.timeout) else base.timeout,
        max_retries=override.max_retries if _is_set(override.max_retries) else base.max_retries,
        min_models_required=(
            override.min_models_required
            if _is_set(override.min_models_required)
            else base.min_models_required
        ),
        on_model_failure=(
            override.on_model_failure if _is_set(override.on_model_failure) else base.on_model_failure
        ),
    )


def _is_set(value: Any) -> bool:
    """Whether an override field carries an explicit (non-``None``) value.

    ``False`` means "leave this field to the next-lower level of the chain";
    an explicit ``0``/``False``/``""`` is still *set* and therefore wins, so a
    caller can deliberately lower a limit to zero rather than being silently
    overridden back to a default.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value != ""
    return True


# ── Resolved dispatch ─────────────────────────────────────────────────────

@dataclass
class ResolvedDispatch:
    """A fully resolved dispatch: one authoritative intent per required role.

    ``profile_name`` names the resolved profile; ``roles`` maps each requested
    role key to its :class:`ResolvedRole`. ``limits`` is the single resolved
    :class:`Limits` every role shares (the same one chain produced it).
    """

    profile_name: str
    roles: dict[str, ResolvedRole] = field(default_factory=dict)
    limits: Optional[Limits] = None

    def role(self, key: str) -> Optional[ResolvedRole]:
        return self.roles.get(key)

    def resolved_models(self) -> dict[str, Optional[ResolvedModel]]:
        """The requested/resolved model receipt per role, for the evidence record."""
        return {key: role.model for key, role in self.roles.items()}


def _require_nonempty_path(path: Any) -> str:
    """Return ``path`` as a non-empty string, refusing anything else.

    An explicit profile path is the whole point of criterion 1: a non-string,
    empty, or whitespace-only path is refused here, before any profile load and
    therefore before any process launch.
    """
    if not isinstance(path, str) or not path.strip():
        raise ProfileResolutionError(
            f"a dispatch profile path is required and must be a non-empty "
            f"string, got {path!r}",
            field="profile.path",
        )
    return path.strip()


def _resolve_role_model(role: RoleDefinition) -> Optional[ResolvedModel]:
    """Build the requested/resolved model receipt for a declared role.

    A role with no declared model has no receipt (its model is decided by
    Faigate tier resolution, not by this profile). A role with a declared model
    resolves that model to a concrete id; for a concrete declared id the
    resolved id is the id itself. The two are kept apart regardless.
    """
    if not role.model:
        return None
    requested = role.model
    resolved = _resolve_model_id(requested)
    return ResolvedModel(requested=requested, resolved=resolved)


def _resolve_model_id(model: str) -> str:
    """Resolve a declared model string to a concrete id via the model-spec seam.

    Uses the same :func:`skillweave.routing.modelspec` resolution the fan-out
    path uses, so a declared model and a fan-out spec can never disagree about
    what a string means. A concrete id resolves to itself.
    """
    from skillweave.routing.modelspec import from_value, resolve

    return resolve(from_value(model))


def resolve_dispatch_profile(
    profile_path: str,
    required_roles: Sequence[str],
    *,
    limits_override: Optional[Limits] = None,
    profile_loader=None,
) -> ResolvedDispatch:
    """Resolve an explicit profile into one authoritative intent per role.

    ``profile_path`` is the caller-declared path (no default: see criterion 1).
    ``required_roles`` names the roles that *must* resolve. ``limits_override``
    is the caller's explicit per-dispatch limit override, the top of the single
    precedence chain.

    ``profile_loader`` is an injection seam for tests; it defaults to
    :func:`skillweave.routing.profile.load_profiles_from_location`, which
    already refuses a missing or malformed location.

    Fails before any process launch when:

    * the profile path is absent or non-empty-invalid (named as the field);
    * the profile cannot be loaded (a missing path surfaces from the loader);
    * a required role is absent from the profile — the role is named, and the
      failure is a ``ProfileResolutionError``, never a silently skipped slot.
    """
    path = _require_nonempty_path(profile_path)
    loader = profile_loader or load_profiles_from_location
    profiles = loader(path)
    if not profiles:
        raise ProfileResolutionError(
            f"profile location '{path}' loaded no profiles", field="profile.path"
        )

    (profile,) = profiles.values() if len(profiles) == 1 else _resolve_single(path, profiles)
    if not isinstance(profile, RoutingProfile):
        raise ProfileResolutionError(
            f"profile at '{path}' did not resolve to a RoutingProfile, "
            f"got {type(profile).__name__}",
            field="profile.path",
        )

    resolved: dict[str, ResolvedRole] = {}
    for role_key in required_roles:
        if not isinstance(role_key, str) or not role_key.strip():
            raise ProfileResolutionError(
                f"required role must be a non-empty string, got {role_key!r}",
                field="required_roles",
            )
        role = profile.role(role_key)
        if role is None:
            raise ProfileResolutionError(
                f"required role '{role_key}' is not declared in profile "
                f"'{profile.name}'",
                field=f"roles.{role_key}",
            )
        model_receipt = _resolve_role_model(role)
        tool = role.tool
        resolved[role_key] = ResolvedRole(
            role=role_key,
            profile=profile.name,
            model=model_receipt,
            tool=tool,
            in_place=tool is None,
            limits=resolve_limits(profile.limits, limits_override),
        )

    return ResolvedDispatch(
        profile_name=profile.name,
        roles=resolved,
        limits=resolve_limits(profile.limits, limits_override),
    )


def _resolve_single(path: str, profiles: Mapping[str, Any]) -> RoutingProfile:
    """Pick the single profile when a location loads more than one.

    The dispatch contract's ``ProfileReference`` names one profile path, which
    the example data keeps as a single-profile file. A location that yields
    several profiles is therefore ambiguous for a dispatch intent; it is refused
    naming the location, rather than guess which of them to run.
    """
    raise ProfileResolutionError(
        f"profile location '{path}' declared {len(profiles)} profiles; a "
        f"dispatch resolution requires exactly one named profile",
        field="profile.path",
    )


__all__ = [
    "ProfileResolutionError",
    "ResolvedModel",
    "ResolvedRole",
    "ResolvedDispatch",
    "resolve_limits",
    "resolve_dispatch_profile",
]
