"""Version-sync contract (SW-SKILL-SYNC-001).

One release line reports one version. ``pyproject.toml`` is the single source of
truth (see `.version.yaml`); the bundle manifest (``capability.yaml``), the
``capabilities[]`` list it names, and every skill's own ``capability.yaml`` must
all report the same compatible version. An installed skill therefore reports the
same version as the runtime, and the drift recorded in
REALITY-BASELINE §2 ("runtime 1.3.6, skills 1.3.0") is closed and pinned.

Nothing here touches the machine: every path is resolved from the repository
root and read from disk, never from ``~/.claude`` or ``~/.config``.
"""

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml has no project version"
    return match.group(1)


def _skill_dirs() -> list[Path]:
    skills = REPO_ROOT / "skills"
    return sorted(d for d in skills.iterdir() if (d / "capability.yaml").exists())


class TestVersionSync:
    """Runtime, bundle, and skill-package versions agree on one release line."""

    def test_pyproject_version_is_136(self):
        assert _pyproject_version() == "1.3.6"

    def test_bundle_manifest_version_matches_pyproject(self):
        manifest = yaml.safe_load((REPO_ROOT / "capability.yaml").read_text())
        assert manifest["version"] == _pyproject_version()

    def test_every_skill_capability_matches_pyproject(self):
        expected = _pyproject_version()
        for skill_dir in _skill_dirs():
            cap = yaml.safe_load((skill_dir / "capability.yaml").read_text())
            assert cap["version"] == expected, (
                f"{skill_dir.name}/capability.yaml version {cap['version']!r} "
                f"!= runtime {expected!r}"
            )

    def test_bundle_capabilities_list_matches_skill_versions(self):
        manifest = yaml.safe_load((REPO_ROOT / "capability.yaml").read_text())
        by_name = {
            yaml.safe_load((d / "capability.yaml").read_text())["name"]: d
            for d in _skill_dirs()
        }
        expected = _pyproject_version()
        for entry in manifest["capabilities"]:
            name = entry["name"]
            skill_dir = by_name[name]
            on_disk = yaml.safe_load((skill_dir / "capability.yaml").read_text())["version"]
            assert entry["version"] == on_disk == expected, (
                f"{name}: capability.yaml entry {entry['version']!r} vs disk "
                f"{on_disk!r} vs runtime {expected!r}"
            )

    def test_no_skill_reports_a_stale_130_version(self):
        for skill_dir in _skill_dirs():
            cap = yaml.safe_load((skill_dir / "capability.yaml").read_text())
            assert cap["version"] != "1.3.0", (
                f"{skill_dir.name} still reports the drifted 1.3.0"
            )
