#!/usr/bin/env python3
"""
SkillWeave Next Level Installer.

This module provides a Python-based installer for SkillWeave skills across
multiple AI agent platforms. It also handles Next Level feature initialization.
"""

import os
import sys
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any

# Import SkillWeave Next Level components
from .persistence import SkillWeavePersistence, ensure_skillweave_folder

logger = logging.getLogger(__name__)

# Agent configuration
AGENT_CONFIG = [
    # (name, type, path, extension)
    ("opencode", "single", "~/.config/opencode/commands", ".md"),
    ("claude-code", "directory", "~/.claude/skills", ""),
    ("codex", "directory", "~/.codex/skills", ""),
    ("gemini-cli", "directory", "~/.gemini/skills", ""),
    ("antigravity", "directory", "~/.gemini/antigravity/skills", ""),
    ("openclaw", "directory", "~/.config/openclaw/skills", ""),
    ("aider", "directory", "~/.config/aider/skills", ""),
    ("windsurf", "directory", "~/.config/windsurf/skills", ""),
    ("qwen", "directory", "~/.qwen/skills", ""),
]

# SkillWeave skills to install
SKILLS = [
    "skillweave-blueprint",
    "skillweave-promptchain-generate",
    "skillweave-promptchain-validate",
    "skillweave-promptchain-execute",
    "skillweave-releasechain",
    "frontend-design",
    "skillweave-lifecycle",
    "skillweave-discovery",
    "skillweave-design",
    "skillweave-launch",
    "skillweave-post-release",
    "skillweave-repo-health",
    "skillweave-observe",
]

# Central repository directory
CENTRAL_REPO = Path.home() / ".skillweave"
CENTRAL_SKILLS_DIR = CENTRAL_REPO / "skills"

