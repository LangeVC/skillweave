"""
Unit tests for mode_manager module.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tempfile
import shutil
from pathlib import Path

from skillweave.mode_manager import ModeManager, ModeBehavior, RiskMode
from skillweave.persistence import SkillWeaveConfig, ensure_skillweave_folder


def test_mode_behavior_for_mode():
    """Test ModeBehavior.for_mode creates appropriate configurations."""
    # Conservative mode
    conservative = ModeBehavior.for_mode(RiskMode.CONSERVATIVE)
    assert conservative.require_approval is True
    assert conservative.max_parallel_tasks == 1
    assert conservative.auto_continue is False
    assert conservative.validation_strictness == "high"
    assert conservative.require_tests is True
    assert conservative.require_review is True
    assert conservative.allow_destructive is False
    assert conservative.require_confirmation is True
    assert conservative.safety_checks is True
    assert conservative.optimize_for_speed is False
    assert conservative.allow_experimental is False
    
    # Medium mode
    medium = ModeBehavior.for_mode(RiskMode.MEDIUM)
    assert medium.require_approval is False
    assert medium.max_parallel_tasks == 3
    assert medium.auto_continue is True
    assert medium.validation_strictness == "medium"
    assert medium.require_tests is True
    assert medium.require_review is False
    assert medium.allow_destructive is False
    assert medium.require_confirmation is True
    assert medium.safety_checks is True
    assert medium.optimize_for_speed is False
    assert medium.allow_experimental is False
    
    # Unicorn mode
    unicorn = ModeBehavior.for_mode(RiskMode.UNICORN)
    assert unicorn.require_approval is False
    assert unicorn.max_parallel_tasks == 10
    assert unicorn.auto_continue is True
    assert unicorn.validation_strictness == "low"
    assert unicorn.require_tests is False
    assert unicorn.require_review is False
    assert unicorn.allow_destructive is True
    assert unicorn.require_confirmation is True  # Changed to True for critical operations
    assert unicorn.safety_checks is True
    assert unicorn.optimize_for_speed is True
    assert unicorn.allow_experimental is True


def test_mode_manager_initialization():
    """Test ModeManager initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Default mode should be MEDIUM
        manager = ModeManager(tmpdir)
        assert manager.get_mode() == RiskMode.MEDIUM
        assert isinstance(manager.get_behavior(), ModeBehavior)
        
        # Test with different mode in config
        persistence = ensure_skillweave_folder(tmpdir)
        config = SkillWeaveConfig(mode=RiskMode.CONSERVATIVE)
        persistence.save_config(config)
        
        manager2 = ModeManager(tmpdir)
        assert manager2.get_mode() == RiskMode.CONSERVATIVE
        behavior = manager2.get_behavior()
        assert behavior.require_approval is True
        assert behavior.max_parallel_tasks == 1


def test_mode_manager_overrides():
    """Test that ModeManager applies overrides from config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = ensure_skillweave_folder(tmpdir)
        
        # Set conservative mode with overrides
        config = SkillWeaveConfig(
            mode=RiskMode.CONSERVATIVE,
            overrides={
                "conservative": {
                    "max_parallel_tasks": 2,  # Override from 1
                    "require_tests": False,    # Override from True
                    "validation_strictness": "medium"  # Override from high
                }
            }
        )
        persistence.save_config(config)
        
        manager = ModeManager(tmpdir)
        behavior = manager.get_behavior()
        
        # Check overrides applied
        assert behavior.max_parallel_tasks == 2
        assert behavior.require_tests is False
        assert behavior.validation_strictness == "medium"
        
        # Other values should remain as conservative defaults
        assert behavior.require_approval is True
        assert behavior.allow_destructive is False


def test_should_require_approval():
    """Test should_require_approval method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Conservative mode
        persistence = ensure_skillweave_folder(tmpdir)
        config = SkillWeaveConfig(mode=RiskMode.CONSERVATIVE)
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_require_approval("any_action") is True
        
        # Medium mode
        config.mode = RiskMode.MEDIUM
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        # Medium mode doesn't require approval (only confirmation for specific operations)
        assert manager.should_require_approval("destructive") is False
        assert manager.should_require_approval("high_risk") is False
        assert manager.should_require_approval("low_risk") is False
        
        # Unicorn mode
        config.mode = RiskMode.UNICORN
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_require_approval("any_action") is False


