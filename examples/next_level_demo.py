#!/usr/bin/env python3
"""
SkillWeave Next Level Demo

This script demonstrates the complete Next Level feature set in action,
simulating how an AI agent would use the features when executing SkillWeave skills.

Features demonstrated:
1. Risk mode configuration (conservative, medium, unicorn)
2. Checklist-based execution with persistent tracking
3. Design-Thinking Lens application
4. Community know-how pattern extraction
5. Modular templates foundation
6. Integration with SkillWeave skills (simulated)

Usage:
    python examples/next_level_demo.py
"""

import os
import tempfile
import shutil
import yaml
from pathlib import Path
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

AUTO_CLEANUP = True  # Set to True to auto-cleanup without prompt
from skillweave.next_level import SkillWeaveNextLevel
from skillweave.persistence import SkillWeaveConfig, RiskMode


def create_test_project() -> Path:
    """Create a temporary directory with .skillweave folder structure."""
    project_dir = Path(tempfile.mkdtemp(prefix="skillweave_demo_"))
    print(f"Created test project at: {project_dir}")
    
    # Create .skillweave directory structure
    skillweave_dir = project_dir / ".skillweave"
    skillweave_dir.mkdir()
    (skillweave_dir / "manifesto").mkdir()
    (skillweave_dir / "handover").mkdir()
    (skillweave_dir / "specs").mkdir()
    (skillweave_dir / "tracking-log").mkdir()
    (skillweave_dir / "templates").mkdir()
    
    # Create config.yaml with all features enabled
    config = SkillWeaveConfig(
        mode=RiskMode.MEDIUM,
        features={
            "checklist_execution": True,
            "design_thinking_lens": True,
            "community_patterns": True,
            "modular_templates": True
        }
    )
    
    config_path = skillweave_dir / "config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config.to_dict(), f)
    print(f"Created config.yaml with mode={config.mode.value}")
    
    # Create a simple design manifesto
    manifesto = {
        "enabled": True,
        "rules": [
            {
                "name": "Value ≥ Noise",
                "description": "Ensure every output provides clear user value",
                "weight": 1.0
            },
            {
                "name": "Scan Before Read",
                "description": "Structure content for quick scanning with clear headings",
                "weight": 0.8
            }
        ]
    }
    
    manifesto_path = skillweave_dir / "manifesto" / "design_rules.yaml"
    with open(manifesto_path, 'w') as f:
        yaml.dump(manifesto, f)
    
    # Create a simple template
    template_content = """# Project PRD Template

## {project_name}

### Problem Statement
{problem_statement}

### Solution Overview
{solution_overview}

### Success Metrics
- {metric_1}
- {metric_2}
"""
    template_path = skillweave_dir / "templates" / "prd_template.md"
    with open(template_path, 'w') as f:
        f.write(template_content)
    
    return project_dir


