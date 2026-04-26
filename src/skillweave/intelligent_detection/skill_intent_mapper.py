"""
Skill intent mapper for SkillWeave intelligent detection engine.

Maps detected intents to specific SkillWeave skills with confidence scoring,
considering skill dependencies and prerequisites.

This is the initial implementation for T-015. Future enhancements may
include learning from user feedback and historical patterns.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from .prompt_analyzer import Intent

try:
    from ..capability import Capability, CapabilityRegistry
    CAPABILITY_AVAILABLE = True
except ImportError:
    CAPABILITY_AVAILABLE = False


class Skill(str, Enum):
    """SkillWeave skill identifiers."""
    BLUEPRINT = "skillweave-blueprint"
    PROMPTCHAIN_GENERATE = "skillweave-promptchain-generate"
    PROMPTCHAIN_VALIDATE = "skillweave-promptchain-validate"
    PROMPTCHAIN_EXECUTE = "skillweave-promptchain-execute"
    RELEASECHAIN = "skillweave-releasechain"
    UNKNOWN = "unknown"


@dataclass
class SkillMappingResult:
    """Result of skill intent mapping."""
    primary_skill: Skill
    alternative_skills: List[Skill]
    confidence: float  # 0.0 to 1.0
    required_capabilities: List[str]
    missing_prerequisites: List[str]
    dependencies: List[Skill]
    recommendation_reason: str


class SkillIntentMapper:
    """
    Maps intents to SkillWeave skills with dependency awareness.
    
    Features:
    - Intent-to-skill mapping with confidence scoring
    - Skill dependency and prerequisite checking
    - Alternative skill recommendations
    - Capability-based mapping (if available)
    """
    
    # Primary mapping: intent -> skill
    INTENT_TO_SKILL: Dict[Intent, Skill] = {
        Intent.CREATE_BLUEPRINT: Skill.BLUEPRINT,
        Intent.GENERATE_PROMPTCHAIN: Skill.PROMPTCHAIN_GENERATE,
        Intent.VALIDATE_PROMPTCHAIN: Skill.PROMPTCHAIN_VALIDATE,
        Intent.EXECUTE_PROMPTCHAIN: Skill.PROMPTCHAIN_EXECUTE,
        Intent.EXECUTE_RELEASECHAIN: Skill.RELEASECHAIN,
        Intent.CONFIGURE: Skill.UNKNOWN,  # No specific skill
        Intent.HELP: Skill.UNKNOWN,
        Intent.UNKNOWN: Skill.UNKNOWN,
    }
    
    # Skill dependencies: skill -> list of prerequisite skills
    SKILL_DEPENDENCIES: Dict[Skill, List[Skill]] = {
        Skill.PROMPTCHAIN_GENERATE: [Skill.BLUEPRINT],
        Skill.PROMPTCHAIN_VALIDATE: [Skill.PROMPTCHAIN_GENERATE],
        Skill.PROMPTCHAIN_EXECUTE: [Skill.PROMPTCHAIN_VALIDATE, Skill.PROMPTCHAIN_GENERATE],
        Skill.RELEASECHAIN: [Skill.PROMPTCHAIN_EXECUTE],
    }
    
    # Skill descriptions for user-friendly messages
    SKILL_DESCRIPTIONS: Dict[Skill, str] = {
        Skill.BLUEPRINT: "Create structured PRD through guided interview",
        Skill.PROMPTCHAIN_GENERATE: "Generate prompt sequences from PRD or topic",
        Skill.PROMPTCHAIN_VALIDATE: "Validate and improve prompt sequences",
        Skill.PROMPTCHAIN_EXECUTE: "Execute prompt sequences with dependency-aware batching",
        Skill.RELEASECHAIN: "Ralph Loop-powered development pipeline",
        Skill.UNKNOWN: "Unknown skill",
    }
    
    # Alternative mappings for ambiguous intents
    # intent -> list of alternative skills with weights
    INTENT_ALTERNATIVES: Dict[Intent, List[tuple[Skill, float]]] = {
        Intent.CREATE_BLUEPRINT: [
            (Skill.PROMPTCHAIN_GENERATE, 0.3),  # Could also generate promptchain
        ],
        Intent.GENERATE_PROMPTCHAIN: [
            (Skill.BLUEPRINT, 0.4),  # Might need blueprint first
        ],
        Intent.VALIDATE_PROMPTCHAIN: [
            (Skill.PROMPTCHAIN_GENERATE, 0.6),  # Could generate instead
        ],
        Intent.EXECUTE_PROMPTCHAIN: [
            (Skill.PROMPTCHAIN_VALIDATE, 0.5),  # Might need validation first
            (Skill.PROMPTCHAIN_GENERATE, 0.3),
        ],
        Intent.EXECUTE_RELEASECHAIN: [
            (Skill.PROMPTCHAIN_EXECUTE, 0.7),  # Might need promptchain execution first
        ],
    }
    
    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize skill intent mapper.
        
        Args:
            project_root: Optional project root for capability registry
        """
        self.project_root = project_root
        self.capability_registry = None
        
        if CAPABILITY_AVAILABLE:
            try:
                self.capability_registry = CapabilityRegistry(project_root)
            except:
                pass
    
    def map_intent_to_skill(
        self, 
        intent: Intent, 
        parameters: Dict[str, Any],
        intent_confidence: float = 1.0
    ) -> SkillMappingResult:
        """
        Map an intent to the most appropriate SkillWeave skill.
        
        Args:
            intent: Detected intent from prompt analyzer
            parameters: Extracted parameters from prompt
            intent_confidence: Confidence score from prompt analyzer (0.0-1.0)
            
        Returns:
            SkillMappingResult with primary skill, alternatives, and confidence
        """
        # Step 1: Get primary skill for intent
        primary_skill = self.INTENT_TO_SKILL.get(intent, Skill.UNKNOWN)
        
        # Step 2: Calculate confidence based on intent confidence and parameter alignment
        skill_confidence = self._calculate_skill_confidence(
            primary_skill, intent, parameters, intent_confidence
        )
        
        # Step 3: Get alternative skills
        alternative_skills = self._get_alternative_skills(intent, skill_confidence)
        
        # Step 4: Check dependencies and prerequisites
        dependencies = self.SKILL_DEPENDENCIES.get(primary_skill, [])
        missing_prerequisites = self._check_missing_prerequisites(
            primary_skill, parameters
        )
        
        # Step 5: Determine required capabilities
        required_capabilities = self._get_required_capabilities(primary_skill)
        
        # Step 6: Generate recommendation reason
        recommendation_reason = self._generate_recommendation_reason(
            primary_skill, intent, skill_confidence, missing_prerequisites
        )
        
        return SkillMappingResult(
            primary_skill=primary_skill,
            alternative_skills=alternative_skills,
            confidence=skill_confidence,
            required_capabilities=required_capabilities,
            missing_prerequisites=missing_prerequisites,
            dependencies=dependencies,
            recommendation_reason=recommendation_reason,
        )
    
    def _calculate_skill_confidence(
        self,
        skill: Skill,
        intent: Intent,
        parameters: Dict[str, Any],
        intent_confidence: float
    ) -> float:
        """Calculate confidence score for skill mapping."""
        base_confidence = intent_confidence
        
        # Adjust based on parameter alignment
        parameter_score = self._score_parameter_alignment(skill, parameters)
        
        # Adjust based on capability availability (if registry available)
        capability_score = 1.0
        if self.capability_registry and skill != Skill.UNKNOWN:
            capability_score = self._score_capability_availability(skill)
        
        final_confidence = (
            base_confidence * 0.5 +
            parameter_score * 0.3 +
            capability_score * 0.2
        )
        
        return min(max(final_confidence, 0.0), 1.0)
    
    def _score_parameter_alignment(self, skill: Skill, parameters: Dict[str, Any]) -> float:
        """Score how well parameters align with skill requirements."""
        # Define required/optional parameters for each skill
        skill_parameters: Dict[Skill, Dict[str, bool]] = {
            Skill.BLUEPRINT: {
                "idea": False,  # Optional but recommended
                "domain": False,
                "complexity": False,
                "output_format": False,
                "risk_mode": False,
            },
            Skill.PROMPTCHAIN_GENERATE: {
                "skill": True,  # Required: target skill
                "complexity": False,
                "output_format": False,
                "risk_mode": False,
            },
            Skill.PROMPTCHAIN_VALIDATE: {
                "skill": True,  # Required: sequence to validate
                "risk_mode": False,
            },
            Skill.PROMPTCHAIN_EXECUTE: {
                "skill": True,  # Required: sequence to execute
                "risk_mode": False,
            },
            Skill.RELEASECHAIN: {
                "skill": True,  # Required: PRD or sequence
                "risk_mode": False,
            },
        }
        
        skill_reqs = skill_parameters.get(skill, {})
        if not skill_reqs:
            return 0.5  # Neutral score for unknown skill
        
        # Calculate alignment score
        total_params = len(skill_reqs)
        if total_params == 0:
            return 0.5
        
        matched = 0
        required_missing = 0
        
        for param_name, required in skill_reqs.items():
            if param_name in parameters:
                matched += 1
            elif required:
                required_missing += 1
        
        penalty = required_missing * 0.3
        
        base_score = matched / total_params
        
        score = max(base_score - penalty, 0.0)
        
        # Minimum baseline when no required params are missing
        if required_missing == 0:
            score = max(score, 0.5)
        
        return score
    
    def _score_capability_availability(self, skill: Skill) -> float:
        """Score based on capability availability."""
        if not self.capability_registry or not CAPABILITY_AVAILABLE:
            return 1.0  # Assume available if we can't check
        
        # Map skill to capability
        skill_to_capability = {
            Skill.BLUEPRINT: Capability.GENERATE_BLUEPRINT,
            Skill.PROMPTCHAIN_GENERATE: Capability.GENERATE_PROMPTCHAIN,
            Skill.PROMPTCHAIN_VALIDATE: Capability.VALIDATE_PROMPTCHAIN,
            Skill.PROMPTCHAIN_EXECUTE: Capability.EXECUTE_PROMPTCHAIN,
            Skill.RELEASECHAIN: Capability.EXECUTE_RELEASECHAIN,
        }
        
        capability = skill_to_capability.get(skill)
        if not capability:
            return 0.5  # Unknown capability
        
        # Check if capability has any available agents
        agents = self.capability_registry.get_agents_for_capability(capability)
        if agents:
            return 1.0
        else:
            return 0.3  # Capability not available
    
    def _get_alternative_skills(
        self, 
        intent: Intent, 
        primary_confidence: float
    ) -> List[Skill]:
        """Get alternative skills for ambiguous intents."""
        alternatives = []
        
        # Get predefined alternatives
        intent_alternatives = self.INTENT_ALTERNATIVES.get(intent, [])
        
        for skill, weight in intent_alternatives:
            # Only include if weight suggests reasonable alternative
            if weight > 0.2 and weight < primary_confidence + 0.2:
                alternatives.append(skill)
        
        # Limit to top 3 alternatives
        return alternatives[:3]
    
    def _check_missing_prerequisites(
        self, 
        skill: Skill, 
        parameters: Dict[str, Any]
    ) -> List[str]:
        """Check for missing prerequisites for the skill."""
        missing = []
        
        # Check for required parameters based on skill
        if skill == Skill.BLUEPRINT:
            if "idea" not in parameters:
                missing.append("Project idea (idea parameter)")
        
        elif skill == Skill.PROMPTCHAIN_GENERATE:
            if "skill" not in parameters:
                missing.append("Target skill (skill parameter)")
        
        elif skill in [Skill.PROMPTCHAIN_VALIDATE, Skill.PROMPTCHAIN_EXECUTE, Skill.RELEASECHAIN]:
            if "skill" not in parameters:
                missing.append("Target skill or sequence (skill parameter)")
        
        # Check skill dependencies
        dependencies = self.SKILL_DEPENDENCIES.get(skill, [])
        for dep in dependencies:
            # In a real implementation, we would check if dependency output exists
            # For now, just note potential dependency
            missing.append(f"Output from {dep.value} skill")
        
        return missing
    
    def _get_required_capabilities(self, skill: Skill) -> List[str]:
        """Get required capabilities for the skill."""
        if not CAPABILITY_AVAILABLE:
            return []
        
        skill_to_capability = {
            Skill.BLUEPRINT: ["generate_blueprint"],
            Skill.PROMPTCHAIN_GENERATE: ["generate_promptchain"],
            Skill.PROMPTCHAIN_VALIDATE: ["validate_promptchain"],
            Skill.PROMPTCHAIN_EXECUTE: ["execute_promptchain"],
            Skill.RELEASECHAIN: ["execute_releasechain"],
        }
        
        return skill_to_capability.get(skill, [])
    
    def _generate_recommendation_reason(
        self,
        skill: Skill,
        intent: Intent,
        confidence: float,
        missing_prerequisites: List[str]
    ) -> str:
        """Generate human-readable recommendation reason."""
        skill_desc = self.SKILL_DESCRIPTIONS.get(skill, "Unknown skill")
        
        if skill == Skill.UNKNOWN:
            return "Unable to determine appropriate skill. Please clarify your request."
        
        reason_parts = [f"Recommended '{skill.value}' ({skill_desc})"]
        
        if confidence > 0.8:
            reason_parts.append("high confidence match")
        elif confidence > 0.5:
            reason_parts.append("moderate confidence match")
        else:
            reason_parts.append("low confidence match")
        
        if missing_prerequisites:
            reason_parts.append(f"requires: {', '.join(missing_prerequisites)}")
        
        return ". ".join(reason_parts) + "."
    
    def batch_map(
        self, 
        intents: List[Intent], 
        parameters_list: List[Dict[str, Any]],
        intent_confidences: List[float]
    ) -> List[SkillMappingResult]:
        """Map multiple intents to skills."""
        results = []
        for intent, params, conf in zip(intents, parameters_list, intent_confidences):
            results.append(self.map_intent_to_skill(intent, params, conf))
        return results


# Convenience function
def map_intent_to_skill(
    intent: Intent, 
    parameters: Dict[str, Any], 
    project_root: Optional[str] = None,
    intent_confidence: float = 1.0
) -> SkillMappingResult:
    """Convenience function for quick skill mapping."""
    mapper = SkillIntentMapper(project_root)
    return mapper.map_intent_to_skill(intent, parameters, intent_confidence)