"""
Design-Thinking Lens module for SkillWeave Next Level.

Applies design thinking principles to outputs and decisions.
"""

import yaml
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .persistence import SkillWeavePersistence, ensure_skillweave_folder, is_feature_enabled


class DesignRule(str, Enum):
    """Design thinking rules."""
    VALUE_NOISE = "value_noise"  # Value ≥ Noise
    SCAN_BEFORE_READ = "scan_before_read"  # Scan Before Read
    ACTIVE_OVER_AVAILABLE = "active_over_available"  # Active Over Available
    GLANCE_FIRST = "glance_first"  # Glance First, Drill-Down on Demand
    WIDGET_WORKSPACE = "widget_workspace"  # Widget ≠ Workspace
    DECISION_READY_DATA = "decision_ready_data"  # Decision-Ready Data


@dataclass
class DesignRuleDefinition:
    """Definition of a design rule."""
    name: str
    description: str
    applies_to: List[str]  # Skills this rule applies to
    enabled: bool = True
    strictness: str = "medium"  # low, medium, high


@dataclass
class DesignThinkingConfig:
    """Configuration for design thinking lens."""
    enabled: bool = False
    rules: Dict[str, DesignRuleDefinition] = field(default_factory=dict)
    strictness: str = "medium"  # Global strictness
    custom_rules: List[Dict[str, Any]] = field(default_factory=list)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DesignThinkingConfig":
        """Create from dictionary."""
        enabled = data.get("enabled", False)
        strictness = data.get("strictness", "medium")
        custom_rules = data.get("custom_rules", [])
        
        # Build default rules
        rules = {}
        default_rules_data = data.get("rules", {})
        
        default_rules = [
            DesignRuleDefinition(
                name="value_noise",
                description="Every element must provide clear value; remove or reduce noise.",
                applies_to=["blueprint", "promptchain", "releasechain"],
                enabled=default_rules_data.get("value_noise", True),
                strictness=strictness,
            ),
            DesignRuleDefinition(
                name="scan_before_read",
                description="Information should be scannable before requiring deep reading.",
                applies_to=["blueprint", "promptchain", "releasechain"],
                enabled=default_rules_data.get("scan_before_read", True),
                strictness=strictness,
            ),
            DesignRuleDefinition(
                name="active_over_available",
                description="Prefer active decisions over making all options available.",
                applies_to=["blueprint", "promptchain", "releasechain"],
                enabled=default_rules_data.get("active_over_available", False),
                strictness=strictness,
            ),
            DesignRuleDefinition(
                name="glance_first",
                description="Provide overview first, details on request.",
                applies_to=["blueprint", "promptchain", "releasechain"],
                enabled=default_rules_data.get("glance_first", True),
                strictness=strictness,
            ),
            DesignRuleDefinition(
                name="widget_workspace",
                description="Clearly distinguish between components (widgets) and the workspace.",
                applies_to=["releasechain"],  # Primarily for UI development
                enabled=default_rules_data.get("widget_workspace", True),
                strictness=strictness,
            ),
            DesignRuleDefinition(
                name="decision_ready_data",
                description="Present data in a format ready for decision-making.",
                applies_to=["blueprint", "promptchain"],
                enabled=default_rules_data.get("decision_ready_data", True),
                strictness=strictness,
            ),
        ]
        
        for rule in default_rules:
            rules[rule.name] = rule
        
        return cls(
            enabled=enabled,
            rules=rules,
            strictness=strictness,
            custom_rules=custom_rules,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        rules_dict = {}
        for rule_name, rule in self.rules.items():
            rules_dict[rule_name] = rule.enabled
        
        return {
            "enabled": self.enabled,
            "rules": rules_dict,
            "strictness": self.strictness,
            "custom_rules": self.custom_rules,
        }


class DesignThinkingLens:
    """Applies design thinking principles to skill outputs."""
    
    def __init__(self, project_root: Optional[str] = None):
        self.persistence = ensure_skillweave_folder(project_root)
        self.config = self._load_config()
        
    def _load_config(self) -> DesignThinkingConfig:
        """Load design thinking configuration."""
        # Check if feature is enabled
        if not is_feature_enabled("design_thinking_lens", self.persistence.project_root):
            return DesignThinkingConfig(enabled=False)
        
        # Try to load from manifesto
        manifesto_path = self.persistence.skillweave_dir / "manifesto" / "design-rules.yaml"
        if manifesto_path.exists():
            with open(manifesto_path, 'r') as f:
                data = yaml.safe_load(f) or {}
            return DesignThinkingConfig.from_dict(data)
        
        # Default config
        return DesignThinkingConfig(enabled=True)
    
    def is_enabled(self) -> bool:
        """Check if design thinking lens is enabled."""
        return self.config.enabled
    
    def get_applicable_rules(self, skill_name: str) -> List[DesignRuleDefinition]:
        """Get rules applicable to a specific skill."""
        if not self.is_enabled():
            return []
        
        applicable = []
        for rule in self.config.rules.values():
            if rule.enabled and skill_name in rule.applies_to:
                applicable.append(rule)
        
        # Add custom rules that apply to this skill
        for custom_rule in self.config.custom_rules:
            apply_to = custom_rule.get("apply_to", [])
            if skill_name in apply_to:
                applicable.append(DesignRuleDefinition(
                    name=custom_rule.get("name", "custom"),
                    description=custom_rule.get("description", ""),
                    applies_to=apply_to,
                    enabled=True,
                    strictness=self.config.strictness,
                ))
        
        return applicable
    
    def apply_to_content(self, skill_name: str, content: str, content_type: str = "text") -> Dict[str, Any]:
        """
        Apply design thinking lens to content.
        
        Args:
            skill_name: Name of skill (blueprint, promptchain, releasechain)
            content: Content to analyze
            content_type: Type of content (text, ui, architecture, etc.)
        
        Returns:
            Dictionary with feedback and suggestions
        """
        if not self.is_enabled():
            return {"enabled": False, "feedback": []}
        
        applicable_rules = self.get_applicable_rules(skill_name)
        feedback = []
        
        for rule in applicable_rules:
            rule_feedback = self._apply_rule(rule, content, content_type, skill_name)
            if rule_feedback:
                feedback.append({
                    "rule": rule.name,
                    "description": rule.description,
                    "feedback": rule_feedback,
                    "strictness": rule.strictness,
                })
        
        return {
            "enabled": True,
            "feedback": feedback,
            "summary": self._generate_summary(feedback),
        }
    
    def _apply_rule(self, rule: DesignRuleDefinition, content: str, content_type: str, skill_name: str) -> List[str]:
        """Apply a single rule to content."""
        feedback = []
        
        if rule.name == "value_noise":
            feedback.extend(self._check_value_noise(content, content_type))
        elif rule.name == "scan_before_read":
            feedback.extend(self._check_scan_before_read(content))
        elif rule.name == "active_over_available":
            feedback.extend(self._check_active_over_available(content, skill_name))
        elif rule.name == "glance_first":
            feedback.extend(self._check_glance_first(content))
        elif rule.name == "widget_workspace":
            feedback.extend(self._check_widget_workspace(content, content_type))
        elif rule.name == "decision_ready_data":
            feedback.extend(self._check_decision_ready_data(content))
        
        return feedback
    
    def _check_value_noise(self, content: str, content_type: str) -> List[str]:
        """Check if content has clear value vs. noise."""
        feedback = []
        
        if content_type == "ui":
            # Check for excessive decorative elements
            decorative_indicators = ["decorative", "ornamental", "purely aesthetic"]
            for indicator in decorative_indicators:
                if indicator in content.lower():
                    feedback.append(f"Consider removing purely decorative elements: '{indicator}'")
        
        # Check for redundant information
        lines = content.split('\n')
        unique_lines = set(lines)
        if len(lines) > 20 and len(unique_lines) / len(lines) < 0.7:
            feedback.append("High redundancy detected. Consider removing repetitive content.")
        
        return feedback
    
    def _check_scan_before_read(self, content: str) -> List[str]:
        """Check if content is scannable."""
        feedback = []
        
        lines = content.split('\n')
        
        # Check for headers
        header_count = sum(1 for line in lines if line.strip().startswith('#') and len(line.strip()) > 1)
        if header_count < 3 and len(lines) > 20:
            feedback.append("Add more headers to improve scannability.")
        
        # Check paragraph length
        current_para_length = 0
        for line in lines:
            if line.strip() == "":
                if current_para_length > 5:
                    feedback.append("Consider breaking up long paragraphs for better scannability.")
                current_para_length = 0
            else:
                current_para_length += 1
        
        # Check for bullet points
        bullet_count = sum(1 for line in lines if line.strip().startswith('-') or line.strip().startswith('*'))
        if bullet_count < 5 and len(lines) > 30:
            feedback.append("Consider using bullet points or lists for better scannability.")
        
        return feedback
    
    def _check_active_over_available(self, content: str, skill_name: str) -> List[str]:
        """Check if content guides decisions vs. presenting all options."""
        feedback = []
        
        if skill_name == "blueprint":
            # Check for decision points vs. open-ended options
            if "options:" in content.lower() or "alternatives:" in content.lower():
                option_sections = content.lower().count("options:") + content.lower().count("alternatives:")
                recommendation_sections = content.lower().count("recommendation:") + content.lower().count("suggest:")
                
                if option_sections > recommendation_sections:
                    feedback.append("Provide clear recommendations instead of just listing options.")
        
        return feedback
    
    def _check_glance_first(self, content: str) -> List[str]:
        """Check if content provides overview first."""
        feedback = []
        
        lines = content.split('\n')
        
        # Check for executive summary or overview at beginning
        first_1000_chars = content[:1000].lower()
        summary_indicators = ["summary", "overview", "executive", "tl;dr", "tl;dr"]
        has_summary = any(indicator in first_1000_chars for indicator in summary_indicators)
        
        if not has_summary and len(content) > 2000:
            feedback.append("Add an executive summary or overview at the beginning.")
        
        return feedback
    
    def _check_widget_workspace(self, content: str, content_type: str) -> List[str]:
        """Check for clear widget/workspace separation (for UI)."""
        if content_type != "ui":
            return []
        
        feedback = []
        
        # Simple checks for UI terminology
        ui_elements = ["toolbar", "sidebar", "panel", "widget", "control", "button"]
        workspace_terms = ["canvas", "workspace", "main area", "content area"]
        
        element_count = sum(1 for element in ui_elements if element in content.lower())
        workspace_count = sum(1 for term in workspace_terms if term in content.lower())
        
        if element_count > 0 and workspace_count == 0:
            feedback.append("Clearly distinguish UI controls from the main workspace.")
        
        return feedback
    
    def _check_decision_ready_data(self, content: str) -> List[str]:
        """Check if data is presented for decision-making."""
        feedback = []
        
        # Check for tables without summaries
        table_count = content.count("|")
        if table_count > 20:
            # Look for analysis or insights
            analysis_indicators = ["conclusion", "insight", "trend", "summary", "key finding"]
            has_analysis = any(indicator in content.lower() for indicator in analysis_indicators)
            
            if not has_analysis:
                feedback.append("Add analysis or summary to help with decision-making.")
        
        return feedback
    
    def _generate_summary(self, feedback: List[Dict[str, Any]]) -> str:
        """Generate summary of design thinking feedback."""
        if not feedback:
            return "No design thinking suggestions."
        
        total_rules = len(feedback)
        total_suggestions = sum(len(item["feedback"]) for item in feedback)
        
        summary_parts = []
        summary_parts.append(f"**Design-Thinking Review** ({total_suggestions} suggestions from {total_rules} rules)")
        
        for item in feedback:
            if item["feedback"]:
                rule_name = item["rule"].replace("_", " ").title()
                suggestions = len(item["feedback"])
                summary_parts.append(f"- **{rule_name}**: {suggestions} suggestion(s)")
        
        return "\n".join(summary_parts)
    
    def generate_markdown_feedback(self, analysis_result: Dict[str, Any]) -> str:
        """Generate markdown format feedback for inclusion in outputs."""
        if not analysis_result.get("enabled", False):
            return ""
        
        feedback = analysis_result.get("feedback", [])
        if not feedback:
            return ""
        
        lines = []
        lines.append("## Design-Thinking Notes")
        lines.append("")
        
        for item in feedback:
            if item["feedback"]:
                rule_name = item["rule"].replace("_", " ").title()
                lines.append(f"### {rule_name}")
                lines.append(f"*{item['description']}*")
                lines.append("")
                
                for suggestion in item["feedback"]:
                    lines.append(f"- {suggestion}")
                lines.append("")
        
        return "\n".join(lines)