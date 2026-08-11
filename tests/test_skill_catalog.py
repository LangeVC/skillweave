"""
Tests for skill catalog integrity — canonical names, duplicate detection,
unregistered SKILL.md files, and relic removal verification.
"""

import os
import re
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
CAPABIITY_YAML = REPO_ROOT / "capability.yaml"
INSTALLER_PY = REPO_ROOT / "src" / "skillweave" / "installer.py"


def _parse_capability_names() -> list[str]:
    with open(CAPABIITY_YAML) as f:
        data = yaml.safe_load(f)
    return [c["name"] for c in data["capabilities"]]


def _parse_installer_skills() -> list[str]:
    content = INSTALLER_PY.read_text()
    match = re.search(r"SKILLS\s*=\s*\[(.*?)\]", content, re.DOTALL)
    if not match:
        return []
    names = re.findall(r'"([^"]+)"', match.group(1))
    return names


def _discover_skill_dirs() -> list[Path]:
    return sorted(
        d for d in SKILLS_DIR.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


def _parse_frontmatter_name(skill_md: Path) -> str | None:
    content = skill_md.read_text()
    match = re.search(r"^name:\s*(\S+)", content, re.MULTILINE)
    return match.group(1) if match else None


class TestSkillCatalogCount:
    """Verify exactly 13 canonical skills in capability.yaml and installer.py."""

    EXPECTED_COUNT = 13

    def test_capability_yaml_has_13_skills(self):
        names = _parse_capability_names()
        assert len(names) == self.EXPECTED_COUNT, (
            f"capability.yaml has {len(names)} capabilities, expected {self.EXPECTED_COUNT}: {names}"
        )

    def test_installer_skills_has_13_entries(self):
        names = _parse_installer_skills()
        assert len(names) == self.EXPECTED_COUNT, (
            f"installer.py SKILLS has {len(names)} entries, expected {self.EXPECTED_COUNT}: {names}"
        )

    def test_capability_and_installer_names_match(self):
        cap_names = set(_parse_capability_names())
        inst_names = set(_parse_installer_skills())
        assert cap_names == inst_names, (
            f"capability.yaml and installer.py SKILLS mismatch.\n"
            f"Only in capability.yaml: {cap_names - inst_names}\n"
            f"Only in installer.py: {inst_names - cap_names}"
        )


class TestSkillCatalogDuplicates:
    """Verify zero duplicate name values across all SKILL.md files."""

    def test_no_duplicate_frontmatter_names(self):
        names = {}
        for skill_dir in _discover_skill_dirs():
            skill_md = skill_dir / "SKILL.md"
            name = _parse_frontmatter_name(skill_md)
            if name is None:
                continue
            if name in names:
                raise AssertionError(
                    f"Duplicate name '{name}' found in:\n"
                    f"  {names[name]}\n"
                    f"  {skill_md}"
                )
            names[name] = str(skill_md)
        assert len(names) >= 1, "No SKILL.md files found"


class TestSkillCatalogRegistration:
    """Verify every SKILL.md is registered, no unregistered skill files exist."""

    def test_all_skill_dirs_are_registered(self):
        registered = set(_parse_capability_names())
        skill_dirs = set()
        for skill_dir in _discover_skill_dirs():
            name = _parse_frontmatter_name(skill_dir / "SKILL.md")
            if name:
                skill_dirs.add(name)
        unregistered = skill_dirs - registered
        assert not unregistered, (
            f"Unregistered SKILL.md files found (not in capability.yaml): {unregistered}"
        )

    def test_no_registered_skill_is_missing_directory(self):
        registered = set(_parse_capability_names())
        skill_dirs = set()
        for skill_dir in _discover_skill_dirs():
            name = _parse_frontmatter_name(skill_dir / "SKILL.md")
            if name:
                skill_dirs.add(name)
        missing = registered - skill_dirs
        assert not missing, (
            f"Registered skills with no SKILL.md on disk: {missing}"
        )


class TestLaunchRelicRemoval:
    """Verify the skills/launch/ relic directory no longer exists."""

    def test_launch_directory_does_not_exist(self):
        launch_dir = SKILLS_DIR / "launch"
        assert not launch_dir.exists(), (
            f"Relic directory still exists: {launch_dir}. It should have been removed."
        )

    def test_no_launch_skill_md_on_disk(self):
        launch_skill = SKILLS_DIR / "launch" / "SKILL.md"
        assert not launch_skill.exists(), (
            f"Relic SKILL.md still exists: {launch_skill}. It should have been removed."
        )
