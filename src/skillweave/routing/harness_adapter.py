"""The generic runner/harness adapter interface, with the router as decider (SW-158).

Four things live here, and the boundary between them is the point:

1. **The adapter interface is generic.** :class:`HarnessAdapter` is an abstract
   contract an adapter plugin implements — its name, the capabilities it holds,
   how it turns a decision into a launch command, and how it hands the work to a
   launcher seam. The interface itself names *no* concrete harness: every
   host-specific fact (identity, capability set, argv) belongs to a plugin
   subclass. The core never branches on an adapter name; it reads capability
   data. An adapter that cannot honour a decision is refused by name, never
   silently downgraded.

2. **SkillWeave states what it needs, not what to run.** :class:`AdapterRequest`
   carries a :class:`CapabilityRequirement` — the provider-neutral capabilities
   the run requires *plus* the complexity signal (a
   :class:`~skillweave.routing.decide.ComplexityRank`, a bare rank, or a tier
   name). The capabilities are validated against
   :data:`HARNESS_CAPABILITIES` and an unknown one falls closed at construction,
   so a typo can never read as "no requirement".

3. **The router owns the final decision.** :class:`RouterSeam` is the seam the
   core hands the requirement to. The router — :class:`FaigateRouter` is the
   default implementation, but any seam will do — decides the *model mix* and
   the *dispatch strategy* and returns them as a :class:`DispatchStrategy`. The
   adapter does not choose models and does not choose the strategy; it accepts
   the router's decision or refuses it. A different router therefore produces a
   different decision with no change to any adapter.

4. **A plugin implements the interface.** :class:`OpenClaudeAdapter` is one
   such plugin: it declares its own identity, its own capability set, and its
   own transport argv, and does nothing the generic interface does not sanction.
   :class:`HarnessAdapterRegistry` finds plugins by their declared name and by
   capability, so the composition root wires a plugin in without the core ever
   naming it.

Layering note
-------------

The capability vocabulary is declared here rather than imported from
``skillweave.dispatch.harness_contract`` because ``dispatch`` depends on
``routing`` and not the other way round; a backwards import would be a cycle.
The two vocabularies are the same provider-neutral contract, and the integration
test asserts they stay in lockstep, so the duplication cannot drift silently.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from .decide import ComplexityRank
from .profile import (
    TIER_BALANCED,
    TIER_DEEP,
    TIER_FAST,
    VALID_TIERS,
    tier_to_router,
)


# ── The provider-neutral capability vocabulary ─────────────────────────────

#: The capability names an adapter may declare and a run may require. The core
#: reads these as data; a name outside this tuple is refused rather than
#: treated as satisfied. Kept in lockstep with
#: ``skillweave.dispatch.harness_contract.CAPABILITIES`` (asserted by the
#: integration test) — the two are one contract, declared on each side of the
#: one-way ``dispatch -> routing`` dependency.
HARNESS_CAPABILITIES: tuple[str, ...] = (
    "native-tool",
    "external-process",
    "in-place",
    "stdin",
    "status",
    "cancel",
    "state-namespace",
    "installed-skill-digest",
)


# ── The dispatch strategies the router may choose ──────────────────────────

STRATEGY_INLINE = "inline"
STRATEGY_SINGLE = "single"
STRATEGY_PARALLEL = "parallel"

#: What each strategy requires of the adapter that will honour it. The router
#: chooses the strategy; the adapter's capability set is then reconciled against
#: this table before any launch. Adding a strategy edits data; it never adds a
#: branch to an adapter.
STRATEGY_CAPABILITIES: dict[str, tuple[str, ...]] = {
    STRATEGY_INLINE: ("in-place",),
    STRATEGY_SINGLE: ("external-process", "stdin"),
    STRATEGY_PARALLEL: ("external-process", "status"),
}


class HarnessAdapterError(ValueError):
    """A requirement, router decision, plan, or adapter capability is invalid.

    Raised before any launch. ``asset`` names the field that failed (a
    capability, an adapter, a complexity value) whenever one can be named, so
    the refusal is attributable rather than a bare NO.
    """

    def __init__(self, message: str, *, asset: Optional[str] = None) -> None:
        super().__init__(message)
        self.asset = asset


# ── What SkillWeave asks for ───────────────────────────────────────────────

#: The rank axis ``decide`` consumes: 0 -> fast, 1 -> balanced, >=2 -> deep.
#: The conversion is declared here once, as the same ordered tuple, so the
#: complexity signal the router reads is the one measure ``decide`` already
#: uses — never a second, disagreeing scale.
_RANK_TO_TIER = (TIER_FAST, TIER_BALANCED, TIER_DEEP)


def tier_for_complexity(
    complexity: Any,
) -> tuple[str, Optional[ComplexityRank]]:
    """Resolve the complexity signal onto the tier axis the router casts from.

    Accepts exactly the three forms ``decide`` accepts, and refuses anything
    else by name:

    * a :class:`~skillweave.routing.decide.ComplexityRank` — its raw metrics are
      kept and returned alongside the derived tier, so the record can name which
      input produced which tier;
    * a bare non-negative integer rank (0 -> fast, 1 -> balanced, >=2 -> deep);
    * a tier name (``fast``/``balanced``/``deep``).

    Returns ``(tier, rank_or_none)``: the rank is non-``None`` exactly when raw
    metrics were converted here. A ``None``, negative, or unrecognised value
    falls closed with :class:`HarnessAdapterError`.
    """
    if isinstance(complexity, ComplexityRank):
        return _tier_from_rank(complexity.rank), complexity
    if isinstance(complexity, str):
        if complexity not in VALID_TIERS:
            raise HarnessAdapterError(
                f"unknown complexity '{complexity}' "
                f"(expected one of {sorted(VALID_TIERS)})",
                asset=complexity,
            )
        return complexity, None
    if isinstance(complexity, int) and not isinstance(complexity, bool):
        if complexity < 0:
            raise HarnessAdapterError(
                f"complexity rank must be non-negative, got {complexity}",
                asset="complexity",
            )
        return _tier_from_rank(complexity), None
    raise HarnessAdapterError(
        "complexity must be a ComplexityRank, a tier name, or a non-negative "
        f"integer, got {complexity!r}",
        asset="complexity",
    )


def _tier_from_rank(rank: int) -> str:
    """Map a non-negative rank onto the named tier axis (shared tail)."""
    return _RANK_TO_TIER[min(rank, len(_RANK_TO_TIER) - 1)]


@dataclass(frozen=True)
class CapabilityRequirement:
    """What a run needs of an adapter, plus the complexity that drives routing.

    ``capabilities`` is the provider-neutral subset the run requires; an empty
    tuple means the run requires nothing specific. ``complexity`` is the
    declared signal the router casts from — it is required, because a router
    asked to decide without one would have to invent it. An unknown capability
    name, or a missing complexity, is refused here (falls closed) rather than
    surfacing later as a satisfied requirement.
    """

    complexity: Any
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.complexity is None:
            raise HarnessAdapterError(
                "a capability requirement needs a complexity signal to route on",
                asset="complexity",
            )
        caps = tuple(self.capabilities)
        if isinstance(self.capabilities, str) or not isinstance(caps, tuple):
            raise HarnessAdapterError(
                "requirement capabilities must be a tuple of capability names",
                asset="capabilities",
            )
        for cap in caps:
            if cap not in HARNESS_CAPABILITIES:
                raise HarnessAdapterError(
                    f"unknown capability '{cap}' "
                    f"(expected one of {list(HARNESS_CAPABILITIES)})",
                    asset=cap,
                )
        object.__setattr__(self, "capabilities", caps)

    @property
    def required(self) -> frozenset[str]:
        return frozenset(self.capabilities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capabilities": list(self.capabilities),
            "complexity": (
                self.complexity.to_dict()
                if isinstance(self.complexity, ComplexityRank)
                else self.complexity
            ),
        }


@dataclass(frozen=True)
class AdapterRequest:
    """One run's hand-off to the adapter: what it needs, and the work itself.

    This is the object SkillWeave passes to the router. It carries the
    :class:`CapabilityRequirement` (capabilities + complexity) verbatim and the
    exact work bytes, so the router decides from the stated need and the adapter
    later receives the decision alongside the same request — never a
    reconstructed one.
    """

    run_id: str
    role: str
    requirement: CapabilityRequirement
    work: bytes = b""
    subject_repo: str = ""
    subject_commit: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, CapabilityRequirement):
            raise HarnessAdapterError(
                "an adapter request requires a CapabilityRequirement",
                asset="requirement",
            )
        if not isinstance(self.work, (bytes, bytearray)):
            raise HarnessAdapterError(
                "adapter request work must be bytes",
                asset="work",
            )
        object.__setattr__(self, "work", bytes(self.work))

    @property
    def capabilities(self) -> tuple[str, ...]:
        return self.requirement.capabilities

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "role": self.role,
            "requirement": self.requirement.to_dict(),
            "work_bytes": len(self.work),
            "subject_repo": self.subject_repo,
            "subject_commit": self.subject_commit,
        }


# ── What the router decides ────────────────────────────────────────────────

@dataclass(frozen=True)
class DispatchStrategy:
    """The router's final decision: which models run, and how they are driven.

    ``model_mix`` is the concrete model pool the router cast; ``strategy`` is
    one of :data:`STRATEGY_CAPABILITIES` (inline, single, parallel); ``mode`` is
    the router's own stage mode; ``router`` names the router that decided. The
    adapter neither fills nor overrides these fields — it accepts them or
    refuses the plan. Every field is validated at construction so a decision
    with no models, an unknown strategy, or an unnamed router never reaches a
    launch.
    """

    strategy: str
    model_mix: tuple[str, ...]
    mode: str
    router: str
    chairman: Optional[str] = None
    tier: Optional[str] = None
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.strategy not in STRATEGY_CAPABILITIES:
            raise HarnessAdapterError(
                f"unknown dispatch strategy '{self.strategy}' "
                f"(expected one of {sorted(STRATEGY_CAPABILITIES)})",
                asset="strategy",
            )
        models = tuple(str(m) for m in self.model_mix)
        if not models or any(not m.strip() for m in models):
            raise HarnessAdapterError(
                "a dispatch decision must name at least one non-empty model",
                asset="model_mix",
            )
        if not isinstance(self.router, str) or not self.router.strip():
            raise HarnessAdapterError(
                "a dispatch decision must name the router that made it",
                asset="router",
            )
        object.__setattr__(self, "model_mix", models)

    def required_capabilities(self) -> tuple[str, ...]:
        """The capabilities the router's chosen strategy demands of an adapter."""
        return STRATEGY_CAPABILITIES[self.strategy]

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "model_mix": list(self.model_mix),
            "mode": self.mode,
            "router": self.router,
            "chairman": self.chairman,
            "tier": self.tier,
            "rationale": self.rationale,
        }


