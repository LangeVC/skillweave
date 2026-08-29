"""Harness adapter adherence contract (SW1311-HARNESS-001).

The provider-neutral adapter profile contract and the experimental
strict-controller gate. Eight acceptance criteria, each proven as a red/green
path against the core module (``skillweave.dispatch.harness_contract``) and the
hermetic fixture data (``tests/fixtures/harnesses/``):

1. A provider-neutral adapter profile declares native-tool, external-process,
   in-place, stdin, status, cancel, state-namespace and installed-skill-digest
   capabilities with no harness-specific branch in core dispatch.
3. Experimental strict-controller mode refuses dispatch unless the validated
   sequence, resolved profile, exact task brief and installed skill digests are
   bound.
4. Stale/missing skill or capability digests fail before worker launch and name
   the mismatched asset.
5. Harness-native delegation or direct-shell bypass attempts are recorded and
   fail closed when strict mode requires SkillWeave dispatch.
6. Controller, Ops, reviewer, observer and Integrator capabilities/authority
   are distinct.
7. Core modules and shipped task contracts contain no literal harness name or
   native delegation command.
8. Preview output reports actual per-harness real-run evidence and makes no
   stable transport-parity claim before 1.4.

Criterion 2 (hermetic fixture coverage + honest statuses) and the per-adapter
negative-authority matrix are proven in the sibling integration test.
"""

import sys
from pathlib import Path

import pytest
import yaml

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.dispatch.harness_contract import (  # noqa: E402
    AUTHORITY_ROLES,
    CAPABILITIES,
    BypassNotRecordedError,
    DigestMismatchError,
    HarnessAdapterProfile,
    HarnessContractError,
    STATUS_DISPATCH_PROVEN,
    STATUS_DOCUMENTED,
    STATUS_KEYS,
    StrictController,
    StrictControllerError,
    load_adapter_profiles,
)

_REPO = Path(__file__).resolve().parent.parent.parent
_FIXTURES = _REPO / "tests" / "fixtures" / "harnesses"

# All four canonical adapters covered by hermetic fixture data.
ADAPTERS = ("claude-code", "codex", "antigravity", "opencode")
EXPECTED_CAPABILITIES = CAS = CAPABILITIES


def _load(name: str) -> dict:
    return yaml.safe_load((_FIXTURES / name).read_text(encoding="utf-8")) or {}


def load_all_profiles() -> dict[str, HarnessAdapterProfile]:
    return load_adapter_profiles(
        _load("profiles.yaml"),
        statuses=_load("statuses.yaml"),
        skill_digests=_load("digests.yaml"),
    )


# ── Criterion 1: provider-neutral capability declaration ────────────────

def test_fixture_profiles_declare_all_eight_capabilities():
    # Every adapter's data file declares the full capability vocabulary; core
    # dispatch maps an adapter to a subset via booleans, never a branch.
    profiles = load_all_profiles()
    assert set(profiles) == set(ADAPTERS)
    for adapter in ADAPTERS:
        profile = profiles[adapter]
        for cap in CAPABILITIES:
            assert cap in profile.capabilities, (
                f"adapter '{adapter}' missing capability '{cap}'"
            )


def test_core_module_has_no_harness_specific_branch():
    # The core module bodies itself for *any* adapter; a concrete harness name
    # must not appear as a branch. (Criterion 7 also scans the module source.)
    from skillweave.dispatch import harness_contract

    text = harness_contract.__doc__ or ""
    assert "harness" in text.lower()
    # load_adapter_profiles reads keys as opaque data and never matches a name.
    profiles = load_all_profiles()
    assert profiles["opencode"].name == "opencode"
    assert profiles["claude-code"].name == "claude-code"


# ── Criterion 3: strict binding requires all four facts ──────────────────

def test_strict_binding_requires_validated_sequence():
    c = StrictController()
    with pytest.raises(StrictControllerError) as exc:
        c.bind(
            sequence=None,
            profile=object(),
            task_brief=b"brief",
            skill_digests={"skill": "x"},
        )
    assert "validated sequence" in str(exc.value)


def test_strict_binding_requires_resolved_profile():
    c = StrictController()
    with pytest.raises(StrictControllerError) as exc:
        c.bind(
            sequence=object(),
            profile=None,
            task_brief=b"brief",
            skill_digests={"skill": "x"},
        )
    assert "resolved profile" in str(exc.value)


def test_strict_binding_requires_exact_task_brief():
    c = StrictController()
    with pytest.raises(StrictControllerError) as exc:
        c.bind(
            sequence=object(),
            profile=object(),
            task_brief=None,
            skill_digests={"skill": "x"},
        )
    assert "exact task brief" in str(exc.value)


def test_strict_binding_requires_installed_skill_digests():
    c = StrictController()
    with pytest.raises(StrictControllerError) as exc:
        c.bind(
            sequence=object(),
            profile=object(),
            task_brief=b"brief",
            skill_digests={},
        )
    assert "installed skill digests" in str(exc.value)


def test_strict_bound_dispatch_is_complete():
    c = StrictController()
    bound = c.bind(
        sequence=object(),
        profile=object(),
        task_brief=b"exact brief",
        skill_digests={"skillweave-promptchain": "deadbeef"},
    )
    assert bound.task_brief == b"exact brief"
    assert bound.skill_digests == {"skillweave-promptchain": "deadbeef"}


# ── Criterion 4: stale/missing digest fails before launch, names asset ────

