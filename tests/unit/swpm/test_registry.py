#!/usr/bin/env python3
"""
Unit tests for registry.py
"""

import tempfile
from pathlib import Path
from datetime import datetime
from swpm.registry import Registry
from swpm.models import Skill

def test_registry_initialization():
    """Test that registry creates database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "registry.db"
        registry = Registry(db_path)
        assert registry.db_path == db_path
        assert db_path.exists()

def test_add_and_get_skill():
    """Test adding and retrieving a skill."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = Registry(Path(tmpdir) / "registry.db")
        
        skill = Skill(owner="global", 
            name="test-skill",
            version="1.0.0",
            fingerprint="abc123",
            install_path=Path("/tmp/test"),
            installed_at=datetime.now(),
            dependencies=["dep1", "dep2"]
        )
        
        # Add skill
        success = registry.add_skill(skill)
        assert success
        
        # Retrieve skill
        retrieved = registry.get_skill("test-skill", "1.0.0")
        assert retrieved is not None
        assert retrieved.name == skill.name
        assert retrieved.version == skill.version
        assert retrieved.fingerprint == skill.fingerprint
        assert str(retrieved.install_path) == str(skill.install_path)
        
        # Retrieve latest version
        latest = registry.get_skill("test-skill")
        assert latest is not None
        assert latest.version == "1.0.0"

def test_add_duplicate_skill():
    """Test that duplicate skills are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = Registry(Path(tmpdir) / "registry.db")
        
        skill = Skill(owner="global", 
            name="test-skill",
            version="1.0.0",
            fingerprint="abc123",
            install_path=Path("/tmp/test"),
            installed_at=datetime.now(),
            dependencies=[]
        )
        
        assert registry.add_skill(skill)
        assert not registry.add_skill(skill)  # Should fail due to unique constraint

def test_remove_skill():
    """Test skill removal."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = Registry(Path(tmpdir) / "registry.db")
        
        skill = Skill(owner="global", 
            name="test-skill",
            version="1.0.0",
            fingerprint="abc123",
            install_path=Path("/tmp/test"),
            installed_at=datetime.now(),
            dependencies=[]
        )
        registry.add_skill(skill)
        
        # Remove specific version
        removed = registry.remove_skill("test-skill", "1.0.0")
        assert removed
        assert registry.get_skill("test-skill", "1.0.0") is None
        
        # Add multiple versions
        skill2 = Skill(owner="global", 
            name="test-skill",
            version="2.0.0",
            fingerprint="def456",
            install_path=Path("/tmp/test2"),
            installed_at=datetime.now(),
            dependencies=[]
        )
        registry.add_skill(skill2)
        
        # Remove all versions
        removed_all = registry.remove_skill("test-skill")
        assert removed_all
        assert registry.get_skill("test-skill") is None

def test_list_skills():
    """Test listing all skills."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = Registry(Path(tmpdir) / "registry.db")
        
        skills = [
            Skill(owner="global", 
                name=f"skill-{i}",
                version="1.0.0",
                fingerprint=f"fp{i}",
                install_path=Path(f"/tmp/skill{i}"),
                installed_at=datetime.now(),
                dependencies=[]
            )
            for i in range(3)
        ]
        
        for skill in skills:
            registry.add_skill(skill)
        
        listed = registry.list_skills()
        assert len(listed) == 3
        names = {skill.name for skill in listed}
        assert names == {"skill-0", "skill-1", "skill-2"}

def test_search_skills():
    """Test skill search."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = Registry(Path(tmpdir) / "registry.db")
        
        skill1 = Skill(owner="global", 
            name="awesome-skill",
            version="1.0.0",
            fingerprint="abc123",
            install_path=Path("/tmp/awesome"),
            installed_at=datetime.now(),
            dependencies=[]
        )
        skill2 = Skill(owner="global", 
            name="test-tool",
            version="2.0.0",
            fingerprint="xyz789",
            install_path=Path("/tmp/tool"),
            installed_at=datetime.now(),
            dependencies=[]
        )
        registry.add_skill(skill1)
        registry.add_skill(skill2)
        
        # Search by name
        results = registry.search_skills("awesome")
        assert len(results) == 1
        assert results[0].name == "awesome-skill"
        
        # Search by fingerprint
        results = registry.search_skills("xyz")
        assert len(results) == 1
        assert results[0].fingerprint == "xyz789"
        
        # Search with no matches
        results = registry.search_skills("nonexistent")
        assert len(results) == 0

def test_skill_count():
    """Test skill counting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = Registry(Path(tmpdir) / "registry.db")
        assert registry.skill_count() == 0
        
        skill = Skill(owner="global", 
            name="test-skill",
            version="1.0.0",
            fingerprint="abc123",
            install_path=Path("/tmp/test"),
            installed_at=datetime.now(),
            dependencies=[]
        )
        registry.add_skill(skill)
        assert registry.skill_count() == 1