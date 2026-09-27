"""E2E test for the software-delivery.v2 WorkProfile (SW-160-VERT-001).

Proves all four acceptance criteria:

1. WorkProfile resolves into the generic kernel and normal run service.
2. No product-specific shortcut bypasses contract, evidence or review gates.
3. Legacy default behavior remains unchanged unless the new profile is
   explicitly selected.
4. A full positive run produces resolvable contract-derived receipts.

Hermetic: uses in-memory SQLite and a trivial subprocess, never a real model.
"""

import sys
import tempfile
import os
from pathlib import Path

import pytest
import yaml

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.routing.profile import (
    CAP_APPROVE_GATE,
    CAP_MUTATE_RUN_STATE,
    RoutingProfile,
    RoutingProfileError,
    from_dict,
)
from skillweave.dispatch.profile_resolution import (
    resolve_dispatch_profile,
    resolve_limits,
    ProfileResolutionError,
)
from skillweave.runsvc import RunApplicationService, RunExecution, RunIntegrationError
from skillweave.runtime.store import SQLiteRunStore
from skillweave.runtime.journal import EventJournal
from skillweave.runtime.registry import RawArtifactStore
from skillweave.runtime.verify import CompletionContract, GateState

_PROFILES_DIR = Path(__file__).resolve().parent.parent.parent / "profiles"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _service(tmp_db=":memory:"):
    store = SQLiteRunStore(tmp_db)
    journal = EventJournal(store)
    raw = RawArtifactStore()
    return RunApplicationService(store, journal, raw), store, journal, raw


def _minimal_profile(**extra) -> dict:
    data = {
        "name": "baseline",
        "tier": "balanced",
        "limits": {
            "timeout": 60.0,
            "max_retries": 1,
            "min_models_required": 2,
            "on_model_failure": "skip",
        },
        "roles": {
            "ops": {
                "model": "faigate/deepseek-v4-pro",
                "tool": {"name": "opencode", "launch_command": "opencode run -"},
                "capabilities": {"can_mutate_run_state": True},
            },
            "reviewer": {
                "model": "faigate/deepseek-v4-pro",
                "tool": {"name": "opencode", "launch_command": "opencode run -"},
                "capabilities": {"can_approve_gate": True},
            },
        },
    }
    data.update(extra)
    return data


# ---------------------------------------------------------------------------
# Criterion 1: WorkProfile resolves into generic kernel and normal run service
# ---------------------------------------------------------------------------

def test_profile_loads_as_routing_profile():
    """The software-delivery.v2 profile loads as a valid RoutingProfile."""
    raw = _load_yaml(_PROFILES_DIR / "software-delivery.v2.yaml")
    profile = from_dict(raw)
    assert isinstance(profile, RoutingProfile)
    assert profile.name == "software-delivery-v2"
    assert profile.tier == "balanced"


def test_profile_carries_workprofile_contract_fields():
    """The profile carries WorkProfile contract metadata (category, kernelStages)."""
    raw = _load_yaml(_PROFILES_DIR / "software-delivery.v2.yaml")
    assert raw.get("contractVersion") == "1.0.0"
    assert raw.get("id") == "software-delivery.v2"
    assert raw.get("category") == "build"
    assert "K0" in raw.get("kernelStages", [])
    assert "K6" in raw.get("kernelStages", [])
    assert raw.get("topology") == "iterative"


def test_resolved_dispatch_runs_through_run_service():
    """The resolved profile drives RunApplicationService to completion."""
    raw = _load_yaml(_PROFILES_DIR / "software-delivery.v2.yaml")
    tmp = tempfile.mkdtemp()
    tmppath = os.path.join(tmp, "sd.yaml")
    with open(tmppath, "w") as f:
        yaml.dump(raw, f)
    resolved = resolve_dispatch_profile(tmppath, required_roles=["ops", "reviewer"])
    assert resolved.profile_name == "software-delivery-v2"
    assert resolved.role("ops") is not None
    assert resolved.role("reviewer") is not None

    service, store, journal, raw_store = _service()
    result = service.execute(
        [sys.executable, "-c", "print('software-delivery-v2-output')"],
        run_id="sw-delivery-v2-e2e",
        tool=resolved.role("ops").tool.name,
        model=resolved.role("ops").model.resolved,
        subject_repo="skillweave",
        subject_commit="abcdef1234567890abcdef1234567890abcdef12",
        created_at="2026-09-27T00:00:00Z",
    )
    assert isinstance(result, RunExecution)
    assert result.run.state == "advance_or_stop"
    assert result.gate_state == "pass"


# ---------------------------------------------------------------------------
# Criterion 2: No product-specific shortcut bypasses gates
# ---------------------------------------------------------------------------