# ── The router seam ────────────────────────────────────────────────────────

class RouterSeam(ABC):
    """The seam that owns the model-mix and dispatch-strategy decision.

    The core hands a :class:`AdapterRequest` to :meth:`route` and uses whatever
    :class:`DispatchStrategy` comes back, unchanged. ``name`` identifies the
    deciding router in the record. Any object exposing ``name`` and ``route``
    satisfies the seam; :class:`FaigateRouter` is the default implementation.
    """

    name: str

    @abstractmethod
    def route(self, request: AdapterRequest) -> DispatchStrategy:
        """Decide the model mix and dispatch strategy for ``request``."""


class FaigateRouter(RouterSeam):
    """The default router: cast the tier from complexity against the presets.

    The tier is derived from the request's complexity signal through the shared
    :func:`tier_for_complexity` step, then mapped onto a router preset and a
    stage mode through the existing ``tier_to_router`` table. The preset's model
    pool *is* the model mix — this never invents a model — and the strategy is
    parallel when the router casts more than one model, single otherwise.

    ``presets`` is injectable so a caller (and the tests) can route against a
    hermetic table without touching the live ``ROUTER_PROFILES``.
    """

    name = "faigate"

    def __init__(self, presets: Optional[Mapping[str, Mapping[str, Any]]] = None) -> None:
        if presets is None:
            from .faigate_adapter import ROUTER_PROFILES

            presets = ROUTER_PROFILES
        if not isinstance(presets, Mapping) or not presets:
            raise HarnessAdapterError(
                "faigate routing needs a non-empty preset table",
                asset="presets",
            )
        self._presets = {str(k): dict(v) for k, v in presets.items()}

    def route(self, request: AdapterRequest) -> DispatchStrategy:
        tier, rank = tier_for_complexity(request.requirement.complexity)
        preset_name, mode = tier_to_router(tier)
        preset = self._presets.get(preset_name)
        if preset is None:
            raise HarnessAdapterError(
                f"faigate has no preset '{preset_name}' for tier '{tier}'",
                asset=preset_name,
            )
        models = tuple(str(m) for m in (preset.get("models") or ()))
        if not models:
            raise HarnessAdapterError(
                f"faigate preset '{preset_name}' casts no models",
                asset=preset_name,
            )
        strategy = STRATEGY_PARALLEL if len(models) > 1 else STRATEGY_SINGLE
        cast = f" ({len(models)} models)" if rank is None else ""
        return DispatchStrategy(
            strategy=strategy,
            model_mix=models,
            mode=mode,
            router=self.name,
            chairman=preset.get("chairman"),
            tier=tier,
            rationale=(
                f"tier '{tier}'{cast} -> preset '{preset_name}', mode '{mode}', "
                f"strategy '{strategy}'"
            ),
        )


