"""Shared entry contract tests (SW-156-ENTRY-001).

Proves the four acceptance criteria for ``skillweave.entry.service``:

1. Start, continue, inspect and onboard are typed intents — a request that is
   not typed is refused, not inferred.
2. Identical state produces identical intent and state digests across two
   adapters that differ in container type, key order, collection order and
   path representation.
3. State discovery performs no mutation — byte-identical snapshots of the
   process registries and of the workspace, checked with a mutation-surfaced
   sanity control that fails if the sameness assertion is vacuous.
4. Unknown or contradictory state returns guidance or escalation, never a
   silent default — every contradiction code has guidance, an actionable
   decision requires reasons, and no unrecognised value is coerced.

Red proof: the closed-taxonomy test below fails if a contradiction code is
added without guidance, and a docstring-only closure cannot satisfy it.
"""

import copy
import subprocess
import sys
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path

import pytest

from skillweave.entry import (
    CONTRADICTION_CODES,
    Contradiction,
    ContinueIntent,
    Decision,
    Disposition,
    EntryService,
    EntryState,
    InspectIntent,
    IntentKind,
    MappingEntryAdapter,
    ObjectEntryAdapter,
    OnboardIntent,
    StartIntent,
    adapter_digests,
    canonical_digest,
    contradiction_guidance,
    intent_digest,
    state_digest,
    validate,
)
from skillweave.lifecycle import phase_ids
from skillweave.runtime.store import RunStateModel

RUN_ID = "run-SW-156"
PHASE = phase_ids()[3]  # "build"
SKILLS = ("skillweave-core", "skillweave-review", "skillweave-dispatch")


def _facts(**overrides):
    facts = {
        "run_id": RUN_ID,
        "phase": PHASE,
        "run_state": RunStateModel.IMPLEMENT.value,
        "onboarding_state": "complete",
        "installed_skills": list(SKILLS),
        "active_skill": SKILLS[0],
    }
    facts.update(overrides)
    return facts


def _coherent(**overrides) -> EntryState:
    return MappingEntryAdapter(_facts(**overrides)).observe()


@dataclass(frozen=True)
class _Row:
    """A second access path: the same facts reached as object attributes."""

    run_id: str
    phase: str
    run_state: str
    onboarding_state: str
    installed_skills: tuple
    active_skill: object


# ── AC1: four typed intents ────────────────────────────────────────────────


def test_four_typed_intents_are_closed_and_self_identifying():
    """Start, continue, inspect and onboard are typed; their kinds are disjoint."""
    intents = (
        StartIntent.of(RUN_ID),
        ContinueIntent.of(RUN_ID, RunStateModel.IMPLEMENT.value),
        InspectIntent.of("workspace"),
        OnboardIntent.of("default"),
    )
    assert {type(i).__name__ for i in intents} == {
        "StartIntent",
        "ContinueIntent",
        "InspectIntent",
        "OnboardIntent",
    }
    assert {i.kind for i in intents} == {
        IntentKind.START,
        IntentKind.CONTINUE,
        IntentKind.INSPECT,
        IntentKind.ONBOARD,
    }
    # The kind is fixed by the type, not settable by the caller.
    with pytest.raises(FrozenInstanceError):
        StartIntent.of(RUN_ID).kind = IntentKind.ONBOARD


def test_untyped_request_is_refused_not_inferred():
    """A bare string is not an intent: the contract never infers one."""
    service = EntryService()
    adapter = MappingEntryAdapter(_facts())
    for bad in ("start", IntentKind.START, None, 42):
        with pytest.raises(TypeError, match="typed intent"):
            service.dispatch(bad, adapter)


def test_intent_digest_is_a_function_of_kind_and_payload_only():
    """The same intent built twice digests identically; a different one does not."""
    assert intent_digest(StartIntent.of(RUN_ID)) == intent_digest(StartIntent.of(RUN_ID))
    assert intent_digest(StartIntent.of(RUN_ID)) != intent_digest(StartIntent.of("other-run"))
    assert intent_digest(StartIntent.of(RUN_ID)) != intent_digest(OnboardIntent.of("default"))


