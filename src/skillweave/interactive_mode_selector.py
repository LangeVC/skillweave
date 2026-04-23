"""
Interactive mode selection for SkillWeave.

Provides context-aware risk mode suggestions and interactive selection
when no mode is explicitly configured.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from enum import Enum

from .persistence import RiskMode, SkillWeavePersistence, ensure_skillweave_folder
from .risk_mode_resolver import RiskModeResolver


class PersistenceOption(str, Enum):
    """Persistence options for mode selection."""
    TEMPORARY = "temporary"  # Only for current session
    PROJECT = "project"      # Save to project config
    GLOBAL = "global"        # Save to global config


class InteractiveModeSelector:
    """Interactive risk mode selector with context-aware suggestions."""
    
    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root or os.getcwd()).resolve()
        self.resolver = RiskModeResolver(project_root)
        self.persistence = ensure_skillweave_folder(project_root)
    
    def analyze_project(self) -> Dict[str, Any]:
        """
        Analyze project to gather context for mode suggestion.
        
        Returns:
            Dictionary with analysis results:
            - has_git: bool (is git repository)
            - file_count: int (approximate number of files)
            - has_existing_config: bool (has .skillweave/config.yaml)
            - config_mode: Optional[str] (existing mode if any)
            - is_large_project: bool (heuristic)
            - is_new_project: bool (heuristic based on few files)
        """
        analysis = {
            "has_git": False,
            "file_count": 0,
            "has_existing_config": False,
            "config_mode": None,
            "is_large_project": False,
            "is_new_project": False,
        }
        
        # Check for git repository
        git_dir = self.project_root / ".git"
        analysis["has_git"] = git_dir.exists()
        
        # Count files (approximate, limit to 1000 for performance)
        try:
            # Count files in project root, excluding .git and virtual envs
            count = 0
            for root, dirs, files in os.walk(self.project_root, topdown=True):
                # Skip .git directories
                dirs[:] = [d for d in dirs if d != ".git" and not d.startswith(".")]
                count += len(files)
                if count > 1000:
                    count = 1000
                    break
            analysis["file_count"] = count
        except (OSError, PermissionError):
            pass
        
        # Check for existing SkillWeave config
        config_path = self.project_root / ".skillweave" / "config.yaml"
        if config_path.exists():
            analysis["has_existing_config"] = True
            try:
                from .persistence import get_config
                config = get_config(str(self.project_root))
                analysis["config_mode"] = config.mode.value
            except Exception:
                pass
        
        # Heuristics
        analysis["is_large_project"] = analysis["file_count"] > 100
        analysis["is_new_project"] = analysis["file_count"] < 10 and not analysis["has_existing_config"]
        
        return analysis
    
    def suggest_mode(self, analysis: Optional[Dict[str, Any]] = None) -> Tuple[RiskMode, str]:
        """
        Suggest appropriate risk mode based on project analysis.
        
        Args:
            analysis: Optional pre-computed analysis (will compute if None)
        
        Returns:
            Tuple of (suggested RiskMode, reasoning string)
        """
        if analysis is None:
            analysis = self.analyze_project()
        
        # Default suggestion
        suggestion = RiskMode.MEDIUM
        reasoning = "Balanced approach suitable for most projects."
        
        # Context-aware adjustments
        if analysis["is_new_project"]:
            suggestion = RiskMode.UNICORN
            reasoning = "New project with few files - optimistic mode allows faster iteration."
        elif analysis["is_large_project"]:
            suggestion = RiskMode.CONSERVATIVE
            reasoning = "Large project with many files - conservative mode reduces risk of unintended changes."
        elif analysis["has_existing_config"] and analysis["config_mode"]:
            # Respect existing configuration
            try:
                suggestion = RiskMode(analysis["config_mode"])
                reasoning = f"Using existing project configuration ({suggestion.value} mode)."
            except ValueError:
                pass
        
        # If project is a git repository but no existing config, suggest medium
        if analysis["has_git"] and not analysis["has_existing_config"]:
            suggestion = RiskMode.MEDIUM
            reasoning = "Git repository detected - medium mode provides good balance of safety and speed."
        
        return suggestion, reasoning
    
    def interactive_select(self, 
                          prefer_persistent: bool = True,
                          force_interactive: bool = False) -> Tuple[RiskMode, PersistenceOption]:
        """
        Interactively select risk mode (for CLI use).
        
        Args:
            prefer_persistent: Whether to prefer persistent storage
            force_interactive: Force interactive mode even if mode is already configured
        
        Returns:
            Tuple of (selected RiskMode, persistence option)
        
        Note:
            This function is intended for CLI use. For AI agent integration,
            use `suggest_mode()` and handle interaction separately.
        """
        # First check if mode is already resolved via hierarchy
        current_mode = self.resolver.get_effective_risk_mode()
        if current_mode and not force_interactive:
            # Mode already configured, return it
            return current_mode, PersistenceOption.PROJECT
        
        # Get suggestion
        suggested_mode, reasoning = self.suggest_mode()
        
        # Interactive prompt
        print("\n" + "="*60)
        print("SkillWeave Risk Mode Selection")
        print("="*60)
        print()
        print(f"Project: {self.project_root}")
        print()
        print("Analysis:")
        analysis = self.analyze_project()
        if analysis["has_existing_config"]:
            print(f"  • Existing config: {analysis['config_mode'] or 'not set'}")
        print(f"  • Git repository: {'yes' if analysis['has_git'] else 'no'}")
        print(f"  • File count: {analysis['file_count']}")
        print(f"  • Project size: {'large' if analysis['is_large_project'] else 'medium' if analysis['file_count'] > 10 else 'small'}")
        print()
        print(f"Suggestion: {suggested_mode.value.upper()} mode")
        print(f"Reasoning: {reasoning}")
        print()
        print("Available modes:")
        print("  1. CONSERVATIVE - Maximum safety, explicit approvals, strict validation")
        print("  2. MEDIUM       - Balanced approach, standard safety checks")
        print("  3. UNICORN      - Optimistic, minimal confirmations, maximum speed")
        print()
        
        while True:
            try:
                choice = input(f"Select mode (1-3, or press Enter for {suggested_mode.value}): ").strip()
                if not choice:
                    selected_mode = suggested_mode
                    break
                
                choice_map = {"1": RiskMode.CONSERVATIVE, "2": RiskMode.MEDIUM, "3": RiskMode.UNICORN}
                if choice in choice_map:
                    selected_mode = choice_map[choice]
                    break
                else:
                    print("Invalid choice. Please enter 1, 2, or 3.")
            except (EOFError, KeyboardInterrupt):
                print("\nSelection cancelled. Using suggested mode.")
                selected_mode = suggested_mode
                break
        
        # Persistence option
        print()
        print("Persistence options:")
        print("  1. Temporary - Use for current session only (no config changes)")
        print("  2. Project   - Save to project's .skillweave/config.yaml")
        print("  3. Global    - Save to global ~/.skillweave/config.yaml")
        print()
        
        while True:
            try:
                if prefer_persistent:
                    default_choice = "2"
                    default_text = "project"
                else:
                    default_choice = "1"
                    default_text = "temporary"
                
                persistence_choice = input(f"Select persistence (1-3, or Enter for {default_text}): ").strip()
                if not persistence_choice:
                    persistence_choice = default_choice
                
                persistence_map = {
                    "1": PersistenceOption.TEMPORARY,
                    "2": PersistenceOption.PROJECT,
                    "3": PersistenceOption.GLOBAL,
                }
                if persistence_choice in persistence_map:
                    persistence = persistence_map[persistence_choice]
                    break
                else:
                    print("Invalid choice. Please enter 1, 2, or 3.")
            except (EOFError, KeyboardInterrupt):
                print("\nUsing default persistence option.")
                persistence = PersistenceOption.PROJECT if prefer_persistent else PersistenceOption.TEMPORARY
                break
        
        # Save if persistent
        if persistence != PersistenceOption.TEMPORARY:
            self.save_mode(selected_mode, persistence)
        
        print()
        print(f"Selected: {selected_mode.value.upper()} mode ({persistence.value} storage)")
        print("="*60)
        
        return selected_mode, persistence
    
    def save_mode(self, mode: RiskMode, persistence: PersistenceOption) -> None:
        """
        Save selected mode to configuration.
        
        Args:
            mode: RiskMode to save
            persistence: Where to save it
        """
        if persistence == PersistenceOption.PROJECT:
            config = self.persistence.load_config()
            config.mode = mode
            self.persistence.save_config(config)
        elif persistence == PersistenceOption.GLOBAL:
            # Save to global config
            global_persistence = ensure_skillweave_folder(Path.home())
            config = global_persistence.load_config()
            config.mode = mode
            global_persistence.save_config(config)


def interactive_mode_selection(project_root: Optional[str] = None,
                              prefer_persistent: bool = True) -> RiskMode:
    """
    Convenience function for interactive mode selection.
    
    Args:
        project_root: Project root directory (defaults to current directory)
        prefer_persistent: Whether to prefer persistent storage
    
    Returns:
        Selected risk mode
    """
    selector = InteractiveModeSelector(project_root)
    mode, _ = selector.interactive_select(prefer_persistent=prefer_persistent)
    return mode