# ── The generic adapter interface ──────────────────────────────────────────

@dataclass(frozen=True)
class HarnessPlan:
    """A decision the adapter has accepted: the router's strategy plus the
    capability set the adapter must hold to honour it.

    ``required_capabilities`` is the union of what the run asked for and what
    the router's strategy demands. A plan exists only when the adapter holds
    every one of them, so a plan is always executable by the adapter that
    produced it.
    """

    adapter: str
    request: AdapterRequest
    strategy: DispatchStrategy
    required_capabilities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "request": self.request.to_dict(),
            "strategy": self.strategy.to_dict(),
            "required_capabilities": list(self.required_capabilities),
        }


@dataclass(frozen=True)
class HarnessOutcome:
    """What an executed plan produced: the command, and the launcher's result.

    ``succeeded`` reflects the launcher's own verdict. When the result cannot
    state one, the outcome reads as not-succeeded (falls closed) rather than
    claiming a success nobody reported.
    """

    adapter: str
    plan: HarnessPlan
    command: tuple[str, ...]
    result: Any = None

    @property
    def succeeded(self) -> bool:
        return bool(getattr(self.result, "succeeded", False))

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "command": list(self.command),
            "strategy": self.plan.strategy.to_dict(),
            "succeeded": self.succeeded,
        }


