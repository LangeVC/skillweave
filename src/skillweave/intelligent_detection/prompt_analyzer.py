"""
Prompt analyzer for SkillWeave intelligent detection engine.

Analyzes user prompts to determine intent and extract parameters using
keyword/pattern matching (rule-based approach).

This is the initial implementation for T-012. Future enhancements may
include NLP-based analysis.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Set


class Intent(str, Enum):
    """Intent classification for user prompts."""
    CREATE_BLUEPRINT = "create_blueprint"
    GENERATE_PROMPTCHAIN = "generate_promptchain"
    VALIDATE_PROMPTCHAIN = "validate_promptchain"
    EXECUTE_PROMPTCHAIN = "execute_promptchain"
    EXECUTE_RELEASECHAIN = "execute_releasechain"
    CONFIGURE = "configure"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class PromptAnalysisResult:
    """Result of prompt analysis."""
    intent: Intent
    confidence: float  # 0.0 to 1.0
    extracted_parameters: Dict[str, Any]
    raw_prompt: str
    keywords_found: List[str]
    suggestions: List[str]


class PromptAnalyzer:
    """
    Rule-based prompt analyzer using keyword and pattern matching.
    
    Features:
    - Keyword matching for intent detection
    - Simple parameter extraction using regex patterns
    - Confidence scoring based on keyword matches
    - Support for skill-specific parameter detection
    """
    
    # Keyword mapping: intent -> list of keywords/phrases (lowercase)
    INTENT_KEYWORDS: Dict[Intent, List[str]] = {
        Intent.CREATE_BLUEPRINT: [
            "blueprint", "prd", "product requirements", "requirements document",
            "plan", "project plan", "spec", "specification", "design doc",
            "project requirements", "feature spec", "scope document"
        ],
        Intent.GENERATE_PROMPTCHAIN: [
            "generate promptchain", "create promptchain", "make promptchain",
            "prompt sequence", "chain of prompts", "prompt workflow",
            "generate sequence", "create sequence", "prompt chain"
        ],
        Intent.VALIDATE_PROMPTCHAIN: [
            "validate promptchain", "check promptchain", "review promptchain",
            "verify promptchain", "audit promptchain", "test promptchain",
            "validate sequence", "check sequence", "review sequence",
            "validate", "validation", "verify", "check", "review", "audit"
        ],
        Intent.EXECUTE_PROMPTCHAIN: [
            "execute promptchain", "run promptchain", "perform promptchain",
            "execute sequence", "run sequence", "perform sequence",
            "do promptchain", "carry out promptchain", "implement promptchain",
            "execute", "run", "perform", "implement", "carry out"
        ],
        Intent.EXECUTE_RELEASECHAIN: [
            "releasechain", "execute releasechain", "run releasechain",
            "perform releasechain", "deploy", "release", "publish",
            "ship", "deliver", "production deploy"
        ],
        Intent.CONFIGURE: [
            "configure", "setup", "install", "settings", "config",
            "preferences", "options", "set up", "initialize"
        ],
        Intent.HELP: [
            "help", "what can you do", "how to", "guide", "tutorial",
            "documentation", "examples", "support", "assist"
        ]
    }
    
    # Parameter patterns: parameter_name -> list of regex patterns
    PARAMETER_PATTERNS: Dict[str, List[str]] = {
        "idea": [
            r'idea=["\']([^"\']+)["\']',
            r'idea=([^\s]+)',
            r'idea[:\s]+["\']?([^"\'\n]+)',
            r'project\s*[:\-]\s*["\']?([^"\'\n]+)',
            r'build\s*[:\-]\s*["\']?([^"\'\n]+)',
            r'create\s*[:\-]\s*["\']?([^"\'\n]+)',
        ],
        "domain": [
            r'domain=["\']([^"\']+)["\']',
            r'domain=([^\s]+)',
            r'domain[:\s]+["\']?([^"\'\n]+)',
            r'for["\']?\s*[:\-]?\s*["\']?([^"\'\n]+)\s*(?:app|platform|tool|system)',
        ],
        "complexity": [
            r'complexity=["\']([^"\']+)["\']',
            r'complexity=([^\s]+)',
            r'complexity[:\s]+["\']?([^"\'\n]+)',
            r'(simple|medium|complex)\s+(?:project|task|feature)',
        ],
        "output_format": [
            r'output_format=["\']([^"\']+)["\']',
            r'output_format=([^\s]+)',
            r'format[:\s]+["\']?([^"\'\n]+)',
            r'(json|markdown|both)\s+output',
        ],
        "risk_mode": [
            r'risk_mode=["\']([^"\']+)["\']',
            r'risk_mode=([^\s]+)',
            r'risk[:\s]+["\']?([^"\'\n]+)',
            r'(conservative|medium|unicorn)\s+mode',
        ],
        "skill": [
            r'skill=["\']([^"\']+)["\']',
            r'skill=([^\s]+)',
            r'use["\']?\s*[:\-]?\s*["\']?([^"\'\n]+)\s+skill',
        ]
    }
    
    def __init__(self, sensitivity: str = "medium"):
        self.sensitivity = sensitivity
        self.confidence_thresholds = {
            "conservative": 0.7,
            "medium": 0.5,
            "aggressive": 0.3,
        }
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}
        for param_name, patterns in self.PARAMETER_PATTERNS.items():
            self._compiled_patterns[param_name] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
    
    def analyze(self, prompt: str) -> PromptAnalysisResult:
        prompt_lower = prompt.lower().strip()

        if not prompt_lower:
            return PromptAnalysisResult(
                intent=Intent.UNKNOWN,
                confidence=0.0,
                extracted_parameters={},
                raw_prompt=prompt,
                keywords_found=[],
                suggestions=["Please provide a prompt describing what you'd like to do."]
            )

        intent_scores = self._score_intents(prompt_lower)
        top_intent, confidence = self._select_top_intent(intent_scores)
        extracted_params = self._extract_parameters(prompt)
        suggestions = self._generate_suggestions(top_intent, extracted_params, confidence)
        keywords_found = self._get_keywords_found(prompt_lower, top_intent)

        return PromptAnalysisResult(
            intent=top_intent,
            confidence=confidence,
            extracted_parameters=extracted_params,
            raw_prompt=prompt,
            keywords_found=keywords_found,
            suggestions=suggestions
        )
    
    def _score_intents(self, prompt_lower: str) -> Dict[Intent, float]:
        scores: Dict[Intent, float] = {}

        for intent, keywords in self.INTENT_KEYWORDS.items():
            matches = 0
            for keyword in keywords:
                if keyword in prompt_lower:
                    matches += 1
                elif ' ' in keyword:
                    if all(word in prompt_lower for word in keyword.split()):
                        matches += 1

            if matches:
                scores[intent] = min(0.7 + (matches - 1) * 0.15, 1.0)
            else:
                scores[intent] = 0.0

        return scores
    
    def _select_top_intent(self, intent_scores: Dict[Intent, float]) -> tuple[Intent, float]:
        """Select top intent with confidence threshold."""
        if not intent_scores:
            return Intent.UNKNOWN, 0.0
        
        # Get intent with highest score
        top_intent = max(intent_scores.items(), key=lambda x: x[1])
        
        # Apply confidence threshold based on sensitivity
        threshold = self.confidence_thresholds.get(self.sensitivity, 0.5)
        
        if top_intent[1] >= threshold:
            return top_intent
        else:
            # Below threshold, classify as unknown
            return Intent.UNKNOWN, top_intent[1]
    
    def _extract_parameters(self, prompt: str) -> Dict[str, Any]:
        extracted: Dict[str, Any] = {}

        for param_name, compiled_patterns in self._compiled_patterns.items():
            for pattern in compiled_patterns:
                matches = pattern.findall(prompt)
                if matches:
                    value = matches[0].strip()
                    if value:
                        extracted[param_name] = value
                        break

        return extracted
    
    def _generate_suggestions(
        self, 
        intent: Intent, 
        parameters: Dict[str, Any],
        confidence: float
    ) -> List[str]:
        """Generate suggestions based on analysis results."""
        suggestions = []
        
        # Low confidence suggestion
        if confidence < 0.3:
            suggestions.append(
                "I'm not sure what you're asking for. Could you provide more details?"
            )
        
        # Missing parameter suggestions based on intent
        if intent == Intent.CREATE_BLUEPRINT:
            if "idea" not in parameters:
                suggestions.append(
                    "To create a blueprint, please specify your project idea using 'idea=\"...\"'"
                )
            if "domain" not in parameters:
                suggestions.append(
                    "Consider specifying a domain (e.g., 'domain=\"saas\"') for better recommendations"
                )
        
        elif intent == Intent.GENERATE_PROMPTCHAIN:
            if "skill" not in parameters:
                suggestions.append(
                    "To generate a promptchain, specify which skill to target with 'skill=\"skillweave-blueprint\"'"
                )
        
        # General suggestion for all intents
        if not parameters and confidence > 0.5:
            suggestions.append(
                "You can provide parameters like idea, domain, complexity, or risk_mode for more precise results."
            )
        
        return suggestions
    
    def _get_keywords_found(self, prompt_lower: str, intent: Intent) -> List[str]:
        """Get list of keywords found for the selected intent."""
        keywords = self.INTENT_KEYWORDS.get(intent, [])
        found = []
        for keyword in keywords:
            if keyword in prompt_lower:
                found.append(keyword)
        return found
    
    def batch_analyze(self, prompts: List[str]) -> List[PromptAnalysisResult]:
        """Analyze multiple prompts."""
        return [self.analyze(prompt) for prompt in prompts]


# Convenience function
def analyze_prompt(prompt: str, sensitivity: str = "medium") -> PromptAnalysisResult:
    """Convenience function for quick prompt analysis."""
    analyzer = PromptAnalyzer(sensitivity=sensitivity)
    return analyzer.analyze(prompt)