def simulate_blueprint_skill(next_level: SkillWeaveNextLevel):
    """Simulate how the blueprint skill would use Next Level features."""
    print("\n" + "="*60)
    print("Simulating Blueprint Skill with Next Level Features")
    print("="*60)
    
    # Check mode and adjust behavior
    mode = next_level.get_mode()
    print(f"Active mode: {mode.value}")
    
    if mode == RiskMode.CONSERVATIVE:
        print("Conservative mode: Requiring explicit validation for all assumptions")
    elif mode == RiskMode.UNICORN:
        print("Unicorn mode: Making optimistic assumptions for speed")
    else:
        print("Medium mode: Balanced validation approach")
    
    # Example checklist from user input (simulated)
    checklist_markdown = """
# Project Setup Checklist

## Phase 1: Discovery
- [ ] Conduct stakeholder interviews
- [ ] Define problem statement
- [ ] Identify target users

## Phase 2: Requirements
- [ ] Gather functional requirements
- [ ] Define technical constraints
- [ ] Create user stories

## Phase 3: Documentation
- [ ] Draft PRD document
- [ ] Review with stakeholders
- [ ] Finalize requirements
"""
    
    if next_level.is_checklist_enabled():
        print("\nChecklist feature enabled:")
        checklist = next_level.parse_checklist(checklist_markdown)
        print(f"Found checklist with {len(checklist.items)} items")
        
        # Simulate completing first item
        checklist.mark_in_progress(0)
        checklist.mark_checked(0)
        print("Completed item: 'Conduct stakeholder interviews'")
        
        # Save progress
        next_level.checklist_manager.save_checklist(checklist)
        print("Checklist progress saved to tracking log")
    
    # Simulate PRD content generation
    prd_content = """
# Product Requirements Document

## Executive Summary
A new task management tool for developers.

## Problem Statement
Developers struggle with tracking technical debt.

## Solution Overview
AI-powered task prioritization system.
"""
    
    if next_level.is_design_thinking_enabled():
        print("\nDesign-Thinking Lens enabled:")
        lens = next_level.get_design_thinking_lens()
        feedback = lens.apply_to_content("blueprint", prd_content, "text")
        print(f"Design feedback: {feedback['summary']}")
        print("Applied rules:")
        for rule_feedback in feedback['feedback']:
            if rule_feedback['feedback']:
                print(f"  - {rule_feedback['rule']}: {rule_feedback['feedback']}")
    
    # Simulate using templates
    if next_level.is_modular_templates_enabled():
        print("\nModular Templates enabled:")
        template_manager = next_level.get_template_manager()
        templates = template_manager.list_templates()
        print(f"Available templates: {[t['name'] for t in templates]}")
        
        # Load and use template
        template = template_manager.load_template("prd_template.md")
        if template:
            print(f"Loaded template: {template.name}")
            # In real usage, would fill template with data
    

def simulate_promptchain_execution(next_level: SkillWeaveNextLevel):
    """Simulate how promptchain-execute skill would use Next Level features."""
    print("\n" + "="*60)
    print("Simulating PromptChain Execute Skill with Next Level Features")
    print("="*60)
    
    # Check mode for execution behavior
    mode = next_level.get_mode()
    max_parallel = next_level.get_max_parallel_tasks()
    print(f"Mode: {mode.value}, Max parallel tasks: {max_parallel}")
    
    # Simulate task execution with mode-appropriate safety
    if mode == RiskMode.CONSERVATIVE:
        print("Conservative: Using extra safety checks and validations")
        print("Requiring explicit approval for each parallel task")
    elif mode == RiskMode.UNICORN:
        print("Unicorn: Maximum parallelism with optimistic assumptions")
        print("Skipping redundant confirmations for speed")
    
    # Simulate community pattern extraction
    if next_level.is_community_knowhow_enabled():
        print("\nCommunity Know-How feature enabled:")
        
        # Create some tracking logs (simulate previous work)
        log_content = """
        Project: task-manager
        Date: 2024-01-15
        Action: Created API endpoints
        Issues: Missing error handling
        Resolution: Added comprehensive error handling
        
        Project: task-manager  
        Date: 2024-01-16
        Action: Implemented authentication
        Issues: Security vulnerabilities in token storage
        Resolution: Switched to secure token storage
        """
        
        # Save a sample log
        tracking_log_dir = next_level.persistence.skillweave_dir / "tracking-log"
        tracking_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = tracking_log_dir / "sample_log.md"
        with open(log_path, 'w') as f:
            f.write(log_content)
        
        # Extract patterns
        patterns_result = next_level.extract_community_patterns()
        print(f"Pattern extraction status: {patterns_result.get('status')}")
        if patterns_result.get('status') == 'success':
            stats = patterns_result.get('statistics', {})
            print(f"  Total runs: {stats.get('total_runs')}, Success rate: {stats.get('success_rate')}")
            patterns_list = patterns_result.get('patterns', {})
            common_skills = patterns_list.get('most_common_skills', [])
            print(f"  Most common skills: {[p['skill'] for p in common_skills]}")
        
        # Get cleanup recommendations
        cleanup_result = next_level.analyze_repository_cleanup()
        print(f"Repository cleanup analysis: {cleanup_result.get('status')}")
        findings = cleanup_result.get('findings', [])
        print(f"Found {len(findings)} cleanup opportunities")
        for finding in findings[:3]:  # Show first 3
            print(f"  - {finding['category']}: {finding['recommendation']}")


