#!/usr/bin/env python3
"""
Example integration of intelligent guidance with a SkillWeave skill.

This example shows how a skill can use the intelligent detection engine
to validate user requests, detect skill mismatches, and trigger onboarding flows.

Usage:
    This example is meant to be adapted by skill authors. The key integration point
    is the `integrate_with_skill()` function which provides a simple interface
    for skill validation and guidance.
"""

import os
import sys

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from skillweave.intelligent_detection import integrate_with_skill, SkillIntegrationHelper, Skill
from dataclasses import asdict


def example_basic_integration():
    """
    Basic example of skill integration.
    
    This shows the minimum integration needed for a skill to use
    intelligent detection.
    """
    print("=== Example 1: Basic Skill Integration ===")
    
    # Simulate a user requesting a skill
    user_prompt = "I need to create a blueprint for an AI-powered ecommerce platform"
    skill_name = "skillweave-blueprint"
    provided_params = {
        "idea": "AI ecommerce platform",
        "domain": "ecommerce"
    }
    
    # Call integration helper
    result = integrate_with_skill(
        skill_name=skill_name,
        user_prompt=user_prompt,
        provided_params=provided_params,
        project_root=os.getcwd()
    )
    
    print(f"Skill invoked: {result['skill_invoked']}")
    print(f"Skill recommended: {result['skill_recommended']}")
    print(f"Skill match: {result['skill_match']}")
    print(f"Confidence: {result['confidence_score']:.0%}")
    print(f"Action: {result['action']}")
    
    # Handle different actions
    if result['action'] == 'proceed':
        print("✓ Skill selection is appropriate. Proceeding with execution.")
        # Execute the skill with validated parameters
        execute_skill(skill_name, result['validated_parameters'])
        
    elif result['action'] == 'gather_parameters':
        print("⚠️ Missing or invalid parameters detected.")
        print(f"Missing: {result['missing_parameters']}")
        print(f"Invalid: {result['invalid_parameters']}")
        # Prompt user for missing parameters
        gathered_params = gather_missing_parameters(result)
        # Re-validate with gathered parameters
        new_result = integrate_with_skill(
            skill_name=skill_name,
            user_prompt=user_prompt,
            provided_params={**provided_params, **gathered_params}
        )
        
    elif result['action'] == 'switch_skill':
        print(f"🔄 Consider switching to {result['recommended_skill']}")
        print(f"Reason: {result['switch_reason']}")
        # Ask user if they want to switch
        if confirm_skill_switch(result['recommended_skill']):
            # Switch to recommended skill
            print(f"Switching to {result['recommended_skill']}")
            # Execute the recommended skill instead
            execute_skill(result['recommended_skill'], result['validated_parameters'])
        else:
            # Continue with original skill
            print("Continuing with original skill as requested.")
            execute_skill(skill_name, result['validated_parameters'])
            
    elif result['action'] == 'onboarding_flow':
        print("🎯 Onboarding flow triggered.")
        print("This would start a guided onboarding process to:")
        print("1. Validate skill choice")
        print("2. Gather missing parameters")
        print("3. Provide context-specific guidance")
        # In a real implementation, you would call the onboarding controller
        # For this example, we'll show what information is available
        print(f"\nGuidance available: {result['guidance']}")
        print(f"Missing parameters: {result['missing_parameters']}")
        print(f"Parameter prompts: {result['parameter_prompts']}")
    
    print()


