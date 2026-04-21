"""
Persistent state management for SkillWeave Next Level.

This module handles the .skillweave folder structure, configuration,
and tracking logs to enable session recovery and mode-based behavior.
"""

import os
import yaml
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum


class RiskMode(str, Enum):
    CONSERVATIVE = "conservative"
    MEDIUM = "medium"
    UNICORN = "unicorn"


@dataclass
class SkillWeaveConfig:
    """Configuration for SkillWeave project."""
    DEFAULT_FEATURES = {
        "checklist_execution": False,
        "design_thinking_lens": False,
        "community_patterns": False,
        "modular_templates": False,
        "capability_routing": False,
    }
    mode: RiskMode = RiskMode.MEDIUM
    features: Dict[str, bool] = field(default_factory=lambda: SkillWeaveConfig.DEFAULT_FEATURES.copy())
    overrides: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillWeaveConfig":
        """Create config from dictionary."""
        mode = RiskMode(data.get("mode", "medium"))
        # Merge with default features to ensure all keys exist
        user_features = data.get("features", {})
        features = cls.DEFAULT_FEATURES.copy()
        features.update(user_features)
        overrides = data.get("overrides", {})
        return cls(mode=mode, features=features, overrides=overrides)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "mode": self.mode.value,
            "features": self.features,
            "overrides": self.overrides,
        }


class SkillWeavePersistence:
    """Manages the .skillweave folder and persistent state."""

    FOLDER_NAME = ".skillweave"
    SUBDIRS = ["handover", "specs", "tracking-log", "manifesto"]
    CONFIG_FILE = "config.yaml"
    GITIGNORE_ENTRY = f"{FOLDER_NAME}/tracking-log/*"

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize persistence manager.
        
        Args:
            project_root: Root directory of the project. If None, uses current
                         working directory.
        """
        self.project_root = Path(project_root or os.getcwd()).resolve()
        self.skillweave_dir = self.project_root / self.FOLDER_NAME
        self.config = None

    def ensure_folder_structure(self) -> None:
        """
        Create .skillweave folder with subdirectories if they don't exist.
        Also ensures .gitignore includes tracking-log exclusion.
        """
        # Create main folder
        self.skillweave_dir.mkdir(exist_ok=True, parents=True)
        
        # Create subdirectories
        for subdir in self.SUBDIRS:
            (self.skillweave_dir / subdir).mkdir(exist_ok=True)
        
        # Create default config if missing
        config_path = self.skillweave_dir / self.CONFIG_FILE
        if not config_path.exists():
            self._create_default_config(config_path)
        
        # Update .gitignore if needed
        self._ensure_gitignore()
        
        # Create README files in subdirectories
        self._create_readme_files()

    def _create_default_config(self, config_path: Path) -> None:
        """Create default configuration file."""
        default_config = SkillWeaveConfig()
        self.save_config(default_config)

    def _ensure_gitignore(self) -> None:
        """Ensure .gitignore excludes tracking-log but not config/manifesto."""
        gitignore_path = self.project_root / ".gitignore"
        if not gitignore_path.exists():
            return
        
        content = gitignore_path.read_text()
        lines = content.splitlines()
        
        # Check if our entry exists
        entry = self.GITIGNORE_ENTRY
        if entry not in lines:
            lines.append("")
            lines.append(f"# SkillWeave tracking logs (auto-generated)")
            lines.append(entry)
            gitignore_path.write_text("\n".join(lines))

    def _create_readme_files(self) -> None:
        """Create README.md files in subdirectories explaining their purpose."""
        readme_content = {
            "handover": "# Handover Documents\n\nDocuments for handing over work between agents or to humans.",
            "specs": "# Specifications\n\nProject specifications, PRDs, architecture documents.",
            "tracking-log": "# Tracking Logs\n\nAuto-generated progress logs. Excluded from git.",
            "manifesto": "# Project Manifesto\n\nProject-specific rules, mode settings, design principles.",
        }
        
        for subdir, content in readme_content.items():
            readme_path = self.skillweave_dir / subdir / "README.md"
            if not readme_path.exists():
                readme_path.write_text(content)

    def load_config(self) -> SkillWeaveConfig:
        """Load configuration from .skillweave/config.yaml."""
        config_path = self.skillweave_dir / self.CONFIG_FILE
        if not config_path.exists():
            self.ensure_folder_structure()
        
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        self.config = SkillWeaveConfig.from_dict(data)
        return self.config

    def save_config(self, config: SkillWeaveConfig) -> None:
        """Save configuration to .skillweave/config.yaml."""
        # Ensure .skillweave directory exists
        self.skillweave_dir.mkdir(exist_ok=True, parents=True)
        config_path = self.skillweave_dir / self.CONFIG_FILE
        with open(config_path, 'w') as f:
            yaml.dump(config.to_dict(), f, default_flow_style=False, sort_keys=False)
        self.config = config

    def get_tracking_log_path(self, session_id: str) -> Path:
        """Get path for a tracking log file."""
        timestamp = datetime.now().strftime("%Y%m%d")
        filename = f"{timestamp}-{session_id}.json"
        return self.skillweave_dir / "tracking-log" / filename

    def save_tracking_log(self, session_id: str, data: Dict[str, Any]) -> Path:
        """
        Save tracking log data.
        
        Returns:
            Path to the saved log file.
        """
        log_path = self.get_tracking_log_path(session_id)
        # Ensure tracking-log directory exists
        log_path.parent.mkdir(exist_ok=True, parents=True)
        with open(log_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return log_path

    def load_tracking_log(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load tracking log data."""
        log_path = self.get_tracking_log_path(session_id)
        if not log_path.exists():
            return None
        with open(log_path, 'r') as f:
            return json.load(f)

    def list_tracking_logs(self) -> List[Dict[str, str]]:
        """List all tracking logs with metadata."""
        log_dir = self.skillweave_dir / "tracking-log"
        logs = []
        if not log_dir.exists():
            return logs
        for log_file in log_dir.glob("*.json"):
            try:
                with open(log_file, 'r') as f:
                    data = json.load(f)
                    logs.append({
                        "file": log_file.name,
                        "session_id": data.get("session_id", "unknown"),
                        "timestamp": data.get("timestamp", "unknown"),
                        "size": log_file.stat().st_size,
                    })
            except:
                continue
        return logs


