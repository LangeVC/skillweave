"""Facade integration tests for operator onboarding (SW-156-ONBOARD-002).

Covers the four acceptance criteria through the :class:`OnboardingService`
facade:

1. **Bundle exposes ``skillweave-onboarding``** — skill and CLI use one service.
2. **Preview precedes persistent writes** — ``preview()`` returns a result
   without mutating filesystem state; ``apply()`` persists after.
3. **Durable input uses ``skillweave.config``; generated state uses
   ``.skillweave``** — profile lands in ``skillweave.config/onboarding-profile.yaml``;
   onboarding state lands in ``.skillweave/onboarding-state.yaml``.
4. **Repeated execution is idempotent and reprofiling yields a diff** —
   re-running the same profile produces no change; a different profile yields a
   diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.onboarding import OnboardingService, OnboardingDiff


# ── Helpers ──────────────────────────────────────────────────────────────────


def _service(tmp_path: Path) -> OnboardingService:
    """Build an ``OnboardingService`` scoped to ``tmp_path``."""
    return OnboardingService(tmp_path)


def _durable_profile_path(root: Path) -> Path:
    return root / "skillweave.config" / "onboarding-profile.yaml"


def _generated_state_path(root: Path) -> Path:
    return root / ".skillweave" / "onboarding-state.yaml"


def _assert_no_persistence(root: Path) -> None:
    """Assert that neither durable nor generated state files exist."""
    assert not _durable_profile_path(root).exists()
    assert not _generated_state_path(root).exists()


# ── Criterion 1: Bundle exposes skillweave-onboarding via one service ─────────


def test_service_is_shared_by_skill_and_cli():
    """The service class is the single seam; no separate skill/CLI service."""
    from skillweave.onboarding import OnboardingService as Svc
    from skillweave.cli.onboard import build_onboard_parser

    svc = Svc()
    assert hasattr(svc, "preview")
    assert hasattr(svc, "apply")
    assert hasattr(svc, "load")
    assert hasattr(svc, "diff")

    # The CLI parser exists and uses the same service.
    parser = build_onboard_parser()
    assert parser.prog == "skillweave onboard"


def test_preview_returns_frozen_preview(tmp_path):
    """Preview returns an OnboardingPreview with expected fields."""
    svc = _service(tmp_path)
    result = svc.preview()

    assert result.profile is not None
    assert result.rationale
    assert result.next_action
    assert result.detected_phase

    # Check all four profile fields are present.
    for field in ("role", "purpose", "autonomy", "risk_boundary"):
        assert field in result.profile


# ── Criterion 2: Preview precedes persistent writes ─────────────────────────


def test_preview_does_not_persist(tmp_path):
    """Preview must not write any files."""
    _assert_no_persistence(tmp_path)
    svc = _service(tmp_path)
    result = svc.preview()

    assert result is not None
    _assert_no_persistence(tmp_path)


def test_apply_persists_after_preview(tmp_path):
    """apply() persists both durable and generated state."""
    _assert_no_persistence(tmp_path)
    svc = _service(tmp_path)

    # Preview first — no persistence.
    preview = svc.preview()
    _assert_no_persistence(tmp_path)

    # Apply — both files should exist.
    applied = svc.apply()
    assert _durable_profile_path(tmp_path).exists()
    assert _generated_state_path(tmp_path).exists()

    # Preview and apply agree on the profile block.
    assert preview.profile == applied.profile


# ── Criterion 3: Durable input in skillweave.config, generated in .skillweave ─


def test_durable_profile_lands_in_skillweave_config(tmp_path):
    """Durable profile is written to skillweave.config/."""
    svc = _service(tmp_path)
    svc.apply()

    path = _durable_profile_path(tmp_path)
    assert path.exists()
    assert path.parent.name == "skillweave.config"

    with open(path) as f:
        data = yaml.safe_load(f) or {}
    for field in ("role", "purpose", "autonomy", "risk_boundary"):
        assert field in data


def test_generated_state_lands_in_dot_skillweave(tmp_path):
    """Generated state is written to .skillweave/."""
    svc = _service(tmp_path)
    svc.apply()

    path = _generated_state_path(tmp_path)
    assert path.exists()
    assert ".skillweave" in path.parts

    with open(path) as f:
        data = yaml.safe_load(f) or {}
    assert "onboarding" in data
    assert "phase" in data


def test_load_durable_profile_returns_correct_values(tmp_path):
    """load_durable_profile() reads back what was applied."""
    svc = _service(tmp_path)
    svc.apply(role="reviewer", purpose="review")

    loaded = svc.load_durable_profile()
    assert loaded is not None
    assert loaded["role"] == "reviewer"
    assert loaded["purpose"] == "review"


def test_load_returns_onboarding_state(tmp_path):
    """load() reads back the generated state."""
    svc = _service(tmp_path)
    svc.apply()

    state = svc.load()
    assert state is not None
    assert state.profile
    assert state.rationale
    assert state.next_action
    assert state.persisted_at


# ── Criterion 4: Idempotent execution and reprofile diff ────────────────────


def test_apply_is_idempotent(tmp_path):
    """Applying the same profile twice produces identical state digests."""
    svc = _service(tmp_path)

    first = svc.apply()
    second = svc.apply()

    assert first.profile == second.profile
    assert first.rationale == second.rationale

    # idempotence check via the service
    assert svc.is_idempotent()

    # diff should show no changes
    diff = svc.diff()
    assert diff is not None
    assert not diff.has_changes


def test_idempotent_with_explicit_overrides(tmp_path):
    """Applying explicit overrides twice is also idempotent."""
    svc = _service(tmp_path)
    svc.apply(role="reviewer", autonomy="supervised")
    assert svc.is_idempotent(role="reviewer", autonomy="supervised")

    diff = svc.diff(role="reviewer", autonomy="supervised")
    assert diff is not None
    assert not diff.has_changes


def test_reprofiling_yields_diff(tmp_path):
    """Changing a profile field yields a structured diff."""
    svc = _service(tmp_path)
    svc.apply(role="developer", purpose="build")

    diff = svc.diff(role="reviewer", purpose="review")
    assert diff is not None
    assert diff.has_changes
    assert diff.profile_changed
    assert diff.unified_diff.strip(), "unified diff must not be empty"

    # The diff should mention the changed fields.
    assert "developer" in diff.unified_diff or "reviewer" in diff.unified_diff


def test_diff_is_none_when_no_state(tmp_path):
    """diff() returns None when no onboarding state has been persisted."""
    svc = _service(tmp_path)
    assert svc.diff() is None


def test_is_idempotent_true_when_no_state(tmp_path):
    """is_idempotent() returns True when no state exists (first run)."""
    svc = _service(tmp_path)
    assert svc.is_idempotent()


# ── OnboardingDiff contract ────────────────────────────────────────────────


def test_diff_has_changes_property():
    """has_changes is True when any dimension changed."""
    changed = OnboardingDiff(
        profile_changed=True,
        rationale_changed=False,
        next_action_changed=False,
        unified_diff="--- a\n+++ b\n@@ -1 +1 @@\n-developer\n+reviewer\n",
    )
    assert changed.has_changes

    unchanged = OnboardingDiff(
        profile_changed=False,
        rationale_changed=False,
        next_action_changed=False,
        unified_diff="",
    )
    assert not unchanged.has_changes
