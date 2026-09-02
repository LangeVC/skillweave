"""
Unit tests for persistence module.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tempfile
import shutil
from pathlib import Path
import yaml
import json

from skillweave.persistence import (
    SkillWeavePersistence,
    SkillWeaveConfig,
    RiskMode,
    ensure_skillweave_folder,
    get_config,
    get_mode_only,
    is_feature_enabled,
    get_mode_specific_setting,
)


# ---------------------------------------------------------------------------
# SW152-008 — skillweave.config/ as the durable input tier
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SHIPPED_CATALOGUE = _REPO_ROOT / "config" / "catalogue.yaml"


def _catalogue_bytes(tmpdir: Path) -> bytes:
    """Return the bytes of the seeded tier-2 catalogue (raises if absent)."""
    return (Path(tmpdir) / "skillweave.config" / "catalogue.yaml").read_bytes()


def test_skillweave_persistence_initialization():
    """Test that persistence manager initializes correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        assert persistence.project_root == Path(tmpdir).resolve()
        assert persistence.skillweave_dir == Path(tmpdir).resolve() / ".skillweave"
        assert persistence.config is None


def test_ensure_folder_structure():
    """Test creation of .skillweave folder structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        # Check main folder exists
        assert persistence.skillweave_dir.exists()
        assert persistence.skillweave_dir.is_dir()
        
        # Check subdirectories
        for subdir in ["handover", "specs", "tracking-log", "manifesto"]:
            subdir_path = persistence.skillweave_dir / subdir
            assert subdir_path.exists(), f"Missing subdirectory: {subdir}"
            assert subdir_path.is_dir()
        
        # Check config file exists
        config_path = persistence.skillweave_dir / "config.yaml"
        assert config_path.exists()
        
        # Check README files
        for subdir in ["handover", "specs", "tracking-log", "manifesto"]:
            readme_path = persistence.skillweave_dir / subdir / "README.md"
            assert readme_path.exists()
        
        # Check .gitignore entry
        gitignore_path = Path(tmpdir) / ".gitignore"
        if gitignore_path.exists():
            content = gitignore_path.read_text()
            assert ".skillweave/tracking-log/*" in content


def test_default_config():
    """Test default configuration values."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        config = persistence.load_config()
        
        assert config.mode == RiskMode.MEDIUM
        assert config.features["checklist_execution"] is False
        assert config.features["design_thinking_lens"] is False
        assert config.features["community_patterns"] is False
        assert config.overrides == {}


def test_save_and_load_config():
    """Test saving and loading configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        # Create custom config
        config = SkillWeaveConfig(
            mode=RiskMode.CONSERVATIVE,
            features={
                "checklist_execution": True,
                "design_thinking_lens": False,
                "community_patterns": True,
            },
            overrides={"conservative": {"max_parallel_tasks": 1}}
        )
        
        persistence.save_config(config)
        
        # Load config back
        loaded_config = persistence.load_config()
        
        assert loaded_config.mode == RiskMode.CONSERVATIVE
        assert loaded_config.features["checklist_execution"] is True
        assert loaded_config.features["community_patterns"] is True
        assert loaded_config.overrides["conservative"]["max_parallel_tasks"] == 1


def test_tracking_log_operations():
    """Test saving and loading tracking logs."""
    import re
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        session_id = "test-session-123"
        log_data = {
            "session_id": session_id,
            "timestamp": "2025-01-01T12:00:00",
            "steps_completed": 5,
            "current_step": "ARCH-001",
        }
        
        # Save log
        log_path = persistence.save_tracking_log(session_id, log_data)
        assert log_path.exists()
        # Check filename pattern: YYYYMMDD-session_id.json
        import re
        pattern = r"^\d{8}-" + re.escape(session_id) + r"\.json$"
        assert re.match(pattern, log_path.name) is not None
        assert log_path.name.endswith(f"{session_id}.json")
        
        # Load log
        loaded_data = persistence.load_tracking_log(session_id)
        assert loaded_data is not None
        assert loaded_data["session_id"] == session_id
        assert loaded_data["steps_completed"] == 5
        
        # List logs
        logs = persistence.list_tracking_logs()
        assert len(logs) == 1
        assert logs[0]["session_id"] == session_id


def test_ensure_skillweave_folder_function():
    """Test the convenience function ensure_skillweave_folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = ensure_skillweave_folder(tmpdir)
        assert isinstance(persistence, SkillWeavePersistence)
        assert persistence.skillweave_dir.exists()