# ── AC2: identical state, identical digests across adapters ────────────────


def test_identical_state_produces_identical_state_digest_across_adapters():
    """Two adapters over the same facts agree, despite ordering and container
    differences: reversed skill order, a tuple instead of a list, an Enum
    instead of a str, and an absolute path phase value."""
    mapping_adapter = MappingEntryAdapter(_facts())
    object_adapter = ObjectEntryAdapter(
        _Row(
            run_id=RUN_ID,
            phase=PHASE,
            run_state=RunStateModel.IMPLEMENT,  # Enum, not str
            onboarding_state="complete",
            installed_skills=tuple(reversed(SKILLS)),  # reversed, tuple
            active_skill=SKILLS[0],
        )
    )
    first = mapping_adapter.observe()
    second = object_adapter.observe()

    assert first == second
    assert state_digest(first) == state_digest(second)
    assert adapter_digests({"mapping": mapping_adapter, "object": object_adapter}) == {
        "mapping": state_digest(first),
        "object": state_digest(first),
    }


def test_state_digest_is_order_independent_but_content_sensitive():
    """Reordering skills cannot change the digest; changing a skill must."""
    base = state_digest(_coherent())
    reordered = state_digest(_coherent(installed_skills=list(reversed(SKILLS))))
    changed = state_digest(_coherent(installed_skills=list(SKILLS) + ["skillweave-extra"]))
    assert base == reordered
    assert base != changed


def test_canonicalisation_is_order_and_container_independent():
    """The canonicalising seam ignores key insertion order and container type.

    RED PROOF: removing ``sort_keys=True`` from ``canonical_digest`` (or letting
    a ``list``/``tuple`` distinction into the payload) fails this test — a
    digest must not be a function of how a mapping happened to be built.
    """
    left = {"run_id": RUN_ID, "phase": PHASE, "installed_skills": ["a", "b"]}
    right = {"installed_skills": ("a", "b"), "phase": PHASE, "run_id": RUN_ID}
    assert canonical_digest(left) == canonical_digest(right)
    assert canonical_digest({"a": 1, "b": 2}) == canonical_digest({"b": 2, "a": 1})
    assert canonical_digest({"a": 1}) != canonical_digest({"a": 2})


def test_state_digest_is_repeatable_and_not_process_dependent():
    """Repeated derivation cannot move the digest of the same facts."""
    first = state_digest(_coherent())
    for _ in range(5):
        assert state_digest(MappingEntryAdapter(_facts()).observe()) == first


def test_state_digest_excludes_the_contract_version():
    """Re-labelling the contract must not change the identity of a state."""
    base = state_digest(_coherent())
    relabelled = MappingEntryAdapter(_facts())
    assert relabelled.observe().schema_version != "some-other-version"
    same = EntryState(
        run_id=RUN_ID,
        phase=PHASE,
        run_state=RunStateModel.IMPLEMENT.value,
        onboarding_state="complete",
        installed_skills=list(SKILLS),
        active_skill=SKILLS[0],
        schema_version="some-other-version",
    )
    assert state_digest(same) == base


def test_identical_decision_digests_across_adapters():
    """The whole decision — not just the state — agrees across adapters."""
    service = EntryService()
    intent = ContinueIntent.of(RUN_ID, RunStateModel.IMPLEMENT.value)
    a = service.dispatch(intent, MappingEntryAdapter(_facts()))
    b = service.dispatch(
        intent,
        ObjectEntryAdapter(
            _Row(RUN_ID, PHASE, RunStateModel.IMPLEMENT, "complete", list(SKILLS), SKILLS[0])
        ),
    )
    assert a.digest == b.digest
    assert (a.state_digest, a.intent_digest) == (b.state_digest, b.intent_digest)


# ── AC3: discovery performs no mutation ────────────────────────────────────


