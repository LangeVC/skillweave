"""
Tests for RiskModeResolver and hierarchical precedence logic.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from skillweave.risk_mode_resolver import RiskModeResolver, RiskMode
from skillweave.persistence import SkillWeaveConfig, RiskMode as RiskModeEnum


def test_risk_mode_enum():
    """Test RiskMode enum values."""
    assert RiskMode.CONSERVATIVE.value == "conservative"
    assert RiskMode.MEDIUM.value == "medium"
    assert RiskMode.UNICORN.value == "unicorn"
    
    # Test parsing
    assert RiskMode("conservative") == RiskMode.CONSERVATIVE
    assert RiskMode("medium") == RiskMode.MEDIUM
    assert RiskMode("unicorn") == RiskMode.UNICORN


def test_default_mode():
    """Test default risk mode when no configuration exists."""
    resolver = RiskModeResolver()
    # With no config files, env var, or CLI arg, should return default (medium)
    assert resolver.resolve() == "medium"


def test_environment_variable():
    """Test SKILLWEAVE_RISK_MODE environment variable."""
    with patch.dict(os.environ, {"SKILLWEAVE_RISK_MODE": "unicorn"}):
        resolver = RiskModeResolver()
        assert resolver.resolve() == "unicorn"
    
    # Invalid environment variable should fall back
    with patch.dict(os.environ, {"SKILLWEAVE_RISK_MODE": "invalid"}):
        resolver = RiskModeResolver()
        # Should fall back to default (medium) or next precedence
        # Since we have no config files, should be medium
        assert resolver.resolve() == "medium"


def test_project_config(tmp_path):
    """Test project configuration precedence."""
    # Create a temporary project directory
    project_root = tmp_path / "test_project"
    project_root.mkdir()
    
    # Create .skillweave/config.yaml with unicorn mode
    skillweave_dir = project_root / ".skillweave"
    skillweave_dir.mkdir()
    config_path = skillweave_dir / "config.yaml"
    config_data = {"mode": "unicorn"}
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    
    resolver = RiskModeResolver(str(project_root))
    assert resolver.resolve() == "unicorn"
    
    # Environment variable should override project config
    with patch.dict(os.environ, {"SKILLWEAVE_RISK_MODE": "conservative"}):
        resolver = RiskModeResolver(str(project_root))
        assert resolver.resolve() == "conservative"


def test_global_config(tmp_path):
    """Test global configuration loading."""
    # Mock home directory to temporary location
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    
    # Create global config
    global_skillweave = fake_home / ".skillweave"
    global_skillweave.mkdir()
    config_path = global_skillweave / "config.yaml"
    config_data = {"mode": "conservative"}
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)
    
    # Create a temporary project directory without config
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    
    with patch("pathlib.Path.home", return_value=fake_home):
        resolver = RiskModeResolver(str(project_dir))
        # No project config, should use global config
        assert resolver.resolve() == "conservative"


def test_cli_override():
    """Test CLI argument override (highest precedence)."""
    resolver = RiskModeResolver()
    # Test with CLI argument
    assert resolver.resolve(cli_override="unicorn") == "unicorn"
    
    # CLI should override environment variable
    with patch.dict(os.environ, {"SKILLWEAVE_RISK_MODE": "conservative"}):
        assert resolver.resolve(cli_override="medium") == "medium"
    
    # Invalid CLI argument should raise ValueError? Currently returns "medium" due to default
    # Let's check behavior: invalid cli_override passes through to env/project/default
    # The resolver doesn't validate cli_override; it just returns it as string.
    # But the literal type restricts to valid values. In practice, callers should pass valid values.
    # We'll skip validation test.


def test_precedence_hierarchy(tmp_path):
    """Test full precedence hierarchy."""
    # Create global config with medium
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    global_skillweave = fake_home / ".skillweave"
    global_skillweave.mkdir()
    global_config_path = global_skillweave / "config.yaml"
    with open(global_config_path, "w") as f:
        yaml.dump({"mode": "medium"}, f)
    
    # Create project config with conservative
    project_root = tmp_path / "project"
    project_root.mkdir()
    skillweave_dir = project_root / ".skillweave"
    skillweave_dir.mkdir()
    project_config_path = skillweave_dir / "config.yaml"
    with open(project_config_path, "w") as f:
        yaml.dump({"mode": "conservative"}, f)
    
    with patch("pathlib.Path.home", return_value=fake_home):
        # 1. No CLI, no env var -> project config (conservative)
        resolver = RiskModeResolver(str(project_root))
        assert resolver.resolve() == "conservative"
        
        # 2. Add env var -> env var overrides (unicorn)
        with patch.dict(os.environ, {"SKILLWEAVE_RISK_MODE": "unicorn"}):
            assert resolver.resolve() == "unicorn"
            
            # 3. Add CLI arg -> CLI overrides env var (medium)
            assert resolver.resolve(cli_override="medium") == "medium"


def test_load_config_files(tmp_path):
    """Test loading of project and global config files."""
    # Create test configs
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    global_skillweave = fake_home / ".skillweave"
    global_skillweave.mkdir()
    with open(global_skillweave / "config.yaml", "w") as f:
        yaml.dump({"mode": "unicorn", "features": {"checklist_execution": True}}, f)
    
    project_root = tmp_path / "project"
    project_root.mkdir()
    skillweave_dir = project_root / ".skillweave"
    skillweave_dir.mkdir()
    with open(skillweave_dir / "config.yaml", "w") as f:
        yaml.dump({"mode": "conservative"}, f)
    
    with patch("pathlib.Path.home", return_value=fake_home):
        resolver = RiskModeResolver(str(project_root))
        
        # Load project config
        project_config = resolver._load_project_config()
        assert isinstance(project_config, SkillWeaveConfig)
        assert project_config.mode == RiskModeEnum.CONSERVATIVE
        
        # Load global config
        global_config = resolver._load_global_config()
        assert isinstance(global_config, SkillWeaveConfig)
        assert global_config.mode == RiskModeEnum.UNICORN
        assert global_config.features["checklist_execution"] is True


def test_malformed_config_files(tmp_path):
    """Test handling of malformed config files."""
    # Create malformed YAML
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    global_skillweave = fake_home / ".skillweave"
    global_skillweave.mkdir()
    with open(global_skillweave / "config.yaml", "w") as f:
        f.write("invalid: yaml: [")
    
    with patch("pathlib.Path.home", return_value=fake_home):
        resolver = RiskModeResolver()
        # Should handle error gracefully and return default
        # The method should catch the exception and return default config
        global_config = resolver._load_global_config()
        assert isinstance(global_config, SkillWeaveConfig)
        assert global_config.mode == RiskModeEnum.MEDIUM  # default


def test_read_environment_variable():
    """Test _get_env_override method."""
    resolver = RiskModeResolver()
    
    # Valid values
    with patch.dict(os.environ, {"SKILLWEAVE_RISK_MODE": "conservative"}):
        assert resolver._get_env_override() == "conservative"
    
    with patch.dict(os.environ, {"SKILLWEAVE_RISK_MODE": "medium"}):
        assert resolver._get_env_override() == "medium"
    
    with patch.dict(os.environ, {"SKILLWEAVE_RISK_MODE": "unicorn"}):
        assert resolver._get_env_override() == "unicorn"
    
    # Invalid value
    with patch.dict(os.environ, {"SKILLWEAVE_RISK_MODE": "invalid"}):
        assert resolver._get_env_override() is None
    
    # Missing variable
    if "SKILLWEAVE_RISK_MODE" in os.environ:
        del os.environ["SKILLWEAVE_RISK_MODE"]
    assert resolver._get_env_override() is None


def test_convenience_function():
    """Test get_effective_risk_mode convenience function."""
    from skillweave.risk_mode_resolver import get_effective_risk_mode
    
    # Default behavior
    assert get_effective_risk_mode() == "medium"
    
    # With CLI argument
    assert get_effective_risk_mode(cli_override="unicorn") == "unicorn"
    
    # With environment variable
    with patch.dict(os.environ, {"SKILLWEAVE_RISK_MODE": "conservative"}):
        assert get_effective_risk_mode() == "conservative"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])