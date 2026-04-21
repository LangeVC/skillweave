"""
Unit tests for next_level module.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tempfile
import shutil
from pathlib import Path
import json
import yaml

from skillweave.next_level import SkillWeaveNextLevel
from skillweave.persistence import SkillWeaveConfig, RiskMode, ensure_skillweave_folder, SkillWeavePersistence
from skillweave.checklist import Checklist, ChecklistItem


def test_next_level_initialization():
    """Test SkillWeaveNextLevel initialization."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        # Check attributes exist
        assert next_level.project_root == Path(tmpdir).resolve()
        assert hasattr(next_level, 'persistence')
        assert hasattr(next_level, 'config')
        assert hasattr(next_level, 'mode_manager')
        assert hasattr(next_level, 'checklist_manager')
        assert hasattr(next_level, 'design_thinking')
        
        # Check default mode is MEDIUM
        assert next_level.get_mode() == RiskMode.MEDIUM


def test_get_mode_and_guidance():
    """Test get_mode and get_mode_guidance methods."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        mode = next_level.get_mode()
        assert mode in [RiskMode.CONSERVATIVE, RiskMode.MEDIUM, RiskMode.UNICORN]
        
        guidance = next_level.get_mode_guidance("blueprint")
        assert "Mode:" in guidance
        assert len(guidance) > 0
        
        # Test with different skill names
        for skill in ["blueprint", "promptchain", "releasechain"]:
            guidance = next_level.get_mode_guidance(skill)
            assert skill.capitalize() in guidance or "PromptChain" in guidance or "ReleaseChain" in guidance


def test_should_require_approval():
    """Test should_require_approval method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        # Default is MEDIUM mode - doesn't require approval (only confirmation)
        assert next_level.should_require_approval("destructive") is False
        assert next_level.should_require_approval("execution") is False


def test_get_max_parallel_tasks():
    """Test get_max_parallel_tasks method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        # Default MEDIUM mode has 3 max parallel tasks
        assert next_level.get_max_parallel_tasks() == 3


def test_process_with_checklist():
    """Test process_with_checklist method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        # Enable checklist feature
        persistence = next_level.persistence
        config = SkillWeaveConfig(
            mode=RiskMode.MEDIUM,
            features={"checklist_execution": True}
        )
        persistence.save_config(config)
        
        # Create content with checklist
        content = """# Project Setup
        
        ## Tasks
        - [ ] Install dependencies
        - [ ] Configure environment
        - [ ] Run tests
        
        ## Notes
        Some notes here.
        """
        
        # Mock executor function
        execution_order = []
        def mock_executor(item_text, item_id):
            execution_order.append(item_text)
            return True  # Always succeed
        
        # Process checklist
        updated_content, completed = next_level.process_with_checklist(
            content, mock_executor, "Checklist Progress"
        )
        
        # Check results
        assert "Checklist Progress" in updated_content
        assert "Install dependencies" in updated_content
        assert len(execution_order) == 3
        assert "Install dependencies" in execution_order[0]
        
        # When checklist is already completed
        content_completed = """# Project Setup
        
        ## Tasks
        - [x] Install dependencies
        - [x] Configure environment
        - [x] Run tests
        """
        
        execution_order2 = []
        updated_content2, completed2 = next_level.process_with_checklist(
            content_completed, lambda t, i: execution_order2.append(t), "Checklist"
        )
        
        assert completed2 is True
        assert len(execution_order2) == 0  # No execution for completed items


def test_process_with_checklist_disabled():
    """Test process_with_checklist when feature is disabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        # Checklist feature is disabled by default
        content = """# Project
        - [ ] Task 1
        - [ ] Task 2
        """
        
        executions = []
        def executor(text, idx):
            executions.append(text)
            return True
        
        updated_content, completed = next_level.process_with_checklist(
            content, executor, "Tasks"
        )
        
        # Should return original content and False when disabled
        # Use strip() for comparison to handle potential whitespace differences
        assert updated_content.strip() == content.strip()
        assert completed is False
        assert len(executions) == 0


def test_apply_design_thinking():
    """Test apply_design_thinking method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        # Enable design thinking feature
        persistence = next_level.persistence
        config = SkillWeaveConfig(
            mode=RiskMode.MEDIUM,
            features={"design_thinking_lens": True}
        )
        persistence.save_config(config)
        
        content = """# My Feature
        
        This is a description of my feature.
        It has multiple paragraphs.
        
        ## Section
        Some content here.
        """
        
        content_with_feedback, analysis_result = next_level.apply_design_thinking(
            "blueprint", content, "text"
        )
        
        # Check results
        assert content_with_feedback.startswith("# My Feature")
        assert isinstance(analysis_result, dict)
        
        # Feature disabled
        config.features["design_thinking_lens"] = False
        persistence.save_config(config)
        
        content_with_feedback2, analysis_result2 = next_level.apply_design_thinking(
            "blueprint", content, "text"
        )
        
        assert content_with_feedback2 == content
        assert analysis_result2.get("enabled", False) is False


