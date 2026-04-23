"""
Targeted tests for uncovered lines in risk_mode_resolver and mode_manager.

Covers:
- risk_mode_resolver.py:77  (system default fallback)
- risk_mode_resolver.py:107 (_load_global_config when no global config)
- risk_mode_resolver.py:129 (get_effective_mode alias)
- mode_manager.py:147-152  (medium/unicorn branches with approval overrides)
- mode_manager.py:160,164,168 (simple getter methods)
- mode_manager.py:179       (require_confirmation=False override path)
- mode_manager.py:202       (safety_checks=False override path)
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

from skillweave.risk_mode_resolver import RiskModeResolver
from skillweave.mode_manager import ModeManager, RiskMode
from skillweave.persistence import SkillWeaveConfig, ensure_skillweave_folder


# ── risk_mode_resolver gaps ──────────────────────────────────────────────────

def test_system_default_fallback_when_no_configs(tmp_path):
    """Cover line 77: return "medium" when no configs exist and include_global=False."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    project_dir = tmp_path / "project_no_config"
    project_dir.mkdir()

    with patch("pathlib.Path.home", return_value=fake_home):
        resolver = RiskModeResolver(str(project_dir))
        # No project config, no global config, include_global_config=False
        result = resolver.resolve(include_global_config=False)
        assert result == "medium"


def test_system_default_fallback_no_global_config(tmp_path):
    """Cover line 77 + 107: no project config, no global config, include_global=True."""
    fake_home = tmp_path / "empty_home"
    fake_home.mkdir()
    project_dir = tmp_path / "project_no_config"
    project_dir.mkdir()

    with patch("pathlib.Path.home", return_value=fake_home):
        resolver = RiskModeResolver(str(project_dir))
        # No project config AND no global config → hits both line 107 and 77
        result = resolver.resolve(include_global_config=True)
        assert result == "medium"


def test_get_effective_mode_alias(tmp_path):
    """Cover line 129: get_effective_mode delegates to resolve."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    with patch("pathlib.Path.home", return_value=fake_home):
        resolver = RiskModeResolver(str(project_dir))
        # Default should resolve to medium
        assert resolver.get_effective_mode() == "medium"
        # CLI override should work through alias
        assert resolver.get_effective_mode(cli_override="unicorn") == "unicorn"


# ── mode_manager gaps ────────────────────────────────────────────────────────

def test_should_require_approval_medium_with_override(tmp_path):
    """Cover line 148: medium branch in should_require_approval."""
    persistence = ensure_skillweave_folder(tmp_path)
    config = SkillWeaveConfig(
        mode=RiskMode.MEDIUM,
        overrides={"medium": {"require_approval": True}}
    )
    persistence.save_config(config)
    manager = ModeManager(tmp_path)

    # With require_approval=True override, medium should check action_type
    assert manager.should_require_approval("destructive") is True
    assert manager.should_require_approval("high_risk") is True
    assert manager.should_require_approval("low_risk") is False


def test_should_require_approval_unicorn_with_override(tmp_path):
    """Cover line 149-150: unicorn branch in should_require_approval."""
    persistence = ensure_skillweave_folder(tmp_path)
    config = SkillWeaveConfig(
        mode=RiskMode.UNICORN,
        overrides={"unicorn": {"require_approval": True}}
    )
    persistence.save_config(config)
    manager = ModeManager(tmp_path)

    # With require_approval=True override, unicorn should still return False
    assert manager.should_require_approval("anything") is False
    assert manager.should_require_approval("destructive") is False


def test_getter_methods(tmp_path):
    """Cover lines 160, 164, 168: simple getter methods."""
    persistence = ensure_skillweave_folder(tmp_path)
    config = SkillWeaveConfig(mode=RiskMode.CONSERVATIVE)
    persistence.save_config(config)
    manager = ModeManager(tmp_path)

    assert manager.get_validation_strictness() == "high"
    assert manager.should_require_tests() is True
    assert manager.should_require_review() is True

    # Also verify medium mode
    config.mode = RiskMode.MEDIUM
    persistence.save_config(config)
    manager = ModeManager(tmp_path)
    assert manager.get_validation_strictness() == "medium"
    assert manager.should_require_tests() is True
    assert manager.should_require_review() is False

    # And unicorn mode
    config.mode = RiskMode.UNICORN
    persistence.save_config(config)
    manager = ModeManager(tmp_path)
    assert manager.get_validation_strictness() == "low"
    assert manager.should_require_tests() is False
    assert manager.should_require_review() is False


def test_should_require_confirmation_override_false(tmp_path):
    """Cover line 179: require_confirmation=False returns False early."""
    persistence = ensure_skillweave_folder(tmp_path)
    config = SkillWeaveConfig(
        mode=RiskMode.MEDIUM,
        overrides={"medium": {"require_confirmation": False}}
    )
    persistence.save_config(config)
    manager = ModeManager(tmp_path)

    assert manager.should_require_confirmation("delete") is False
    assert manager.should_require_confirmation("any_operation") is False


def test_should_perform_safety_check_override_false(tmp_path):
    """Cover line 202: safety_checks=False returns False early."""
    persistence = ensure_skillweave_folder(tmp_path)
    config = SkillWeaveConfig(
        mode=RiskMode.CONSERVATIVE,
        overrides={"conservative": {"safety_checks": False}}
    )
    persistence.save_config(config)
    manager = ModeManager(tmp_path)

    assert manager.should_perform_safety_check("security") is False
    assert manager.should_perform_safety_check("data_loss") is False
    assert manager.should_perform_safety_check("any_check") is False
