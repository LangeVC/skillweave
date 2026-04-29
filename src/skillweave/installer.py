#!/usr/bin/env python3
"""
SkillWeave installer with Capacium as the primary package manager.

Capacium owns bundle installation and the native skill adapters it already
supports. SkillWeave keeps a thin compatibility bridge for clients that still
consume local skill directories outside Capacium's native skill adapter set.
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .persistence import SkillWeavePersistence

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentTarget:
    name: str
    target_type: str
    path: str
    extension: str
    install_mode: str


AGENT_CONFIG = [
    AgentTarget("opencode", "single", "~/.config/opencode/commands", ".md", "capacium"),
    AgentTarget("claude-code", "directory", "~/.claude/skills", "", "capacium"),
    AgentTarget("codex", "directory", "~/.codex/skills", "", "bridge"),
    AgentTarget("gemini-cli", "directory", "~/.gemini/capabilities", "", "capacium"),
    AgentTarget("antigravity", "directory", "~/.gemini/antigravity/skills", "", "bridge"),
    AgentTarget("openclaw", "directory", "~/.config/openclaw/skills", "", "bridge"),
    AgentTarget("aider", "directory", "~/.config/aider/skills", "", "bridge"),
    AgentTarget("windsurf", "directory", "~/.config/windsurf/skills", "", "bridge"),
    AgentTarget("qwen", "directory", "~/.qwen/skills", "", "bridge"),
]

SKILLS = [
    "skillweave-blueprint",
    "skillweave-promptchain-generate",
    "skillweave-promptchain-validate",
    "skillweave-promptchain-execute",
    "skillweave-releasechain",
    "skillweave-lifecycle",
    "skillweave-discovery",
    "skillweave-design",
    "skillweave-launch",
    "skillweave-post-release",
    "skillweave-repo-health",
    "skillweave-observe",
    "skillweave-council",
]

CAPACIUM_SPEC = "skillweave"
CAPACIUM_OWNER = "global"
CAPACIUM_MANAGED_AGENTS = {"opencode", "claude-code", "gemini-cli"}


class SkillWeaveInstaller:
    """Install SkillWeave through Capacium and bridge remaining skill clients."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.home = Path.home()
        self.global_config_dir = self.home / ".skillweave"
        self.legacy_skills_dir = self.global_config_dir / "skills"
        self.capacium_packages_root = self.home / ".capacium" / "packages" / CAPACIUM_OWNER
        self.cap_binary = shutil.which("cap")
        self.legacy_cleanup_paths = [
            self.home / ".agents" / "skills",
            self.home / ".gemini" / "skills",
        ]

    def expand_path(self, path: str) -> Path:
        """Expand user home and resolve path."""
        return Path(path).expanduser().resolve()

    def has_capacium(self) -> bool:
        return self.cap_binary is not None

    def detect_version(self, source_dir: Path) -> str:
        """Detect the current SkillWeave version from capability.yaml or pyproject."""
        manifest_path = source_dir / "capability.yaml"
        if manifest_path.exists():
            match = re.search(
                r'^version:\s*["\']?([^\n"\']+)["\']?\s*$',
                manifest_path.read_text(),
                re.MULTILINE,
            )
            if match:
                return match.group(1).strip()

        pyproject = source_dir / "pyproject.toml"
        if pyproject.exists():
            match = re.search(
                r'^version\s*=\s*["\']([^"\']+)["\']',
                pyproject.read_text(),
                re.MULTILINE,
            )
            if match:
                return match.group(1).strip()

        raise ValueError(f"Could not detect SkillWeave version from {source_dir}")

    def version_key(self, version: str) -> tuple:
        parts = []
        for part in version.split("."):
            if part.isdigit():
                parts.append(int(part))
            else:
                parts.append(part)
        return tuple(parts)

    def latest_installed_bundle_dir(self) -> Optional[Path]:
        bundle_root = self.capacium_packages_root / CAPACIUM_SPEC
        if not bundle_root.exists():
            return None

        versions = [path for path in bundle_root.iterdir() if path.is_dir()]
        if not versions:
            return None
        return max(versions, key=lambda path: self.version_key(path.name))

    def resolve_source_dir(self, source_dir: Optional[Path]) -> Path:
        if source_dir is not None:
            resolved = source_dir.expanduser().resolve()
            if not (resolved / "capability.yaml").exists():
                raise FileNotFoundError(f"Missing capability.yaml in {resolved}")
            return resolved

        cwd = Path.cwd().resolve()
        if (cwd / "capability.yaml").exists():
            return cwd

        installed_bundle = self.latest_installed_bundle_dir()
        if installed_bundle and (installed_bundle / "capability.yaml").exists():
            return installed_bundle

        raise FileNotFoundError(
            "Could not find a SkillWeave source directory. Run from the repository root "
            "or pass --source <path>."
        )

    def ensure_global_config(self) -> None:
        if self.dry_run:
            logger.info("Would ensure global config directory at %s", self.global_config_dir)
            return

        self.global_config_dir.mkdir(parents=True, exist_ok=True)
        self._create_global_config()
        logger.info("Global SkillWeave config ready at %s", self.global_config_dir)

    def _create_global_config(self) -> None:
        config_path = self.global_config_dir / "config.yaml"
        if config_path.exists():
            return

        config_text = """# SkillWeave Next Level Global Configuration
# This configuration provides defaults for all projects.
# Project-specific .skillweave/config.yaml overrides these settings.

mode: medium

features:
  checklist_execution: true
  design_thinking_lens: true
  community_patterns: false
  modular_templates: false
  capability_routing: false

overrides:
  global: true
  description: "Global SkillWeave configuration. Project-specific .skillweave/config.yaml overrides these settings."
"""
        config_path.write_text(config_text)
        logger.info("Created global config at %s", config_path)

    def copy_skills_from_source(self, source_dir: Path) -> None:
        """Legacy fallback when Capacium is unavailable."""
        source_skills = source_dir / "skills"
        if not source_skills.exists():
            raise FileNotFoundError(f"Skills directory not found: {source_skills}")

        if self.dry_run:
            logger.info("Would copy skills from %s to %s", source_skills, self.legacy_skills_dir)
            return

        self.legacy_skills_dir.mkdir(parents=True, exist_ok=True)
        for path in list(self.legacy_skills_dir.iterdir()):
            if path.is_symlink() or path.is_file():
                path.unlink()
            else:
                shutil.rmtree(path)

        for skill in SKILLS:
            source_skill = source_skills / skill
            if not source_skill.exists():
                logger.warning("Skill directory not found: %s", source_skill)
                continue
            shutil.copytree(source_skill, self.legacy_skills_dir / skill)

        logger.info("Copied %s skills to legacy cache at %s", len(SKILLS), self.legacy_skills_dir)

    def run_cap(self, args: list[str], allow_failure: bool = False) -> bool:
        if not self.cap_binary:
            raise RuntimeError("Capacium CLI is not available")

        cmd = [self.cap_binary, *args]
        pretty = " ".join(str(part) for part in cmd)

        if self.dry_run:
            logger.info("Would run: %s", pretty)
            return True

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout.strip():
            logger.info(result.stdout.strip())
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or pretty
            if allow_failure:
                logger.info("Ignoring Capacium command failure: %s", message)
                return False
            raise RuntimeError(message)
        return True

    def install_bundle_with_capacium(self, source_dir: Path) -> str:
        version = self.detect_version(source_dir)
        self.run_cap(["remove", CAPACIUM_SPEC, "--force"], allow_failure=True)
        self.run_cap(["install", CAPACIUM_SPEC, "--source", str(source_dir)])
        logger.info("Installed SkillWeave bundle via Capacium from %s", source_dir)
        return version

    def uninstall_bundle_with_capacium(self) -> None:
        if not self.has_capacium():
            return
        self.run_cap(["remove", CAPACIUM_SPEC, "--force"], allow_failure=True)

    def cleanup_legacy_duplicates(self) -> int:
        cleaned = 0
        for legacy_path in self.legacy_cleanup_paths:
            if not legacy_path.exists():
                continue
            for skill in SKILLS:
                target = legacy_path / skill
                if target.is_symlink() or target.is_file():
                    if not self.dry_run:
                        target.unlink()
                    cleaned += 1
                elif target.is_dir():
                    if not self.dry_run:
                        shutil.rmtree(target)
                    cleaned += 1
        if cleaned:
            logger.info("Removed %s legacy SkillWeave duplicates", cleaned)
        return cleaned

    def detect_agents(self) -> list[tuple[AgentTarget, Path]]:
        detected = []
        for target in AGENT_CONFIG:
            path = self.expand_path(target.path)
            if target.name == "opencode":
                detected.append((target, path))
                continue
            if path.exists():
                detected.append((target, path))
        return detected

    def agent_exists(self, target: AgentTarget, path: Path) -> bool:
        if target.name == "opencode":
            return True
        return path.exists()

    def target_for_skill(self, target: AgentTarget, path: Path, skill: str) -> Path:
        if target.target_type == "single":
            return path / f"{skill}{target.extension}"
        return path / skill

    def count_installed_skills(self, target: AgentTarget, path: Path) -> int:
        count = 0
        for skill in SKILLS:
            install_path = self.target_for_skill(target, path, skill)
            if install_path.exists() or install_path.is_symlink():
                count += 1
        return count

    def source_dir_for_skill(self, skill: str, version: str, use_capacium: bool) -> Path:
        if use_capacium:
            return self.capacium_packages_root / skill / version
        return self.legacy_skills_dir / skill

    def install_single_file(self, source_dir: Path, target_path: Path) -> bool:
        source_file = source_dir / "SKILL.md"
        if not source_file.exists():
            logger.warning("Missing SKILL.md for %s", source_dir.name)
            return False

        if self.dry_run:
            logger.info("Would create symlink: %s -> %s", target_path, source_file)
            return True

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists() or target_path.is_symlink():
            target_path.unlink()
        target_path.symlink_to(source_file)
        return True

    def install_directory(self, source_dir: Path, target_path: Path) -> bool:
        if not source_dir.exists():
            logger.warning("Missing skill directory: %s", source_dir)
            return False

        if self.dry_run:
            logger.info("Would create directory symlink: %s -> %s", target_path, source_dir)
            return True

        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists() or target_path.is_symlink():
            if target_path.is_symlink():
                target_path.unlink()
            else:
                shutil.rmtree(target_path)
        target_path.symlink_to(source_dir)
        return True

    def install_for_agent(
        self,
        target: AgentTarget,
        path: Path,
        version: str,
        use_capacium: bool,
    ) -> int:
        installed = 0
        for skill in SKILLS:
            source_dir = self.source_dir_for_skill(skill, version, use_capacium)
            target_path = self.target_for_skill(target, path, skill)
            if target.target_type == "single":
                success = self.install_single_file(source_dir, target_path)
            else:
                success = self.install_directory(source_dir, target_path)
            if success:
                installed += 1
        return installed

    def remove_for_agent(self, target: AgentTarget, path: Path) -> int:
        removed = 0
        for skill in SKILLS:
            target_path = self.target_for_skill(target, path, skill)
            if target_path.is_symlink() or target_path.is_file():
                if not self.dry_run:
                    target_path.unlink()
                removed += 1
            elif target_path.is_dir():
                if not self.dry_run:
                    shutil.rmtree(target_path)
                removed += 1
        return removed

    def interactive_select_bridge_agents(self, bridge_agents: list[tuple[AgentTarget, Path]]) -> Optional[set[str]]:
        if not bridge_agents:
            return set()

        print("Capacium-managed agents will be installed automatically: opencode, claude-code, gemini-cli")
        print("Select additional bridge agents for direct skill symlinks:")
        for index, (target, path) in enumerate(bridge_agents, start=1):
            status = "exists" if self.agent_exists(target, path) else "not found"
            print(f"  {index}. {target.name}: {path} ({status})")
        print("  all  = all detected bridge agents")
        print("  none = skip bridge agent symlinks")
        selection = input("> ").strip().lower()

        if selection == "all":
            return {target.name for target, path in bridge_agents if self.agent_exists(target, path)}
        if selection == "none":
            return set()

        selected: set[str] = set()
        for raw in selection.split(","):
            item = raw.strip()
            if not item.isdigit():
                continue
            index = int(item) - 1
            if 0 <= index < len(bridge_agents):
                target, path = bridge_agents[index]
                if self.agent_exists(target, path):
                    selected.add(target.name)
        return selected

    def install_all(
        self,
        source_dir: Optional[Path] = None,
        interactive: bool = False,
    ) -> dict[str, int]:
        source_root = self.resolve_source_dir(source_dir)
        version = self.detect_version(source_root)
        self.ensure_global_config()
        self.cleanup_legacy_duplicates()

        use_capacium = self.has_capacium()
        if use_capacium:
            logger.info("Using Capacium as the primary installer")
            version = self.install_bundle_with_capacium(source_root)
        else:
            logger.warning("Capacium CLI not found; falling back to direct skill cache install")
            self.copy_skills_from_source(source_root)

        detected = self.detect_agents()
        bridge_agents = [
            (target, path)
            for target, path in detected
            if target.install_mode == "bridge"
        ]
        selected_bridge_names: Optional[set[str]] = None
        if interactive:
            selected_bridge_names = self.interactive_select_bridge_agents(bridge_agents)

        results: dict[str, int] = {}
        for target, path in detected:
            if target.install_mode == "capacium" and use_capacium:
                results[target.name] = self.count_installed_skills(target, path)
                continue

            if target.install_mode == "bridge" and selected_bridge_names is not None:
                if target.name not in selected_bridge_names:
                    results[target.name] = self.count_installed_skills(target, path)
                    continue

            if not self.agent_exists(target, path):
                results[target.name] = 0
                continue

            installed = self.install_for_agent(target, path, version, use_capacium=use_capacium)
            results[target.name] = installed

        return results

    def uninstall_all(self) -> dict[str, int]:
        self.cleanup_legacy_duplicates()
        self.uninstall_bundle_with_capacium()

        removed: dict[str, int] = {}
        for target, path in self.detect_agents():
            if target.install_mode == "bridge":
                removed[target.name] = self.remove_for_agent(target, path)
            else:
                removed[target.name] = self.count_installed_skills(target, path) if self.dry_run else 0
        return removed

    def list_agents(self) -> None:
        print("SkillWeave Agent Detection")
        print("==========================")
        for target in AGENT_CONFIG:
            path = self.expand_path(target.path)
            status = "exists" if self.agent_exists(target, path) else "not found"
            print(f"  - {target.name}: {path} [{target.install_mode}] ({status})")

    def troubleshoot(self, source_dir: Optional[Path] = None) -> None:
        source_root = None
        try:
            source_root = self.resolve_source_dir(source_dir)
        except FileNotFoundError:
            pass

        print("SkillWeave Troubleshooting")
        print("==========================")
        print(f"Capacium available: {'yes' if self.has_capacium() else 'no'}")
        if source_root:
            print(f"Source root: {source_root}")
            print(f"Detected version: {self.detect_version(source_root)}")
        installed_bundle = self.latest_installed_bundle_dir()
        if installed_bundle:
            print(f"Installed Capacium bundle: {installed_bundle}")
        else:
            print("Installed Capacium bundle: not found")

        print("")
        for target in AGENT_CONFIG:
            path = self.expand_path(target.path)
            count = self.count_installed_skills(target, path) if self.agent_exists(target, path) else 0
            print(f"  - {target.name}: {count}/{len(SKILLS)} skills visible at {path}")

    def init_project(self, project_root: Optional[Path] = None) -> None:
        if project_root is None:
            project_root = Path.cwd()

        if self.dry_run:
            logger.info("Would initialize Next Level features in %s", project_root)
            return

        persistence = SkillWeavePersistence(str(project_root))
        persistence.ensure_folder_structure()
        logger.info("Initialized SkillWeave Next Level features in %s", project_root)
        logger.info("  Configuration: %s", persistence.skillweave_dir / "config.yaml")
        logger.info("  Subdirectories: %s", persistence.SUBDIRS)


