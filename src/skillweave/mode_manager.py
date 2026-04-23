"""
Mode manager for SkillWeave Next Level.

Handles three risk modes (conservative, medium, unicorn) and their behavior differences.
"""

from typing import Dict, Any, Optional, Literal
from dataclasses import dataclass, field
from enum import Enum

from .persistence import SkillWeavePersistence, ensure_skillweave_folder, get_mode_only, get_mode_specific_setting
from .persistence import RiskMode
from .risk_mode_resolver import RiskModeResolver, get_effective_risk_mode


@dataclass
class ModeBehavior:
    """Behavior configuration for a specific mode."""
    # General behavior
    require_approval: bool = False
    max_parallel_tasks: int = 3
    auto_continue: bool = False
    logging_level: str = "INFO"
    
    # Validation behavior
    validation_strictness: str = "medium"  # low, medium, high
    require_tests: bool = True
    require_review: bool = False
    
    # Safety behavior
    allow_destructive: bool = False
    require_confirmation: bool = True
    safety_checks: bool = True
    
    # Performance behavior  
    optimize_for_speed: bool = False
    allow_experimental: bool = False
    
    @classmethod
    def for_mode(cls, mode: RiskMode) -> "ModeBehavior":
        """Get behavior configuration for a specific mode."""
        if mode == RiskMode.CONSERVATIVE:
            return cls(
                require_approval=True,
                max_parallel_tasks=1,
                auto_continue=False,
                logging_level="DEBUG",
                validation_strictness="high",
                require_tests=True,
                require_review=True,
                allow_destructive=False,
                require_confirmation=True,
                safety_checks=True,
                optimize_for_speed=False,
                allow_experimental=False,
            )
        elif mode == RiskMode.MEDIUM:
            return cls(
                require_approval=False,
                max_parallel_tasks=3,
                auto_continue=True,
                logging_level="INFO",
                validation_strictness="medium",
                require_tests=True,
                require_review=False,
                allow_destructive=False,
                require_confirmation=True,
                safety_checks=True,
                optimize_for_speed=False,
                allow_experimental=False,
            )
        elif mode == RiskMode.UNICORN:
            return cls(
                require_approval=False,
                max_parallel_tasks=10,
                auto_continue=True,
                logging_level="WARNING",
                validation_strictness="low",
                require_tests=False,
                require_review=False,
                allow_destructive=True,
                require_confirmation=True,
                safety_checks=True,
                optimize_for_speed=True,
                allow_experimental=True,
            )
        else:
            return cls()  # pragma: no cover