class SkillWeaveInstaller:
    """Installs SkillWeave skills across multiple AI agent platforms."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.central_repo = CENTRAL_REPO
        self.central_skills_dir = CENTRAL_SKILLS_DIR
        
    def expand_path(self, path: str) -> Path:
        """Expand user home and resolve path."""
        return Path(path).expanduser().resolve()
    
    def ensure_central_repo(self) -> None:
        """Ensure central repository directory exists with proper structure."""
        if self.dry_run:
            logger.info(f"Would create central repo at {self.central_repo}")
            return
        
        self.central_repo.mkdir(parents=True, exist_ok=True)
        self.central_skills_dir.mkdir(parents=True, exist_ok=True)
        
        # Create global Next Level configuration
        self._create_global_config()
        
        logger.info(f"Central repository ready at {self.central_repo}")
    
    def _create_global_config(self) -> None:
        """Create global configuration file with Next Level defaults."""
        config_path = self.central_repo / "config.yaml"
        if config_path.exists():
            return
        
        config = {
            "mode": "medium",
            "features": {
                "checklist_execution": True,
                "design_thinking_lens": True,
                "community_patterns": False,
                "modular_templates": False,
                "capability_routing": False,
            },
            "overrides": {
                "global": True,
                "description": "Global SkillWeave configuration. Project-specific .skillweave/config.yaml overrides these settings."
            }
        }
        
        import yaml
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"Created global config at {config_path}")
    
    def copy_skills_from_source(self, source_dir: Path) -> None:
        """Copy skills from source directory to central repository."""
        source_skills = source_dir / "skills"
        if not source_skills.exists():
            raise FileNotFoundError(f"Skills directory not found: {source_skills}")
        
        if self.dry_run:
            logger.info(f"Would copy skills from {source_skills} to {self.central_skills_dir}")
            return
        
        # Remove existing skills
        if self.central_skills_dir.exists():
            shutil.rmtree(self.central_skills_dir)
        self.central_skills_dir.mkdir(parents=True)
        
        # Copy each skill
        for skill in SKILLS:
            source_skill = source_skills / skill
            if not source_skill.exists():
                logger.warning(f"Skill directory not found: {source_skill}")
                continue
            
            dest_skill = self.central_skills_dir / skill
            shutil.copytree(source_skill, dest_skill)
            logger.info(f"Copied skill: {skill}")
        
        logger.info(f"Copied {len(SKILLS)} skills to central repository")
    
    def detect_agents(self) -> List[Tuple[str, str, Path, str]]:
        """Detect installed agents and return their configurations."""
        detected = []
        for name, typ, path_str, ext in AGENT_CONFIG:
            path = self.expand_path(path_str)
            # For opencode, we always consider it exists (will be created)
            if name == "opencode":
                detected.append((name, typ, path, ext))
                continue
            # For others, check if directory exists
            if path.exists():
                detected.append((name, typ, path, ext))
            else:
                logger.debug(f"Agent not found: {name} at {path}")
        return detected
    
    def install_for_agent(self, agent_name: str, agent_type: str, 
                         agent_path: Path, extension: str) -> int:
        """Install skills for a specific agent."""
        installed = 0
        
        for skill in SKILLS:
            source_dir = self.central_skills_dir / skill
            if not source_dir.exists():
                logger.warning(f"Skill source not found: {source_dir}")
                continue
            
            if agent_type == "single":
                target = agent_path / f"{skill}{extension}"
                source_file = source_dir / "SKILL.md"
                if not source_file.exists():
                    continue
                self._install_single_file(source_file, target)
            else:  # directory
                target = agent_path / skill
                self._install_directory(source_dir, target)
            
            installed += 1
        
        return installed
    
    def _install_single_file(self, source: Path, target: Path) -> None:
        """Install a skill as a single file (symlink)."""
        if self.dry_run:
            logger.info(f"Would create symlink: {target} -> {source}")
            return
        
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        
        target.symlink_to(source)
        logger.debug(f"Created symlink: {target} -> {source}")
    
    def _install_directory(self, source: Path, target: Path) -> None:
        """Install a skill as a directory (symlink)."""
        if self.dry_run:
            logger.info(f"Would create directory symlink: {target} -> {source}")
            return
        
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            if target.is_symlink():
                target.unlink()
            else:
                shutil.rmtree(target)
        
        target.symlink_to(source)
        logger.debug(f"Created directory symlink: {target} -> {source}")
    
    def install_all(self, source_dir: Optional[Path] = None) -> Dict[str, int]:
        """
        Install skills for all detected agents.
        
        Returns:
            Dictionary mapping agent names to number of skills installed.
        """
        if source_dir is None:
            # Assume we're running from the SkillWeave repository root
            source_dir = Path(__file__).parent.parent.parent
        
        logger.info(f"Installing from source: {source_dir}")
        
        # Ensure central repository exists
        self.ensure_central_repo()
        
        # Copy skills from source to central repository
        self.copy_skills_from_source(source_dir)
        
        # Detect agents
        agents = self.detect_agents()
        logger.info(f"Detected {len(agents)} agents")
        
        # Install for each agent
        results = {}
        for name, typ, path, ext in agents:
            logger.info(f"Installing for agent: {name}")
            installed = self.install_for_agent(name, typ, path, ext)
            results[name] = installed
            logger.info(f"Installed {installed} skills for {name}")
        
        # If no agents detected, install to opencode as default
        if not agents:
            logger.warning("No agents detected. Installing to opencode as default.")
            # Find opencode config
            for name, typ, path, ext in AGENT_CONFIG:
                if name == "opencode":
                    installed = self.install_for_agent(name, typ, path, ext)
                    results[name] = installed
                    logger.info(f"Installed {installed} skills for {name} (default)")
                    break
        
        return results
    
    def init_project(self, project_root: Optional[Path] = None) -> None:
        """Initialize Next Level features in a project."""
        if project_root is None:
            project_root = Path.cwd()
        
        if self.dry_run:
            logger.info(f"Would initialize Next Level features in {project_root}")
            return
        
        # Use SkillWeavePersistence to create folder structure
        persistence = SkillWeavePersistence(str(project_root))
        persistence.ensure_folder_structure()
        
        logger.info(f"Initialized SkillWeave Next Level features in {project_root}")
        logger.info(f"  Configuration: {persistence.skillweave_dir / 'config.yaml'}")
        logger.info(f"  Subdirectories: {persistence.SUBDIRS}")

def main():
    """Command-line interface."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="SkillWeave Next Level Installer"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simulate installation without making changes"
    )
    parser.add_argument(
        "--source", type=Path,
        help="Source directory containing skills (default: repository root)"
    )
    parser.add_argument(
        "--init", action="store_true",
        help="Initialize Next Level features in current project"
    )
    parser.add_argument(
        "--list-agents", action="store_true",
        help="List detected agents and exit"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    
    installer = SkillWeaveInstaller(dry_run=args.dry_run)
    
    if args.list_agents:
        agents = installer.detect_agents()
        print("Detected agents:")
        for name, typ, path, ext in agents:
            print(f"  - {name}: {path} ({typ})")
        sys.exit(0)
    
    if args.init:
        installer.init_project()
        print("Next Level features initialized in current project.")
        sys.exit(0)
    
    # Default action: install skills
    results = installer.install_all(args.source)
    
    # Print summary
    print("\n" + "="*50)
    print("SkillWeave Installation Summary")
    print("="*50)
    total_installed = sum(results.values())
    print(f"Total skill instances: {total_installed}")
    for agent, count in results.items():
        print(f"  - {agent}: {count} skills")
    print()
    print("Installed skills:")
    for skill in SKILLS:
        print(f"  - {skill}")
    print()
    print("Next Level features are ready to use.")
    print("Run 'skillweave-install --init' in a project to initialize.")
    print("="*50)

if __name__ == "__main__":
    main()