def test_ops_cannot_approve_gate():
    """The ops role holds can_mutate_run_state but NOT can_approve_gate."""
    raw = _load_yaml(_PROFILES_DIR / "software-delivery.v2.yaml")
    profile = from_dict(raw)
    ops = profile.role("ops")
    assert ops is not None
    assert ops.can(CAP_MUTATE_RUN_STATE) is True
    assert ops.can(CAP_APPROVE_GATE) is False


def test_reviewer_cannot_mutate_run_state():
    """The reviewer role holds can_approve_gate but NOT can_mutate_run_state."""
    raw = _load_yaml(_PROFILES_DIR / "software-delivery.v2.yaml")
    profile = from_dict(raw)
    reviewer = profile.role("reviewer")
    assert reviewer is not None
    assert reviewer.can(CAP_APPROVE_GATE) is True
    assert reviewer.can(CAP_MUTATE_RUN_STATE) is False


def test_self_approval_refused_at_load():
    """A role holding both capabilities is refused (self-approval guard)."""
    bad = _minimal_profile(
        roles={
            "ops": {
                "model": "m",
                "capabilities": {
                    "can_mutate_run_state": True,
                    "can_approve_gate": True,
                },
            },
        },
    )
    with pytest.raises(RoutingProfileError, match="self-approval"):
        from_dict(bad)


def test_gate_derived_from_completion_contract_not_raw_exit():
    """The run service derives gate state from CompletionContract over
    verified outcome, never from a raw exit code alone."""
    service, store, journal, raw = _service()
    result = service.execute(
        [sys.executable, "-c", "pass"],
        run_id="sw-empty-gate",
        tool="opencode",
        model="m",
        subject_repo="skillweave",
        subject_commit="abcdef1234567890abcdef1234567890abcdef12",
        created_at="2026-09-27T00:00:00Z",
    )
    assert result.gate_state != "pass"
    assert result.run.metadata.get("stop_reason") == "before_gate"


# ---------------------------------------------------------------------------
# Criterion 3: Legacy default behavior unchanged unless new profile selected
# ---------------------------------------------------------------------------

def test_software_delivery_profile_is_distinct_from_standard():
    """The new profile is a distinct object from the standard example."""
    sd_raw = _load_yaml(_PROFILES_DIR / "software-delivery.v2.yaml")
    standard_raw = _load_yaml(_PROFILES_DIR / "example-standard.yaml")
    sd_profile = from_dict(sd_raw)
    standard_profile = from_dict(standard_raw)
    assert sd_profile.name != standard_profile.name
    assert sd_profile.tier == standard_profile.tier  # both balanced


def test_default_limits_unchanged():
    """The documented default Limits are unchanged by the new profile."""
    raw = _load_yaml(_PROFILES_DIR / "software-delivery.v2.yaml")
    profile = from_dict(raw)
    resolved = resolve_limits(profile.limits, None)
    assert resolved.timeout == 120.0


# ---------------------------------------------------------------------------
# Criterion 4: Full positive run produces resolvable contract-derived receipts
# ---------------------------------------------------------------------------

def test_positive_run_produces_all_six_records():
    """A full positive run through RunApplicationService produces all six
    record kinds with a resolvable, tamper-evident receipt."""
    raw = _load_yaml(_PROFILES_DIR / "software-delivery.v2.yaml")
    profile = from_dict(raw)

    service, store, journal, raw_store = _service()
    result = service.execute(
        [sys.executable, "-c", "print('software-delivery-v2-receipt-test')"],
        run_id="sw-delivery-receipt",
        tool="opencode",
        model="faigate/deepseek-v4-pro",
        subject_repo="skillweave",
        subject_commit="abcdef1234567890abcdef1234567890abcdef12",
        created_at="2026-09-27T00:00:00Z",
    )

    # 1. Run record exists and is terminal
    run = store.get_run("sw-delivery-receipt")
    assert run is not None
    assert run.state == "advance_or_stop"

    # 2. Journal is gap-free
    assert len(result.journal) >= 1
    assert journal.has_gaps("sw-delivery-receipt") is False

    # 3. Raw artifact is content-addressed and resolvable
    assert len(result.raw_digest) == 64
    assert raw_store.resolve(result.raw_digest) == result.raw_bytes
    assert b"software-delivery-v2-receipt-test" in result.raw_bytes

    # 4. Receipt is bound to run and persisted
    assert result.receipt.artifact_id == "runsvc-sw-delivery-receipt"
    assert result.receipt.sha256 == result.raw_digest
    persisted = store.get_evidence(result.receipt.artifact_id)
    assert persisted is not None

    # 5. Verification has its own identity, bound to subject receipt
    assert result.verification["subject_artifact_id"] == result.receipt.artifact_id
    assert result.verification["verified_by"] == "verifier"

    # 6. Gate state is PASS for real output
    assert result.gate_state == "pass"