def example_advanced_integration():
    """
    Advanced example using the SkillIntegrationHelper class directly.
    
    This provides more control over the integration process and allows
    for custom user interaction handling.
    """
    print("\n=== Example 2: Advanced Integration ===")
    
    # Initialize the helper
    helper = SkillIntegrationHelper(project_root=os.getcwd())
    
    # Convert skill name to Skill enum
    try:
        skill = Skill("skillweave-promptchain-generate")
    except ValueError:
        print("Invalid skill name")
        return
    
    # Simulate user request
    user_prompt = "Generate a promptchain for validating blueprints"
    provided_params = {"skill": "skillweave-blueprint"}
    
    # Get intelligent guidance
    guidance = helper.get_skill_guidance(user_prompt, skill)
    
    print(f"Prompt analysis: {guidance['prompt_analysis'].get('intent', 'unknown')}")
    print(f"Skill match: {guidance['skill_match']}")
    print(f"Confidence: {guidance['confidence_score']:.0%}")
    
    if guidance['recommendations']:
        print("Recommendations:")
        for rec in guidance['recommendations']:
            print(f"  - {rec['message']} (confidence: {rec['confidence']:.0%})")
    
    # Validate parameters
    from skillweave.intelligent_detection.parameter_validator import ParameterValidator
    validator = ParameterValidator(strict_mode=False)
    validation_result = validator.validate(skill, provided_params)
    
    print(f"\nParameter validation:")
    print(f"  Valid: {validation_result.is_valid}")
    print(f"  Missing required: {validation_result.missing_required}")
    print(f"  Completeness score: {validation_result.completeness_score:.0%}")
    
    # Determine next steps
    if guidance['skill_match'] and validation_result.is_valid and not validation_result.missing_required:
        print("\n✓ All checks passed. Ready to execute skill.")
    else:
        print("\n⚠️ Issues detected. Consider:")
        if not guidance['skill_match']:
            print("  - Reviewing skill choice")
        if not validation_result.is_valid or validation_result.missing_required:
            print("  - Providing missing parameters")
    
    print()


def example_onboarding_flow():
    """
    Example of triggering onboarding flow for skill mismatch.
    
    This shows how to handle cases where the user's request might
    be better served by a different skill.
    """
    print("\n=== Example 3: Onboarding Flow ===")
    
    # Simulate skill mismatch scenario
    user_prompt = "Validate and execute my prompt sequence"
    skill_name = "skillweave-blueprint"  # User invoked blueprint skill
    provided_params = {}
    
    result = integrate_with_skill(
        skill_name=skill_name,
        user_prompt=user_prompt,
        provided_params=provided_params
    )
    
    print(f"User invoked: {skill_name}")
    print(f"Detected intent: {result['parameter_validation'].get('intent', 'unknown')}")
    print(f"Recommended skill: {result['recommended_skill']}")
    print(f"Confidence: {result['confidence_score']:.0%}")
    
    if result['action'] == 'switch_skill':
        print("\nSkill mismatch detected. Onboarding flow would:")
        print("1. Explain why a different skill might be better")
        print("2. Show what each skill does")
        print("3. Ask user to confirm skill choice")
        print("4. Gather any missing parameters")
        print("5. Transition to the selected skill")
        
        # Example of what an onboarding flow might look like
        print("\n--- Onboarding Dialog ---")
        print(f"AI: I notice you're trying to '{user_prompt}'.")
        print(f"    The '{result['recommended_skill']}' skill might be more appropriate.")
        print(f"    Reason: {result['switch_reason']}")
        print("    Would you like to:")
        print(f"    1. Use '{result['recommended_skill']}' (recommended)")
        print(f"    2. Continue with '{skill_name}'")
        print("    3. Get more information about both skills")
        print("---")
    
    print()


def execute_skill(skill_name, parameters):
    """Example skill execution function."""
    print(f"\n[Executing {skill_name} with parameters: {parameters}]")
    # In a real implementation, this would call the actual skill
    print("Skill execution complete.")


def gather_missing_parameters(integration_result):
    """Example function to gather missing parameters."""
    print("\n[Gathering missing parameters]")
    # In a real implementation, this would prompt the user
    # For this example, return empty dict
    return {}


def confirm_skill_skill(recommended_skill):
    """Example function to confirm skill switch."""
    # In a real implementation, this would ask the user
    # For this example, return True
    return True


def main():
    """Run all examples."""
    print("SkillWeave Intelligent Guidance Integration Examples")
    print("=" * 60)
    
    example_basic_integration()
    example_advanced_integration()
    example_onboarding_flow()
    
    print("\n" + "=" * 60)
    print("Summary:")
    print("- Use `integrate_with_skill()` for simple integration")
    print("- Use `SkillIntegrationHelper` for advanced control")
    print("- Handle different 'action' results appropriately")
    print("- Follow guidance recommendations for better user experience")
    print("- Trigger onboarding flows for complex mismatches")


if __name__ == "__main__":
    main()