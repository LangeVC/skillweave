"""Version-sync contract (SW1312-VERSION-TOPOLOGY-001).

Extends the original SW-SKILL-SYNC-001 contract so that runtime, bundle,
bundle member pins and every independently installable skill capability are
separate declared artifact roles, not one collapsed bundle version. The tests
here *derive* their expected surfaces and roles from ``.version.yaml`` rather
than hardcoding a second inventory: a new or removed ``skills/*/capability.yaml``
fails inventory validation until ``.version.yaml`` and bundle membership are
reconciled.

Snapshot drift is reported per distinct state, named explicitly:
``missing``, ``duplicate``, ``misclassified``, ``stale`` and
``same-version-different-inventory``. Each state is asserted separately so the
failure message names the exact condition instead of collapsing everything into
one ``!=``.

Nothing here touches the machine: every path is resolved from the repository
root and read from disk, never from ``~/.claude`` or ``~/.config``.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The roles a location entry may declare. Kept here as the classification
# authority so a typo in .version.yaml is a *misclassified* failure, loud and
# named, instead of silently ignored.
KNOWN_ROLES = ("runtime_product", "distribution_bundle", "bundle_member_pins", "skill_capability")


def _load_topology() -> dict:
    return yaml.safe_load((REPO_ROOT / ".version.yaml").read_text())


def _locations() -> list[dict]:
    return _load_topology()["locations"]


def _read_first_match(path: str, pattern: str) -> str | None:
    text = (REPO_ROOT / path).read_text()
    for line in text.splitlines():
        m = re.match(pattern, line)
        if m:
            return m.group(1)
    return None


def _all_skill_dirs() -> list[str]:
    skills = REPO_ROOT / "skills"
    return sorted(d.name for d in skills.iterdir() if (d / "capability.yaml").exists())


def _skill_entries() -> list[dict]:
    return [loc for loc in _locations() if loc.get("role") == "skill_capability"]


class TestVersionSnapshotSources:
    """Surfaces and roles are derived from .version.yaml, not hardcoded."""

    def test_source_of_truth_is_pyproject(self):
        assert _load_topology()["source_of_truth"] == "pyproject.toml"

    def test_locations_named_and_required_are_well_formed(self):
        for loc in _locations():
            assert "path" in loc and loc["path"], f"location missing path: {loc}"
            assert "role" in loc, f"location missing role: {loc}"
            assert "pattern" in loc, f"location missing pattern: {loc}"
            assert "required" in loc, f"location missing required: {loc}"

    def test_every_role_is_one_of_the_known_classifications(self):
        unknown = [loc for loc in _locations() if loc["role"] not in KNOWN_ROLES]
        assert unknown == [], f"misclassified role(s): {[u['role'] for u in unknown]}"

    def test_exactly_one_runtime_and_one_bundle_and_one_pin_surface(self):
        roles = Counter(loc["role"] for loc in _locations())
        assert roles["runtime_product"] == 1, f"runtime_product count {roles['runtime_product']}"
        assert roles["distribution_bundle"] == 1, f"distribution_bundle count {roles['distribution_bundle']}"
        assert roles["bundle_member_pins"] == 1, f"bundle_member_pins count {roles['bundle_member_pins']}"

    def test_specific_paths_map_to_specific_roles(self):
        by_path = {loc["path"]: loc["role"] for loc in _locations()}
        assert by_path["pyproject.toml"] == "runtime_product", (
            f"pyproject.toml classified {by_path['pyproject.toml']!r}, not runtime_product"
        )
        # distribution_bundle and bundle_member_pins share capability.yaml but
        # must be distinguishable by role.
        cap_roles = {loc["role"] for loc in _locations() if loc["path"] == "capability.yaml"}
        assert cap_roles == {"distribution_bundle", "bundle_member_pins"}, (
            f"capability.yaml roles are {sorted(cap_roles)!r}"
        )
        for loc in _skill_entries():
            assert loc["path"].startswith("skills/") and loc["role"] == "skill_capability"
        assert all(
            loc["role"] == "skill_capability" for loc in _skill_entries()
        ), "a skills/*/capability.yaml is not classified as skill_capability"


class TestInventoryAgainstSkillTree:
    """Every shipped skill appears in the declaration; the declaration never
    drifts from the on-disk skill inventory."""

    def test_every_shipped_skill_has_a_declared_skill_capability(self):
        declared = {loc["path"] for loc in _skill_entries()}
        on_disk = {f"skills/{d}/capability.yaml" for d in _all_skill_dirs()}
        missing = on_disk - declared
        assert missing == set(), f"missing skill_capability declarations: {sorted(missing)}"

    def test_no_declared_skill_capability_lacks_an_on_disk_manifest(self):
        declared = {loc["path"] for loc in _skill_entries()}
        on_disk = {f"skills/{d}/capability.yaml" for d in _all_skill_dirs()}
        stale = declared - on_disk
        assert stale == set(), f"stale skill_capability declarations (no on-disk file): {sorted(stale)}"

    def test_no_duplicate_skill_capability_paths(self):
        paths = [loc["path"] for loc in _skill_entries()]
        dupes = [p for p, n in Counter(paths).items() if n > 1]
        assert dupes == [], f"duplicate skill_capability declarations: {sorted(dupes)}"


class TestBundlePinsMatchOnDiskSkills:
    """Bundle capabilities[] entries are pins to on-disk skill artifacts
    (name + source + version), not the authority over those skills."""

    def _bundle_capabilities(self) -> list[dict]:
        return yaml.safe_load((REPO_ROOT / "capability.yaml").read_text())["capabilities"]

    def _skill_by_name(self) -> dict[str, dict]:
        out = {}
        for d in _all_skill_dirs():
            cap = yaml.safe_load((REPO_ROOT / "skills" / d / "capability.yaml").read_text())
            out[cap["name"]] = cap
        return out

    def test_every_bundle_pin_names_an_on_disk_skill_with_matching_source(self):
        skills = self._skill_by_name()
        for entry in self._bundle_capabilities():
            name = entry["name"]
            assert name in skills, f"bundle pin {name} has no on-disk skill"
            expected_source = f"./skills/{name}"
            assert entry["source"] == expected_source, (
                f"bundle pin {name} source {entry['source']!r} != on-disk {expected_source!r}"
            )

    def test_bundle_pin_version_matches_on_disk_skill_version(self):
        skills = self._skill_by_name()
        for entry in self._bundle_capabilities():
            name = entry["name"]
            on_disk = skills[name]["version"]
            assert entry["version"] == on_disk, (
                f"bundle pin {name} version {entry['version']!r} != on-disk skill {on_disk!r}"
            )


class TestLockstepPolicy:
    """Under the declared lockstep policy, every surface carries one version."""

    def test_release_policy_is_lockstep(self):
        assert _load_topology()["release_policy"] == "lockstep"

    def test_all_surfaces_share_the_runtime_version(self):
        topo = _load_topology()
        runtime = _read_first_match(
            "pyproject.toml", r'^version\s*=\s*"(\d+\.\d+\.\d+)"'
        )
        assert runtime is not None, "pyproject.toml has no version"
        assert re.fullmatch(r"\d+\.\d+\.\d+", runtime), f"not semver: {runtime!r}"

        skill_by_disk = {}
        for d in _all_skill_dirs():
            cap = yaml.safe_load((REPO_ROOT / "skills" / d / "capability.yaml").read_text())
            skill_by_disk[d] = cap

        for loc in _locations():
            value = _read_first_match(loc["path"], loc["pattern"])
            assert value is not None, f"no match for {loc['role']} at {loc['path']}"
            assert value == runtime, (
                f"{loc['role']} at {loc['path']} is {value!r}, not runtime {runtime!r} "
                f"(lockstep policy violated)"
            )

    def test_same_version_cannot_hide_a_different_inventory(self):
        # The lockstep version matches, but two inventories must still agree on
        # their member set. Same version with a different skill list is a real
        # failure state, detected here as same-version-different-inventory.
        bundle_members = {
            e["name"] for e in self._bundle_capabilities()
        }
        declared_skills = {
            loc["path"].split("/")[1]
            for loc in _skill_entries()
            if loc["path"].startswith("skills/")
        }
        assert bundle_members == declared_skills, (
            f"same-version-different-inventory: bundle members "
            f"{sorted(bundle_members)} != declared skills {sorted(declared_skills)}"
        )

    def _bundle_capabilities(self):
        return yaml.safe_load((REPO_ROOT / "capability.yaml").read_text())["capabilities"]