def test_get_config_function():
    """Test the get_config convenience function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # First ensure folder exists
        ensure_skillweave_folder(tmpdir)
        
        config = get_config(tmpdir)
        assert isinstance(config, SkillWeaveConfig)
        assert config.mode == RiskMode.MEDIUM


def test_risk_mode_enum():
    """Test RiskMode enum values."""
    assert RiskMode.CONSERVATIVE.value == "conservative"
    assert RiskMode.MEDIUM.value == "medium"
    assert RiskMode.UNICORN.value == "unicorn"
    
    # Test from string
    assert RiskMode("conservative") == RiskMode.CONSERVATIVE
    assert RiskMode("medium") == RiskMode.MEDIUM
    assert RiskMode("unicorn") == RiskMode.UNICORN


def test_get_mode_only():
    """Test get_mode_only helper function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Default mode should be "medium"
        mode = get_mode_only(tmpdir)
        assert mode == "medium"
        
        # Change config and test
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        config = SkillWeaveConfig(mode=RiskMode.CONSERVATIVE)
        persistence.save_config(config)
        
        mode = get_mode_only(tmpdir)
        assert mode == "conservative"


def test_is_feature_enabled():
    """Test is_feature_enabled helper function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Default features are disabled
        assert is_feature_enabled("checklist_execution", tmpdir) is False
        assert is_feature_enabled("design_thinking_lens", tmpdir) is False
        
        # Enable a feature and test
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        config = SkillWeaveConfig(
            features={"checklist_execution": True, "design_thinking_lens": False}
        )
        persistence.save_config(config)
        
        assert is_feature_enabled("checklist_execution", tmpdir) is True
        assert is_feature_enabled("design_thinking_lens", tmpdir) is False
        assert is_feature_enabled("nonexistent", tmpdir) is False


def test_get_mode_specific_setting():
    """Test get_mode_specific_setting helper function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Default no overrides
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        # Test default value
        value = get_mode_specific_setting("conservative.max_parallel_tasks", 3, tmpdir)
        assert value == 3
        
        # Set overrides and test
        config = SkillWeaveConfig(
            mode=RiskMode.CONSERVATIVE,
            overrides={
                "conservative": {"max_parallel_tasks": 1, "require_approval": True},
                "unicorn": {"max_parallel_tasks": 10}
            }
        )
        persistence.save_config(config)
        
        # Get setting for current mode (conservative)
        value = get_mode_specific_setting("conservative.max_parallel_tasks", 3, tmpdir)
        assert value == 1
        
        # Nested path
        value = get_mode_specific_setting("conservative.require_approval", False, tmpdir)
        assert value is True
        
        # Different mode than current (should still work)
        value = get_mode_specific_setting("unicorn.max_parallel_tasks", 5, tmpdir)
        assert value == 10
        
        # Non-existent path returns default
        value = get_mode_specific_setting("conservative.nonexistent", "default", tmpdir)
        assert value == "default"


# ---------------------------------------------------------------------------
# SW152-008 — skillweave.config/ as the durable input tier
# ---------------------------------------------------------------------------

def test_preflight_seeds_config_tier_from_packaged_defaults():
    """Criterion 1: an empty project gets skillweave.config/ populated from
    the shipped default, not left empty or leaked into .skillweave/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()

        tier2_dir = Path(tmpdir) / "skillweave.config"
        assert tier2_dir.is_dir(), "skillweave.config/ was not created"

        catalogue = tier2_dir / "catalogue.yaml"
        assert catalogue.is_file(), "skillweave.config/catalogue.yaml was not seeded"

        # Seeded content must match the shipped tier-1 deliverable byte-for-byte.
        assert catalogue.read_bytes() == _SHIPPED_CATALOGUE.read_bytes()

        # The tier-2 config tier must NOT leak into the git-excluded substrate.
        assert not (persistence.skillweave_dir / "catalogue.yaml").exists()


def test_preflight_preserves_tuned_config_tier():
    """Criterion 2: a second preflight over a modified skillweave.config/
    leaves the modified file byte-identical (never overwrite a tuning)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()

        catalogue = Path(tmpdir) / "skillweave.config" / "catalogue.yaml"
        tuned = b"# team-tuned roster\nmodels: {}\n"
        catalogue.write_bytes(tuned)

        persistence.ensure_folder_structure()

        assert catalogue.read_bytes() == tuned, (
            "a second preflight overwrote the team's tuned catalogue"
        )


def test_gitignore_inverted_and_anchored():
    """Criterion 3: the consumer .gitignore receives /.skillweave/ (anchored)
    and never a skillweave.config/ entry."""
    with tempfile.TemporaryDirectory() as tmpdir:
        gitignore = Path(tmpdir) / ".gitignore"
        gitignore.write_text("# existing entry\n", encoding="utf-8")

        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()

        content = gitignore.read_text()

        # The anchored exclusion is written (inverts the old tracking-log-only form).
        assert "/.skillweave/" in content
        # The old unanchored-per-file entry is gone.
        assert ".skillweave/tracking-log/*" not in content
        # skillweave.config/ is a durable input tier — never gitignored.
        assert "skillweave.config" not in content


def test_gitignore_entry_is_exact_class_constant():
    """The written entry is the anchored form and lives on the class."""
    assert SkillWeavePersistence.GITIGNORE_ENTRY == "/.skillweave/"