class HarnessAdapter(ABC):
    """The generic runner/harness adapter interface. No harness is named here.

    An adapter plugin declares its own ``name`` and its own ``capabilities()``
    as data; the interface provides the two shared steps:

    * :meth:`plan` hands the request to the router, takes the router's decision
      verbatim, and reconciles it against the adapter's declared capabilities.
      A missing capability — whether the run required it or the router's
      strategy demands it — refuses the plan by name, before any launch.
    * :meth:`execute` asks the plugin for its own transport argv
      (:meth:`build_command`) and passes the work to the injected ``launch``
      seam, returning a :class:`HarnessOutcome`.

    Nothing in this class branches on an adapter name, a model id, or a
    strategy name beyond the declared :data:`STRATEGY_CAPABILITIES` table.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The plugin's own identity, opaque to the generic core."""

    @abstractmethod
    def capabilities(self) -> frozenset[str]:
        """The capability names this plugin holds, declared as data."""

    @abstractmethod
    def build_command(self, plan: HarnessPlan) -> Sequence[str]:
        """The plugin's own transport argv for an accepted plan.

        This is the only host-specific knowledge in the class: it belongs to the
        plugin, never to the interface.
        """

    def supports(self, capability: str) -> bool:
        """Whether this plugin holds ``capability``.

        Falls closed: an unknown or absent capability is ``False``, never a
        benefit of the doubt.
        """
        return capability in self.capabilities()

    def plan(
        self,
        request: AdapterRequest,
        router: Optional[RouterSeam] = None,
    ) -> HarnessPlan:
        """Route ``request``, then accept or refuse the router's decision.

        The router decides; the adapter only reconciles. ``router`` defaults to
        :class:`FaigateRouter`, so a caller states its need and nothing else.
        A router that cannot route, a decision the adapter cannot honour, or a
        requirement the adapter does not meet all fall closed with
        :class:`HarnessAdapterError` naming the asset.
        """
        if not isinstance(request, AdapterRequest):
            raise HarnessAdapterError(
                "plan() requires an AdapterRequest",
                asset="request",
            )
        decider = FaigateRouter() if router is None else router
        if not callable(getattr(decider, "route", None)):
            raise HarnessAdapterError(
                "the router seam must expose route(request)",
                asset="router",
            )

        decision = decider.route(request)
        if not isinstance(decision, DispatchStrategy):
            raise HarnessAdapterError(
                "the router must return a DispatchStrategy",
                asset="router",
            )

        needed = tuple(
            dict.fromkeys(
                tuple(request.requirement.capabilities)
                + tuple(decision.required_capabilities())
            )
        )
        missing = [cap for cap in needed if not self.supports(cap)]
        if missing:
            raise HarnessAdapterError(
                f"adapter '{self.name}' cannot honour the decision from router "
                f"'{decision.router}': missing capability {missing}",
                asset=missing[0],
            )
        return HarnessPlan(
            adapter=self.name,
            request=request,
            strategy=decision,
            required_capabilities=needed,
        )

    def execute(
        self,
        plan: HarnessPlan,
        *,
        launch: Callable[[Sequence[str], HarnessPlan], Any],
    ) -> HarnessOutcome:
        """Hand an accepted plan to the ``launch`` seam and record the outcome.

        ``launch`` is injected: the interface owns the hand-off, not the
        process. A non-callable seam is refused before the plugin's argv is
        even built, so a missing launcher is never mistaken for a run.
        """
        if not isinstance(plan, HarnessPlan):
            raise HarnessAdapterError(
                "execute() requires a HarnessPlan",
                asset="plan",
            )
        if not callable(launch):
            raise HarnessAdapterError(
                "execute() requires a callable launch seam",
                asset="launch",
            )
        command = tuple(str(part) for part in self.build_command(plan))
        if not command:
            raise HarnessAdapterError(
                f"adapter '{self.name}' built an empty command",
                asset="command",
            )
        result = launch(list(command), plan)
        return HarnessOutcome(
            adapter=self.name,
            plan=plan,
            command=command,
            result=result,
        )


