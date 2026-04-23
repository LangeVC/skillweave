"""
Intelligent Detection Engine for SkillWeave v0.5.5.

Provides hyper-intelligent recommendation engine that analyzes user prompts,
validates skill suitability, detects missing information, and triggers guided onboarding flows.
"""

from .prompt_analyzer import PromptAnalyzer, PromptAnalysisResult
from .skill_intent_mapper import SkillIntentMapper, SkillMappingResult, Skill
from .parameter_validator import ParameterValidator, ParameterValidationResult
from .skill_detection_orchestrator import SkillDetectionOrchestrator
from .learning_system import LearningSystem, FeedbackTracker, FeedbackEvent, FeedbackEventType
from .onboarding_flow_controller import OnboardingFlowController, OnboardingState, OnboardingResult, UserInteraction, UserAction
from .skill_integration import SkillIntegrationHelper, integrate_with_skill

__all__ = [
    "PromptAnalyzer",
    "PromptAnalysisResult",
    "SkillIntentMapper",
    "SkillMappingResult",
    "Skill",
    "ParameterValidator",
    "ParameterValidationResult",
    "SkillDetectionOrchestrator",
    "LearningSystem",
    "FeedbackTracker",
    "FeedbackEvent",
    "FeedbackEventType",
    "OnboardingFlowController",
    "OnboardingState",
    "OnboardingResult",
    "UserInteraction",
    "UserAction",
    "SkillIntegrationHelper",
    "integrate_with_skill",
]