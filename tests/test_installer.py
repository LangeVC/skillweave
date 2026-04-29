"""Tests for the Capacium-first SkillWeave installer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from skillweave.installer import SKILLS, SkillWeaveInstaller


def make_source_repo(root: Path, version: str = "0.7.0") -> Path:
    (root / "skills").mkdir(parents=True)
    (root / "capability.yaml").write_text(
        f"kind: bundle\nname: skillweave\nversion: {version}\ndescription: test bundle\nauthor: SkillWeave Team\n"
    )
    (root / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')

    for skill in SKILLS:
        skill_dir = root / "skills" / skill
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {skill}\n")

    return root


def create_capacium_packages(home: Path, version: str) -> None:
    packages_root = home / ".capacium" / "packages" / "global"
    for skill in SKILLS:
        skill_dir = packages_root / skill / version
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(f"# {skill}\n")


def install_capacium_managed_links(home: Path, version: str) -> None:
    packages_root = home / ".capacium" / "packages" / "global"

    opencode_dir = home / ".config" / "opencode" / "commands"
    opencode_dir.mkdir(parents=True, exist_ok=True)
    claude_dir = home / ".claude" / "skills"
    claude_dir.mkdir(parents=True, exist_ok=True)
    gemini_dir = home / ".gemini" / "capabilities"
    gemini_dir.mkdir(parents=True, exist_ok=True)

    for skill in SKILLS:
        package_dir = packages_root / skill / version
        (opencode_dir / f"{skill}.md").symlink_to(package_dir / "SKILL.md")
        (claude_dir / skill).symlink_to(package_dir)
        (gemini_dir / skill).symlink_to(package_dir)


def test_latest_installed_bundle_dir_uses_highest_version(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    bundle_root = tmp_path / ".capacium" / "packages" / "global" / "skillweave"
    (bundle_root / "0.7.2").mkdir(parents=True)
    (bundle_root / "0.7.10").mkdir(parents=True)

    installer = SkillWeaveInstaller()
    latest = installer.latest_installed_bundle_dir()

    assert latest is not None
    assert latest.name == "0.7.10"


def test_install_all_prefers_capacium_and_bridges_codex(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    source_root = make_source_repo(tmp_path / "repo")

    commands = []

    installer = SkillWeaveInstaller()
    monkeypatch.setattr(installer, "cap_binary", "/usr/local/bin/cap")

    def fake_run_cap(args, allow_failure=False):
        commands.append(args)
        if args[0] == "install":
            create_capacium_packages(tmp_path, "0.7.0")
            install_capacium_managed_links(tmp_path, "0.7.0")
        return True

    monkeypatch.setattr(installer, "run_cap", fake_run_cap)

    codex_dir = tmp_path / ".codex" / "skills"
    codex_dir.mkdir(parents=True)

    results = installer.install_all(source_dir=source_root)

    assert commands[0][:2] == ["remove", "skillweave"]
    assert commands[1][:2] == ["install", "skillweave"]
    assert results["opencode"] == len(SKILLS)
    assert results["claude-code"] == len(SKILLS)
    assert results["codex"] == len(SKILLS)
    assert results["gemini-cli"] == len(SKILLS)

    codex_link = codex_dir / "skillweave-blueprint"
    assert codex_link.is_symlink()
    assert codex_link.resolve() == tmp_path / ".capacium" / "packages" / "global" / "skillweave-blueprint" / "0.7.0"


def test_install_all_falls_back_without_capacium(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    source_root = make_source_repo(tmp_path / "repo")

    installer = SkillWeaveInstaller()
    monkeypatch.setattr(installer, "cap_binary", None)

    claude_dir = tmp_path / ".claude" / "skills"
    claude_dir.mkdir(parents=True)

    results = installer.install_all(source_dir=source_root)

    assert results["claude-code"] == len(SKILLS)
    claude_link = claude_dir / "skillweave-blueprint"
    assert claude_link.is_symlink()
    assert claude_link.resolve() == tmp_path / ".skillweave" / "skills" / "skillweave-blueprint"