# ── The plugin registry ────────────────────────────────────────────────────

class HarnessAdapterRegistry:
    """A name-and-capability index of adapter plugins.

    Wiring code registers plugins; consumers look them up by the plugin's own
    declared name or by the capabilities they must hold. The registry never
    names a plugin itself — a duplicate name is refused, an unknown name is
    refused by name, and capability lookup reads the plugins' own declarations.
    """

    def __init__(self, adapters: Iterable[HarnessAdapter] = ()) -> None:
        self._by_name: dict[str, HarnessAdapter] = {}
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: HarnessAdapter) -> None:
        if not isinstance(adapter, HarnessAdapter):
            raise HarnessAdapterError(
                "only a HarnessAdapter plugin can be registered",
                asset="adapter",
            )
        name = adapter.name
        if not isinstance(name, str) or not name.strip():
            raise HarnessAdapterError(
                "a plugin must declare a non-empty name",
                asset="name",
            )
        if name in self._by_name:
            raise HarnessAdapterError(
                f"adapter '{name}' is already registered",
                asset=name,
            )
        self._by_name[name] = adapter

    def get(self, name: str) -> HarnessAdapter:
        adapter = self._by_name.get(name)
        if adapter is None:
            raise HarnessAdapterError(
                f"no adapter plugin registered as '{name}'",
                asset=name,
            )
        return adapter

    def names(self) -> list[str]:
        return list(self._by_name)

    def capable_of(self, *capabilities: str) -> list[str]:
        """Names of registered plugins holding every named capability."""
        return [
            name
            for name, adapter in self._by_name.items()
            if all(adapter.supports(cap) for cap in capabilities)
        ]

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    def __len__(self) -> int:
        return len(self._by_name)