# No global instance to avoid cross-project contamination


def get_persistence(project_root: Optional[str] = None) -> SkillWeavePersistence:
    """
    Get persistence instance for project root.
    
    Args:
        project_root: Root directory of the project.
    
    Returns:
        SkillWeavePersistence instance.
    """
    # Always create new instance to avoid cross-project contamination
    return SkillWeavePersistence(project_root)


def ensure_skillweave_folder(project_root: Optional[str] = None) -> SkillWeavePersistence:
    """
    Ensure .skillweave folder exists and return persistence instance.
    
    This is the main entry point for skills to initialize the folder structure.
    """
    persistence = get_persistence(project_root)
    persistence.ensure_folder_structure()
    return persistence


def get_config(project_root: Optional[str] = None) -> SkillWeaveConfig:
    """Load and return configuration."""
    # Create new instance each time to avoid caching issues
    persistence = SkillWeavePersistence(project_root)
    return persistence.load_config()


# Token-optimized helper functions
def get_mode_only(project_root: Optional[str] = None) -> str:
    """
    Get only the mode string.
    
    Returns:
        "conservative", "medium", or "unicorn"
    """
    config = get_config(project_root)
    return config.mode.value


def is_feature_enabled(feature_name: str, project_root: Optional[str] = None) -> bool:
    """
    Check if a specific feature is enabled.
    
    Args:
        feature_name: Name of feature (e.g., "checklist_execution")
    
    Returns:
        True if feature is enabled, False otherwise
    """
    config = get_config(project_root)
    return config.features.get(feature_name, False)


def get_mode_specific_setting(setting_path: str, default: Any = None, project_root: Optional[str] = None) -> Any:
    """
    Get a mode-specific override setting.
    
    Args:
        setting_path: Dot notation path (e.g., "conservative.max_parallel_tasks")
        default: Default value if setting not found
    
    Returns:
        Setting value or default
    """
    config = get_config(project_root)
    mode = config.mode.value
    
    # Split path and navigate
    parts = setting_path.split('.')
    current = config.overrides
    
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return default
    
    return current