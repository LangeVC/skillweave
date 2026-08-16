"""Declarative routing profiles for SkillWeave.

A :class:`RoutingProfile` is pure DATA. It is loaded from YAML and carries the
four parts that shape how a role's model is chosen and how its tool is launched:

1. **model choice per role** — each role maps to a model id (or the role's own
   request), separate from any shared tier.
2. **tier** — ``fast`` | ``balanced`` | ``deep``. This is the vocabulary the
   PRD names. Resolution to concrete router profile keys (e.g. the
   ``quick``/``standard``/``full`` mode vocabulary that
   the Faigate adapter understands) is Faigate's job; this module only
   *carries* the tier so a resolver can later map it without re-reading raw YAML.
3. **limits** — timeout, max retries, minimum models required, and the
   behaviour to take when one model fails.
4. **target tool** — the tool name and its launch command.

Roles are DATA too, not an enum. The five built-ins (``ops``, ``reviewer``,
``observer``, ``chairman``, ``worker``) are seed definitions; any further role
may be declared in the same YAML. The built-in ``observer`` role is wired to
the existing runtime observer (:class:`skillweave.runtime.observer.ObserverRuntime`),
not re-invented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from skillweave.runtime.observer import ObserverRuntime

TIER_FAST = "fast"
TIER_BALANCED = "balanced"
TIER_DEEP = "deep"

VALID_TIERS = frozenset({TIER_FAST, TIER_BALANCED, TIER_DEEP})

BUILTIN_ROLE_NAMES = (
    "ops",
    "reviewer",
    "observer",
    "chairman",
    "worker",
)

# The two capabilities whose conjunction is self-approval: a role that may both
# mutate run state AND approve a gate can approve its own work. That is the hole
# the ops/reviewer split exists to close, so it is refused at load time.
CAP_MUTATE_RUN_STATE = "can_mutate_run_state"
CAP_APPROVE_GATE = "can_approve_gate"

INCOMPATIBLE_PAIRS = frozenset({
    (CAP_MUTATE_RUN_STATE, CAP_APPROVE_GATE),
})


class RoutingProfileError(ValueError):
    """Raised when a routing profile or role definition is malformed."""


@dataclass
class ToolSpec:
    """The target tool a role runs, plus its launch command."""

    name: str
    launch_command: str
    args: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ToolSpec":
        name = data.get("name")
        launch_command = data.get("launch_command")
        if not name or not launch_command:
            raise RoutingProfileError(
                "tool spec requires 'name' and 'launch_command'"
            )
        args = data.get("args", [])
        if not isinstance(args, list):
            raise RoutingProfileError("tool 'args' must be a list")
        return cls(name=name, launch_command=launch_command, args=list(args))


@dataclass
class RoleDefinition:
    """A role as data: its key, the model that answers for it, its tool, and
    the capabilities it declares in the same profile file.

    ``capabilities`` is a mapping of capability name to truthiness, loaded from
    the profile file and never hardcoded. A role that declares no capabilities
    (or that is not declared at all) has an empty mapping and therefore DENIES
    every check: this is the "falling closed" default.
    """

    key: str
    model: Optional[str] = None
    tool: Optional[ToolSpec] = None
    is_observer: bool = False
    capabilities: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, key: str, data: Mapping[str, Any]) -> "RoleDefinition":
        model = data.get("model")
        tool_data = data.get("tool")
        tool = ToolSpec.from_dict(tool_data) if tool_data else None
        capabilities = dict(data.get("capabilities", {}) or {})
        return cls(
            key=key,
            model=model,
            tool=tool,
            is_observer=bool(data.get("observer", False)),
            capabilities=capabilities,
            metadata=dict(data.get("metadata", {})),
        )

    def can(self, capability: str) -> bool:
        """Return whether this role holds ``capability``.

        Falls closed: an absent capability is ``False``, not ``True``.
        """
        value = self.capabilities.get(capability)
        return bool(value)


def load_matrix(roles: Mapping[str, RoleDefinition]) -> dict[str, RoleDefinition]:
    """Return the capability matrix for a set of roles, keyed by role name.

    This is the "matrix loaded from the file, not hardcoded" surface: it is
    built purely from the declared roles' own ``capabilities`` mappings. A role
    key that is not present simply has no entry, so downstream ``can`` checks
    on it fall closed.
    """
    return {key: role for key, role in roles.items()}


@dataclass
class Limits:
    """Failure and resource limits for a profile.

    ``on_model_failure`` is one of: ``skip`` (drop the failed model and
    continue with the rest), ``retry`` (retry up to ``max_retries``), or
    ``abort`` (raise once ``min_models_required`` can no longer be met).
    """

    timeout: float = 60.0
    max_retries: int = 1
    min_models_required: int = 2
    on_model_failure: str = "skip"

    _VALID_FAILURE_BEHAVIOUR = frozenset({"skip", "retry", "abort"})

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Limits":
        behaviour = data.get("on_model_failure", "skip")
        if behaviour not in cls._VALID_FAILURE_BEHAVIOUR:
            raise RoutingProfileError(
                f"unknown on_model_failure '{behaviour}' "
                f"(expected one of {sorted(cls._VALID_FAILURE_BEHAVIOUR)})"
            )
        return cls(
            timeout=float(data.get("timeout", 60.0)),
            max_retries=int(data.get("max_retries", 1)),
            min_models_required=int(data.get("min_models_required", 2)),
            on_model_failure=behaviour,
        )


@dataclass
class RoutingProfile:
    """A routing profile, declarable as YAML data.

    Carries all four required parts: per-role model choice, tier, limits, and
    target tool — all derived from the raw data at construction time so nothing
    downstream has to re-read YAML.
    """

    name: str
    tier: str = TIER_BALANCED
    limits: Limits = field(default_factory=Limits)
    roles: dict[str, RoleDefinition] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.tier not in VALID_TIERS:
            raise RoutingProfileError(
                f"unknown tier '{self.tier}' (expected one of {sorted(VALID_TIERS)})"
            )
        for key, role in self.roles.items():
            if role.key != key:
                role.key = key

    def role(self, key: str) -> Optional[RoleDefinition]:
        return self.roles.get(key)

    def model_for(self, key: str) -> Optional[str]:
        role = self.roles.get(key)
        return role.model if role else None

    def tool_for(self, key: str) -> Optional[ToolSpec]:
        role = self.roles.get(key)
        return role.tool if role else None

    def capability_matrix(self) -> dict[str, RoleDefinition]:
        """The capability matrix loaded from this profile's own file.

        Roles that were not declared are absent, so a caller checking them
        falls closed rather than defaulting to open.
        """
        return load_matrix(self.roles)

    def role_can(self, key: str, capability: str) -> bool:
        """Whether the role ``key`` holds ``capability``, falling closed.

        An undeclared role, or a declared role missing the capability, returns
        ``False`` and never raises.
        """
        role = self.roles.get(key)
        return role.can(capability) if role else False

    def observer_role(self) -> Optional[RoleDefinition]:
        """Return the built-in ``observer`` role (wired to the runtime observer)."""
        role = self.roles.get("observer")
        if role and role.is_observer:
            return role
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tier": self.tier,
            "limits": {
                "timeout": self.limits.timeout,
                "max_retries": self.limits.max_retries,
                "min_models_required": self.limits.min_models_required,
                "on_model_failure": self.limits.on_model_failure,
            },
            "roles": {
                key: _role_to_dict(role) for key, role in self.roles.items()
            },
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RoutingProfile":
        name = data.get("name")
        if not name:
            raise RoutingProfileError("profile requires a 'name'")

        tier = data.get("tier", TIER_BALANCED)
        limits = Limits.from_dict(data.get("limits", {}))
        roles = builtin_roles()

        declared_roles = data.get("roles", {})
        for key, role_data in declared_roles.items():
            role = RoleDefinition.from_dict(key, role_data)
            # A role that names itself after the runtime observer is wired to it.
            if key == "observer":
                role.is_observer = True
            _check_incompatible(role)
            roles[key] = role

        return cls(
            name=name,
            tier=tier,
            limits=limits,
            roles=roles,
            metadata=dict(data.get("metadata", {})),
        )


def _check_incompatible(role: RoleDefinition) -> None:
    """Refuse roles whose declared capabilities combine into self-approval.

    A single role holding both ``can_mutate_run_state`` and ``can_approve_gate``
    can approve its own work — exactly the separation of duties the ops/reviewer
    split closes. This is checked at LOAD time so a malformed profile cannot be
    constructed in the first place.
    """
    for left, right in INCOMPATIBLE_PAIRS:
        if role.can(left) and role.can(right):
            raise RoutingProfileError(
                f"role '{role.key}' holds both '{left}={role.capabilities.get(left)}' "
                f"and '{right}={role.capabilities.get(right)}': "
                "this is self-approval and is refused at load time"
            )


def builtin_roles() -> dict[str, RoleDefinition]:
    """The five built-in roles as data.

    ``observer`` is wired to the existing runtime observer; the others carry
    only a key (their model is expected from the profile's own role override,
    or from Faigate tier resolution).
    """
    roles: dict[str, RoleDefinition] = {}
    for name in BUILTIN_ROLE_NAMES:
        roles[name] = RoleDefinition(key=name, is_observer=(name == "observer"))
    return roles


def resolve_role(profile: RoutingProfile, key: str) -> RoleDefinition:
    """Resolve a role by key, raising if it is not declared."""
    role = profile.role(key)
    if role is None:
        raise RoutingProfileError(
            f"role '{key}' is not declared in profile '{profile.name}'"
        )
    return role


def from_dict(data: Mapping[str, Any]) -> RoutingProfile:
    """Convenience alias for :meth:`RoutingProfile.from_dict`."""
    return RoutingProfile.from_dict(data)


def load_profile(data: Mapping[str, Any]) -> RoutingProfile:
    """Load a single profile from already-parsed YAML data (a mapping)."""
    return RoutingProfile.from_dict(data)


def load_profiles(data: Any) -> dict[str, RoutingProfile]:
    """Load one or many profiles from parsed YAML.

    Accepts either a single profile mapping or a mapping of name -> profile.
    """
    if isinstance(data, RoutingProfile):
        return {data.name: data}
    if isinstance(data, Mapping):
        if "name" in data and "limits" in data:
            profile = RoutingProfile.from_dict(data)
            return {profile.name: profile}
        return {
            name: RoutingProfile.from_dict(entry)
            for name, entry in data.items()
        }
    raise RoutingProfileError("profiles must be a mapping or a single profile")


def _role_to_dict(role: RoleDefinition) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if role.model is not None:
        out["model"] = role.model
    if role.tool is not None:
        out["tool"] = {
            "name": role.tool.name,
            "launch_command": role.tool.launch_command,
        }
        if role.tool.args:
            out["tool"]["args"] = list(role.tool.args)
    if role.capabilities:
        out["capabilities"] = dict(role.capabilities)
    if role.is_observer:
        out["observer"] = True
    if role.metadata:
        out["metadata"] = dict(role.metadata)
    return out


# Re-export the runtime observer type so callers know exactly what the
# ``observer`` role is wired to, without a second import path.
_OBSERVER_RUNTIME_TYPE = ObserverRuntime
