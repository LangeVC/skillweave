"""Release-topology contract (SW1312-VERSION-TOPOLOGY-001).

Where ``tests/unit/test_version_sync.py`` proves the snapshot agrees with
itself on the *current* tree, this module proves the *release* behaviour:
the product tag binds to the runtime source, bundle and skill artifacts are
verified under the declared decoupled-member-pins policy, CHANGELOG prose stays
outside any automatic bump, and a 1.3.11-to-1.3.12 rehearsal shows that trusting
only the old two declared locations fails red while the expanded declaration
reaches every required surface.

Hermetic: reads the tree, writes only to the pytest ``tmp_path``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
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

        # A product tag must equal the runtime version: no required surface may
        # carry a version that would produce a divergent tag under lockstep.
        # Informational locations (bundle member pins) may legitimately diverge.
        for loc in topo["locations"]:
            if not loc.get("required", True):
                continue  # informational (bundle member pins) may lag on purpose
            v = _read(REPO_ROOT / loc["path"], loc["pattern"])
            assert v == runtime, (
                f"tag-binding failure: {loc['role']} at {loc['path']} is {v!r}, "
                f"runtime is {runtime!r}"
            )

    def test_skill_artifacts_are_decoupled_not_lockstep(self):
        # Under decoupled_member_pins each member skill is informational: its
        # own capability.yaml may LAG the product tag (a packaging-only bump
        # moves neither the member file nor its bundle pin). A member file is
        # therefore NOT lockstep to the tag; pin == member file consistency is
        # the contract, owned by scripts/check-manifest.py. Declaring a skill
        # `required: true` again would drag it back under the lockstep tag gate,
        # so each skill_capability must stay informational.
        topo = _load_topology()
        skills = [loc for loc in topo["locations"] if loc["role"] == "skill_capability"]
        assert skills, "no skill_capability locations declared"
        require_lockstep = [loc["path"] for loc in skills if loc.get("required", True)]
        assert require_lockstep == [], (
            f"skill_capability must stay decoupled (not lockstep) under "
            f"decoupled_member_pins, but declared required: {require_lockstep}"
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
        assert "changelog_managed" in topo, "changelog exclusion must be stated explicitly"
        assert topo["changelog_managed"] is False, "CHANGELOG must not be auto-bumped"
        assert topo["changelog_path"] == "CHANGELOG.md", "CHANGELOG path must be named"

    def test_changelog_path_is_not_among_locations(self):
        topo = _load_topology()
        paths = {loc["path"] for loc in topo["locations"]}
        assert topo["changelog_path"] not in paths, (
            "CHANGELOG.md must not be an automatic bump location"
        )

    def test_changelog_boundary_is_a_flat_scalar_not_a_nested_map(self):
        # The canonical version-sync parser accepts only a restricted YAML
        # subset (flat top-level scalars + the `locations` list). A nested
        # `changelog:` map is unparseable and makes `check`/`check-tag` exit 2
        # before any comparison. The boundary must therefore be flat scalars.
        topo = _load_topology()
        assert "changelog" not in topo, (
            "changelog must be flat top-level scalars, not a nested map"
        )


# ── Criterion 9: 1.3.11 → 1.3.12 rehearsal ─────────────────────────────────
#
# The rehearsal drives the *actual* canonical `version-sync.py` tool (the same
# one the release gate fetches from ops-engine and runs as `check-tag`) through
# subprocess, rather than a parallel reference bump. This proves the expanded
# declaration is consumable by the shipped gate/bump tooling, not merely by the
# test's own logic. The tool is resolved from (in order) `$VERSION_SYNC`, a
# sibling `ops-engine` checkout, or a `langevc/ops-engine` checkout next to the
# repo; when none is present the rehearsal is skipped rather than silently
# substituted for a self-fulfilling reimplementation.


def _canonical_version_sync() -> Path | None:
    """Resolve the canonical version-sync.py; None when not present locally."""
    candidates: list[Path] = []
    env = os.environ.get("VERSION_SYNC")
    if env:
        candidates.append(Path(env))
    # SkillWeave lives under <group>/skillweave/skillweave and the canonical
    # tool under <group>/ops-engine/scripts/version-sync.py (OSS, publicly
    # mirrored) — the same source the release gate fetches at runtime.
    candidates.append(
        REPO_ROOT.parent.parent.parent / "langevc" / "ops-engine" / "scripts" / "version-sync.py"
    )
    candidates.append(REPO_ROOT.parent.parent.parent / "ops-engine" / "scripts" / "version-sync.py")
    for c in candidates:
        if c.exists():
            return c
    return None


def _run_version_sync(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    tool = _canonical_version_sync()
    if tool is None:
        pytest.skip("canonical version-sync.py not found (set VERSION_SYNC or clone ops-engine)")
    return subprocess.run(
        [sys.executable, str(tool), *args, "--repo", str(repo)],
        capture_output=True,
        text=True,
    )


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
        # A bump through the canonical tool against those two leaves every skill
        # manifest (and the bundle pins) at 1.3.11 → fail red.
        repo = _copy_tree(tmp_path)
        old = "1.3.11"
        new = "1.3.12"
        old_topo = {
            "schema": 1,
            "source_of_truth": "pyproject.toml",
            "locations": [
                {"path": "pyproject.toml", "pattern": '^version\\s*=\\s*"(\\d+\\.\\d+\\.\\d+)"'},
                {"path": "capability.yaml", "pattern": "^version:\\s*(\\S+)"},
            ],
        }
        (repo / ".version.yaml").write_text(yaml.safe_dump(old_topo))
        proc = _run_version_sync(repo, "bump", new)
        assert proc.returncode == 0, f"bump failed: {proc.stderr}"
        skill_versions = set()
        for skill in sorted((repo / "skills").iterdir()):
            cap = skill / "capability.yaml"
            if cap.exists():
                m = re.search(r"^version:\s*(\S+)", cap.read_text(), re.MULTILINE)
                skill_versions.add(m.group(1))
        assert "1.3.12" not in skill_versions, (
            "skills must NOT have been reached by the old two-location bump"
        )
        assert skill_versions == {old}, f"unexpected skill version set {skill_versions}"

    def test_expanded_declaration_finishes_synchronized(self, tmp_path):
        repo = _copy_tree(tmp_path)
        new = "1.3.12"
        old = "1.3.11"  # the pre-bump version of the copied test tree

        # The canonical tool must parse and bump the full declaration. If the
        # declaration is outside the tool's YAML subset, `bump` exits 2 here —
        # which is exactly the blocking regression this test guards against.
        proc = _run_version_sync(repo, "bump", new)
        assert proc.returncode == 0, f"bump failed (exit {proc.returncode}): {proc.stderr}"

        # `bump` self-checks; run `check` again for an explicit gate verdict.
        chk = _run_version_sync(repo, "check")
        assert chk.returncode == 0, f"check failed (exit {chk.returncode}): {chk.stderr}"

        # Every REQUIRED declared surface — runtime and the distribution bundle —
        # must report 1.3.12, reached from the single expanded declaration. All
        # informational surfaces — bundle_member_pins AND every skill_capability —
        # are NOT forced by a plain `bump`: a bundle bump can be packaging alone,
        # so pins and member files both stay at the prior version, keeping
        # pin == member file (decoupled_member_pins; consistency owned by
        # check-manifest.py, proven below by reading the on-tree files).
        assert self.TOPO["locations"], "no locations collected"
        for loc in self.TOPO["locations"]:
            v = _read(repo / loc["path"], loc["pattern"])
            assert v is not None, f"no match for {loc['role']} at {loc['path']}"
            if not loc.get("required", True):
                continue  # informational (pins + member files) may lag on purpose
            assert v == new, (
                f"{loc['role']} at {loc['path']} is {v!r}, expected {new!r} after bump"
            )

        # Informational surfaces are untouched by a plain `bump`: the bundle
        # member pins AND each member's own capability.yaml keep the prior
        # version, together, so none of them diverges from its own file.
        bundle = yaml.safe_load((repo / "capability.yaml").read_text())
        skills = [loc["path"] for loc in self.TOPO["locations"] if loc["role"] == "skill_capability"]
        assert skills, "no skill_capability locations to keep decoupled"
        for entry in bundle["capabilities"]:
            assert entry["version"] == old, (
                f"bundle pin {entry['name']} is {entry['version']!r} after bump; "
                f"informational pins must stay at the prior version {old!r} "
                f"(decoupled_member_pins)"
            )
            member_path = next(
                (s for s in skills if s.endswith(f"/{entry['name']}/capability.yaml")), None
            )
            assert member_path is not None, f"no skill_capability location for pin {entry['name']}"
            member_version = _read(repo / member_path, r'^version:\s*(\S+)')
            assert member_version == old, (
                f"member file {member_path} is {member_version!r} after bump; "
                f"informational member files must stay at {old!r} with their pin "
                f"(decoupled_member_pins)"
            )
            assert member_version == entry["version"], (
                f"pin {entry['name']} ({entry['version']!r}) diverged from its own "
                f"member file ({member_version!r})"
            )

        # The release gate runs check-manifest.py after the bump; a decoupled
        # bump that leaves every pin and every member file at the prior version
        # together must still pass it (the exact red/regression the lane fixes).
        manifest_check = REPO_ROOT / "scripts" / "check-manifest.py"
        assert manifest_check.exists(), "scripts/check-manifest.py missing"
        mc = subprocess.run(
            [sys.executable, str(manifest_check), "--repo", str(repo)],
            capture_output=True,
            text=True,
        )
        assert mc.returncode == 0, (
            f"check-manifest after decoupled bump failed (exit {mc.returncode}): "
            f"{mc.stdout}\n{mc.stderr}"
        )

    def test_changelog_untouched_by_bump(self, tmp_path):
        repo = _copy_tree(tmp_path)
        before = (repo / "CHANGELOG.md").read_text()
        proc = _run_version_sync(repo, "bump", "1.3.12")
        assert proc.returncode == 0, f"bump failed: {proc.stderr}"
        after = (repo / "CHANGELOG.md").read_text()
        assert before == after, "CHANGELOG.md must not be rewritten by the bump"
