"""
Risk mode resolver with hierarchical precedence.

Implements the hierarchical override system for SkillWeave risk modes:
1. Command-line override (--risk-mode=...)
2. Environment variable (SKILLWEAVE_RISK_MODE)
3. Project configuration (.skillweave/config.yaml)
4. Global user configuration (~/.skillweave/config.yaml)
5. System default ("medium")
"""

import os
import yaml
from pathlib import Path
from typing import Optional, Literal
from .persistence import SkillWeaveConfig, get_persistence, get_config, RiskMode

RiskModeStr = Literal["conservative", "medium", "unicorn"]


class RiskModeResolver:
    """Resolve effective risk mode using hierarchical precedence."""
    
    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize resolver for a project.
        
        Args:
            project_root: Root directory of the project. If None, uses current
                         working directory.
        """
        self.project_root = Path(project_root or os.getcwd()).resolve()
        self.project_persistence = get_persistence(str(self.project_root))
        
    def resolve(
        self,
        cli_override: Optional[RiskModeStr] = None,
        env_override: Optional[RiskModeStr] = None,
        interactive: bool = True,
        include_global_config: bool = True
    ) -> RiskModeStr:
        """
        Resolve effective risk mode using hierarchical precedence.
        
        Args:
            cli_override: Risk mode from command-line argument (--risk-mode).
            env_override: Risk mode from environment variable SKILLWEAVE_RISK_MODE.
            interactive: If True, prompt user when no mode is specified and
                         project config doesn't exist.
            include_global_config: Whether to include global user configuration.
        
        Returns:
            Effective risk mode string.
        """
        # 1. Command-line override (highest precedence)
        if cli_override is not None:
            return cli_override
        
        # 2. Environment variable
        if env_override is None:
            env_override = self._get_env_override()
        if env_override is not None:
            return env_override
        
        # 3. Project configuration
        project_config = self._load_project_config()
        if project_config is not None:
            return project_config.mode.value
        
        # 4. Global user configuration (optional)
        if include_global_config:
            global_config = self._load_global_config()
            if global_config is not None:
                return global_config.mode.value
        
        # 5. System default
        return "medium"
    
    def _get_env_override(self) -> Optional[RiskModeStr]:
        """Read risk mode from environment variable."""
        env_value = os.environ.get("SKILLWEAVE_RISK_MODE")
        if env_value is None:
            return None
        env_value = env_value.lower().strip()
        if env_value in ("conservative", "medium", "unicorn"):
            return env_value
        # Invalid value: log warning and ignore
        import warnings
        warnings.warn(
            f"Invalid SKILLWEAVE_RISK_MODE value: {env_value}. "
            "Must be one of: conservative, medium, unicorn."
        )
        return None
    
    def _load_project_config(self) -> Optional[SkillWeaveConfig]:
        """Load project configuration if it exists."""
        config_path = self.project_root / ".skillweave" / "config.yaml"
        if config_path.exists():
            return self.project_persistence.load_config()
        return None
    
    def _load_global_config(self) -> Optional[SkillWeaveConfig]:
        """Load global user configuration from ~/.skillweave/config.yaml."""
        home = Path.home()
        global_config_path = home / ".skillweave" / "config.yaml"
        if not global_config_path.exists():
            return None
        try:
            with open(global_config_path, 'r') as f:
                data = yaml.safe_load(f) or {}
            return SkillWeaveConfig.from_dict(data)
        except Exception:
            # If config is malformed, return default config
            import warnings
            warnings.warn(
                f"Failed to load global config from {global_config_path}. "
                "Using default configuration."
            )
            return SkillWeaveConfig()
    
    def get_effective_mode(
        self,
        cli_override: Optional[RiskModeStr] = None,
        env_override: Optional[RiskModeStr] = None,
        interactive: bool = True,
        include_global_config: bool = True
    ) -> RiskModeStr:
        """Alias for resolve() for backward compatibility."""
        return self.resolve(cli_override, env_override, interactive, include_global_config)


def get_effective_risk_mode(
    project_root: Optional[str] = None,
    cli_override: Optional[RiskModeStr] = None,
    env_override: Optional[RiskModeStr] = None,
    interactive: bool = True,
    include_global_config: bool = True
) -> RiskModeStr:
    """
    Convenience function to get effective risk mode.
    
    This is the main entry point for skills to determine the risk mode.
    """
    resolver = RiskModeResolver(project_root)
    return resolver.resolve(cli_override, env_override, interactive, include_global_config)


# Re-export RiskMode for convenience
__all__ = ["RiskModeResolver", "get_effective_risk_mode", "RiskMode"]