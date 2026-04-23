"""
Onboarding flow controller for SkillWeave intelligent detection engine.

Manages interactive guidance sessions, coordinates Q&A for missing parameters,
handles skill switching with parameter migration, and provides stateful
onboarding experience.

This is the initial implementation for T-025. Future enhancements may include
more sophisticated state management and integration with AI agent question tools.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from .skill_detection_orchestrator import DetectionResult, InterventionLevel
from .skill_intent_mapper import Skill
from .parameter_validator import ParameterValidator, ParameterValidationResult


class OnboardingState(str, Enum):
    """State of onboarding flow."""
    INITIAL = "initial"
    ASSESSING = "assessing"
    GATHERING_PARAMETERS = "gathering_parameters"
    SUGGESTING_SKILL_SWITCH = "suggesting_skill_switch"
    CONFIRMING_MIGRATION = "confirming_migration"
    MIGRATING_PARAMETERS = "migrating_parameters"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class UserAction(str, Enum):
    """User actions during onboarding."""
    CONTINUE = "continue"
    SWITCH_SKILL = "switch_skill"
    PROVIDE_PARAMETER = "provide_parameter"
    SKIP_PARAMETER = "skip_parameter"
    CANCEL = "cancel"
    CONFIRM = "confirm"


@dataclass
class OnboardingResult:
    """Result of onboarding flow."""
    success: bool
    skill: Skill  # Final skill (may be switched)
    parameters: Dict[str, Any]
    state: OnboardingState
    messages: List[str]
    switched_skill: bool
    provided_parameters: List[str]


class UserInteraction:
    """
    Abstract interface for user interaction.
    
    Default implementation uses stdin/stdout. Can be overridden by AI agents
    to use their native question/answer tools.
    """
    
    def ask_question(
        self, 
        prompt: str, 
        choices: Optional[List[str]] = None,
        default: Optional[str] = None
    ) -> str:
        """
        Ask user a question with optional choices.
        
        Args:
            prompt: Question text
            choices: List of possible answers (if None, free text)
            default: Default answer if user presses Enter
            
        Returns:
            User's response as string
        """
        # Build prompt with choices
        full_prompt = prompt
        if choices:
            choices_text = "\n".join([f"{i+1}. {choice}" for i, choice in enumerate(choices)])
            full_prompt = f"{prompt}\n{choices_text}\n"
        
        if default:
            full_prompt += f"(default: {default}) "
        
        full_prompt += "> "
        
        # Get input
        try:
            response = input(full_prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return "cancel"
        
        # Handle empty response
        if not response and default:
            return default
        
        # If choices provided, validate
        if choices:
            # Try to parse as number
            if response.isdigit():
                idx = int(response) - 1
                if 0 <= idx < len(choices):
                    return choices[idx]
            # Or as exact match
            if response in choices:
                return response
            # Otherwise, return as-is (will be handled by caller)
        
        return response
    
    def get_input(self, prompt: str) -> str:
        """Get free-text input from user."""
        return self.ask_question(prompt, choices=None)


class OnboardingFlowController:
    """
    Manages guided onboarding flow for SkillWeave skills.
    
    Stateful controller that:
    1. Assesses detection results
    2. Determines required actions (parameter gathering, skill switching)
    3. Guides user through interactive Q&A
    4. Handles parameter migration between skills
    5. Returns updated skill and parameters for execution
    """
    
    def __init__(
        self,
        detection_result: DetectionResult,
        current_skill: Skill,
        current_parameters: Dict[str, Any],
        user_interaction: Optional[UserInteraction] = None,
        parameter_validator: Optional[ParameterValidator] = None,
        user_experience_level: str = "beginner"
    ):
        """
        Initialize onboarding flow controller.
        
        Args:
            detection_result: Result from skill detection analysis
            current_skill: Currently invoked skill
            current_parameters: Parameters provided with current invocation
            user_interaction: User interaction interface (uses stdin if None)
            parameter_validator: Parameter validator instance (creates default if None)
            user_experience_level: "beginner", "intermediate", or "expert"
        """
        self.detection_result = detection_result
        self.current_skill = current_skill
        self.current_parameters = current_parameters.copy()
        self.user_interaction = user_interaction or UserInteraction()
        self.user_experience_level = user_experience_level
        self.parameter_validator = parameter_validator or ParameterValidator()
        
        # State tracking
        self.state = OnboardingState.INITIAL
        self.messages = []
        self.switched_skill = False
        self.provided_parameters = []
        
        # Final results (updated during flow)
        self.final_skill = current_skill
        self.final_parameters = current_parameters.copy()
        
        # Internal state
        self._remaining_parameters = []
        self._skill_switch_suggested = False
        self._skill_switch_accepted = False
        self._migrated_preview = None
        
    def start(self) -> OnboardingResult:
        """
        Start and run the onboarding flow.
        
        Returns:
            OnboardingResult with final skill, parameters, and status
        """
        self.state = OnboardingState.ASSESSING
        self.messages.append("Starting onboarding flow...")
        
        try:
            # Step 1: Determine what's needed based on detection result
            self._assess_needs()
            
            # Step 2: Handle skill switching if needed
            if self._should_suggest_skill_switch():
                self._handle_skill_switching()
                if self.state == OnboardingState.CANCELLED:
                    return self._create_result()
            
            # Step 3: Gather missing parameters
            if self._remaining_parameters:
                self._gather_missing_parameters()
                if self.state == OnboardingState.CANCELLED:
                    return self._create_result()
            
            # Step 4: Complete flow
            self.state = OnboardingState.COMPLETE
            self.messages.append("Onboarding complete. Ready to execute.")
            
            return self._create_result()
            
        except KeyboardInterrupt:
            self.state = OnboardingState.CANCELLED
            self.messages.append("Onboarding cancelled by user.")
            return self._create_result()
        except Exception as e:
            self.messages.append(f"Error during onboarding: {str(e)}")
            self.state = OnboardingState.CANCELLED
            return self._create_result()
    
    def _assess_needs(self) -> None:
        """Assess what's needed based on detection result."""
        # Check for missing required parameters
        missing = self.detection_result.parameter_validation.missing_required
        if missing:
            self._remaining_parameters = missing.copy()
            self.messages.append(
                f"Missing {len(missing)} required parameter(s): {', '.join(missing)}"
            )
        
        # Check for skill mismatch
        if (self.current_skill != self.detection_result.skill_mapping.primary_skill and
            self.detection_result.skill_mapping.primary_skill != Skill.UNKNOWN):
            self._skill_switch_suggested = True
            self.messages.append(
                f"Skill mismatch detected. Consider switching from "
                f"'{self.current_skill.value}' to "
                f"'{self.detection_result.skill_mapping.primary_skill.value}'."
            )
    
    def _should_suggest_skill_switch(self) -> bool:
        """Determine if skill switch should be suggested."""
        if not self._skill_switch_suggested:
            return False
        
        # Based on intervention level and user experience
        intervention = self.detection_result.intervention_level
        if intervention == InterventionLevel.BLOCK:
            return True
        elif intervention == InterventionLevel.REDIRECTION:
            return True
        elif intervention == InterventionLevel.GUIDANCE:
            return self.user_experience_level in ["beginner", "intermediate"]
        elif intervention == InterventionLevel.SUGGESTION:
            return self.user_experience_level == "beginner"
        
        return False
    
    def _handle_skill_switching(self) -> None:
        """Handle skill switching suggestion and confirmation."""
        self.state = OnboardingState.SUGGESTING_SKILL_SWITCH
        
        recommended_skill = self.detection_result.skill_mapping.primary_skill
        
        # Preview parameter migration
        migrated_preview = self.parameter_validator.migrate_parameters(
            self.current_skill, recommended_skill, self.current_parameters
        )
        self._migrated_preview = migrated_preview
        preview_count = len(migrated_preview)
        original_count = len(self.current_parameters)
        migration_note = ""
        if preview_count == 0 and original_count > 0:
            migration_note = " Note: None of your current parameters will be retained."
        elif preview_count < original_count:
            migration_note = f" Note: {preview_count} of {original_count} parameters will be retained."
        
        # Build suggestion message
        suggestion_msg = (
            f"Your request appears to be a better fit for the "
            f"'{recommended_skill.value}' skill. "
            f"Confidence: {self.detection_result.skill_mapping.confidence:.0%}.{migration_note}\n"
            f"Would you like to switch to this skill?"
        )
        
        # Ask user
        response = self.user_interaction.ask_question(
            suggestion_msg,
            choices=["yes", "no", "explain"],
            default="yes" if self.user_experience_level == "beginner" else "no"
        )
        
        if response.lower() == "explain":
            # Provide explanation
            explanation = self.detection_result.skill_mapping.recommendation_reason
            if not explanation:
                explanation = "The detected intent matches this skill's capabilities better."
            self.messages.append(f"Explanation: {explanation}")
            
            # Ask again
            response = self.user_interaction.ask_question(
                "Switch skills?",
                choices=["yes", "no"],
                default="yes" if self.user_experience_level == "beginner" else "no"
            )
        
        if response.lower() == "yes":
            self.state = OnboardingState.CONFIRMING_MIGRATION
            self._perform_skill_switch(recommended_skill)
        else:
            self.messages.append("Continuing with current skill.")
            self._skill_switch_suggested = False
    
    def _perform_skill_switch(self, new_skill: Skill) -> None:
        """Perform skill switch with parameter migration."""
        self.messages.append(f"Switching to '{new_skill.value}' skill.")
        
        # Parameter migration (T-027)
        if self._migrated_preview is not None:
            migrated_params = self._migrated_preview
        else:
            migrated_params = self.parameter_validator.migrate_parameters(
                self.current_skill, new_skill, self.current_parameters
            )
        
        # Update state
        self.final_skill = new_skill
        self.final_parameters = migrated_params
        self.switched_skill = True
        self._skill_switch_accepted = True
        
        self.messages.append(
            f"Parameters migrated: {len(migrated_params)} parameter(s) retained "
            f"(from {len(self.current_parameters)} original)."
        )
    
    def _gather_missing_parameters(self) -> None:
        """Gather missing parameters through interactive Q&A."""
        self.state = OnboardingState.GATHERING_PARAMETERS
        
        self.messages.append(
            f"Please provide the following {len(self._remaining_parameters)} "
            f"missing parameter(s):"
        )
        
        # For each missing parameter, ask user
        for param in self._remaining_parameters[:]:  # Copy list as we modify
            # Get parameter info from schema
            param_info = self.parameter_validator.get_parameter_info(
                self.final_skill, param
            )
            
            # Build informative prompt
            prompt = self._build_parameter_prompt(param, param_info)
            
            # Ask for parameter value with validation loop
            value = None
            while value is None:
                response = self.user_interaction.get_input(prompt)
                
                if response.lower() == "skip":
                    self.messages.append(f"Skipped parameter '{param}'.")
                    # Remove from remaining but don't set value
                    self._remaining_parameters.remove(param)
                    break
                elif response.lower() == "cancel":
                    self.state = OnboardingState.CANCELLED
                    return
                
                # Validate if possible
                is_valid, validation_msg = self._validate_parameter_value(
                    param, response, param_info
                )
                if is_valid:
                    value = response
                else:
                    self.messages.append(validation_msg)
                    # Ask again
                    continue
            
            if value is not None:
                # Store parameter
                self.final_parameters[param] = value
                self.provided_parameters.append(param)
                self._remaining_parameters.remove(param)
                self.messages.append(f"Parameter '{param}' set to: {value}")
        
        # If all parameters gathered, update state
        if not self._remaining_parameters:
            self.messages.append("All required parameters provided.")
    
    def _build_parameter_prompt(self, param_name: str, param_info: Optional[Dict[str, Any]]) -> str:
        """
        Build a user-friendly prompt for a missing parameter.
        
        Args:
            param_name: Name of parameter
            param_info: Parameter schema information
            
        Returns:
            Prompt string for user input
        """
        if param_info is None:
            return f"Please provide value for '{param_name}':"
        
        description = param_info.get("description", "")
        param_type = param_info.get("type", "string")
        required = param_info.get("required", False)
        allowed_values = param_info.get("allowed_values")
        
        # Build prompt
        prompt_parts = [f"Parameter: {param_name}"]
        if description:
            prompt_parts.append(f"Description: {description}")
        
        prompt_parts.append(f"Type: {param_type}")
        
        if required:
            prompt_parts.append("Required: Yes")
        else:
            prompt_parts.append("Required: No (optional)")
        
        if allowed_values:
            prompt_parts.append(f"Allowed values: {', '.join(allowed_values)}")
        
        # Add examples based on type
        if param_type == "string" and not allowed_values:
            prompt_parts.append("Example: 'sample text'")
        elif param_type == "integer":
            prompt_parts.append("Example: 42")
        elif param_type == "boolean":
            prompt_parts.append("Example: true or false")
        
        prompt_parts.append("Enter value (type 'skip' to skip, 'cancel' to cancel):")
        
        return "\n".join(prompt_parts)
    
    def _validate_parameter_value(
        self, 
        param_name: str, 
        value: str, 
        param_info: Optional[Dict[str, Any]]
    ) -> Tuple[bool, str]:
        """
        Validate a parameter value.
        
        Args:
            param_name: Parameter name
            value: User-provided value (string)
            param_info: Parameter schema information
            
        Returns:
            Tuple of (is_valid, validation_message)
        """
        # If no param info, assume valid
        if param_info is None:
            return True, ""
        
        # Convert value to appropriate type if needed
        param_type = param_info.get("type", "string")
        typed_value = value
        
        try:
            if param_type == "integer":
                typed_value = int(value)
            elif param_type == "number":
                typed_value = float(value)
            elif param_type == "boolean":
                # Handle common boolean strings
                lower_val = value.lower()
                if lower_val in ("true", "yes", "1", "on"):
                    typed_value = True
                elif lower_val in ("false", "no", "0", "off"):
                    typed_value = False
                else:
                    return False, f"Invalid boolean value. Use 'true' or 'false'."
        except ValueError:
            return False, f"Value '{value}' cannot be converted to {param_type}."
        
        # Validate using parameter validator
        return self.parameter_validator.validate_single_parameter(
            self.final_skill, param_name, typed_value, param_info
        )
    
    def _create_result(self) -> OnboardingResult:
        """Create final result from current state."""
        return OnboardingResult(
            success=self.state == OnboardingState.COMPLETE,
            skill=self.final_skill,
            parameters=self.final_parameters,
            state=self.state,
            messages=self.messages.copy(),
            switched_skill=self.switched_skill,
            provided_parameters=self.provided_parameters.copy()
        )
    
    def get_current_state(self) -> OnboardingState:
        """Get current state of onboarding flow."""
        return self.state
    
    def add_message(self, message: str) -> None:
        """Add message to onboarding log."""
        self.messages.append(message)