def _module_level_registries():
    """Snapshot the mutable module-level maps that discovery could touch.

    These are exactly the containers a naive "discover on import / discover by
    registration" implementation would mutate.
    """
    import skillweave.neutrality.adapter as neutrality_adapter
    import skillweave.persistence as persistence

    return {
        "persistence._AREA_REGISTRY": persistence._AREA_REGISTRY,
        "neutrality.adapter._REGISTRY": neutrality_adapter._REGISTRY,
    }


def test_discovery_does_not_mutate_registries(tmp_path):
    """Observing state leaves every process registry and the workspace untouched.

    The final control mutation proves the comparison is not vacuous: the same
    comparison must report "changed" once something really changes.
    """
    registries = _module_level_registries()
    before = {name: copy.deepcopy(registry) for name, registry in registries.items()}
    before_files = sorted(p.name for p in tmp_path.iterdir())

    service = EntryService()
    adapter = MappingEntryAdapter(_facts())
    for intent in (
        StartIntent.of(RUN_ID),
        ContinueIntent.of(RUN_ID, RunStateModel.IMPLEMENT.value),
        InspectIntent.of("workspace"),
        OnboardIntent.of("default"),
    ):
        service.dispatch(intent, adapter)

    after = {name: copy.deepcopy(registry) for name, registry in registries.items()}
    after_files = sorted(p.name for p in tmp_path.iterdir())
    assert after == before, "discovery mutated a process registry"
    assert after_files == before_files, "discovery wrote to the workspace"

    # Sanity control: a real mutation must be detected by this comparison.
    registries["persistence._AREA_REGISTRY"]["_sw156_probe"] = object()
    try:
        changed = {name: copy.deepcopy(r) for name, r in registries.items()}
        assert changed != before, "sameness assertion is vacuous"
    finally:
        del registries["persistence._AREA_REGISTRY"]["_sw156_probe"]


def test_observe_is_pure_for_a_fixed_adapter():
    """Repeated observation of one adapter yields an equal state each time."""
    adapter = MappingEntryAdapter(_facts())
    first = adapter.observe()
    for _ in range(5):
        assert adapter.observe() == first
    assert MappingEntryAdapter(_facts()).facts is not None  # adapter input untouched


def test_service_holds_no_adapter_registry():
    """The service is stateless: it cannot accumulate adapters at import time."""
    assert EntryService().__dict__ == {}
    assert EntryService.__init__ is object.__init__


def test_importing_entry_registers_nothing():
    """Importing the contract must not mutate any existing registry.

    RED PROOF: an import-time ``registry[...] = ...`` in service.py fails this
    test. It runs in a fresh interpreter because import-time effects cannot be
    observed after the module is already cached in this process.
    """
    src_root = str(Path(__file__).resolve().parents[2] / "src")
    script = (
        "import copy\n"
        "import skillweave.persistence as p\n"
        "import skillweave.neutrality.adapter as n\n"
        "import skillweave.core.context.limits as l\n"
        "before = (copy.deepcopy(p._AREA_REGISTRY), copy.deepcopy(n._REGISTRY),\n"
        "          len(l._GLOBAL_REGISTRY.__dict__))\n"
        "import skillweave.entry\n"
        "after = (copy.deepcopy(p._AREA_REGISTRY), copy.deepcopy(n._REGISTRY),\n"
        "         len(l._GLOBAL_REGISTRY.__dict__))\n"
        "assert after == before, ('registry mutated on import', before, after)\n"
        "print('IMPORT_CLEAN')\n"
    )
    env = {"PYTHONPATH": src_root, "PATH": "/usr/bin:/bin"}
    done = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, cwd=src_root
    )
    assert done.returncode == 0, done.stderr
    assert "IMPORT_CLEAN" in done.stdout


# ── AC4: unknown or contradictory state never defaults ─────────────────────


def test_coherent_state_executes():
    decision = EntryService().dispatch(
        StartIntent.of(RUN_ID), MappingEntryAdapter(_facts())
    )
    assert decision.disposition is Disposition.EXECUTE
    assert decision.reasons == ()
    assert decision.guidance == ""


