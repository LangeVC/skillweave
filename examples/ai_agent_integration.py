#!/usr/bin/env python3
"""
Example of how an AI agent would integrate intelligent guidance with a skill.

This shows the full workflow from skill invocation through intelligent detection
to potential onboarding.
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from skillweave.intelligent_detection import (
    integrate_with_skill, 
    SkillIntegrationHelper,
    OnboardingFlowController,
    UserInteraction
)
from skillweave.intelligent_detection.skill_intent_mapper import Skill

class AIAgentUserInteraction(UserInteraction):
    """User interaction implementation for an AI agent."""
    
    def ask_question(self, question: str, options: list = None) -> str:
        """Ask a question and return the answer."""
        # In a real AI agent, this would interact with the user
        # For this example, we'll simulate user responses
        print(f"🤖 AI Agent asking user: {question}")
        if options:
            print(f"   Options: {options}")
        
        # Simulate user providing an answer
        if "idea" in question.lower():
            return "An AI-powered task management tool"
        elif "domain" in question.lower():
            return "saas"
        elif "complexity" in question.lower():
            return "medium"
        else:
            return "test answer"
    
    def show_message(self, message: str) -> None:
        """Show a message to the user."""
        print(f"📢 AI Agent showing message: {message}")
    
    def confirm_action(self, action: str) -> bool:
        """Confirm an action with the user."""
        print(f"❓ AI Agent asking confirmation: {action}")
        # Simulate user confirming
        return True


def ai_agent_skill_invocation(skill_name: str, user_prompt: str, provided_params: dict):
    """
    Simulate how an AI agent would handle skill invocation with intelligent guidance.
    """
    print(f"\n{'='*60}")
    print(f"AI Agent: User requested skill '{skill_name}'")
    print(f"User prompt: '{user_prompt}'")
    print(f"Provided params: {provided_params}")
    print(f"{'='*60}\n")
    
    # Step 1: Use intelligent detection to validate the request
    print("Step 1: Analyzing request with intelligent detection...")
    result = integrate_with_skill(
        skill_name=skill_name,
        user_prompt=user_prompt,
        provided_params=provided_params,
        project_root=os.getcwd()
    )
    
    print(f"   Skill match: {result['skill_match']}")
    print(f"   Confidence: {result['confidence_score']:.0%}")
    print(f"   Action: {result['action']}")
    print(f"   Needs onboarding: {result['needs_onboarding']}")
    
    # Step 2: Handle the action
    action = result['action']
    
    if action == "proceed":
        print("\n✅ Skill validation passed. Proceeding with skill execution...")
        print(f"   Using validated parameters: {result['validated_parameters']}")
        # Execute the actual skill here
        return True
        
    elif action == "gather_parameters":
        print(f"\n🔄 Missing parameters detected: {result['missing_parameters']}")
        print("Gathering missing parameters from user...")
        
        # Create user interaction for gathering parameters
        user_interaction = AIAgentUserInteraction()
        
        # In a real implementation, you would ask for each missing parameter
        # For this example, we'll simulate gathering the missing params
        missing_params = {}
        for param in result['missing_parameters']:
            answer = user_interaction.ask_question(f"What value for '{param}'?")
            missing_params[param] = answer
        
        # Re-run integration with updated parameters
        print("\nRe-running integration with gathered parameters...")
        updated_params = {**provided_params, **missing_params}
        new_result = integrate_with_skill(
            skill_name=skill_name,
            user_prompt=user_prompt,
            provided_params=updated_params
        )
        
        if new_result['action'] == "proceed":
            print("✅ All parameters gathered. Proceeding with skill execution...")
            return True
        else:
            print("⚠️ Still missing parameters after gathering.")
            return False
            
    elif action == "switch_skill":
        print(f"\n🔄 Different skill recommended: {result['recommended_skill']}")
        print(f"Reason: {result['switch_reason']}")
        
        # Ask user if they want to switch
        user_interaction = AIAgentUserInteraction()
        confirm = user_interaction.confirm_action(
            f"Switch to {result['recommended_skill']} instead?"
        )
        
        if confirm:
            print(f"✅ Switching to {result['recommended_skill']}...")
            # Load and execute the recommended skill
            return True
        else:
            print("❌ User declined to switch. Continuing with original skill.")
            # Could proceed with original skill or ask for clarification
            return False
            
    elif action == "onboarding_flow":
        print("\n🎓 Starting guided onboarding flow...")
        
        # Create user interaction
        user_interaction = AIAgentUserInteraction()
        
        # Get detection result from integration result
        detection_result = result.get('detection_result')
        if detection_result:
            # Convert dict back to DetectionResult if needed
            # For simplicity, we'll just create the controller
            try:
                # In a real implementation, you would reconstruct the DetectionResult
                # from the dict. For this example, we'll show the concept.
                controller = OnboardingFlowController(
                    detection_result=detection_result,  # Would need proper deserialization
                    current_skill=Skill(skill_name.upper().replace('-', '_')),
                    current_parameters=provided_params,
                    user_interaction=user_interaction
                )
                print("✅ Onboarding flow controller created.")
                print(f"   State: {controller.state}")
                # Run the onboarding flow
                # controller.run()
            except Exception as e:
                print(f"⚠️ Could not create onboarding controller: {e}")
                # Fall back to basic parameter gathering
                print("Falling back to basic parameter gathering...")
        else:
            print("⚠️ No detection result available for onboarding.")
        
        return False
    
    return False


def main():
    """Run example scenarios."""
    
    print("AI Agent Integration with SkillWeave Intelligent Guidance")
    print("=" * 60)
    
    # Scenario 1: Valid skill invocation with missing parameters
    print("\nScenario 1: Blueprint skill with missing parameters")
    ai_agent_skill_invocation(
        skill_name="skillweave-blueprint",
        user_prompt="Create a blueprint for my project",
        provided_params={}  # Missing required 'idea' parameter
    )
    
    # Scenario 2: Potential skill mismatch
    print("\n" + "=" * 60)
    print("\nScenario 2: Potential skill mismatch")
    ai_agent_skill_invocation(
        skill_name="skillweave-blueprint",
        user_prompt="Generate a prompt sequence for me",
        provided_params={"idea": "test"}  # Wrong skill for the prompt
    )
    
    # Scenario 3: Complete valid request
    print("\n" + "=" * 60)
    print("\nScenario 3: Complete valid request")
    ai_agent_skill_invocation(
        skill_name="skillweave-blueprint",
        user_prompt="Create a blueprint for an AI tool",
        provided_params={"idea": "AI tool", "domain": "saas"}
    )


if __name__ == "__main__":
    main()