def register_plugins(
    registry: HarnessAdapterRegistry, *adapters: HarnessAdapter
) -> HarnessAdapterRegistry:
    """Register ``adapters`` on ``registry`` and return it (composition seam).

    A convenience for the wiring step: the registry stays the index, and no
    generic core code needs to know which plugins exist.
    """
    for adapter in adapters:
        registry.register(adapter)
    return registry


# ── A plugin: the OpenClaude harness ───────────────────────────────────────

class OpenClaudeAdapter(HarnessAdapter):
    """The OpenClaude harness, implemented strictly as a plugin (SW-158).

    Everything OpenClaude-specific about this class is *here*, in the plugin:
    the identity it reports, the capabilities it declares, and the transport
    argv it builds. The generic interface above it is untouched — a second
    plugin with a different name, a different capability set, and a different
    argv is registered and driven identically, with no change to any core code.

    ``capabilities`` and ``executable`` are injectable so a caller can declare
    the plugin's real, machine-observed surface without editing the class.
    """

    #: The plugin's own identity. Opaque to the generic core: the interface
    #: treats it as data, so nothing in the core branches on it.
    NAME = "openclaude"

    #: The capabilities this plugin holds, declared as data. Absent from this
    #: set means the plugin does not claim it, and a decision that needs it is
    #: refused by :meth:`HarnessAdapter.plan`.
    DEFAULT_CAPABILITIES: frozenset[str] = frozenset(
        {
            "native-tool",
            "external-process",
            "stdin",
            "status",
            "cancel",
            "state-namespace",
            "installed-skill-digest",
        }
    )

    def __init__(
        self,
        executable: str = "openclaude",
        capabilities: Optional[Iterable[str]] = None,
    ) -> None:
        if not isinstance(executable, str) or not executable.strip():
            raise HarnessAdapterError(
                "the OpenClaude plugin needs a non-empty executable",
                asset="executable",
            )
        self._executable = executable.strip()
        declared = (
            self.DEFAULT_CAPABILITIES
            if capabilities is None
            else frozenset(capabilities)
        )
        for cap in declared:
            if cap not in HARNESS_CAPABILITIES:
                raise HarnessAdapterError(
                    f"unknown capability '{cap}' "
                    f"(expected one of {list(HARNESS_CAPABILITIES)})",
                    asset=cap,
                )
        self._capabilities = frozenset(declared)

    @property
    def name(self) -> str:
        return self.NAME

    @property
    def executable(self) -> str:
        return self._executable

    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    def build_command(self, plan: HarnessPlan) -> Sequence[str]:
        """The plugin's transport argv: its executable, and the router's model.

        The model is the router's primary cast member from
        ``plan.strategy.model_mix`` — read from the decision, never chosen here.
        """
        command = [self._executable]
        if plan.strategy.model_mix:
            command += ["--model", plan.strategy.model_mix[0]]
        return command


__all__ = [
    "HARNESS_CAPABILITIES",
    "STRATEGY_INLINE",
    "STRATEGY_SINGLE",
    "STRATEGY_PARALLEL",
    "STRATEGY_CAPABILITIES",
    "HarnessAdapterError",
    "tier_for_complexity",
    "CapabilityRequirement",
    "AdapterRequest",
    "DispatchStrategy",
    "RouterSeam",
    "FaigateRouter",
    "HarnessPlan",
    "HarnessOutcome",
    "HarnessAdapter",
    "HarnessAdapterRegistry",
    "register_plugins",
    "OpenClaudeAdapter",
]
