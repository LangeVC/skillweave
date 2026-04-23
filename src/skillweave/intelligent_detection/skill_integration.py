"""
Skill Integration Helper for SkillWeave v0.5.5.

Provides a unified interface for skills to use the intelligent detection engine
and onboarding flow system.
"""

from typing import Dict, Any, Optional, Tuple, List
import json
from dataclasses import asdict

from .skill_detection_orchestrator import SkillDetectionOrchestrator
from .onboarding_flow_controller import OnboardingFlowController, OnboardingResult, UserInteraction
from .parameter_validator import ParameterValidator, ParameterValidationResult
from .skill_intent_mapper import Skill, SkillMappingResult
from .prompt_analyzer import PromptAnalysisResult


class SkillIntegrationHelper:
    """
    Helper class for skills to integrate intelligent detection and onboarding.
    
    Provides a simple API for skills to:
    1. Validate user input and detect skill mismatches
    2. Trigger onboarding flow for missing parameters
    3. Handle skill switching recommendations
    4. Provide intelligent guidance based on user context
    """
    
    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize the skill integration helper.
        
        Args:
            project_root: Optional project root directory for configuration
        """
        self.project_root = project_root
        self.orchestrator = SkillDetectionOrchestrator(project_root)
        self.onboarding_controller = None  # Will be initialized when needed
        
    def validate_skill_invocation(
        self,
        user_prompt: str,
        invoked_skill: Skill,
        provided_params: Dict[str, Any],
        user_interaction: Optional[UserInteraction] = None
    ) -> Tuple[bool, Optional[OnboardingResult], Optional[str]]:
        """
        Validate a skill invocation and trigger onboarding if needed.
        
        Args:
            user_prompt: The original user prompt or request
            invoked_skill: The skill that was invoked
            provided_params: Parameters provided by the user
            user_interaction: Optional user interaction interface for onboarding
        
        Returns:
            Tuple of (is_valid, onboarding_result, guidance_message)
            - is_valid: True if the skill invocation is valid and can proceed
            - onboarding_result: OnboardingResult if onboarding was triggered
            - guidance_message: Guidance message for the AI agent
        """
        # Use orchestrator to detect skill and validate parameters
        detection_result = self.orchestrator.detect(
            prompt=user_prompt,
            current_skill=invoked_skill,
            current_parameters=provided_params
        )
        
        # Check skill mismatch
        skill_mismatch = detection_result.skill_mapping.primary_skill != invoked_skill
        skill_confidence = detection_result.confidence_score
        
        # Determine if onboarding is needed
        needs_onboarding = (
            skill_mismatch and skill_confidence >= 0.7  # High confidence mismatch
            or not detection_result.parameter_validation.is_valid  # Invalid parameters
            or detection_result.parameter_validation.missing_required  # Missing required params
        )
        
        guidance_parts = []
        
        # Handle skill mismatch
        if skill_mismatch and skill_confidence >= 0.7:
            guidance_parts.append(
                f"**Skill Mismatch Detected**: Based on your request, "
                f"`{detection_result.skill_mapping.primary_skill.value}` might be more appropriate "
                f"than `{invoked_skill.value}` (confidence: {skill_confidence:.0%})."
            )
            
            if detection_result.skill_mapping.alternative_skills:
                alt_skills = [s.value for s in detection_result.skill_mapping.alternative_skills]
                guidance_parts.append(
                    f"Alternative skills: {', '.join(alt_skills)}"
                )
        
        # Handle parameter validation issues
        if not detection_result.parameter_validation.is_valid:
            if detection_result.parameter_validation.missing_required:
                missing = detection_result.parameter_validation.missing_required
                guidance_parts.append(
                    f"**Missing Required Parameters**: {', '.join(missing)}"
                )
            
            # Collect invalid parameters from findings
            invalid_params = []
            for finding in detection_result.parameter_validation.findings:
                if finding.severity == "error":
                    invalid_params.append(finding.parameter)
            if invalid_params:
                guidance_parts.append(
                    f"**Invalid Parameters**: {', '.join(invalid_params)}"
                )
        
        # Trigger onboarding if needed and user interaction is available
        onboarding_result = None
        if needs_onboarding and user_interaction:
            # Initialize onboarding controller if not already
            if self.onboarding_controller is None:
                self.onboarding_controller = OnboardingFlowController()
                
            # Prepare onboarding context
            onboarding_context = {
                "user_prompt": user_prompt,
                "invoked_skill": invoked_skill.value,
                "recommended_skill": detection_result.skill_mapping.primary_skill.value if skill_mismatch else None,
                "provided_params": provided_params,
                "validation_result": asdict(detection_result.parameter_validation),
                "skill_confidence": skill_confidence,
            }
            
            # Start onboarding flow
            onboarding_result = self.onboarding_controller.start_onboarding(
                user_interaction, onboarding_context
            )
            
            # If onboarding was completed successfully
            if onboarding_result and onboarding_result.state == "completed":
                # Update guidance with onboarding results
                if onboarding_result.skill_switch_decision:
                    guidance_parts.append(
                        f"**Skill Switch**: User confirmed switching to "
                        f"`{onboarding_result.selected_skill}`"
                    )
                
                if onboarding_result.collected_parameters:
                    guidance_parts.append(
                        f"**Parameters Collected**: "
                        f"{len(onboarding_result.collected_parameters)} parameters "
                        f"gathered during onboarding"
                    )
        
        # Determine if the skill invocation is valid
        is_valid = (
            not needs_onboarding  # No critical issues requiring onboarding
            or (onboarding_result and onboarding_result.state == "completed")  # Onboarding completed
        )
        
        guidance_message = "\n\n".join(guidance_parts) if guidance_parts else None
        
        return is_valid, onboarding_result, guidance_message
    
    def _dataclass_to_dict(self, obj):
        """Convert dataclass object to dictionary, handling nested structures."""
        try:
            return asdict(obj)
        except (TypeError, AttributeError):
            # Fallback for non-dataclass objects
            if hasattr(obj, '__dict__'):
                return obj.__dict__.copy()
            elif hasattr(obj, 'to_dict'):
                return obj.to_dict()
            else:
                # Try to extract public attributes
                return {k: getattr(obj, k) for k in dir(obj) if not k.startswith('_') and not callable(getattr(obj, k))}
    
    def get_skill_guidance(
        self,
        user_prompt: str,
        current_skill: Skill
    ) -> Dict[str, Any]:
        """
        Get intelligent guidance for skill execution.
        
        Args:
            user_prompt: The user's prompt or request
            current_skill: The skill being executed
        
        Returns:
            Dictionary with guidance information
        """
        # Use orchestrator's detect method
        detection_result = self.orchestrator.detect(
            prompt=user_prompt,
            current_skill=current_skill
        )
        
        # Convert dataclasses to dictionaries
        prompt_analysis_dict = {}
        skill_mapping_dict = {}
        skill_match = True
        confidence_score = 1.0
        
        if hasattr(detection_result, 'prompt_analysis') and detection_result.prompt_analysis:
            prompt_analysis_dict = self._dataclass_to_dict(detection_result.prompt_analysis)
        
        if hasattr(detection_result, 'skill_mapping') and detection_result.skill_mapping:
            skill_mapping_dict = self._dataclass_to_dict(detection_result.skill_mapping)
            # Check skill match - note: skill_mapping has primary_skill, not recommended_skill
            if hasattr(detection_result.skill_mapping, 'primary_skill'):
                skill_match = detection_result.skill_mapping.primary_skill == current_skill
            elif hasattr(detection_result.skill_mapping, 'recommended_skill'):
                skill_match = detection_result.skill_mapping.recommended_skill == current_skill
        
        if hasattr(detection_result, 'confidence_score'):
            confidence_score = detection_result.confidence_score
        
        guidance = {
            "prompt_analysis": prompt_analysis_dict,
            "skill_mapping": skill_mapping_dict,
            "skill_match": skill_match,
            "confidence_score": confidence_score,
            "recommendations": [],
            "detection_result": asdict(detection_result)
        }
        
        # Add recommendations based on analysis
        if (hasattr(detection_result, 'skill_mapping') and detection_result.skill_mapping):
            skill_mapping = detection_result.skill_mapping
            # Determine primary/recommended skill
            primary_skill = getattr(skill_mapping, 'primary_skill', None) or getattr(skill_mapping, 'recommended_skill', None)
            if primary_skill and primary_skill != current_skill:
                guidance["recommendations"].append({
                    "type": "skill_switch",
                    "message": f"Consider using {primary_skill.value} instead",
                    "confidence": confidence_score
                })
        
        # Add parameter suggestions
        if (hasattr(detection_result, 'prompt_analysis') and 
            hasattr(detection_result.prompt_analysis, 'extracted_parameters') and
            detection_result.prompt_analysis.extracted_parameters):
            guidance["parameter_suggestions"] = detection_result.prompt_analysis.extracted_parameters
        
        return guidance
    
    def create_user_interaction_adapter(self) -> UserInteraction:
        """
        Create a default user interaction adapter.
        
        This adapter can be extended by skills to provide custom
        user interaction handling.
        """
        class DefaultUserInteraction(UserInteraction):
            """Default user interaction adapter for skill integration."""
            
            def ask_question(self, question: str, options: Optional[List[str]] = None) -> str:
                """Ask a question and return the answer."""
                # This default implementation raises NotImplementedError
                # Skills should override this with their actual user interaction
                raise NotImplementedError(
                    "User interaction not configured. "
                    "Skills must provide a UserInteraction implementation."
                )
            
            def show_message(self, message: str) -> None:
                """Show a message to the user."""
                # Default implementation does nothing
                pass
            
            def confirm_action(self, action: str) -> bool:
                """Confirm an action with the user."""
                raise NotImplementedError(
                    "User interaction not configured. "
                    "Skills must provide a UserInteraction implementation."
                )
        
        return DefaultUserInteraction()


def integrate_with_skill(
    skill_name: str = None,
    user_prompt: str = None,
    provided_params: Dict[str, Any] = None,
    project_root: Optional[str] = None,
    # Aliases for backward compatibility and different calling patterns
    current_skill: str = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Convenience function for skill integration.
    
    This function provides a simple entry point for skills to use
    the intelligent detection engine.
    
    Args:
        skill_name: Name of the skill being invoked
        user_prompt: User's prompt or request
        provided_params: Parameters provided by the user
        project_root: Optional project root directory
        current_skill: Alias for skill_name (for backward compatibility)
        **kwargs: Additional keyword arguments (ignored)
    
    Returns:
        Dictionary with integration results including an 'action' field:
        - "proceed": Skill selection is appropriate, parameters are valid
        - "gather_parameters": Missing or invalid parameters detected
        - "switch_skill": Different skill might be more appropriate
        - "onboarding_flow": User needs guided onboarding
    """
    # Handle different parameter names
    if current_skill and not skill_name:
        skill_name = current_skill
    
    # Ensure required parameters are provided
    if not skill_name:
        raise ValueError("skill_name or current_skill must be provided")
    
    if not user_prompt:
        # Try to get user_prompt from kwargs
        user_prompt = kwargs.get('user_prompt', '')
    
    if provided_params is None:
        provided_params = {}
    
    # Convert skill name to Skill enum
    try:
        skill = Skill(skill_name)
    except ValueError:
        # If skill name is not a known Skill enum value,
        # try to find a matching skill
        skill = Skill.SKILLWEAVE_BLUEPRINT  # Default fallback
    
    helper = SkillIntegrationHelper(project_root)
    
    # Get guidance without triggering onboarding
    # (onboarding requires user interaction)
    guidance = helper.get_skill_guidance(user_prompt, skill)
    
    # Validate parameters using the orchestrator's parameter validator
    validation_result = helper.orchestrator.parameter_validator.validate(skill, provided_params)
    
    # Determine action based on analysis
    # Get recommended skill from guidance
    skill_recommended = guidance["skill_mapping"].get("recommended_skill", guidance["skill_mapping"].get("primary_skill", skill))
    
    # Convert skill_recommended to Skill enum if it's a string
    if isinstance(skill_recommended, str):
        try:
            skill_recommended_enum = Skill(skill_recommended)
        except ValueError:
            skill_recommended_enum = Skill.UNKNOWN
    else:
        skill_recommended_enum = skill_recommended
    
    # Determine action based on analysis
    if guidance["skill_match"] and validation_result.is_valid and not validation_result.missing_required:
        action = "proceed"
    elif not guidance["skill_match"]:
        if guidance["confidence_score"] >= 0.7 and skill_recommended_enum != Skill.UNKNOWN:
            action = "switch_skill"
        else:
            action = "onboarding_flow"
    elif not validation_result.is_valid or validation_result.missing_required:
        action = "gather_parameters"
    else:
        action = "onboarding_flow"
    
    # Prepare response - store string values for serialization
    skill_recommended_value = skill_recommended_enum.value if isinstance(skill_recommended_enum, Skill) else str(skill_recommended_enum)
    
    response = {
        "skill_invoked": skill_name,
        "skill_recommended": skill_recommended_value,
        "skill_match": guidance["skill_match"],
        "confidence_score": guidance["confidence_score"],
        "parameter_validation": asdict(validation_result),
        "needs_onboarding": (
            not guidance["skill_match"] 
            or not validation_result.is_valid 
            or (hasattr(validation_result, 'missing_required') and bool(validation_result.missing_required))
        ),
        "guidance": guidance["recommendations"] if guidance["recommendations"] else [],
        "action_required": (
            "Consider validating skill choice or gathering missing parameters."
            if not guidance["skill_match"] or not validation_result.is_valid
            else "Proceed with skill execution."
        ),
        "action": action,
        "validated_parameters": validation_result.valid_parameters if hasattr(validation_result, 'valid_parameters') else provided_params,
        "missing_parameters": validation_result.missing_required if hasattr(validation_result, 'missing_required') else [],
        "invalid_parameters": list(validation_result.invalid_parameters.keys()) if hasattr(validation_result, 'invalid_parameters') else [],
        "parameter_prompts": {},  # Would need to be populated from skill definitions
        "recommended_skill": skill_recommended_value if not guidance["skill_match"] else None,
        "switch_reason": f"Based on your prompt, {skill_recommended_value} might be more appropriate (confidence: {guidance['confidence_score']:.0%})" if not guidance["skill_match"] else None,
        "onboarding_steps": [],  # Would be populated by onboarding controller
        "detection_result": guidance.get("detection_result")  # Include detection result for onboarding controller
    }
    
    return response