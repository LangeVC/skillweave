#!/usr/bin/env python3
"""
Integration tests for opencode framework adapter.
"""

import tempfile
import json
from pathlib import Path
import shutil

from swpm.frameworks.opencode import OpenCodeAdapter


def test_opencode_adapter_install_and_remove():
    """Test full install/remove cycle for opencode adapter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create a mock skill directory
        skill_source = tmpdir_path / "test-skill"
        skill_source.mkdir()
        (skill_source / "SKILL.md").write_text("# Test Skill\nThis is a test skill.")
        (skill_source / ".skillweave-version").write_text("1.2.3")
        
        # Create adapter instance
        adapter = OpenCodeAdapter()
        
        # Mock the opencode skills directory for this instance
        test_opencode_dir = tmpdir_path / ".opencode" / "skills"
        test_opencode_dir.mkdir(parents=True, exist_ok=True)
        adapter.opencode_skills_dir = test_opencode_dir
        # Mock storage directory to avoid writing to real home directory
        adapter.storage.base_dir = tmpdir_path / ".skillweave" / "packages"
        
        # Test installation
        success = adapter.install_skill("test-skill", "1.2.3", skill_source)
        assert success, "Installation should succeed"
        
        # Verify symlink was created
        link_path = test_opencode_dir / "test-skill"
        assert link_path.exists(), "Symlink should exist"
        assert link_path.is_symlink(), "Should be a symlink"
        
        # Verify skill exists check works
        assert adapter.skill_exists("test-skill"), "Skill should be reported as existing"
        
        # Verify metadata extraction
        metadata = adapter.get_skill_metadata("test-skill")
        assert metadata is not None, "Metadata should be extracted"
        assert metadata["name"] == "test-skill", "Metadata should include skill name"
        assert metadata["version"] == "1.2.3", "Metadata should include version"
        assert "files" in metadata, "Metadata should include file list"
        
        # Test removal
        remove_success = adapter.remove_skill("test-skill")
        assert remove_success, "Removal should succeed"
        assert not link_path.exists(), "Symlink should be removed"
        assert not adapter.skill_exists("test-skill"), "Skill should no longer exist"


def test_opencode_adapter_skill_metadata_extraction():
    """Test that skill metadata is correctly extracted and stored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create a more complex mock skill
        skill_source = tmpdir_path / "complex-skill"
        skill_source.mkdir()
        
        # Create skill files
        (skill_source / "SKILL.md").write_text("# Complex Skill\nWith multiple files.")
        (skill_source / "config.json").write_text('{"settings": {"enabled": true}}')
        (skill_source / "scripts").mkdir()
        (skill_source / "scripts" / "install.sh").write_text("#!/bin/bash\necho 'Installing'")
        
        # Create adapter and mock the opencode skills directory
        adapter = OpenCodeAdapter()
        test_opencode_dir = tmpdir_path / ".opencode" / "skills"
        test_opencode_dir.mkdir(parents=True, exist_ok=True)
        adapter.opencode_skills_dir = test_opencode_dir
        # Mock storage directory to avoid writing to real home directory
        adapter.storage.base_dir = tmpdir_path / ".skillweave" / "packages"
        
        # Install skill
        success = adapter.install_skill("complex-skill", "2.0.0", skill_source)
        assert success
        
        # Check metadata file was created
        link_path = test_opencode_dir / "complex-skill"
        target_dir = link_path.resolve()
        metadata_path = target_dir / ".skillweave-meta.json"
        
        assert metadata_path.exists(), "Metadata file should be created"
        
        # Load and verify metadata
        with open(metadata_path) as f:
            metadata = json.load(f)
        
        assert metadata["name"] == "complex-skill"
        assert metadata["version"] == "2.0.0"
        assert len(metadata["files"]) >= 3  # SKILL.md, config.json, scripts/install.sh (directories not included)
        
        # Verify through adapter method
        adapter_metadata = adapter.get_skill_metadata("complex-skill")
        assert adapter_metadata is not None
        assert adapter_metadata["name"] == "complex-skill"


def test_opencode_adapter_nonexistent_skill():
    """Test handling of non-existent skills."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create adapter and mock the opencode skills directory
        adapter = OpenCodeAdapter()
        test_opencode_dir = tmpdir_path / ".opencode" / "skills"
        test_opencode_dir.mkdir(parents=True, exist_ok=True)
        adapter.opencode_skills_dir = test_opencode_dir
        # Mock storage directory to avoid writing to real home directory
        adapter.storage.base_dir = tmpdir_path / ".skillweave" / "packages"
        
        # Check non-existent skill
        assert not adapter.skill_exists("nonexistent"), "Non-existent skill should not exist"
        
        # Get metadata for non-existent skill
        metadata = adapter.get_skill_metadata("nonexistent")
        assert metadata is None, "Metadata for non-existent skill should be None"
        
        # Remove non-existent skill
        remove_success = adapter.remove_skill("nonexistent")
        assert remove_success, "Removing non-existent skill should return True (no-op)"


def test_opencode_adapter_version_handling():
    """Test that adapter correctly handles different versions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        
        # Create two versions of a skill
        skill_v1 = tmpdir_path / "skill-v1"
        skill_v1.mkdir()
        (skill_v1 / "SKILL.md").write_text("# Skill v1.0.0")
        
        skill_v2 = tmpdir_path / "skill-v2" 
        skill_v2.mkdir()
        (skill_v2 / "SKILL.md").write_text("# Skill v2.0.0")
        
        # Create adapter and mock the opencode skills directory
        adapter = OpenCodeAdapter()
        test_opencode_dir = tmpdir_path / ".opencode" / "skills"
        test_opencode_dir.mkdir(parents=True, exist_ok=True)
        adapter.opencode_skills_dir = test_opencode_dir
        # Mock storage directory to avoid writing to real home directory
        adapter.storage.base_dir = tmpdir_path / ".skillweave" / "packages"
        
        # Install v1.0.0
        success1 = adapter.install_skill("multi-version-skill", "1.0.0", skill_v1)
        assert success1
        
        # Install v2.0.0 - should overwrite symlink (only one version active at a time)
        success2 = adapter.install_skill("multi-version-skill", "2.0.0", skill_v2)
        assert success2
        
        # Only one symlink should exist (latest installed version)
        link_path = test_opencode_dir / "multi-version-skill"
        assert link_path.exists()
        
        # Metadata should be for v2.0.0
        metadata = adapter.get_skill_metadata("multi-version-skill")
        assert metadata is not None
        assert metadata["version"] == "2.0.0"