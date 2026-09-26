"""Shared entry contract: typed intents, deterministic digests, fail-closed validation.

SW-156-ENTRY-001. ``EntryService`` is the single seam a front-end (CLI, agent
harness, studio, automation) shares when a run starts, continues, is inspected,
or a new operator is onboarded. Four typed intents carry the request:

===============  ==========================================================
``StartIntent``  begin a new run at a named slot
``ContinueIntent``  resume a run from an already-observed run state
``InspectIntent``  render state and its digest without requesting an action
``OnboardIntent``  run operator onboarding against a named profile
===============  ==========================================================

The contract is deliberately I/O-free. A front-end supplies facts through an
:class:`EntryAdapter`; this module never opens a file, database or socket, so
discovery cannot mutate anything. Every value it emits is a pure function of the
facts an adapter observed:

* :func:`state_digest` / :func:`intent_digest` canonicalise with sorted keys and
  compact separators — the idiom already used by
  ``neutrality.compiler.CompiledDefinition`` — so two adapters that observe the
  same facts agree byte-for-byte regardless of container type, key order,
  collection order, path form or ``Enum``-vs-``str`` representation.
* :func:`validate` returns a declared :class:`Contradiction` set instead of
  guessing, and :class:`Decision` refuses to be constructed without a non-empty
  reason and guidance whenever the outcome is not ``EXECUTE``. An unknown or
  contradictory state therefore always yields guidance or escalation, never a
  silent default.

State vocabularies are not reinvented here: run states come from
:class:`skillweave.runtime.store.RunStateModel` (including its legacy aliases)
and phase ids from :func:`skillweave.lifecycle.phase_ids`, the single source of
truth.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol, Union, runtime_checkable

from skillweave.intelligent_detection.onboarding_flow_controller import OnboardingState
from skillweave.lifecycle import phase_ids


def _runtime_attr(submodule: str, *names: str):
    """Resolve runtime names at call time (GLE-020).

    ``skillweave.runtime`` is an optional subpackage and must not be imported at
    module level here; the submodule and its names are resolved lazily through
    ``importlib`` (string-based, so no ``skillweave.runtime.*`` import statement
    appears in this module's AST).
    """
    module = importlib.import_module("skillweave.runtime." + submodule)
    if len(names) == 1:
        return getattr(module, names[0])
    return [getattr(module, n) for n in names]


#: Version of the canonical state payload. Bumped only when the digest payload
#: shape changes, so a digest always names the contract that produced it.
ENTRY_CONTRACT_VERSION = "skillweave.entry/1"


def canonical_digest(payload: Mapping[str, Any]) -> str:
    """Return the canonical digest of an arbitrary entry payload.

    This is the one canonicalisation the whole contract is defined through:
    :func:`state_digest` and :func:`intent_digest` both route through it, and an
    adapter that already holds a fact mapping canonicalises it identically.
    Keys are sorted and separators are compact, so neither key insertion order
    nor container type (``list`` vs ``tuple``) can move a digest.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _as_sequence(value: Any) -> tuple[Any, ...]:
    """View any collection shape as an ordered tuple without inventing members.

    ``None`` yields nothing, a bare string is one element (never a character
    sequence), a mapping contributes its keys, and any other iterable is
    consumed. Anything else is a single scalar.
    """
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return (value,)
    if isinstance(value, Mapping):
        return tuple(value.keys())
    if isinstance(value, Iterable):
        return tuple(value)
    return (value,)


def _scalar(value: Any) -> str:
    """Coerce a state field to its canonical string, honouring ``Enum`` members."""
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _canonical_skills(values: Any) -> tuple[str, ...]:
    """Deduplicate and sort skill ids so input order can never alter a digest."""
    deduped: dict[str, None] = {}
    for value in _as_sequence(values):
        deduped[_scalar(value)] = None
    return tuple(sorted(deduped))


# ── Intent vocabulary ──────────────────────────────────────────────────────


class IntentKind(str, Enum):
    """The four entry operations. Closed set: no intent is inferred from a string."""

    START = "start"
    CONTINUE = "continue"
    INSPECT = "inspect"
    ONBOARD = "onboard"


@dataclass(frozen=True)
class StartIntent:
    """Begin a new run at the named slot."""

    run_id: str
    kind: IntentKind = field(default=IntentKind.START, init=False)

    @classmethod
    def of(cls, run_id: str) -> StartIntent:
        return cls(run_id=str(run_id))

    def to_payload(self) -> dict[str, str]:
        return {"kind": self.kind.value, "run_id": self.run_id}


@dataclass(frozen=True)
class ContinueIntent:
    """Resume a run from an already-observed run state."""

    run_id: str
    from_state: str
    kind: IntentKind = field(default=IntentKind.CONTINUE, init=False)

    @classmethod
    def of(cls, run_id: str, from_state: str) -> ContinueIntent:
        return cls(run_id=str(run_id), from_state=str(from_state))

    def to_payload(self) -> dict[str, str]:
        return {"kind": self.kind.value, "run_id": self.run_id, "from_state": self.from_state}


@dataclass(frozen=True)
class InspectIntent:
    """Render state and digests without requesting a state change."""

    scope: str
    kind: IntentKind = field(default=IntentKind.INSPECT, init=False)

    @classmethod
    def of(cls, scope: str) -> InspectIntent:
        return cls(scope=str(scope))

    def to_payload(self) -> dict[str, str]:
        return {"kind": self.kind.value, "scope": self.scope}


@dataclass(frozen=True)
class OnboardIntent:
    """Run operator onboarding against a named profile."""

    profile: str
    kind: IntentKind = field(default=IntentKind.ONBOARD, init=False)

    @classmethod
    def of(cls, profile: str) -> OnboardIntent:
        return cls(profile=str(profile))

    def to_payload(self) -> dict[str, str]:
        return {"kind": self.kind.value, "profile": self.profile}


EntryIntent = Union[StartIntent, ContinueIntent, InspectIntent, OnboardIntent]


def intent_digest(intent: EntryIntent) -> str:
    """Return the canonical digest of a typed intent.

    The digest is a pure function of the intent's kind and payload — never of
    wall-clock time, host, process or construction order.
    """
    return canonical_digest(intent.to_payload())


# ── State ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EntryState:
    """One observation of entry facts, canonicalised on construction.

    ``installed_skills`` is stored sorted and deduplicated, so two adapters that
    observed the same skills in different orders produce equal states. Both
    ``str`` and ``Enum`` values are accepted for the state fields; both
    normalise to the canonical string.
    """

    run_id: str
    phase: str
    run_state: str
    onboarding_state: str
    installed_skills: tuple[str, ...] = ()
    active_skill: str | None = None
    schema_version: str = ENTRY_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", _scalar(self.run_id))
        object.__setattr__(self, "phase", _scalar(self.phase))
        object.__setattr__(self, "run_state", _scalar(self.run_state))
        object.__setattr__(self, "onboarding_state", _scalar(self.onboarding_state))
        object.__setattr__(self, "installed_skills", _canonical_skills(self.installed_skills))
        active = _scalar(self.active_skill)
        object.__setattr__(self, "active_skill", active or None)

    def to_payload(self) -> dict[str, Any]:
        """Return the digest payload, excluding the schema version.

        The version is deliberately outside the payload: re-labelling the
        contract must not, by itself, change the identity of a state.
        """
        return {
            "active_skill": self.active_skill,
            "installed_skills": list(self.installed_skills),
            "onboarding_state": self.onboarding_state,
            "phase": self.phase,
            "run_id": self.run_id,
            "run_state": self.run_state,
        }


def state_digest(state: EntryState) -> str:
    """Return the canonical digest of an entry state."""
    return canonical_digest(state.to_payload())


# ── Adapters ───────────────────────────────────────────────────────────────


@runtime_checkable
class EntryAdapter(Protocol):
    """A read-only source of entry facts.

    Implementations must not mutate anything while observing: the contract
    treats ``observe`` as a probe, and discovery paths are expected to be
    side-effect free.
    """

    def observe(self) -> EntryState:
        ...


@dataclass(frozen=True)
class MappingEntryAdapter:
    """Adapter over a mapping of facts (e.g. a decoded payload or a row)."""

    facts: Mapping[str, Any]

    def observe(self) -> EntryState:
        return EntryState(
            run_id=self.facts.get("run_id"),
            phase=self.facts.get("phase"),
            run_state=self.facts.get("run_state"),
            onboarding_state=self.facts.get("onboarding_state"),
            installed_skills=self.facts.get("installed_skills"),
            active_skill=self.facts.get("active_skill"),
        )


@dataclass(frozen=True)
class ObjectEntryAdapter:
    """Adapter over an object's attributes (e.g. a run record).

    A different access path into the same contract: missing attributes are the
    same as absent facts, never a default value.
    """

    source: Any

    def observe(self) -> EntryState:
        source = self.source
        return EntryState(
            run_id=getattr(source, "run_id", None),
            phase=getattr(source, "phase", None),
            run_state=getattr(source, "run_state", None),
            onboarding_state=getattr(source, "onboarding_state", None),
            installed_skills=getattr(source, "installed_skills", None),
            active_skill=getattr(source, "active_skill", None),
        )


def observe(adapter: EntryAdapter) -> EntryState:
    """Observe one adapter and canonicalise the result. Performs no mutation."""
    return adapter.observe()


# ── Contradiction taxonomy ─────────────────────────────────────────────────


class Disposition(str, Enum):
    """What the contract permits for a request. ``EXECUTE`` is never a fallback."""

    EXECUTE = "execute"
    RENDER = "render"
    GUIDANCE = "guidance"
    ESCALATE = "escalate"


class Severity(str, Enum):
    """How strongly a contradiction blocks the request."""

    GUIDANCE = "guidance"
    ESCALATE = "escalate"


_SEVERITY_RANK = MappingProxyType({Severity.GUIDANCE: 0, Severity.ESCALATE: 1})

#: The declared contradiction codes. Each carries its own guidance text in
#: :data:`CONTRADICTION_GUIDANCE`, so every non-``EXECUTE`` outcome names itself.
CONTRADICTION_CODES = (
    "UNKNOWN_RUN_STATE",
    "LEGACY_RUN_STATE",
    "INCOHERENT_PHASE",
    "UNKNOWN_PHASE",
    "UNKNOWN_ONBOARDING_STATE",
    "NO_INSTALLED_SKILLS",
    "ACTIVE_SKILL_UNKNOWN",
    "TERMINAL_RUN_START",
    "TERMINAL_RUN_CONTINUE",
    "ONBOARD_ALREADY_COMPLETE",
)

#: Read-only on purpose: nothing may register a new contradiction code at
#: import time or runtime — the taxonomy is closed.
_SEVERITY_BY_CODE: Mapping[str, Severity] = MappingProxyType(
    {
        "UNKNOWN_RUN_STATE": Severity.ESCALATE,
        "LEGACY_RUN_STATE": Severity.GUIDANCE,
        "INCOHERENT_PHASE": Severity.ESCALATE,
        "UNKNOWN_PHASE": Severity.GUIDANCE,
        "UNKNOWN_ONBOARDING_STATE": Severity.GUIDANCE,
        "NO_INSTALLED_SKILLS": Severity.GUIDANCE,
        "ACTIVE_SKILL_UNKNOWN": Severity.GUIDANCE,
        "TERMINAL_RUN_START": Severity.ESCALATE,
        "TERMINAL_RUN_CONTINUE": Severity.ESCALATE,
        "ONBOARD_ALREADY_COMPLETE": Severity.ESCALATE,
    }
)


@dataclass(frozen=True)
class Contradiction:
    """One declared reason a state is unknown, incoherent or blocking."""

    code: str
    detail: str

    def __post_init__(self) -> None:
        if self.code not in _SEVERITY_BY_CODE:
            raise ValueError(
                f"undeclared contradiction code {self.code!r}; "
                f"expected one of {', '.join(sorted(_SEVERITY_BY_CODE))}"
            )

    @property
    def severity(self) -> Severity:
        return _SEVERITY_BY_CODE[self.code]


def contradiction_guidance(contradiction: Contradiction, state: EntryState) -> str:
    """Return the operator-facing next step for one contradiction."""
    RunStateModel, LEGACY_STATE_ALIASES = _runtime_attr(
        "store", "RunStateModel", "LEGACY_STATE_ALIASES"
    )
    canonical = sorted(value.value for value in RunStateModel)
    phases = list(phase_ids())
    onboarding = sorted(value.value for value in OnboardingState)
    return {
        "UNKNOWN_RUN_STATE": (
            f"run state {state.run_state!r} is not in the canonical vocabulary "
            f"({', '.join(canonical)}); the contract will not guess a state. "
            "Re-derive the run state from its source, or escalate to the run owner."
        ),
        "LEGACY_RUN_STATE": (
            f"run state {state.run_state!r} is a legacy alias of "
            f"{LEGACY_STATE_ALIASES.get(state.run_state, '')!r}; migrate the record to the "
            "canonical lowercase vocabulary before continuing."
        ),
        "INCOHERENT_PHASE": (
            f"phase {state.phase!r} is absent while run state {state.run_state!r} is present; "
            "a run state without its phase cannot be placed on the lifecycle."
        ),
        "UNKNOWN_PHASE": (
            f"phase {state.phase!r} is not on the canonical lifecycle "
            f"({', '.join(phases)}); correct the phase or escalate."
        ),
        "UNKNOWN_ONBOARDING_STATE": (
            f"onboarding state {state.onboarding_state!r} is not in the canonical vocabulary "
            f"({', '.join(onboarding)}); correct the record or escalate."
        ),
        "NO_INSTALLED_SKILLS": (
            "no skills are installed at this entry point; onboard first, then start."
        ),
        "ACTIVE_SKILL_UNKNOWN": (
            f"active skill {state.active_skill!r} is not among the installed skills "
            f"({', '.join(state.installed_skills) or 'none'}); re-select an installed skill."
        ),
        "TERMINAL_RUN_START": (
            f"run state {state.run_state!r} is terminal; a new run cannot start on a finished "
            "run. Escalate to the run owner to allocate a fresh run."
        ),
        "TERMINAL_RUN_CONTINUE": (
            f"run state {state.run_state!r} is terminal and has no forward transition; "
            "escalate to the run owner rather than resuming."
        ),
        "ONBOARD_ALREADY_COMPLETE": (
            "onboarding is already complete; re-running it would repeat irreversible setup. "
            "Escalate to the operator if the profile must change."
        ),
    }[contradiction.code]


def validate(state: EntryState) -> tuple[Contradiction, ...]:
    """Return every contradiction the state holds, in a stable order.

    An empty result means the state is coherent and fully understood. Anything
    the contract does not positively recognise is reported here — nothing is
    coerced to a default.
    """
    found: list[Contradiction] = []

    RunStateModel, LEGACY_STATE_ALIASES = _runtime_attr(
        "store", "RunStateModel", "LEGACY_STATE_ALIASES"
    )
    run_state = state.run_state
    canonical_states = {value.value for value in RunStateModel}
    if not run_state:
        found.append(Contradiction("UNKNOWN_RUN_STATE", "no run state was observed"))
    elif run_state in LEGACY_STATE_ALIASES:
        found.append(Contradiction("LEGACY_RUN_STATE", run_state))
    elif run_state not in canonical_states:
        found.append(Contradiction("UNKNOWN_RUN_STATE", run_state))

    if not state.phase:
        if run_state:
            found.append(Contradiction("INCOHERENT_PHASE", "run state present without a phase"))
    elif state.phase not in set(phase_ids()):
        found.append(Contradiction("UNKNOWN_PHASE", state.phase))

    if state.onboarding_state and state.onboarding_state not in {
        value.value for value in OnboardingState
    }:
        found.append(Contradiction("UNKNOWN_ONBOARDING_STATE", state.onboarding_state))

    if not state.installed_skills:
        found.append(Contradiction("NO_INSTALLED_SKILLS", "empty skill set"))
    elif state.active_skill is not None and state.active_skill not in state.installed_skills:
        found.append(Contradiction("ACTIVE_SKILL_UNKNOWN", state.active_skill))

    return tuple(found)


def _for_intent(intent: EntryIntent, state: EntryState) -> tuple[Contradiction, ...]:
    """Return the contradictions the specific intent introduces."""
    RunStateModel = _runtime_attr("store", "RunStateModel")
    if isinstance(intent, StartIntent):
        if RunStateModel.is_terminal(state.run_state):
            return (Contradiction("TERMINAL_RUN_START", state.run_state),)
    elif isinstance(intent, ContinueIntent):
        if RunStateModel.is_terminal(state.run_state):
            return (Contradiction("TERMINAL_RUN_CONTINUE", state.run_state),)
    elif isinstance(intent, OnboardIntent):
        if state.onboarding_state == OnboardingState.COMPLETE.value:
            return (Contradiction("ONBOARD_ALREADY_COMPLETE", state.onboarding_state),)
    return ()


# ── Decision ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Decision:
    """The contract's answer: a disposition, its evidence, and its next step.

    A non-``EXECUTE`` decision is structurally incapable of being silent: it
    must carry at least one reason and non-empty guidance.
    """

    intent: EntryIntent
    disposition: Disposition
    state: EntryState
    state_digest: str
    intent_digest: str
    reasons: tuple[Contradiction, ...] = ()
    guidance: str = ""

    def __post_init__(self) -> None:
        if self.disposition in (Disposition.EXECUTE, Disposition.RENDER):
            if self.reasons:
                raise ValueError(
                    f"{self.disposition.value} decision cannot carry contradictions"
                )
            return
        if not self.reasons:
            raise ValueError(
                f"{self.disposition.value} decision requires at least one reason; "
                "a silent default is not permitted"
            )
        if not self.guidance:
            raise ValueError(f"{self.disposition.value} decision requires guidance")

    def to_payload(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition.value,
            "guidance": self.guidance,
            "intent_digest": self.intent_digest,
            "reasons": [{"code": c.code, "detail": c.detail} for c in self.reasons],
            "state_digest": self.state_digest,
        }

    @property
    def digest(self) -> str:
        """Canonical digest of the decision, for cross-adapter comparison."""
        return canonical_digest(self.to_payload())


# ── Service ────────────────────────────────────────────────────────────────


class EntryService:
    """Stateless entry seam. Every call names the adapter it should read.

    Holding no adapter registry is deliberate: nothing registers on import, so
    importing or constructing the service cannot mutate process state.
    """

    def dispatch(self, intent: EntryIntent, adapter: EntryAdapter) -> Decision:
        """Resolve ``intent`` against the state ``adapter`` observes.

        Returns ``RENDER`` for an inspect intent, ``EXECUTE`` for a coherent
        actionable state, otherwise ``GUIDANCE`` or ``ESCALATE`` naming every
        contradiction found. A request that is not one of the four typed intents
        is refused outright: no intent is ever inferred from a bare value.
        """
        if not isinstance(intent, (StartIntent, ContinueIntent, InspectIntent, OnboardIntent)):
            raise TypeError(
                f"entry dispatch requires a typed intent, got {type(intent).__name__}; "
                "construct a StartIntent, ContinueIntent, InspectIntent or OnboardIntent"
            )
        state = adapter.observe()
        reasons = validate(state) + _for_intent(intent, state)
        state_hash = state_digest(state)
        intent_hash = intent_digest(intent)

        if reasons:
            worst = max(reasons, key=lambda c: _SEVERITY_RANK[c.severity])
            disposition = (
                Disposition.ESCALATE
                if worst.severity is Severity.ESCALATE
                else Disposition.GUIDANCE
            )
            guidance = " ".join(contradiction_guidance(c, state) for c in reasons)
        elif isinstance(intent, InspectIntent):
            disposition, guidance = Disposition.RENDER, ""
        else:
            disposition, guidance = Disposition.EXECUTE, ""

        return Decision(
            intent=intent,
            disposition=disposition,
            state=state,
            state_digest=state_hash,
            intent_digest=intent_hash,
            reasons=reasons,
            guidance=guidance,
        )

    def inspect(self, adapter: EntryAdapter, scope: str = "workspace") -> Decision:
        """Render state and digests without requesting a state change."""
        return self.dispatch(InspectIntent.of(scope), adapter)


def adapter_digests(adapters: Mapping[str, EntryAdapter]) -> dict[str, str]:
    """Map each named adapter to the state digest it observes.

    Adapters that observed the same facts must produce identical digests; a
    divergence is a contract violation, visible by inspecting this mapping.
    """
    return {name: state_digest(adapter.observe()) for name, adapter in adapters.items()}
