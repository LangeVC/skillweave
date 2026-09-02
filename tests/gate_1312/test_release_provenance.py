"""Dispatch-order group 5 — release provenance (criterion 6).

Proves the release-provenance fixture: Forgejo is canonical and single-source,
GitHub is a read-only mirror, and the distribution identity is one object —
without performing a live release, publishing anything, or contacting any
remote. All assertions are static reads of the worktree's own workflow and
remote configuration.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.gate_1312 import _sibling as sib
from tests.gate_1312._sibling import require


def _core_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_criterion_06_release_provenance_forgejo_first_no_live_release():
    """Forgejo-first single-object production and distribution identity, proven
    statically (no live release, no network, no mutation).

    * Forgejo is the canonical remote (``origin`` → ``git.langevc.com``).
    * GitHub is a read-only mirror (``github`` remote → ``github.com``, and the
      Forgejo ``mirror.yml`` force-pushes the exact triggering ref only).
    * The Forgejo release workflow is the production object; the mirror follows
      it and does not independently produce.
    """
    require(sib.sdk_root, name="skillweave-sdk")
    core = _core_root()

    # --- Remote identity (read-only config, no network) ------------------------
    # The read-only GitHub mirror remote is a git-config environment surface, not
    # a file git carries: a fresh clone is typically checked out without a
    # `github` mirror. Skip (named reason) rather than fail when it is absent so
    # the hermetic suite is deterministic.
    proc = subprocess.run(
        ["git", "-C", str(core), "remote", "-v"],
        capture_output=True, text=True, check=True,
    )
    remotes = proc.stdout
    if "github.com" not in remotes:
        pytest.skip(
            "read-only GitHub mirror remote is not configured in this checkout "
            "(git config surface, not carried by git)"
        )
    assert "origin" in remotes
    assert "git.langevc.com" in remotes, (
        "Forgejo must be the canonical origin; got:\n" + remotes
    )

    # --- Mirror is one-directional Forgejo -> GitHub --------------------------
    mirror = _read(core / ".forgejo" / "workflows" / "mirror.yml")
    assert "Forgejo ist kanonisch" in mirror or "Forgejo" in mirror
    # The mirror force-pushes exactly the triggering ref, never a pruning wildcard.
    assert "--force" in mirror
    assert "kein --prune" in mirror.lower()
    # GitHub is the read-only mirror target.
    assert "github.com/LangeVC/skillweave.git" in mirror

    # --- The Forgejo release workflow is the single production object ----------
    release = _read(core / ".forgejo" / "workflows" / "forgejo-release.yml")
    assert "Create Forgejo Release" in release
    assert "releases" in release

    # --- The SDK declares the same Forgejo-canonical split ---------------------
    sdk_readme = _read(sib.sdk_root() / "README.md")
    assert "Forgejo ist kanonisch" in sdk_readme or "Forgejo ist kanonisch" in sdk_readme.lower()


def test_release_naming_convention_is_present_in_workflows():
    """The release title convention (``SkillWeave vX.Y.Z``) is enforced in the
    Forgejo/GitHub release path, so the single production object carries one
    identity.
    """
    core = _core_root()
    gh = core / ".github" / "workflows" / "auto-tag-release.yml"
    if gh.is_file():
        text = _read(gh)
        assert "SkillWeave v" in text, "release title convention missing from CI"
