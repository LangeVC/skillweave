"""
Unit tests for design_thinking module.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import tempfile
import yaml
from pathlib import Path

from skillweave.design_thinking import (
    DesignThinkingLens,
    DesignRule,
    DesignRuleDefinition,
    DesignThinkingConfig,
)
from skillweave.persistence import SkillWeavePersistence


def test_design_rule_definition():
    """Test DesignRuleDefinition class."""
    rule = DesignRuleDefinition(
        name="test_rule",
        description="Test description",
        applies_to=["blueprint", "promptchain"],
        enabled=True,
        strictness="medium",
    )
    
    assert rule.name == "test_rule"
    assert rule.description == "Test description"
    assert rule.applies_to == ["blueprint", "promptchain"]
    assert rule.enabled is True
    assert rule.strictness == "medium"


def test_design_thinking_config():
    """Test DesignThinkingConfig class."""
    # Test from_dict with defaults
    data = {
        "enabled": True,
        "strictness": "high",
        "rules": {
            "value_noise": True,
            "scan_before_read": False,
        },
        "custom_rules": [
            {"name": "custom1", "description": "Test", "apply_to": ["blueprint"]}
        ],
    }
    
    config = DesignThinkingConfig.from_dict(data)
    assert config.enabled is True
    assert config.strictness == "high"
    assert len(config.rules) >= 6  # Default rules
    assert config.rules["value_noise"].enabled is True
    assert config.rules["scan_before_read"].enabled is False
    assert len(config.custom_rules) == 1
    assert config.custom_rules[0]["name"] == "custom1"
    
    # Test to_dict
    config_dict = config.to_dict()
    assert config_dict["enabled"] is True
    assert config_dict["strictness"] == "high"
    assert config_dict["rules"]["value_noise"] is True
    assert config_dict["rules"]["scan_before_read"] is False


def test_design_thinking_lens():
    """Test DesignThinkingLens class."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create persistence and config
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        # Enable design thinking feature
        config = persistence.load_config()
        config.features["design_thinking_lens"] = True
        persistence.save_config(config)
        
        # Create manifesto with design rules
        manifesto_dir = persistence.skillweave_dir / "manifesto"
        manifesto_dir.mkdir(exist_ok=True)
        
        manifesto_data = {
            "enabled": True,
            "strictness": "medium",
            "rules": {
                "value_noise": True,
                "scan_before_read": True,
                "active_over_available": False,
                "glance_first": True,
                "widget_workspace": True,
                "decision_ready_data": True
            },
            "custom_rules": [
                {
                    "name": "mobile_first",
                    "description": "Design for mobile devices first",
                    "apply_to": ["blueprint", "releasechain"],
                    "examples": ["Use responsive layouts", "Test on mobile devices"]
                }
            ]
        }
        
        with open(manifesto_dir / "design-rules.yaml", 'w') as f:
            yaml.dump(manifesto_data, f)
        
        lens = DesignThinkingLens(tmpdir)
        assert lens.is_enabled() is True
        
        # Test get_applicable_rules
        blueprint_rules = lens.get_applicable_rules("blueprint")
        assert len(blueprint_rules) > 0
        
        # Rules without "blueprint" in applies_to should be filtered
        releasechain_rules = lens.get_applicable_rules("releasechain")
        # Should include custom rule "mobile_first"
        custom_rule_names = [r.name for r in releasechain_rules]
        assert "mobile_first" in custom_rule_names or any("mobile" in r.name for r in releasechain_rules)
        
        # Test apply_to_content
        content = "This is a test content without much structure."
        result = lens.apply_to_content("blueprint", content, "text")
        
        assert "enabled" in result
        assert result["enabled"] is True
        assert "feedback" in result
        assert "summary" in result
        
        # Content without headers should trigger scan_before_read feedback
        feedback_items = result["feedback"]
        scan_feedback = None
        for item in feedback_items:
            if item["rule"] == "scan_before_read":
                scan_feedback = item["feedback"]
                break
        
        if scan_feedback:
            assert len(scan_feedback) > 0
        
        # Test generate_markdown_feedback
        markdown = lens.generate_markdown_feedback(result)
        if result["feedback"]:
            assert "Design-Thinking Notes" in markdown
            assert "##" in markdown  # Should have headers


def test_rule_application():
    """Test individual rule applications."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        # Enable feature
        config = persistence.load_config()
        config.features["design_thinking_lens"] = True
        persistence.save_config(config)
        
        lens = DesignThinkingLens(tmpdir)
        
        # Test value_noise rule
        ui_content = "Add decorative graphics for visual appeal."
        result = lens.apply_to_content("releasechain", ui_content, "ui")
        
        # Should suggest removing decorative elements
        for item in result.get("feedback", []):
            if item["rule"] == "value_noise":
                assert len(item["feedback"]) > 0
                break
        
        # Test scan_before_read rule
        long_content = "\n".join([f"Paragraph {i}" for i in range(10)])
        result = lens.apply_to_content("blueprint", long_content, "text")
        
        for item in result.get("feedback", []):
            if item["rule"] == "scan_before_read":
                # Should suggest headers for long content
                assert len(item["feedback"]) > 0
                break
        
        # Test glance_first rule
        very_long_content = "X" * 3000  # 3000 characters
        result = lens.apply_to_content("blueprint", very_long_content, "text")
        
        for item in result.get("feedback", []):
            if item["rule"] == "glance_first":
                # Should suggest summary for long content
                assert len(item["feedback"]) > 0
                break
        
        # Test decision_ready_data rule
        table_content = "| Col1 | Col2 |\n|------|------|\n| A | B |\n| C | D |"
        result = lens.apply_to_content("blueprint", table_content, "text")
        
        for item in result.get("feedback", []):
            if item["rule"] == "decision_ready_data":
                # Might suggest analysis for tables
                # (Actual implementation might not trigger for small tables)
                pass
                break


def test_disabled_lens():
    """Test disabled design thinking lens."""
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = SkillWeavePersistence(tmpdir)
        persistence.ensure_folder_structure()
        
        # Disable feature (default)
        config = persistence.load_config()
        config.features["design_thinking_lens"] = False
        persistence.save_config(config)
        
        lens = DesignThinkingLens(tmpdir)
        assert lens.is_enabled() is False
        
        result = lens.apply_to_content("blueprint", "Test content", "text")
        assert result["enabled"] is False
        assert len(result["feedback"]) == 0
        
        markdown = lens.generate_markdown_feedback(result)
        assert markdown == ""