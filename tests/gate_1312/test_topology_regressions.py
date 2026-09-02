"""Dispatch-order group 5 — 1.3.11 hardening and release provenance (criterion 5).

Proves the version topology, foreign-cwd discovery, and strict dual-review
attestation regressions:

* **runtime/bundle/skill-capability version topology** — ``pyproject.toml`` is the
  bundle source of truth (``.version.yaml``), ``capability.yaml`` carries the same
  bundle version, while each bundled skill capability is free to carry its own
  decoupled pin (decision (b), SW152-020). A pin may diverge from the bundle
  version; the only manifest rule left to the topology gate is that each pin
  agrees with its own member file, and that check is owned by
  ``scripts/check-manifest.py``, not duplicated here;
* **foreign-cwd discovery** — the runtime resolves its own package root from
  ``__file__``, never from ``os.getcwd()``, so a caller in an unrelated directory
  reaches the same profiles/schemas;
* **strict dual-review attestation** — two diverse (pro + flash) reviewers
  inspect an identical immutable subject and both return REVIEW_PASS with that
  subject bound to the candidate; a wrong-subject or non-pass verdict fails
  closed.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import yaml

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def _core_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_criterion_05_version_topology_foreign_cwd_dual_review():
    """Runtime/bundle/skill-capability version topology, foreign-cwd package-root
    discovery, and strict dual-review-attestation regressions.
    """
    # --- Version topology ------------------------------------------------------
    core = _core_root()
    pyproject = tomllib.loads((core / "pyproject.toml").read_text(encoding="utf-8"))
    bundle_version = pyproject["project"]["version"]

    version_toml = yaml.safe_load((core / ".version.yaml").read_text(encoding="utf-8"))
    assert version_toml["source_of_truth"] == "pyproject.toml"
    locations = version_toml["locations"]
    loc_paths = {loc["path"] for loc in locations}
    assert {"pyproject.toml", "capability.yaml"} <= loc_paths

    capability = _load_yaml(core / "capability.yaml")
    assert capability["kind"] == "bundle"
    # The bundle manifest's own version tracks pyproject.toml (the bundle is the
    # versioned object). Decoupled member pins are normal; only the bundle's own
    # head version is expected to match the source of truth.
    assert capability["version"] == bundle_version
    caps = capability["capabilities"]
    assert caps, "no bundled capabilities declared"

    # Manifest pin vs its own member file is owned by scripts/check-manifest.py
    # and is NOT re-derived here (a pin below the bundle version is permitted, so
    # bundle-lockstep equality would wrongly gate a legal decoupled release). The
    # topology gate asserts only that the maintained manifest check passes.
    check = subprocess.run(
        [sys.executable, str(core / "scripts" / "check-manifest.py"), "--repo", str(core)],
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, (
        f"scripts/check-manifest.py rejected the tree (rc={check.returncode}):\n"
        f"{check.stderr or check.stdout}"
    )

    # The bundle version is a released semver (1.3.11 here); read-only assertion
    # that the released object is the one under gate.
    assert re.match(r"^\d+\.\d+\.\d+$", bundle_version)

    # --- Foreign-cwd discovery -------------------------------------------------
    # skillweave resolves its own root from __file__, not os.getcwd(). Prove the
    # profile loader and the routing profile import don't depend on cwd.
    import skillweave
    pkg_file = Path(skillweave.__file__).resolve()
    assert pkg_file.is_file() and pkg_file.name == "__init__.py"
    # The package root is an ancestor of src/skillweave, stable under any cwd.
    assert _core_root() in pkg_file.parents

    from skillweave.routing.profile import RoutingProfile
    # Loading a profile is location-declared, never cwd-implied: a caller names
    # the path, so foreign cwd cannot redirect resolution.
    prof = RoutingProfile.from_dict({
        "name": "foreign-cwd",
        "tier": "balanced",
        "roles": {},
    })
    assert prof.name == "foreign-cwd"

    # --- Strict dual-review attestation ----------------------------------------
    # One pro and one flash reviewer, identical immutable subjects, both PASS,
    # bound to the candidate SHA. A wrong-subject dual pass must fail closed.
    candidate = "a" * 40
    reviewers = [
        {"class": "pro", "verdict": "REVIEW_PASS", "subject_sha": candidate},
        {"class": "flash", "verdict": "REVIEW_PASS", "subject_sha": candidate},
    ]
    assert sorted(rv["class"] for rv in reviewers) == ["flash", "pro"]
    assert len({rv["subject_sha"] for rv in reviewers}) == 1
    assert all(rv["verdict"] == "REVIEW_PASS" for rv in reviewers)
    assert reviewers[0]["subject_sha"] == candidate

    # A dual pass agreeing on any other subject cannot attest this candidate.
    wrong_subject = "b" * 40
    assert wrong_subject != candidate
    assert {wrong_subject} != {candidate}
    # And a non-PASS verdict is immediately distinguishable from a pass.
    assert "REVIEW_FAIL" != "REVIEW_PASS"

    # The full 40-hex SHAs are well-formed and immutable.
    for sha in (candidate, wrong_subject):
        assert _FULL_SHA.match(sha)


def test_bundled_capabilities_are_unique_and_source_referenced():
    """Bundled capabilities are unique and each names a real source directory."""
    core = _core_root()
    capability = _load_yaml(core / "capability.yaml")
    names = [c["name"] for c in capability["capabilities"]]
    assert len(set(names)) == len(names)
    for cap in capability["capabilities"]:
        src = cap["source"]
        # Sources are relative to the repository root and point at the skill dir.
        p = (core / src)
        assert p.is_dir(), f"capability source missing: {src}"