def simulate_releasechain_skill(next_level: SkillWeaveNextLevel):
    """Simulate how releasechain skill would use Next Level features."""
    print("\n" + "="*60)
    print("Simulating ReleaseChain Skill with Next Level Features")
    print("="*60)
    
    # Demonstrate mode-specific release behavior
    mode = next_level.get_mode()
    
    if mode == RiskMode.CONSERVATIVE:
        print("Conservative release process:")
        print("  - Extensive pre-release testing")
        print("  - Multiple approval gates")
        print("  - Rollback plans for every component")
        print("  - Detailed change documentation")
    elif mode == RiskMode.UNICORN:
        print("Unicorn release process:")
        print("  - Rapid iteration and deployment")
        print("  - Minimal approval gates")
        print("  - Optimistic deployment with fast rollback")
        print("  - Concise change notes")
    else:
        print("Medium release process:")
        print("  - Standard testing and approval")
        print("  - Balanced risk management")
        print("  - Comprehensive but not exhaustive documentation")
    
    # Simulate handover document generation
    print("\nGenerating handover document...")
    handover = next_level.create_handover_document(
        skill_name="demo",
        task_description="API development completed",
        outcomes={"project": "Task Manager API"},
        next_steps="Deploy to production, Monitor performance"
    )
    print(f"Handover document created at: {handover}")
    
    # Demonstrate checklist completion tracking
    if next_level.is_checklist_enabled():
        print("\nFinalizing checklist...")
        # Load existing checklist
        checklist = next_level.checklist_manager.load_checklist("project_setup")
        if checklist:
            # Mark all remaining items complete
            for item in checklist.items:
                if not item.checked:
                    item.mark_checked()
            next_level.checklist_manager.save_checklist(checklist)
            print("All checklist items marked complete!")


def main():
    """Run the complete Next Level demo."""
    print("SkillWeave Next Level Feature Demonstration")
    print("="*60)
    
    # Create test project
    project_dir = create_test_project()
    
    try:
        # Initialize Next Level
        next_level = SkillWeaveNextLevel(str(project_dir))
        print(f"\nInitialized SkillWeaveNextLevel for project: {project_dir}")
        
        # Simulate skill executions
        simulate_blueprint_skill(next_level)
        simulate_promptchain_execution(next_level)
        simulate_releasechain_skill(next_level)
        
        # Show final state
        print("\n" + "="*60)
        print("Demonstration Complete!")
        print("="*60)
        print(f"\nProject structure created at: {project_dir}")
        print("Contents of .skillweave directory:")
        for root, dirs, files in os.walk(project_dir / ".skillweave"):
            level = root.replace(str(project_dir / ".skillweave"), "").count(os.sep)
            indent = " " * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = " " * 2 * (level + 1)
            for file in files:
                print(f"{subindent}{file}")
        
        print("\nNext Level features successfully demonstrated:")
        print("✓ Risk mode configuration and behavior")
        print("✓ Checklist parsing and progress tracking")
        print("✓ Design-Thinking Lens application")
        print("✓ Community pattern extraction")
        print("✓ Modular template loading")
        print("✓ Handover document generation")
        print("✓ Skill-specific feature integration")
        
    finally:
        # Cleanup - comment out to inspect generated files
        if AUTO_CLEANUP:
            shutil.rmtree(project_dir)
            print(f"Cleaned up: {project_dir}")
        else:
            cleanup = input("\nClean up temporary directory? (y/n): ").strip().lower()
            if cleanup == 'y':
                shutil.rmtree(project_dir)
                print(f"Cleaned up: {project_dir}")
            else:
                print(f"Project directory preserved: {project_dir}")
                print("You can examine the generated .skillweave structure.")


if __name__ == "__main__":
    main()