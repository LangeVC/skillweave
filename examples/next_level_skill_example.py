#!/usr/bin/env python3
"""
Example demonstrating how SkillWeave Next Level features can be used
within a skill execution context.

This example simulates how a skill (like skillweave-blueprint) would
integrate Next Level features when executed by opencode/Claude.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from skillweave.next_level import SkillWeaveNextLevel
from skillweave.persistence import RiskMode, is_feature_enabled
from skillweave.checklist import ChecklistParser, ChecklistManager
from skillweave.design_thinking import DesignThinkingLens


def simulate_skill_execution_with_next_level():
    """Simulate a skill execution that uses Next Level features."""
    
    # Create a temporary project directory for demonstration
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)
        
        print("=" * 60)
        print("SKILL EXECUTION WITH NEXT LEVEL FEATURES")
        print("=" * 60)
        print(f"Project root: {project_root}")
        
        # Create config with all features enabled
        config_content = """
mode: medium
features:
  checklist_execution: true
  design_thinking_lens: true
  community_patterns: true
  modular_templates: true
overrides: {}
"""
        config_file = project_root / ".skillweave" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(config_content)
        
        # Initialize Next Level
        print("\n1. Initializing SkillWeaveNextLevel...")
        next_level = SkillWeaveNextLevel(str(project_root))
        
        # Check current mode
        mode = next_level.get_mode()
        print(f"   Current mode: {mode.value}")
        print(f"   Mode guidance: {next_level.get_mode_guidance('blueprint')[:80]}...")
        
        # Simulate skill input with checklist
        markdown_content = """
# Project Blueprint Checklist

## Research Phase
- [x] Define project scope and objectives
- [ ] Conduct market research
- [ ] Identify target users
- [ ] Analyze competitors

## Design Phase  
- [ ] Create user personas
- [ ] Design user journey maps
- [ ] Define MVP features

## Planning Phase
- [ ] Create technical architecture
- [ ] Estimate development timeline
- [ ] Identify risks and mitigations
"""
        
        # Parse checklist if feature enabled
        if is_feature_enabled("checklist_execution", str(project_root)):
            print("\n2. Parsing checklist from markdown content...")
            # Parse checklist
            checklist = ChecklistParser.parse_markdown(markdown_content)
            print(f"   Found checklist with {len(checklist.items)} items")
            
            # Mark first item in progress (update status)
            if checklist.items:
                # Update status directly (in real usage would use checklist manager)
                from skillweave.checklist import ChecklistItemStatus
                checklist.items[1].status = ChecklistItemStatus.IN_PROGRESS
                checklist.items[1].started_at = "2024-01-01T12:00:00"  # Example timestamp
                print(f"   Marked item '{checklist.items[1].text}' as in progress")
            
            # Save checklist state using checklist manager
            checklist_manager = ChecklistManager(str(project_root))
            checklist_manager.save_checklist(checklist)
            print(f"   Saved checklist state to {project_root}/.skillweave/tracking-log/")
        
        # Apply design thinking lens if enabled
        if is_feature_enabled("design_thinking_lens", str(project_root)):
            print("\n3. Applying design thinking lens...")
            
            # Example content to critique
            example_output = """
            Our product will have many features including AI integration, real-time collaboration, 
            advanced analytics, and machine learning capabilities. Users can do everything they need 
            in one place without switching between different tools.
            """
            
            # Use design thinking lens
            design_thinking = DesignThinkingLens(str(project_root))
            analysis_result = design_thinking.apply_to_content(
                "blueprint", example_output, "text"
            )
            
            print(f"   Design analysis result:")
            print(f"   - Enabled: {analysis_result.get('enabled', False)}")
            if analysis_result.get('enabled', False):
                feedback = design_thinking.generate_markdown_feedback(analysis_result)
                print(f"   - Feedback: {feedback[:100]}...")
        
        # Use community know-how if enabled
        if is_feature_enabled("community_patterns", str(project_root)):
            print("\n4. Using community know-how...")
            
            # Analyze tracking logs (would be populated in real usage)
            patterns = next_level.extract_community_patterns()
            print(f"   Extracted patterns: {patterns.get('status', 'unknown')}")
            if patterns.get('status') == 'success':
                print(f"   - Found {len(patterns.get('patterns', []))} patterns")
            
            # Get cleanup recommendations
            recommendations = next_level.analyze_repository_cleanup()
            print(f"   Repository cleanup analysis: {recommendations.get('status', 'unknown')}")
            if recommendations.get('status') == 'success':
                print(f"   - {len(recommendations.get('recommendations', []))} recommendations")
        
        # Use modular templates if enabled
        if is_feature_enabled("modular_templates", str(project_root)):
            print("\n5. Using modular templates...")
            
            # List available templates
            templates = next_level.list_templates()
            print(f"   Found {len(templates)} templates in .skillweave/templates/")
            
            # Example: Load a template if it exists
            template = next_level.load_template("project_blueprint")
            if template:
                print(f"   Loaded template: {template.get('name', 'unnamed')}")
            else:
                print(f"   Template 'project_blueprint' not found (expected for demo)")
        
        # Demonstrate mode-specific behavior
        print("\n6. Demonstrating mode-specific behavior:")
        
        # Check if approval is required for an operation
        operation = "execute_destructive_operation"
        requires_approval = next_level.should_require_approval(operation)
        print(f"   Operation '{operation}' requires approval: {requires_approval}")
        
        # Get parallel task limit based on mode
        max_parallel = next_level.get_max_parallel_tasks()
        print(f"   Maximum parallel tasks (mode-based): {max_parallel}")
        
        # Get safety check requirements
        safety_enabled = next_level.mode_manager.should_perform_safety_check("data_validation")
        print(f"   Safety checks enabled for 'data_validation': {safety_enabled}")
        
        print("\n" + "=" * 60)
        print("SKILL EXECUTION COMPLETE")
        print("=" * 60)
        print("\nNext Level features provide:")
        print("1. Mode-aware execution (conservative/medium/unicorn)")
        print("2. Checklist tracking across sessions")
        print("3. Design thinking feedback for better outputs")
        print("4. Community patterns and cleanup recommendations")
        print("5. Modular templates for consistent documentation")
        print("\nAll state persisted in .skillweave/ directory")


def demonstrate_mode_differences():
    """Demonstrate how different modes affect skill behavior."""
    
    print("\n" + "=" * 60)
    print("MODE DIFFERENCES DEMONSTRATION")
    print("=" * 60)
    
    for mode_enum in [RiskMode.CONSERVATIVE, RiskMode.MEDIUM, RiskMode.UNICORN]:
        print(f"\n--- {mode_enum.value.upper()} MODE ---")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config for this mode
            config_content = f"""
