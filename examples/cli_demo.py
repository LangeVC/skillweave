#!/usr/bin/env python3
"""
Command-line interface demonstration for SkillWeave Next Level features.

This script shows how Next Level features can be accessed from a CLI,
which could be used by skills running in opencode/Claude.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Optional

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from skillweave.next_level import SkillWeaveNextLevel
from skillweave.persistence import ensure_skillweave_folder, is_feature_enabled, RiskMode, SkillWeaveConfig
from skillweave.checklist import ChecklistParser, ChecklistManager
from skillweave.design_thinking import DesignThinkingLens
from skillweave.mode_manager import ModeManager


def init_project(project_root: str, mode: str = "medium"):
    """Initialize a project with Next Level features."""
    print(f"Initializing SkillWeave Next Level in: {project_root}")
    
    # Ensure folder structure exists
    persistence = ensure_skillweave_folder(project_root)
    
    # Create config with default features
    config = SkillWeaveConfig.from_dict({
        "mode": mode,
        "features": {
            "checklist_execution": True,
            "design_thinking_lens": True,
            "community_patterns": True,
            "modular_templates": True,
        },
        "overrides": {}
    })
    
    persistence.save_config(config)
    print(f"Created config with mode: {mode}")
    print(f"Features enabled: {', '.join(config.features.keys())}")
    
    return SkillWeaveNextLevel(project_root)


def demo_checklist(next_level: SkillWeaveNextLevel, markdown_file: Optional[str] = None):
    """Demonstrate checklist feature."""
    if not is_feature_enabled("checklist_execution", next_level.project_root):
        print("Checklist feature not enabled. Enable in config.yaml")
        return
    
    if markdown_file:
        with open(markdown_file, 'r') as f:
            content = f.read()
    else:
        content = """
# Sample Checklist
- [ ] First task
- [x] Completed task  
- [ ] Another task
"""
    
    print("\n=== Checklist Demo ===")
    
    # Parse checklist
    checklist = ChecklistParser.parse_markdown(content)
    print(f"Parsed checklist with {len(checklist.items)} items")
    
    # Save checklist
    checklist_manager = ChecklistManager(str(next_level.project_root))
    checklist_hash = checklist_manager.save_checklist(checklist)
    print(f"Checklist saved to tracking log with hash: {checklist_hash}")
    
    # Display checklist items
    print(f"Checklist items:")
    for i, item in enumerate(checklist.items):
        status = "✓" if item.status.value == "checked" else "◻"
        print(f"  {i+1}. [{status}] {item.text}")


def demo_design_thinking(next_level: SkillWeaveNextLevel, content: str):
    """Demonstrate design thinking lens."""
    if not is_feature_enabled("design_thinking_lens", next_level.project_root):
        print("Design thinking feature not enabled. Enable in config.yaml")
        return
    
    print("\n=== Design Thinking Demo ===")
    
    design_thinking = DesignThinkingLens(str(next_level.project_root))
    analysis_result = design_thinking.apply_to_content(
        "blueprint", content, "text"
    )
    
    print(f"Analysis enabled: {analysis_result.get('enabled', False)}")
    
    if analysis_result.get('enabled', False):
        feedback = design_thinking.generate_markdown_feedback(analysis_result)
        print(f"\nFeedback:\n{feedback}")


def demo_mode_features(next_level: SkillWeaveNextLevel):
    """Demonstrate mode-specific features."""
    print("\n=== Mode Features Demo ===")
    
    mode = next_level.get_mode()
    print(f"Current mode: {mode.value}")
    print(f"Max parallel tasks: {next_level.get_max_parallel_tasks()}")
    
    # Check various operations
    operations = [
        ("destructive_operation", "execute_destructive_operation"),
        ("make_assumption", "make_assumption"),
        ("skip_validation", "skip_validation"),
    ]
    
    print("\nOperation approval requirements:")
    for name, op_type in operations:
        requires = next_level.should_require_approval(op_type)
        print(f"  {name}: {'Requires approval' if requires else 'Auto-approved'}")


def demo_community_patterns(next_level: SkillWeaveNextLevel):
    """Demonstrate community patterns."""
    if not is_feature_enabled("community_patterns", next_level.project_root):
        print("Community patterns feature not enabled. Enable in config.yaml")
        return
    
    print("\n=== Community Patterns Demo ===")
    
    patterns = next_level.extract_community_patterns()
    print(f"Pattern extraction status: {patterns.get('status', 'unknown')}")
    
    if patterns.get('status') == 'success':
        pattern_list = patterns.get('patterns', [])
        print(f"Found {len(pattern_list)} patterns")
        for pattern in pattern_list[:3]:  # Show first 3
            print(f"  - {pattern.get('type', 'unknown')}: {pattern.get('description', '')[:80]}...")
    
    cleanup = next_level.analyze_repository_cleanup()
    print(f"\nRepository cleanup status: {cleanup.get('status', 'unknown')}")
    
    if cleanup.get('status') == 'success':
        recommendations = cleanup.get('recommendations', [])
        print(f"Found {len(recommendations)} recommendations")
        for rec in recommendations[:3]:  # Show first 3
            print(f"  - {rec.get('type', 'unknown')}: {rec.get('description', '')[:80]}...")


def main():
    parser = argparse.ArgumentParser(description="SkillWeave Next Level CLI Demo")
    parser.add_argument("--project", default=".", help="Project root directory")
    parser.add_argument("--mode", choices=["conservative", "medium", "unicorn"], 
                       default="medium", help="Risk mode")
    parser.add_argument("--checklist-file", help="Markdown file with checklist")
    parser.add_argument("--design-content", help="Content for design thinking analysis")
    
    args = parser.parse_args()
    
    project_root = os.path.abspath(args.project)
    
    # Initialize or load Next Level
    next_level = init_project(project_root, args.mode)
    
    # Run demonstrations
    demo_checklist(next_level, args.checklist_file)
    
    design_content = args.design_content or """
    Our product needs to have all the features users want.
    We should implement everything at once to make users happy.
    The interface should show all options at the same time.
    """
    demo_design_thinking(next_level, design_content)
    
    demo_mode_features(next_level)
    demo_community_patterns(next_level)
    
    print("\n=== Summary ===")
    print(f"Project: {project_root}")
    print(f"Next Level features initialized in: {project_root}/.skillweave/")
    print(f"Config file: {project_root}/.skillweave/config.yaml")
    print(f"Tracking logs: {project_root}/.skillweave/tracking-log/")
    print(f"\nTo use in skills:")
    print("1. Check for .skillweave/config.yaml in project root")
    print("2. Initialize SkillWeaveNextLevel(project_root)")
    print("3. Check feature flags with is_feature_enabled()")
    print("4. Use mode-appropriate behavior")


if __name__ == "__main__":
    main()