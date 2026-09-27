"""
Tests for skill catalog integrity.

The catalog is declared in exactly three places. This module proves they agree
without hardcoding a skill count anywhere:

1. ``capability.yaml`` — the bundle manifest's ``capabilities:`` block (the SSOT).
2. ``installer.py`` — the module-level ``SKILLS`` list the installer copies.
3. ``skills/*/SKILL.md`` — the capability each on-disk skill directory declares
   in its frontmatter ``name:``.

Every assertion is a set comparison between those surfaces, so adding one skill
directory plus its capability.yaml entry (and the matching installer entry)
requires no edit to this file. ``TestAddedSkillRequiresNoTestEdit`` demonstrates
that by building the current catalog, adding one skill, and re-running the same
comparison.
"""

import re
import shutil
import sys
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
CAPABILITY_YAML = REPO_ROOT / "capability.yaml"
INSTALLER_PY = REPO_ROOT / "src" / "skillweave" / "installer.py"


def _parse_capability_names() -> list[str]:
    with open(CAPABILITY_YAML) as f:
        data = yaml.safe_load(f)
    return [c["name"] for c in data["capabilities"]]


def _parse_installer_skills() -> list[str]:
    content = INSTALLER_PY.read_text()
    match = re.search(r"^SKILLS\s*=\s*\[(.*?)\]", content, re.DOTALL | re.MULTILINE)
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


def _discovered_skill_names() -> set[str]:
    names = set()
    for skill_dir in _discover_skill_dirs():
        name = _parse_frontmatter_name(skill_dir / "SKILL.md")
        if name:
            names.add(name)
    return names


def _catalog_surfaces() -> tuple[set[str], set[str], set[str]]:
    """Return (declared, installed, discovered) skill-name sets."""
    return (
        set(_parse_capability_names()),
        set(_parse_installer_skills()),
        _discovered_skill_names(),
    )


class TestCatalogAgreement:
    """The declared catalog, installer registry and on-disk skills must agree."""

    def test_catalog_is_not_empty(self):
        declared, installed, discovered = _catalog_surfaces()
        assert declared, "capability.yaml declares no capabilities"
        assert installed, "installer.py declares no SKILLS entries"
        assert discovered, "no SKILL.md files found under skills/"

    def test_declared_catalog_matches_installer_registry(self):
        declared, installed, _ = _catalog_surfaces()
        assert declared == installed, (
            "capability.yaml and installer.py SKILLS disagree.\n"
            f"Only in capability.yaml: {sorted(declared - installed)}\n"
            f"Only in installer.py: {sorted(installed - declared)}"
        )

    def test_declared_catalog_matches_discovered_skills(self):
        declared, _, discovered = _catalog_surfaces()
        assert declared == discovered, (
            "capability.yaml and skills/*/SKILL.md disagree.\n"
            f"Declared but no SKILL.md on disk: {sorted(declared - discovered)}\n"
            f"SKILL.md on disk but not declared: {sorted(discovered - declared)}"
        )

    def test_installer_registry_matches_discovered_skills(self):
        _, installed, discovered = _catalog_surfaces()
        assert installed == discovered, (
            "installer.py SKILLS and skills/*/SKILL.md disagree.\n"
            f"Installed but no SKILL.md on disk: {sorted(installed - discovered)}\n"
            f"SKILL.md on disk but not installed: {sorted(discovered - installed)}"
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


class TestAddedSkillRequiresNoTestEdit:
    """A new skill directory + capability entry must pass with no edit here."""

    NEW_SKILL = "skillweave-added-fixture"

    def test_one_added_skill_needs_no_test_edit(self, tmp_path, monkeypatch):
        baseline = len(set(_parse_capability_names()))
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()

        # Mirror the current on-disk catalog byte-for-byte (preserves the
        # dir-name != skill-name mapping, e.g. skills/skillweave -> skillweave-entry).
        for src in _discover_skill_dirs():
            dst = skills_dir / src.name
            dst.mkdir()
            shutil.copy2(src / "SKILL.md", dst / "SKILL.md")

        # Add exactly ONE new skill directory ...
        new_dir = skills_dir / self.NEW_SKILL
        new_dir.mkdir()
        (new_dir / "SKILL.md").write_text(
            f"---\nname: {self.NEW_SKILL}\n---\n\n# {self.NEW_SKILL}\n"
        )

        # ... plus its capability.yaml entry ...
        data = yaml.safe_load(CAPABILITY_YAML.read_text())
        data["capabilities"].append(
            {
                "name": self.NEW_SKILL,
                "source": f"./skills/{self.NEW_SKILL}",
                "version": data["version"],
            }
        )
        cap = tmp_path / "capability.yaml"
        cap.write_text(yaml.safe_dump(data))

        # ... plus the matching installer entry.
        installer = tmp_path / "installer.py"
        installer.write_text(
            INSTALLER_PY.read_text().replace(
                "SKILLS = [", f'SKILLS = [\n    "{self.NEW_SKILL}",', 1
            )
        )

        monkeypatch.setattr(sys.modules[__name__], "SKILLS_DIR", skills_dir)
        monkeypatch.setattr(sys.modules[__name__], "CAPABILITY_YAML", cap)
        monkeypatch.setattr(sys.modules[__name__], "INSTALLER_PY", installer)

        declared, installed, discovered = _catalog_surfaces()
        assert declared == installed == discovered
        assert self.NEW_SKILL in declared
        assert len(declared) == baseline + 1


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