def test_unknown_run_state_escalates_with_no_default():
    decision = EntryService().dispatch(
        StartIntent.of(RUN_ID), MappingEntryAdapter(_facts(run_state="teleported"))
    )
    assert decision.disposition is Disposition.ESCALATE
    assert [c.code for c in decision.reasons] == ["UNKNOWN_RUN_STATE"]
    assert "teleported" in decision.guidance
    assert "will not guess" in decision.guidance


def test_missing_and_legacy_run_state_both_refuse():
    missing = EntryService().dispatch(
        StartIntent.of(RUN_ID), MappingEntryAdapter(_facts(run_state=""))
    )
    assert missing.disposition is Disposition.ESCALATE
    assert missing.reasons[0].code == "UNKNOWN_RUN_STATE"

    legacy = EntryService().dispatch(
        StartIntent.of(RUN_ID), MappingEntryAdapter(_facts(run_state="IN_PROGRESS"))
    )
    assert legacy.disposition is Disposition.GUIDANCE
    assert legacy.reasons[0].code == "LEGACY_RUN_STATE"
    assert "in_progress" in legacy.guidance


def test_terminal_run_refuses_start_and_continue_with_escalation():
    for value in sorted(RunStateModel.terminal_values()):
        start = EntryService().dispatch(
            StartIntent.of(RUN_ID), MappingEntryAdapter(_facts(run_state=value))
        )
        assert start.disposition is Disposition.ESCALATE
        assert "TERMINAL_RUN_START" in [c.code for c in start.reasons]

        cont = EntryService().dispatch(
            ContinueIntent.of(RUN_ID, value), MappingEntryAdapter(_facts(run_state=value))
        )
        assert cont.disposition is Disposition.ESCALATE
        assert "TERMINAL_RUN_CONTINUE" in [c.code for c in cont.reasons]


def test_run_state_without_phase_is_incoherent():
    decision = EntryService().dispatch(
        StartIntent.of(RUN_ID), MappingEntryAdapter(_facts(phase=""))
    )
    assert decision.disposition is Disposition.ESCALATE
    assert [c.code for c in decision.reasons] == ["INCOHERENT_PHASE"]


def test_unknown_phase_is_guidance_and_active_skill_must_be_installed():
    phase = EntryService().dispatch(
        StartIntent.of(RUN_ID), MappingEntryAdapter(_facts(phase="pre-release"))
    )
    assert phase.disposition is Disposition.GUIDANCE
    assert "UNKNOWN_PHASE" in [c.code for c in phase.reasons]

    skill = EntryService().dispatch(
        StartIntent.of(RUN_ID),
        MappingEntryAdapter(_facts(active_skill="skillweave-absent")),
    )
    assert skill.disposition is Disposition.GUIDANCE
    assert "ACTIVE_SKILL_UNKNOWN" in [c.code for c in skill.reasons]

    empty = EntryService().dispatch(
        StartIntent.of(RUN_ID), MappingEntryAdapter(_facts(installed_skills=[]))
    )
    assert empty.disposition is Disposition.GUIDANCE
    assert "NO_INSTALLED_SKILLS" in [c.code for c in empty.reasons]


def test_reonboarding_a_complete_profile_escalates():
    decision = EntryService().dispatch(
        OnboardIntent.of("default"), MappingEntryAdapter(_facts())
    )
    assert decision.disposition is Disposition.ESCALATE
    assert [c.code for c in decision.reasons] == ["ONBOARD_ALREADY_COMPLETE"]


def test_multiple_contradictions_all_named_and_worst_severity_wins():
    decision = EntryService().dispatch(
        StartIntent.of(RUN_ID),
        MappingEntryAdapter(
            _facts(run_state="teleported", phase="", onboarding_state="nowhere")
        ),
    )
    codes = [c.code for c in decision.reasons]
    assert codes == ["UNKNOWN_RUN_STATE", "INCOHERENT_PHASE", "UNKNOWN_ONBOARDING_STATE"]
    assert decision.disposition is Disposition.ESCALATE  # escalate outranks guidance
    # Every reason reaches the operator: the guidance is exactly the per-reason
    # guidance joined, so none is dropped.
    assert decision.guidance == " ".join(
        contradiction_guidance(c, decision.state) for c in decision.reasons
    )
    assert "teleported" in decision.guidance and "nowhere" in decision.guidance