def test_get_max_parallel_tasks():
    """Test get_max_parallel_tasks method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for mode, expected in [
            (RiskMode.CONSERVATIVE, 1),
            (RiskMode.MEDIUM, 3),
            (RiskMode.UNICORN, 10)
        ]:
            persistence = ensure_skillweave_folder(tmpdir)
            config = SkillWeaveConfig(mode=mode)
            persistence.save_config(config)
            manager = ModeManager(tmpdir)
            assert manager.get_max_parallel_tasks() == expected


def test_should_require_confirmation():
    """Test should_require_confirmation method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Conservative mode
        persistence = ensure_skillweave_folder(tmpdir)
        config = SkillWeaveConfig(mode=RiskMode.CONSERVATIVE)
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_require_confirmation("any_operation") is True
        
        # Medium mode
        config.mode = RiskMode.MEDIUM
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_require_confirmation("delete") is True
        assert manager.should_require_confirmation("overwrite") is True
        assert manager.should_require_confirmation("modify_core") is True
        assert manager.should_require_confirmation("deploy") is True
        assert manager.should_require_confirmation("safe_operation") is False
        
        # Unicorn mode
        config.mode = RiskMode.UNICORN
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_require_confirmation("delete_production") is True
        assert manager.should_require_confirmation("format_disk") is True
        assert manager.should_require_confirmation("any_other") is False


def test_should_perform_safety_check():
    """Test should_perform_safety_check method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Conservative mode
        persistence = ensure_skillweave_folder(tmpdir)
        config = SkillWeaveConfig(mode=RiskMode.CONSERVATIVE)
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_perform_safety_check("any_check") is True
        
        # Medium mode
        config.mode = RiskMode.MEDIUM
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_perform_safety_check("security") is True
        assert manager.should_perform_safety_check("data_loss") is True
        assert manager.should_perform_safety_check("breaking_change") is True
        assert manager.should_perform_safety_check("minor_check") is False
        
        # Unicorn mode
        config.mode = RiskMode.UNICORN
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_perform_safety_check("data_loss") is True
        assert manager.should_perform_safety_check("other_check") is False


def test_get_mode_guidance():
    """Test get_mode_guidance method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for mode in [RiskMode.CONSERVATIVE, RiskMode.MEDIUM, RiskMode.UNICORN]:
            persistence = ensure_skillweave_folder(tmpdir)
            config = SkillWeaveConfig(mode=mode)
            persistence.save_config(config)
            manager = ModeManager(tmpdir)
            
            # Test general guidance
            guidance = manager.get_mode_guidance("blueprint")
            assert f"Mode: {mode.value.title()}" in guidance
            assert len(guidance) > 0
            
            # Test skill-specific guidance
            for skill in ["blueprint", "promptchain", "releasechain"]:
                guidance = manager.get_mode_guidance(skill)
                assert skill.capitalize() in guidance or "PromptChain" in guidance or "ReleaseChain" in guidance


def test_is_destructive_allowed():
    """Test is_destructive_allowed method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = ensure_skillweave_folder(tmpdir)
        
        config = SkillWeaveConfig(mode=RiskMode.CONSERVATIVE)
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.is_destructive_allowed() is False
        
        config.mode = RiskMode.MEDIUM
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.is_destructive_allowed() is False
        
        config.mode = RiskMode.UNICORN
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.is_destructive_allowed() is True


def test_should_optimize_for_speed():
    """Test should_optimize_for_speed method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = ensure_skillweave_folder(tmpdir)
        
        config = SkillWeaveConfig(mode=RiskMode.CONSERVATIVE)
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_optimize_for_speed() is False
        
        config.mode = RiskMode.MEDIUM
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_optimize_for_speed() is False
        
        config.mode = RiskMode.UNICORN
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.should_optimize_for_speed() is True


def test_is_experimental_allowed():
    """Test is_experimental_allowed method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = ensure_skillweave_folder(tmpdir)
        
        config = SkillWeaveConfig(mode=RiskMode.CONSERVATIVE)
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.is_experimental_allowed() is False
        
        config.mode = RiskMode.MEDIUM
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.is_experimental_allowed() is False
        
        config.mode = RiskMode.UNICORN
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.is_experimental_allowed() is True


def test_get_logging_level():
    """Test get_logging_level method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = ensure_skillweave_folder(tmpdir)
        
        config = SkillWeaveConfig(mode=RiskMode.CONSERVATIVE)
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.get_logging_level() == "DEBUG"
        
        config.mode = RiskMode.MEDIUM
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.get_logging_level() == "INFO"
        
        config.mode = RiskMode.UNICORN
        persistence.save_config(config)
        manager = ModeManager(tmpdir)
        assert manager.get_logging_level() == "WARNING"


if __name__ == "__main__":
    # Run tests
    test_mode_behavior_for_mode()
    test_mode_manager_initialization()
    test_mode_manager_overrides()
    test_should_require_approval()
    test_get_max_parallel_tasks()
    test_should_require_confirmation()
    test_should_perform_safety_check()
    test_get_mode_guidance()
    test_is_destructive_allowed()
    test_should_optimize_for_speed()
    test_is_experimental_allowed()
    test_get_logging_level()
    print("All tests passed!")