class ModeManager:
    """Manages mode-specific behavior for SkillWeave skills."""
    
    def __init__(
        self, 
        project_root: Optional[str] = None,
        cli_risk_mode: Optional[Literal["conservative", "medium", "unicorn"]] = None,
        env_risk_mode: Optional[Literal["conservative", "medium", "unicorn"]] = None
    ):
        self.persistence = ensure_skillweave_folder(project_root)
        self.config = self.persistence.load_config()
        
        # Get effective risk mode using hierarchical precedence
        self.effective_mode_str = get_effective_risk_mode(
            project_root=project_root,
            cli_override=cli_risk_mode,
            env_override=env_risk_mode,
            interactive=False,
            include_global_config=True
        )
        # Convert string to RiskMode enum
        self.mode = RiskMode(self.effective_mode_str)
        self.behavior = ModeBehavior.for_mode(self.mode)
        
        # Apply any overrides from config for the effective mode
        self._apply_overrides()
    
    def _apply_overrides(self) -> None:
        """Apply mode-specific overrides from config."""
        overrides = self.config.overrides.get(self.mode.value, {})
        
        for key, value in overrides.items():
            if hasattr(self.behavior, key):
                setattr(self.behavior, key, value)
    
    def get_mode(self) -> RiskMode:
        """Get current mode."""
        return self.mode
    
    def get_behavior(self) -> ModeBehavior:
        """Get current behavior configuration."""
        return self.behavior
    
    def should_require_approval(self, action_type: str) -> bool:
        """
        Determine if approval is required for a specific action.
        
        Args:
            action_type: Type of action (e.g., "destructive", "execution", "review")
        """
        if not self.behavior.require_approval:
            return False
        
        # Mode-specific logic
        if self.mode == RiskMode.CONSERVATIVE:
            return True
        elif self.mode == RiskMode.MEDIUM:
            return action_type in ["destructive", "high_risk"]
        elif self.mode == RiskMode.UNICORN:
            return False
        
        return False  # pragma: no cover

    def get_max_parallel_tasks(self) -> int:
        """Get maximum parallel tasks allowed."""
        return self.behavior.max_parallel_tasks
    
    def get_validation_strictness(self) -> str:
        """Get validation strictness level."""
        return self.behavior.validation_strictness
    
    def should_require_tests(self) -> bool:
        """Determine if tests are required."""
        return self.behavior.require_tests
    
    def should_require_review(self) -> bool:
        """Determine if review is required."""
        return self.behavior.require_review
    
    def is_destructive_allowed(self) -> bool:
        """Determine if destructive operations are allowed."""
        return self.behavior.allow_destructive
    
    def should_require_confirmation(self, operation: str) -> bool:
        """
        Determine if confirmation is required for an operation.
        """
        if not self.behavior.require_confirmation:
            return False
        
        # Conservative mode requires confirmation for everything
        if self.mode == RiskMode.CONSERVATIVE:
            return True
        
        # Medium mode requires confirmation for risky operations
        if self.mode == RiskMode.MEDIUM:
            risky_operations = ["delete", "overwrite", "modify_core", "deploy"]
            return operation in risky_operations
        
        # Unicorn mode rarely requires confirmation
        if self.mode == RiskMode.UNICORN:
            critical_operations = ["delete_production", "format_disk"]
            return operation in critical_operations
        
        return False  # pragma: no cover

    def should_perform_safety_check(self, check_type: str) -> bool:
        """
        Determine if a safety check should be performed.
        """
        if not self.behavior.safety_checks:
            return False
        
        if self.mode == RiskMode.CONSERVATIVE:
            return True
        elif self.mode == RiskMode.MEDIUM:
            important_checks = ["security", "data_loss", "breaking_change"]
            return check_type in important_checks
        elif self.mode == RiskMode.UNICORN:
            critical_checks = ["data_loss"]
            return check_type in critical_checks
        
        return False  # pragma: no cover
    
    def should_optimize_for_speed(self) -> bool:
        """Determine if we should optimize for speed over safety."""
        return self.behavior.optimize_for_speed
    
    def is_experimental_allowed(self) -> bool:
        """Determine if experimental features are allowed."""
        return self.behavior.allow_experimental
    
    def get_logging_level(self) -> str:
        """Get logging level for current mode."""
        return self.behavior.logging_level
    
    def get_mode_guidance(self, skill_name: str) -> str:
        """
        Get mode-specific guidance for a skill.
        
        Returns markdown string with guidance.
        """
        guidance = []
        guidance.append(f"## Mode: {self.mode.value.title()}")
        guidance.append("")
        
        if self.mode == RiskMode.CONSERVATIVE:
            guidance.append("**Conservative Mode**: Maximum safety, security, and reliability.")
            guidance.append("- All operations require approval")
            guidance.append("- Extensive validation and testing")
            guidance.append("- No destructive operations")
            guidance.append("- Detailed logging")
        elif self.mode == RiskMode.MEDIUM:
            guidance.append("**Medium Mode**: Balanced approach between safety and productivity.")
            guidance.append("- Standard validation")
            guidance.append("- Moderate parallel execution")
            guidance.append("- Destructive operations require confirmation")
            guidance.append("- Balanced error handling")
        elif self.mode == RiskMode.UNICORN:
            guidance.append("**Unicorn Mode**: Maximum creativity, speed, and innovation.")
            guidance.append("- Minimal validation")
            guidance.append("- Maximized parallel execution")
            guidance.append("- Experimental features allowed")
            guidance.append("- Performance prioritized")
        
        guidance.append("")
        
        # Add skill-specific guidance
        if skill_name == "blueprint":
            guidance.extend(self._get_blueprint_guidance())
        elif skill_name == "promptchain":
            guidance.extend(self._get_promptchain_guidance())
        elif skill_name == "releasechain":
            guidance.extend(self._get_releasechain_guidance())
        
        return "\n".join(guidance)
    
    def _get_blueprint_guidance(self) -> list:
        """Get blueprint-specific guidance."""
        guidance = []
        guidance.append("### Blueprint Skill Guidance")
        
        if self.mode == RiskMode.CONSERVATIVE:
            guidance.append("- Validate all assumptions")
            guidance.append("- Require explicit approval for technology choices")
            guidance.append("- Generate detailed documentation")
            guidance.append("- Suggest proven, stable technologies")
        elif self.mode == RiskMode.MEDIUM:
            guidance.append("- Validate critical assumptions")
            guidance.append("- Suggest balanced technology choices")
            guidance.append("- Generate standard documentation")
        elif self.mode == RiskMode.UNICORN:
            guidance.append("- Make optimistic assumptions")
            guidance.append("- Suggest cutting-edge technologies")
            guidance.append("- Generate lightweight documentation")
        
        return guidance
    
    def _get_promptchain_guidance(self) -> list:
        """Get promptchain-specific guidance."""
        guidance = []
        guidance.append("### PromptChain Skills Guidance")
        
        if self.mode == RiskMode.CONSERVATIVE:
            guidance.append("- Add extra validation steps")
            guidance.append("- Require human confirmation before each batch")
            guidance.append("- Limit parallel execution")
            guidance.append("- Enforce comprehensive testing")
        elif self.mode == RiskMode.MEDIUM:
            guidance.append("- Standard validation")
            guidance.append("- Human confirmation at major gates")
            guidance.append("- Moderate parallel execution")
            guidance.append("- Standard testing requirements")
        elif self.mode == RiskMode.UNICORN:
            guidance.append("- Minimal validation")
            guidance.append("- Autonomous execution")
            guidance.append("- Maximize parallel execution")
            guidance.append("- Lightweight testing")
        
        return guidance
    
    def _get_releasechain_guidance(self) -> list:
        """Get releasechain-specific guidance."""
        guidance = []
        guidance.append("### ReleaseChain Skill Guidance")
        
        if self.mode == RiskMode.CONSERVATIVE:
            guidance.append("- Require manual approval for each task")
            guidance.append("- Run extensive security checks")
            guidance.append("- Limit autonomous execution")
            guidance.append("- Prevent destructive operations")
        elif self.mode == RiskMode.MEDIUM:
            guidance.append("- Automatic execution with checkpoints")
            guidance.append("- Standard security checks")
            guidance.append("- Balanced autonomy")
            guidance.append("- Destructive operations require confirmation")
        elif self.mode == RiskMode.UNICORN:
            guidance.append("- Fully autonomous execution")
            guidance.append("- Minimal security checks")
            guidance.append("- High autonomy")
            guidance.append("- Allow destructive operations with warning")
        
        return guidance