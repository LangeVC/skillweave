"""Release-topology contract (SW1312-VERSION-TOPOLOGY-001).

Where ``tests/unit/test_version_sync.py`` proves the snapshot agrees with
itself on the *current* tree, this module proves the *release* behaviour:
the product tag binds to the runtime source, bundle and skill artifacts are
verified under the declared lockstep policy, CHANGELOG prose stays outside any
automatic bump, and a 1.3.11-to-1.3.12 rehearsal shows that trusting only the
old two declared locations fails red while the expanded declaration reaches
every surface.

Hermetic: reads the tree, writes only to the pytest ``tmp_path``.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_topology(repo: Path = REPO_ROOT) -> dict:
    return yaml.safe_load((repo / ".version.yaml").read_text())


def _read(path: Path, pattern: str) -> str | None:
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        m = re.match(pattern, line)
        if m:
            return m.group(1)
    return None


def _version_surfaces(repo: Path, topo: dict) -> dict[str, str]:
    """Return {role/or-path: version} for every declared location."""
    out: dict[str, str] = {}
    for loc in topo["locations"]:
        v = _read(repo / loc["path"], loc["pattern"])
        out[loc["path"]] = v
    return out


# ── Criterion 7: tag binding ────────────────────────────────────────────────


class TestTagBinding:
    def test_product_tag_binds_to_runtime_source(self):
        topo = _load_topology()
        # The tag is derived from the runtime source, which is the declared
        # source_of_truth and the runtime_product location.
        assert topo["source_of_truth"] == "pyproject.toml"
        runtime = None
        for loc in topo["locations"]:
            if loc["role"] == "runtime_product":
                runtime = _read(REPO_ROOT / loc["path"], loc["pattern"])
        assert runtime is not None
        assert re.fullmatch(r"\d+\.\d+\.\d+", runtime), f"runtime not semver: {runtime!r}"

        # A product tag must equal the runtime version: no other surface may
        # carry a version that would produce a divergent tag under lockstep.
        for loc in topo["locations"]:
            v = _read(REPO_ROOT / loc["path"], loc["pattern"])
            assert v == runtime, (
                f"tag-binding failure: {loc['role']} at {loc['path']} is {v!r}, "
                f"runtime is {runtime!r}"
            )

    def test_every_skill_artifact_matches_the_product_tag(self):
        topo = _load_topology()
        runtime = None
        for loc in topo["locations"]:
            if loc["role"] == "runtime_product":
                runtime = _read(REPO_ROOT / loc["path"], loc["pattern"])
        for loc in topo["locations"]:
            if loc["role"] == "skill_capability":
                v = _read(REPO_ROOT / loc["path"], loc["pattern"])
                assert v == runtime, (
                    f"skill {loc['path']} version {v!r} diverges from product tag {runtime!r}"
                )

    def test_bundle_manifest_version_matches_the_product_tag(self):
        topo = _load_topology()
        runtime = None
        bundle = None
        for loc in topo["locations"]:
            if loc["role"] == "runtime_product":
                runtime = _read(REPO_ROOT / loc["path"], loc["pattern"])
            elif loc["role"] == "distribution_bundle":
                bundle = _read(REPO_ROOT / loc["path"], loc["pattern"])
        assert bundle == runtime, (
            f"bundle manifest version {bundle!r} diverges from product tag {runtime!r}"
        )


# ── Criterion 8: changelog boundary ─────────────────────────────────────────


class TestChangelogBoundary:
    def test_changelog_is_declared_unmanaged(self):
        topo = _load_topology()
        assert "changelog" in topo, "changelog exclusion must be stated explicitly"
        ch = topo["changelog"]
        assert ch.get("managed") is False, "CHANGELOG must not be auto-bumped"

    def test_changelog_path_is_not_among_locations(self):
        topo = _load_topology()
        paths = {loc["path"] for loc in topo["locations"]}
        assert topo["changelog"]["path"] not in paths, (
            "CHANGELOG.md must not be an automatic bump location"
        )


# ── Criterion 9: 1.3.11 → 1.3.12 rehearsal ─────────────────────────────────


def _apply_bump(repo: Path, topo: dict, old: str, new: str) -> None:
    """Reference bump: rewrite every declared location's matching version to
    ``new``. Consumes only .version.yaml locations (no hardcoded inventory)."""
    for loc in topo["locations"]:
        p = repo / loc["path"]
        text = p.read_text()
        match = re.search(loc["pattern"], text, re.MULTILINE)
        assert match, f"no match for {loc['role']} at {loc['path']}"
        # bundle_member_pins names a single path whose pattern matches many
        # lines (one per member); replace every occurrence. Other roles match
        # exactly one surface, so "all" is equivalent to "one".
        count = 0 if loc.get("role") == "bundle_member_pins" else 1
        new_text = re.sub(
            loc["pattern"],
            lambda m: m.group(0).replace(old, new),
            text,
            count=count,
            flags=re.MULTILINE,
        )
        p.write_text(new_text)


def _copy_tree(tmp: Path, src=REPO_ROOT) -> Path:
    dest = tmp / "tree"
    # Copy only the files the topology and its checks read, keeping it small.
    for rel in ["pyproject.toml", "capability.yaml", ".version.yaml", "skills", "CHANGELOG.md"]:
        s = src / rel
        d = dest / rel
        if s.is_dir():
            shutil.copytree(s, d, ignore=shutil.ignore_patterns("__pycache__"))
        elif s.exists():
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
    return dest


class TestRehearsal:
    TOPO = _load_topology()

    def test_old_two_locations_fails_red(self, tmp_path):
        # The old declaration trusted only pyproject.toml and capability.yaml.
        # A 1.3.11 → 1.3.12 bump against those two leaves every skill manifest
        # (and the bundle pins) at 1.3.11 → fail red.
        repo = _copy_tree(tmp_path)
        old = "1.3.11"
        new = "1.3.12"
        old_topo = {
            "locations": [
                {"path": "pyproject.toml", "pattern": '^version\\s*=\\s*"(\\d+\\.\\d+\\.\\d+)"'},
                {"path": "capability.yaml", "pattern": "^version:\\s*(\\S+)"},
            ]
        }
        _apply_bump(repo, old_topo, old, new)
        skill_versions = set()
        for skill in sorted((repo / "skills").iterdir()):
            cap = skill / "capability.yaml"
            if cap.exists():
                m = re.search(r"^version:\s*(\S+)", cap.read_text(), re.MULTILINE)
                skill_versions.add(m.group(1))
        assert "1.3.12" not in skill_versions, (
            "skills must NOT have been reached by the old two-location bump"
        )
        assert skill_versions == {"1.3.11"}, f"unexpected skill version set {skill_versions}"

    def test_expanded_declaration_finishes_synchronized(self, tmp_path):
        repo = _copy_tree(tmp_path)
        old = "1.3.11"
        new = "1.3.12"
        _apply_bump(repo, self.TOPO, old, new)

        surfaces = _version_surfaces(repo, self.TOPO)
        # Every declared surface — runtime, bundle, bundle pins and all skills —
        # must now report 1.3.12, reached from the single expanded declaration.
        assert surfaces, "no surfaces collected"
        for path, v in surfaces.items():
            assert v == new, f"{path} is {v!r}, expected {new!r} after bump"

        # The bundle member pins (capabilities[] entries) also reached 1.3.12.
        bundle = yaml.safe_load((repo / "capability.yaml").read_text())
        for entry in bundle["capabilities"]:
            assert entry["version"] == new, (
                f"bundle pin {entry['name']} still {entry['version']!r} after bump"
            )

    def test_changelog_untouched_by_bump(self, tmp_path):
        repo = _copy_tree(tmp_path)
        before = (repo / "CHANGELOG.md").read_text()
        _apply_bump(repo, self.TOPO, "1.3.11", "1.3.12")
        after = (repo / "CHANGELOG.md").read_text()
        assert before == after, "CHANGELOG.md must not be rewritten by the bump"
