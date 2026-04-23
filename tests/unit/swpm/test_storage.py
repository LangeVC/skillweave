#!/usr/bin/env python3
"""
Unit tests for storage.py
"""

import tempfile
from pathlib import Path
import pytest
from swpm.storage import StorageManager

def test_storage_manager_initialization():
    """Test that StorageManager creates base directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "packages"
        manager = StorageManager(base_dir)
        assert manager.base_dir == base_dir
        assert base_dir.exists()

def test_get_package_dir():
    """Test directory creation for skill versions."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = StorageManager(Path(tmpdir) / "packages")
        skill_dir = manager.get_package_dir("test-skill", "1.0.0")
        assert skill_dir.exists()
        assert skill_dir.name == "1.0.0"
        assert skill_dir.parent.name == "test-skill"

def test_create_symlink():
    """Test symlink creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "packages"
        manager = StorageManager(base_dir)
        
        # Create a dummy skill directory
        skill_dir = manager.get_package_dir("test-skill", "1.0.0")
        (skill_dir / "skill.md").write_text("# Test Skill")
        
        # Create a mock framework directory
        framework_dir = Path(tmpdir) / ".opencode" / "skills"
        framework_dir.mkdir(parents=True)
        
        # Override framework directory path (hack)
        import swpm.storage
        original_home = Path.home
        Path.home = lambda: Path(tmpdir)
        try:
            success = manager.create_symlink("test-skill", "1.0.0", "opencode")
            assert success
            link_path = framework_dir / "test-skill"
            assert link_path.exists()
            assert link_path.is_symlink()
            assert link_path.resolve() == skill_dir.resolve()
        finally:
            Path.home = original_home

def test_remove_symlink():
    """Test symlink removal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir) / "packages"
        manager = StorageManager(base_dir)
        
        skill_dir = manager.get_package_dir("test-skill", "1.0.0")
        (skill_dir / "skill.md").write_text("# Test Skill")
        
        framework_dir = Path(tmpdir) / ".opencode" / "skills"
        framework_dir.mkdir(parents=True)
        
        import swpm.storage
        original_home = Path.home
        Path.home = lambda: Path(tmpdir)
        try:
            # Create symlink
            manager.create_symlink("test-skill", "1.0.0", "opencode")
            link_path = framework_dir / "test-skill"
            assert link_path.exists()
            
            # Remove symlink
            success = manager.remove_symlink("test-skill", "opencode")
            assert success
            assert not link_path.exists()
        finally:
            Path.home = original_home

def test_storage_usage():
    """Test storage usage calculation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = StorageManager(Path(tmpdir) / "packages")
        
        # Create a skill with a file
        skill_dir = manager.get_package_dir("skill1", "1.0.0")
        file_path = skill_dir / "file.txt"
        file_path.write_text("x" * 1024)  # 1KB
        
        total_size, package_count = manager.get_storage_usage()
        assert package_count == 1
        assert total_size >= 1024
        
        # Add another skill
        skill_dir2 = manager.get_package_dir("skill2", "2.0.0")
        (skill_dir2 / "small.txt").write_text("abc")
        
        total_size2, package_count2 = manager.get_storage_usage()
        assert package_count2 == 2
        assert total_size2 >= 1024 + 3