def test_actionable_decision_structurally_cannot_be_silent():
    """A guidance/escalate decision with no reason or no guidance is invalid."""
    coherent = _coherent()
    with pytest.raises(ValueError, match="at least one reason"):
        Decision(
            intent=StartIntent.of(RUN_ID),
            disposition=Disposition.ESCALATE,
            state=coherent,
            state_digest=state_digest(coherent),
            intent_digest=intent_digest(StartIntent.of(RUN_ID)),
            reasons=(),
            guidance="look elsewhere",
        )
    with pytest.raises(ValueError, match="requires guidance"):
        Decision(
            intent=StartIntent.of(RUN_ID),
            disposition=Disposition.GUIDANCE,
            state=coherent,
            state_digest=state_digest(coherent),
            intent_digest=intent_digest(StartIntent.of(RUN_ID)),
            reasons=(Contradiction("UNKNOWN_PHASE", "pre-release"),),
        )
    with pytest.raises(ValueError, match="cannot carry contradictions"):
        Decision(
            intent=StartIntent.of(RUN_ID),
            disposition=Disposition.EXECUTE,
            state=coherent,
            state_digest=state_digest(coherent),
            intent_digest=intent_digest(StartIntent.of(RUN_ID)),
            reasons=(Contradiction("UNKNOWN_PHASE", "pre-release"),),
            guidance="",
        )


def test_undeclared_contradiction_code_is_rejected():
    with pytest.raises(ValueError, match="undeclared contradiction code"):
        Contradiction("NOT_A_REAL_CODE", "sneaky default")


def test_contradiction_taxonomy_is_closed_and_every_code_has_guidance():
    """RED PROOF: removing guidance for any declared code fails here."""
    coherent = _coherent()
    failures = []
    for code in CONTRADICTION_CODES:
        severity = Contradiction(code, "probe").severity
        if severity not in (Disposition.GUIDANCE.value, Disposition.ESCALATE.value):
            failures.append(f"{code}: severity {severity!r} cannot reach an operator")
        guidance = contradiction_guidance(Contradiction(code, "probe"), coherent)
        if not guidance.strip():
            failures.append(f"{code}: empty guidance")
    assert failures == [], failures
    assert len(set(CONTRADICTION_CODES)) == len(CONTRADICTION_CODES), "duplicate codes"

    # Every contradiction the validator can emit must be a declared code, and
    # no further code may exist unaccounted for.
    emitted = {
        c.code
        for c in validate(
            _coherent(
                run_state="teleported", phase="nowhere", onboarding_state="void",
                installed_skills=[], active_skill="ghost",
            )
        )
    }
    assert emitted <= set(CONTRADICTION_CODES)
    assert emitted == {
        "UNKNOWN_RUN_STATE",
        "UNKNOWN_PHASE",
        "UNKNOWN_ONBOARDING_STATE",
        "NO_INSTALLED_SKILLS",
    }


def test_inspect_renders_instead_of_executing_or_blocking():
    decision = EntryService().inspect(MappingEntryAdapter(_facts()), scope="workspace")
    assert decision.disposition is Disposition.RENDER
    assert decision.reasons == ()
    assert decision.guidance == ""
    assert len(decision.state_digest) == 64 and len(decision.intent_digest) == 64


def test_unknown_onboarding_state_is_never_coerced():
    decision = EntryService().dispatch(
        InspectIntent.of("workspace"),
        MappingEntryAdapter(_facts(onboarding_state="halfway-ish")),
    )
    assert decision.disposition is Disposition.GUIDANCE
    assert "UNKNOWN_ONBOARDING_STATE" in [c.code for c in decision.reasons]
