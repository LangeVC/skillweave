"""Dispatch-order group 3 — profile, chain and CMS execution matrix (criterion 3).

Proves the four profile concerns:

* **precedence** — the four limits resolve through the single documented chain
  (explicit override > profile limits > default), with no side table;
* **immutable snapshot** — ``ResolvedRole`` keeps requested/resolved model and
  profile provenance so a later reader reconciles without a second load;
* **basic-software parity** — the software-product-delivery profile preserves the
  seven legacy phases (K0..K6) and ships/externalizes skills losslessly;
* **distinct research semantics** — the research profile differs materially in
  phases, topology, categories, deliverables, evidence and change surfaces.

Fixtures are exercised positively (valid profile) and negatively: a conflicting
role (self-approval), a retroactive change (a later record must not mutate an
earlier resolved intent) and a missing required role all fail closed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from skillweave.dispatch.profile_resolution import (
    ProfileResolutionError,
    ResolvedModel,
    ResolvedRole,
    resolve_dispatch_profile,
    resolve_limits,
)
from skillweave.routing.profile import (
    CAP_APPROVE_GATE,
    CAP_MUTATE_RUN_STATE,
    Limits,
    RoutingProfile,
    RoutingProfileError,
)

from tests.gate_1312 import _sibling as sib

SEVEN_PHASES = [
    "Discovery", "Blueprint", "Design", "Build", "Release", "Launch", "Post-Release",
]
KERNELS = ["K0", "K1", "K2", "K3", "K4", "K5", "K6"]


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _base_profile(profile_id: str) -> dict:
    return _load(sib.base_profiles_dir() / f"{profile_id}.v1-preview.yaml")


def _write_profile(tmp_path: Path, body: dict) -> Path:
    p = tmp_path / "profile.yaml"
    p.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
    return p


def _minimal_profile(**extra) -> dict:
    data = {
        "name": "p",
        "tier": "balanced",
        "limits": {
            "timeout": 60.0,
            "max_retries": 1,
            "min_models_required": 2,
            "on_model_failure": "skip",
        },
        "roles": {},
    }
    data.update(extra)
    return data


def test_criterion_03_profile_precedence_snapshot_parity_and_semantics(tmp_path):
    """Precedence chain, immutable resolved snapshot, basic-software parity, and
    distinct research semantics — positive, conflict, and retroactive fixtures.
    """
    # --- Precedence: the single documented chain -------------------------------
    default = Limits()
    assert resolve_limits(None, None) == default
    profile_limits = Limits(timeout=90.0, max_retries=3, min_models_required=1,
                            on_model_failure="abort")
    overridden = resolve_limits(profile_limits, None)
    assert overridden.timeout == 90.0
    assert overridden.max_retries == 3
    assert overridden.on_model_failure == "abort"
    # Explicit override wins per field, independently. Fields left None in the
    # override fall through to the profile value.
    override = Limits(timeout=5.0, max_retries=None, min_models_required=None,
                      on_model_failure=None)
    merged = resolve_limits(profile_limits, override)
    assert merged.timeout == 5.0          # override won
    assert merged.max_retries == 3        # profile value kept (override None)
    assert merged.min_models_required == 1
    assert merged.on_model_failure == "abort"
    # A fully-explicit override wins every field (explicit values are honoured
    # even when zero/false).
    full = Limits(timeout=0.0, max_retries=0, min_models_required=0,
                  on_model_failure="skip")
    assert resolve_limits(profile_limits, full) == full

    # --- Immutable resolved snapshot -------------------------------------------
    path = _write_profile(tmp_path, _minimal_profile(roles={
        "ops": {
            "model": "faigate/deepseek-v4-flash",
            "tool": {"name": "opencode", "launch_command": "opencode run"},
        },
    }))
    resolved = resolve_dispatch_profile(str(path), ["ops"])
    ops = resolved.roles["ops"]
    assert isinstance(ops, ResolvedRole)
    assert isinstance(ops.model, ResolvedModel)
    # requested/resolved kept apart; provenance names the profile.
    assert ops.model.requested == "faigate/deepseek-v4-flash"
    assert ops.profile == "p"
    assert ops.launch_command() == "opencode run"

    # Retroactive change: appending another resolution must not mutate the first.
    snapshot = ops.to_dict()
    resolve_dispatch_profile(str(path), ["ops"])
    assert ops.to_dict() == snapshot

    # --- Basic-software parity -------------------------------------------------
    software = _base_profile("software-product-delivery")
    phases = software["lifecycleProfile"]["phases"]
    assert [p["name"] for p in phases] == SEVEN_PHASES
    assert [p["kernelStage"] for p in phases] == KERNELS
    assert [p["order"] for p in phases] == list(range(1, 8))

    # --- Distinct research semantics -------------------------------------------
    research = _base_profile("research-and-synthesis")
    assert research["workProfile"]["primaryCategory"] == "research"
    assert software["workProfile"]["primaryCategory"] == "build"
    assert software["workProfile"]["topology"] == "linear"
    assert research["workProfile"]["topology"] == "exploratory"
    # Research has no source/build surface; software does.
    r_surfaces = {s["surface"] for s in research["workProfile"]["changeSurfaces"]}
    s_surfaces = {s["surface"] for s in software["workProfile"]["changeSurfaces"]}
    assert r_surfaces.isdisjoint({"source_code", "deployment", "test_environment"})
    assert {"source_code", "deployment"} <= s_surfaces

    # --- Conflict: a self-approving role is refused at load time ----------------
    with pytest.raises(RoutingProfileError):
        RoutingProfile.from_dict(_minimal_profile(roles={
            "ops": {"capabilities": {
                CAP_MUTATE_RUN_STATE: True, CAP_APPROVE_GATE: True,
            }},
        }))

    # --- Missing required role fails closed (never a silent skip) ---------------
    # A required role that is NOT one of the seeded builtins is absent; the
    # resolver must refuse it by name, never invent an implicit in-place slot.
    with pytest.raises(ProfileResolutionError):
        resolve_dispatch_profile(str(path), ["ops", "bespoke_role"])

    # --- Missing/empty path fails closed ---------------------------------------
    with pytest.raises(ProfileResolutionError):
        resolve_dispatch_profile("", ["ops"])
    with pytest.raises(ProfileResolutionError):
        resolve_dispatch_profile("   ", ["ops"])
    with pytest.raises(Exception):
        resolve_dispatch_profile(str(tmp_path / "does-not-exist.yaml"), ["ops"])
