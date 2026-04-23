"""
Skill detection orchestrator for SkillWeave intelligent detection engine.

Main coordinator that analyzes prompts, maps to skills, validates parameters,
and makes intervention decisions with configurable sensitivity.

This is the initial implementation for T-021. Future enhancements may
include learning from user feedback and adaptive threshold adjustment.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
from .prompt_analyzer import PromptAnalyzer, PromptAnalysisResult, Intent
from .skill_intent_mapper import SkillIntentMapper, SkillMappingResult, Skill
from .parameter_validator import ParameterValidator, ParameterValidationResult

try:
    from .learning_system import LearningSystem, FeedbackEventType
    LEARNING_SYSTEM_AVAILABLE = True
except ImportError:
    LEARNING_SYSTEM_AVAILABLE = False
    LearningSystem = None
    FeedbackEventType = None


class InterventionLevel(str, Enum):
    """Level of intervention recommended."""
    NONE = "none"           # No intervention needed
    SUGGESTION = "suggestion"  # Provide gentle suggestion
    GUIDANCE = "guidance"   # Offer guided help
    REDIRECTION = "redirection"  # Suggest different skill
    BLOCK = "block"        # Block execution (severe mismatch)


@dataclass
class DetectionResult:
    """Complete result of skill detection."""
    prompt_analysis: PromptAnalysisResult
    skill_mapping: SkillMappingResult
    parameter_validation: ParameterValidationResult
    intervention_level: InterventionLevel
    intervention_message: str
    recommended_action: str
    confidence_score: float  # Overall confidence (0.0-1.0)


class SkillDetectionOrchestrator:
    """
    Main orchestrator for intelligent skill detection.
    
    Coordinates:
    - Prompt analysis (intent detection)
    - Skill intent mapping
    - Parameter validation
    - Intervention decision making
    
    Configurable sensitivity based on risk mode and user preferences.
    """
    
    def __init__(
        self, 
        project_root: Optional[str] = None,
        sensitivity: str = "medium",
        auto_switch_threshold: float = 70.0,
        strict_validation: bool = False,
        learning_system: Optional["LearningSystem"] = None
    ):
        """
        Initialize orchestrator.
        
        Args:
            project_root: Project root for skill scanning
            sensitivity: "conservative", "medium", or "aggressive"
            auto_switch_threshold: 0-100 score threshold for suggesting skill switch
            strict_validation: If True, use strict parameter validation
            learning_system: Optional learning system for adaptive thresholds
        """
        self.project_root = project_root
        self.learning_system = learning_system
        
        # Apply learning adjustments if available
        if learning_system and LEARNING_SYSTEM_AVAILABLE:
            # Override sensitivity and threshold with learned preferences
            # unless explicitly provided (non-default values)
            if sensitivity == "medium":  # Default value, can be overridden
                sensitivity = learning_system.get_adjusted_sensitivity()
            # Similarly for threshold
            if auto_switch_threshold == 70.0:
                auto_switch_threshold = learning_system.get_adjusted_threshold()
        
        self.sensitivity = sensitivity
        self.auto_switch_threshold = auto_switch_threshold / 100.0  # Convert to 0-1
        self.strict_validation = strict_validation
        
        # Initialize components
        self.prompt_analyzer = PromptAnalyzer(sensitivity=sensitivity)
        self.skill_mapper = SkillIntentMapper(project_root)
        self.parameter_validator = ParameterValidator(strict_mode=strict_validation)
        
        # Sensitivity thresholds for intervention
        self.intervention_thresholds = {
            "conservative": {
                "suggestion": 0.3,   # Low confidence triggers suggestion
                "guidance": 0.5,     # Moderate confidence triggers guidance
                "redirection": 0.7,  # High confidence triggers redirection
                "block": 0.9,        # Very high confidence triggers block
            },
            "medium": {
                "suggestion": 0.2,
                "guidance": 0.4,
                "redirection": 0.6,
                "block": 0.8,
            },
            "aggressive": {
                "suggestion": 0.1,
                "guidance": 0.3,
                "redirection": 0.5,
                "block": 0.7,
            }
        }
    
    def detect(
        self, 
        prompt: str, 
        current_skill: Optional[Skill] = None,
        current_parameters: Optional[Dict[str, Any]] = None
    ) -> DetectionResult:
        """
        Perform complete skill detection analysis.
        
        Args:
            prompt: User prompt text
            current_skill: Currently invoked skill (if any)
            current_parameters: Parameters provided with current invocation
            
        Returns:
            DetectionResult with analysis and recommendations
        """
        # Step 1: Analyze prompt
        prompt_analysis = self.prompt_analyzer.analyze(prompt)
        
        # Step 2: Map intent to skill
        skill_mapping = self.skill_mapper.map_intent_to_skill(
            prompt_analysis.intent,
            prompt_analysis.extracted_parameters,
            prompt_analysis.confidence
        )
        
        # Step 3: Validate parameters against mapped skill
        # Combine extracted parameters with current parameters
        all_parameters = prompt_analysis.extracted_parameters.copy()
        if current_parameters:
            all_parameters.update(current_parameters)
        
        parameter_validation = self.parameter_validator.validate(
            skill_mapping.primary_skill,
            all_parameters
        )
        
        # Step 4: Determine intervention level
        intervention_level, intervention_message = self._determine_intervention(
            prompt_analysis,
            skill_mapping,
            parameter_validation,
            current_skill
        )
        
        # Step 5: Calculate overall confidence score
        confidence_score = self._calculate_confidence_score(
            prompt_analysis.confidence,
            skill_mapping.confidence,
            parameter_validation.completeness_score,
            skill_mapping.primary_skill
        )
        
        # Step 6: Determine recommended action
        recommended_action = self._determine_recommended_action(
            intervention_level,
            skill_mapping,
            parameter_validation,
            current_skill
        )
        
        return DetectionResult(
            prompt_analysis=prompt_analysis,
            skill_mapping=skill_mapping,
            parameter_validation=parameter_validation,
            intervention_level=intervention_level,
            intervention_message=intervention_message,
            recommended_action=recommended_action,
            confidence_score=confidence_score
        )
    
    def _determine_intervention(
        self,
        prompt_analysis: PromptAnalysisResult,
        skill_mapping: SkillMappingResult,
        parameter_validation: ParameterValidationResult,
        current_skill: Optional[Skill]
    ) -> Tuple[InterventionLevel, str]:
        """Determine appropriate intervention level and message."""
        # Calculate mismatch score if current skill provided
        mismatch_score = 0.0
        if current_skill and current_skill != Skill.UNKNOWN:
            if current_skill != skill_mapping.primary_skill:
                mismatch_score = 1.0 - skill_mapping.confidence
            else:
                mismatch_score = 0.0
        
        # Calculate parameter completeness score
        param_score = 1.0 - parameter_validation.completeness_score
        
        # Calculate overall issue score
        issue_score = max(mismatch_score, param_score, 1.0 - prompt_analysis.confidence)
        
        # Get thresholds for current sensitivity
        thresholds = self.intervention_thresholds.get(self.sensitivity, self.intervention_thresholds["medium"])
        
        # Determine intervention level
        if issue_score >= thresholds["block"]:
            level = InterventionLevel.BLOCK
        elif issue_score >= thresholds["redirection"]:
            level = InterventionLevel.REDIRECTION
        elif issue_score >= thresholds["guidance"]:
            level = InterventionLevel.GUIDANCE
        elif issue_score >= thresholds["suggestion"]:
            level = InterventionLevel.SUGGESTION
        else:
            level = InterventionLevel.NONE
        
        # Generate intervention message
        message = self._generate_intervention_message(
            level, prompt_analysis, skill_mapping, parameter_validation, current_skill, issue_score
        )
        
        return level, message
    
    def _generate_intervention_message(
        self,
        level: InterventionLevel,
        prompt_analysis: PromptAnalysisResult,
        skill_mapping: SkillMappingResult,
        parameter_validation: ParameterValidationResult,
        current_skill: Optional[Skill],
        issue_score: float
    ) -> str:
        """Generate human-readable intervention message."""
        if level == InterventionLevel.NONE:
            return "No intervention needed. Proceed with execution."
        
        # Build message parts
        parts = []
        
        if level == InterventionLevel.BLOCK:
            parts.append("⚠️ **Severe mismatch detected**")
        elif level == InterventionLevel.REDIRECTION:
            parts.append("🔄 **Consider switching skills**")
        elif level == InterventionLevel.GUIDANCE:
            parts.append("💡 **Guidance recommended**")
        elif level == InterventionLevel.SUGGESTION:
            parts.append("💬 **Suggestion**")
        
        # Add skill mismatch info
        if current_skill and current_skill != skill_mapping.primary_skill:
            parts.append(
                f"You're using '{current_skill.value}', but your request appears to match "
                f"'{skill_mapping.primary_skill.value}' ({skill_mapping.confidence:.0%} confidence)."
            )
        
        # Add parameter issues
        if parameter_validation.missing_required:
            parts.append(
                f"Missing required parameters: {', '.join(parameter_validation.missing_required)}"
            )
        
        if not parameter_validation.is_valid:
            parts.append("Parameter validation failed. Please check your inputs.")
        
        # Add suggestions from prompt analysis
        if prompt_analysis.suggestions:
            parts.extend(prompt_analysis.suggestions)
        
        # Add skill mapping recommendation
        if skill_mapping.recommendation_reason:
            parts.append(skill_mapping.recommendation_reason)
        
        # Add call to action based on level
        if level == InterventionLevel.BLOCK:
            parts.append("**Action required:** Please revise your request or confirm you want to proceed.")
        elif level == InterventionLevel.REDIRECTION:
            parts.append("**Suggestion:** Consider using the recommended skill for better results.")
        elif level == InterventionLevel.GUIDANCE:
            parts.append("**Guidance:** I can help you complete the missing information.")
        elif level == InterventionLevel.SUGGESTION:
            parts.append("**Note:** This is just a suggestion. You can proceed if you prefer.")
        
        return " ".join(parts)
    
    def _calculate_confidence_score(
        self,
        prompt_confidence: float,
        skill_confidence: float,
        param_completeness: float,
        primary_skill: Optional[Skill] = None
    ) -> float:
        """Calculate overall confidence score."""
        # Weighted average based on sensitivity
        if self.sensitivity == "conservative":
            weights = (0.4, 0.4, 0.2)  # Heavy on prompt and skill analysis
        elif self.sensitivity == "aggressive":
            weights = (0.2, 0.3, 0.5)  # More weight on parameters
        else:  # medium
            weights = (0.3, 0.4, 0.3)
        
        weighted_sum = (
            prompt_confidence * weights[0] +
            skill_confidence * weights[1] +
            param_completeness * weights[2]
        )
        
        # Apply skill confidence adjustment from learning system if available
        if self.learning_system and primary_skill and LEARNING_SYSTEM_AVAILABLE:
            adjustment = self.learning_system.get_skill_confidence_adjustment(primary_skill)
            weighted_sum *= adjustment
        
        return min(max(weighted_sum, 0.0), 1.0)
    
    def _determine_recommended_action(
        self,
        intervention_level: InterventionLevel,
        skill_mapping: SkillMappingResult,
        parameter_validation: ParameterValidationResult,
        current_skill: Optional[Skill]
    ) -> str:
        """Determine recommended action based on analysis."""
        if intervention_level == InterventionLevel.NONE:
            return "proceed"
        
        actions = []
        
        # Skill switching action
        if current_skill and current_skill != skill_mapping.primary_skill:
            if intervention_level in [InterventionLevel.REDIRECTION, InterventionLevel.BLOCK]:
                actions.append(f"switch to {skill_mapping.primary_skill.value}")
        
        # Parameter completion action
        if parameter_validation.missing_required:
            actions.append("provide missing parameters")
        
        # Parameter correction action
        if parameter_validation.suggested_corrections:
            actions.append("correct parameter values")
        
        # Guidance action
        if intervention_level == InterventionLevel.GUIDANCE:
            actions.append("request guided assistance")
        
        if not actions:
            return "review and proceed"
        
        return " then ".join(actions)
    
    def should_trigger_onboarding(
        self,
        detection_result: DetectionResult,
        user_experience_level: str = "beginner"
    ) -> bool:
        """
        Determine if onboarding flow should be triggered.
        
        Args:
            detection_result: Result from detect() method
            user_experience_level: "beginner", "intermediate", or "expert"
            
        Returns:
            True if onboarding should be triggered
        """
        # Base decision on intervention level and user experience
        if user_experience_level == "expert":
            # Experts only need help for severe issues
            return detection_result.intervention_level in [
                InterventionLevel.BLOCK, InterventionLevel.REDIRECTION
            ]
        elif user_experience_level == "intermediate":
            # Intermediates need help for guidance and above
            return detection_result.intervention_level in [
                InterventionLevel.GUIDANCE, 
                InterventionLevel.REDIRECTION,
                InterventionLevel.BLOCK
            ]
        else:  # beginner
            # Beginners get help for all interventions
            return detection_result.intervention_level != InterventionLevel.NONE
    
    def record_feedback(
        self,
        event_type: FeedbackEventType,
        prompt: str,
        detection_result: Optional[DetectionResult] = None,
        user_action: Optional[str] = None
    ):
        """
        Record user feedback for learning.
        
        Args:
            event_type: Type of feedback event
            prompt: Original user prompt
            detection_result: Detection result (if available)
            user_action: Description of user action
        """
        if not self.learning_system or not LEARNING_SYSTEM_AVAILABLE:
            return
        
        # Extract info from detection result if provided
        detected_skill = None
        current_skill = None
        confidence_score = 0.0
        intervention_level = "none"
        
        if detection_result:
            detected_skill = detection_result.skill_mapping.primary_skill
            confidence_score = detection_result.confidence_score
            intervention_level = detection_result.intervention_level.value
        
        self.learning_system.record_feedback(
            event_type=event_type,
            prompt=prompt,
            detected_skill=detected_skill,
            current_skill=current_skill,
            confidence_score=confidence_score,
            intervention_level=intervention_level,
            user_action=user_action
        )
    
    def batch_detect(
        self, 
        prompts: List[str], 
        current_skills: Optional[List[Optional[Skill]]] = None,
        current_parameters_list: Optional[List[Optional[Dict[str, Any]]]] = None
    ) -> List[DetectionResult]:
        """Perform detection on multiple prompts."""
        results = []
        
        # Default values if not provided
        if current_skills is None:
            current_skills = [None] * len(prompts)
        if current_parameters_list is None:
            current_parameters_list = [None] * len(prompts)
        
        for prompt, current_skill, current_params in zip(
            prompts, current_skills, current_parameters_list
        ):
            results.append(self.detect(prompt, current_skill, current_params))
        
        return results


# Convenience function
def detect_skill(
    prompt: str,
    project_root: Optional[str] = None,
    current_skill: Optional[Skill] = None,
    current_parameters: Optional[Dict[str, Any]] = None,
    sensitivity: str = "medium"
) -> DetectionResult:
    """Convenience function for quick skill detection."""
    orchestrator = SkillDetectionOrchestrator(
        project_root=project_root,
        sensitivity=sensitivity
    )
    return orchestrator.detect(prompt, current_skill, current_parameters)