mode: {mode_enum.value}
checklist: true
design_thinking: true
community_knowhow: true
modular_templates: true
"""
            config_file = Path(temp_dir) / ".skillweave" / "config.yaml"
            config_file.parent.mkdir(parents=True, exist_ok=True)
            config_file.write_text(config_content)
            
            next_level = SkillWeaveNextLevel(temp_dir)
            
            # Show mode characteristics
            print(f"Max parallel tasks: {next_level.get_max_parallel_tasks()}")
            
            # Check approval requirements
            operations = [
                "execute_destructive_operation",
                "make_assumption", 
                "skip_validation",
                "use_experimental_feature"
            ]
            
            for op in operations:
                requires = next_level.should_require_approval(op)
                print(f"  {op}: {'Requires approval' if requires else 'Auto-approved'}")
            
            # Check safety checks
            checks = ["data_validation", "user_confirmation", "risk_assessment"]
            for check in checks:
                enabled = next_level.mode_manager.should_perform_safety_check(check)
                print(f"  {check} safety: {'Enabled' if enabled else 'Disabled'}")


def main():
    """Main demonstration function."""
    print("SkillWeave Next Level - Skill Integration Example")
    print("=" * 60)
    
    # Simulate skill execution
    simulate_skill_execution_with_next_level()
    
    # Demonstrate mode differences
    demonstrate_mode_differences()
    
    print("\n" + "=" * 60)
    print("EXAMPLE COMPLETE")
    print("=" * 60)
    print("\nIntegration pattern for skills:")
    print("1. Check for .skillweave/config.yaml in project root")
    print("2. Initialize SkillWeaveNextLevel(project_root)")
    print("3. Use feature checks: is_checklist_enabled(), etc.")
    print("4. Respect mode behavior: get_max_parallel_tasks(), requires_approval_for()")
    print("5. Apply design feedback when generating content")
    print("6. Use checklists for structured task tracking")
    print("7. Persist state via save_checklist(), save_tracking_log()")


if __name__ == "__main__":
    main()