def print_install_summary(results: dict[str, int]) -> None:
    print("\n" + "=" * 50)
    print("SkillWeave Installation Summary")
    print("=" * 50)
    total_installed = sum(results.values())
    print(f"Total skill instances: {total_installed}")
    for agent, count in results.items():
        print(f"  - {agent}: {count} skills")
    print()
    print("Installed skills:")
    for skill in SKILLS:
        print(f"  - {skill}")
    print()
    print("Capacium manages native bundle installation; compatibility bridges cover the remaining skill clients.")
    print("Run 'skillweave-install --init' in a project to initialize SkillWeave project folders.")
    print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description="SkillWeave installer")
    parser.add_argument("--dry-run", action="store_true", help="Simulate installation without making changes")
    parser.add_argument("--source", type=Path, help="Source directory containing capability.yaml")
    parser.add_argument("--init", action="store_true", help="Initialize Next Level features in current project")
    parser.add_argument("--list", dest="list_agents", action="store_true", help="List detected agents and exit")
    parser.add_argument("--list-agents", dest="list_agents", action="store_true", help="List detected agents and exit")
    parser.add_argument("--interactive", "-i", action="store_true", help="Prompt for bridge-agent selection")
    parser.add_argument("--uninstall", action="store_true", help="Uninstall SkillWeave")
    parser.add_argument("--update", action="store_true", help="Refresh installation from source")
    parser.add_argument("--troubleshoot", action="store_true", help="Show installation diagnostics")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    installer = SkillWeaveInstaller(dry_run=args.dry_run)

    if args.list_agents:
        installer.list_agents()
        return

    if args.init:
        installer.init_project()
        print("Next Level features initialized in current project.")
        return

    if args.troubleshoot:
        installer.troubleshoot(args.source)
        return

    if args.uninstall:
        removed = installer.uninstall_all()
        print("Removed SkillWeave compatibility links and requested Capacium bundle removal.")
        for agent, count in removed.items():
            if count:
                print(f"  - {agent}: removed {count} links")
        return

    results = installer.install_all(source_dir=args.source, interactive=args.interactive)
    print_install_summary(results)


if __name__ == "__main__":
    main()