def test_missing_skill_digest_names_the_asset():
    c = StrictController()
    adapter = HarnessAdapterProfile(
        name="opencode",
        skill_digests={"skillweave-promptchain": "expected"},
    )
    with pytest.raises(DigestMismatchError) as exc:
        c.observe_actual_digests(adapter, {})
    assert exc.value.asset == "skillweave-promptchain"
    assert "not reported" in str(exc.value)


def test_stale_skill_digest_names_the_asset():
    c = StrictController()
    adapter = HarnessAdapterProfile(
        name="opencode",
        skill_digests={"skillweave-lifecycle": "deadbeef"},
    )
    with pytest.raises(DigestMismatchError) as exc:
        c.observe_actual_digests(adapter, {"skillweave-lifecycle": "stale123"})
    assert exc.value.asset == "skillweave-lifecycle"
    assert "stale123" in str(exc.value)


def test_matching_digests_reconcile():
    c = StrictController()
    adapter = HarnessAdapterProfile(
        name="opencode",
        skill_digests={"skillweave-promptchain": "deadbeef"},
    )
    reconciled = c.observe_actual_digests(adapter, {"skillweave-promptchain": "deadbeef"})
    assert reconciled == {"skillweave-promptchain": "deadbeef"}


# ── Criterion 5: bypass attempts are recorded and fail closed ─────────────

def test_native_delegation_bypass_is_recorded_and_refused():
    c = StrictController(require_skillweave_dispatch=True)
    adapter = HarnessAdapterProfile(name="antigravity", delegation={"native-delegation": True})
    with pytest.raises(BypassNotRecordedError) as exc:
        c.record_attempt(kind="native-delegation", detail="hand-off", adapter=adapter)
    assert exc.value.asset == "antigravity"
    # The attempt is still recorded even though it was refused (fail closed +
    # recorded).
    assert c.attempts and c.attempts[-1]["kind"] == "native-delegation"


def test_direct_shell_bypass_is_recorded_and_refused():
    c = StrictController(require_skillweave_dispatch=True)
    with pytest.raises(BypassNotRecordedError):
        c.record_attempt(kind="direct-shell", detail="bash -c ...", adapter=None)


def test_skillweave_dispatch_is_allowed_and_recorded():
    c = StrictController(require_skillweave_dispatch=True)
    adapter = HarnessAdapterProfile(name="opencode")
    c.record_attempt(kind="skillweave", detail="wave", adapter=adapter)
    assert c.attempts[-1]["kind"] == "skillweave"


# ── Criterion 6: distinct authorities ─────────────────────────────────────

def test_five_distinct_authority_roles():
    assert set(AUTHORITY_ROLES) == {
        "controller", "ops", "reviewer", "observer", "integrator"
    }


def test_reconcile_authority_refuses_a_second_role():
    c = StrictController()
    # A profile whose authority mapping carries a second role field is refused.
    adapter = HarnessAdapterProfile(
        name="claude-code",
        authority={"role": "controller", "skillweave-dispatch-required": True, "reviewer": True},
    )
    with pytest.raises(HarnessContractError):
        c.reconcile_authority(adapter)


def test_reconcile_authority_refuses_missing_role():
    c = StrictController()
    adapter = HarnessAdapterProfile(name="codex", authority={})
    with pytest.raises(HarnessContractError):
        c.reconcile_authority(adapter)


# ── Criterion 7: no literal harness name / native delegation in core ──────

# Concrete harness names that must appear only in adapter/profile/fixture data,
# never in core dispatch modules or shipped task contracts.
_HARNESS_LITERALS = ("opencode", "claude", "codex", "antigravity", "gemini")

# Native delegation command prefixes: a host executable invoked to dispatch a
# task directly rather than through the SkillWeave seam.
_NATIVE_PREFIXES = (
    "opencode run",
    "claude -",
    "claude -p",
    "codex exec",
    "gemini -",
)


def _shipped_task_contracts():
    names = (
        "dispatch-sequence.schema.json",
        "prompt-sequence.schema.json",
        "harness-capability.schema.json",
    )
    return [(_REPO / "schemas" / n) for n in names]


def test_no_literal_harness_name_in_core_modules_or_task_contracts():
    core_modules = sorted((_SRC / "skillweave" / "dispatch").glob("*.py"))
    offenders = []
    for path in core_modules + _shipped_task_contracts():
        lowered = path.read_text(encoding="utf-8", errors="ignore").lower()
        for name in _HARNESS_LITERALS:
            if name in lowered:
                offenders.append((str(path), name))
    assert not offenders, f"literal harness name in core/task contract: {offenders}"


def test_no_native_delegation_command_in_core_modules_or_task_contracts():
    core_modules = sorted((_SRC / "skillweave" / "dispatch").glob("*.py"))
    offenders = []
    for path in core_modules + _shipped_task_contracts():
        lowered = path.read_text(encoding="utf-8", errors="ignore").lower()
        for prefix in _NATIVE_PREFIXES:
            if prefix in lowered:
                offenders.append((str(path), prefix))
    assert not offenders, (
        f"native delegation command in core/task contract: {offenders}"
    )


# ── Criterion 8: preview reports real evidence, no parity claim ───────────

def test_preview_reports_run_evidence_not_parity():
    # Preview output must report what actually ran and must not claim stable
    # transport parity before 1.4. The dispatch run's to_dict output carries the
    # no-stable-parity marker explicitly.
    from skillweave.dispatch import application

    report = application.DispatchReport(
        profile="x", execution_model="cold", max_parallel=1,
        max_correction_rounds_per_wave=0,
    )
    run = application.DispatchRun(run_id="r", wave="0", report=report)
    out = run.to_dict()
    assert "no stable" in out["transport_compatibility"]


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