def test_get_project_status():
    """Test get_project_status method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        status = next_level.get_project_status()
        
        # Check structure
        assert "mode" in status
        assert "features_enabled" in status
        assert "tracking_logs_count" in status
        assert "recent_logs" in status
        assert "checklist_progress" in status
        assert "checklist_completed" in status
        assert "project_root" in status
        
        # Check values
        assert status["mode"] == "medium"
        assert isinstance(status["features_enabled"], dict)
        assert "checklist_execution" in status["features_enabled"]
        assert "design_thinking_lens" in status["features_enabled"]
        assert "community_patterns" in status["features_enabled"]
        assert isinstance(status["tracking_logs_count"], int)
        assert isinstance(status["recent_logs"], list)


def test_create_handover_document():
    """Test create_handover_document method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        outcomes = {
            "completed_tasks": ["task1", "task2"],
            "metrics": {"coverage": "85%", "tests_passed": 42},
            "status": "success"
        }
        
        handover_path = next_level.create_handover_document(
            skill_name="blueprint",
            task_description="Create project architecture",
            outcomes=outcomes,
            next_steps="Implement core modules"
        )
        
        # Check file was created
        assert handover_path.exists()
        assert handover_path.suffix == ".md"
        
        # Check content
        content = handover_path.read_text()
        assert "# Handover Document: blueprint" in content
        assert "Create project architecture" in content
        assert "completed_tasks" in content
        assert "coverage" in content
        assert "Implement core modules" in content
        assert "**Mode**: medium" in content
        
        # Check it's in handover directory
        assert ".skillweave/handover/" in str(handover_path)


def test_update_project_manifesto():
    """Test update_project_manifesto method."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        # Initial update
        updates1 = {
            "project_constraints": ["No external APIs", "Must use Python 3.9+"],
            "design_principles": ["Mobile-first", "Accessibility by default"],
            "custom_notes": {"priority": "high", "owner": "team-alpha"}
        }
        
        manifesto_path = next_level.update_project_manifesto(updates1)
        assert manifesto_path.exists()
        
        # Load and check content
        with open(manifesto_path, 'r') as f:
            manifesto = yaml.safe_load(f)
        
        assert "project_constraints" in manifesto
        assert "design_principles" in manifesto
        assert "custom_notes" in manifesto
        assert len(manifesto["project_constraints"]) == 2
        assert "Mobile-first" in manifesto["design_principles"]
        assert manifesto["custom_notes"]["priority"] == "high"
        
        # Update existing manifesto
        updates2 = {
            "project_constraints": ["Add new constraint"],
            "custom_notes": {"status": "in-progress"}
        }
        
        manifesto_path2 = next_level.update_project_manifesto(updates2)
        
        # Load updated manifesto
        with open(manifesto_path2, 'r') as f:
            manifesto2 = yaml.safe_load(f)
        
        # Check updates (lists should be extended)
        assert len(manifesto2["project_constraints"]) == 3  # 2 original + 1 new
        assert "No external APIs" in manifesto2["project_constraints"]
        assert "Add new constraint" in manifesto2["project_constraints"]
        
        # dict values should be updated
        assert manifesto2["custom_notes"]["priority"] == "high"  # Original
        assert manifesto2["custom_notes"]["status"] == "in-progress"  # New
        assert manifesto2["custom_notes"]["owner"] == "team-alpha"  # Original


def test_integration_with_tracking_logs():
    """Test integration with tracking logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        next_level = SkillWeaveNextLevel(tmpdir)
        
        # Save a tracking log
        persistence = next_level.persistence
        log_data = {
            "session_id": "test-session-001",
            "timestamp": "2025-01-01T12:00:00",
            "action": "test_action",
            "details": {"steps": 5, "status": "success"}
        }
        
        log_path = persistence.save_tracking_log("test-session-001", log_data)
        assert log_path.exists()
        
        # Check project status includes logs
        status = next_level.get_project_status()
        assert status["tracking_logs_count"] >= 1
        
        # Recent logs should include our test log
        recent_logs = status["recent_logs"]
        assert len(recent_logs) >= 1
        found = False
        for log in recent_logs:
            if log.get("session_id") == "test-session-001":
                found = True
                break
        assert found


def test_different_modes_integration():
    """Test integration across different modes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for mode in [RiskMode.CONSERVATIVE, RiskMode.MEDIUM, RiskMode.UNICORN]:
            # Set mode in config using persistence directly
            persistence = SkillWeavePersistence(tmpdir)
            persistence.ensure_folder_structure()  # Ensure folder exists before saving
            config = SkillWeaveConfig(mode=mode)
            persistence.save_config(config)
            
            # Create new next_level instance
            next_level = SkillWeaveNextLevel(tmpdir)
            
            # Verify mode is set correctly
            assert next_level.get_mode() == mode
            
            # Test mode-specific methods
            max_tasks = next_level.get_max_parallel_tasks()
            if mode == RiskMode.CONSERVATIVE:
                assert max_tasks == 1
            elif mode == RiskMode.MEDIUM:
                assert max_tasks == 3
            elif mode == RiskMode.UNICORN:
                assert max_tasks == 10


if __name__ == "__main__":
    # Run tests
    test_next_level_initialization()
    test_get_mode_and_guidance()
    test_should_require_approval()
    test_get_max_parallel_tasks()
    test_process_with_checklist()
    test_process_with_checklist_disabled()
    test_apply_design_thinking()
    test_get_project_status()
    test_create_handover_document()
    test_update_project_manifesto()
    test_integration_with_tracking_logs()
    test_different_modes_integration()
    print("All tests passed!")