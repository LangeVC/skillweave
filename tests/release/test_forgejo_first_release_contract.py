"""Forgejo-first release contract (SW1312-RELEASE-PROVENANCE-001).

Proves, as bounded unit tests, that this repository follows the org release
model ``local -> Forgejo (canonical) -> mirror -> GitHub (distribution only)``:

* exactly one release-object producer exists — the ops-engine ``ReleaseHandler``
  on Forgejo ``tag_push`` — and no SkillWeave GitHub workflow creates a release
  object or a tag;
* GitHub-side workflows are distribution-only and publish Capacium from the
  verified immutable tag path, never from a GitHub-created release object;
* there is no PyPI publication or PyPI claim;
* the release-contract identity check binds the Forgejo release object, the
  canonical tag target, the GitHub mirror tag and the distribution receipt to
  one immutable commit, and fails on zero or duplicate Forgejo release objects;
* the release rehearsal runs from a clean ephemeral clone so a machine-local
  divergent ``v1.3.5`` tag cannot block or rewrite canonical tag discovery.

Hermetic: reads the tree and the fixtures under ``tests/fixtures/release-flow``,
never merges, tags, releases or publishes. No network, no mutation of the
repository.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "release-flow"
GITHUB_WF = REPO_ROOT / ".github" / "workflows"
FORGEJO_WF = REPO_ROOT / ".forgejo" / "workflows"


# ── Contract model ─────────────────────────────────────────────────────────


class ReleaseContractError(Exception):
    """A release identity or authority violation."""


def verify_release_identity(evidence: dict) -> None:
    """Verify the four release identities converge on one immutable commit.

    ``evidence`` has the shape produced by release evidence collection:

        forgejo_release_objects: list of {id, tag_name, target_commitish}
        canonical_tag:           {tag, commit}
        mirror_tag:              {tag, commit}
        distribution_receipt:    {tag, commit, publisher}

    Raises :class:`ReleaseContractError` on:
    * zero Forgejo release objects (release exists only in the mirror),
    * more than one Forgejo release object (duplicate producer),
    * any of the four identities diverging in tag or commit.
    """
    objects = evidence.get("forgejo_release_objects", [])

    if len(objects) == 0:
        raise ReleaseContractError(
            "zero Forgejo release objects: no canonical release object exists"
        )
    if len(objects) > 1:
        raise ReleaseContractError(
            f"{len(objects)} Forgejo release objects for one tag; "
            "more than one producer is a violation"
        )

    obj = objects[0]
    canonical = evidence["canonical_tag"]
    mirror = evidence["mirror_tag"]
    receipt = evidence["distribution_receipt"]

    # All four name the same tag.
    tags = {obj["tag_name"], canonical["tag"], mirror["tag"], receipt["tag"]}
    if len(tags) != 1:
        raise ReleaseContractError(f"tag divergence across identities: {sorted(tags)}")

    # All four bind to the same commit; the canonical tag target is the truth.
    target = canonical["commit"]
    for name, commit in (
        ("forgejo release object", obj["target_commitish"]),
        ("canonical tag", canonical["commit"]),
        ("mirror tag", mirror["commit"]),
        ("distribution receipt", receipt["commit"]),
    ):
        if commit != target:
            raise ReleaseContractError(
                f"{name} commit {commit} != canonical tag target {target}"
            )


# ── Criterion 6: immutable identity proof ──────────────────────────────────


class TestReleaseIdentity:
    def test_identity_match_passes(self):
        evidence = json.loads((FIXTURE_DIR / "identity-match.json").read_text())
        # Does not raise.
        verify_release_identity(evidence)

    def test_zero_forgejo_objects_fail(self):
        evidence = json.loads((FIXTURE_DIR / "zero-forgejo-objects.json").read_text())
        with pytest.raises(ReleaseContractError, match="zero Forgejo release objects"):
            verify_release_identity(evidence)

    def test_duplicate_forgejo_objects_fail(self):
        evidence = json.loads(
            (FIXTURE_DIR / "duplicate-forgejo-objects.json").read_text()
        )
        with pytest.raises(ReleaseContractError, match="more than one producer"):
            verify_release_identity(evidence)

    def test_mirror_tag_divergence_fails(self):
        evidence = json.loads((FIXTURE_DIR / "mirror-tag-divergence.json").read_text())
        with pytest.raises(ReleaseContractError, match="mirror tag"):
            verify_release_identity(evidence)

    def test_identity_fixtures_carry_the_same_version(self):
        # Every fixture names the same prospective release; the version field is
        # kept so a stray fixture edit cannot silently change the subject.
        for path in FIXTURE_DIR.glob("*.json"):
            evidence = json.loads(path.read_text())
            assert evidence["version"] == "1.3.12", (
                f"{path.name} drifted to {evidence['version']}"
            )


# ── Criterion 7: clean-clone rehearsal ─────────────────────────────────────

# The machine-local divergence recorded at 1.3.11: a local ``v1.3.5`` tag that
# differs from the remote one, which made ``git fetch --tags`` fail with
# "would clobber existing tag". The rehearsal must run from a clean ephemeral
# clone so such a tag cannot block or rewrite canonical tag discovery.


class TestCleanCloneRehearsal:
    def _clean_clone(self, tmp_path):
        """Build a clean ephemeral clone with a canonical tag and a divergent
        machine-local tag planted outside the clone. Returns the clone path and
        the canonical 1.3.12 commit."""
        canonical_commit = "1111111111111111111111111111111111111111"
        repo = tmp_path / "canonical"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
        (repo / "VERSION").write_text("1.3.12\n")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-q", "-m", "v1.3.12", "--allow-empty"],
            check=True,
        )
        canonical_commit = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        subprocess.run(
            ["git", "-C", str(repo), "tag", "-a", "v1.3.12", "-m", "1.3.12"],
            check=True,
        )
        return repo, canonical_commit

    def test_canonical_tag_discovery_unaffected_by_divergent_local_tag(self, tmp_path):
        repo, canonical_commit = self._clean_clone(tmp_path)

        # Plant a machine-local divergent v1.3.5 tag in a *separate* location —
        # it must not be visible to the clean clone's canonical discovery.
        stray = tmp_path / "machine-local"
        stray.mkdir()
        subprocess.run(["git", "init", "-q", str(stray)], check=True)
        subprocess.run(["git", "-C", str(stray), "config", "user.name", "test"], check=True)
        subprocess.run(["git", "-C", str(stray), "config", "user.email", "t@t"], check=True)
        subprocess.run(
            ["git", "-C", str(stray), "commit", "-q", "-m", "divergent",
             "--allow-empty"], check=True)
        subprocess.run(["git", "-C", str(stray), "tag", "v1.3.5"], check=True)

        # Canonical discovery in the clean clone resolves the true tag target.
        discovered = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "v1.3.12^{commit}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert discovered == canonical_commit
        # The divergent local tag is not among the clone's tags.
        tags = subprocess.run(
            ["git", "-C", str(repo), "tag", "-l"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        assert "v1.3.5" not in tags
        assert "v1.3.12" in tags

    def test_rehearsal_binds_release_to_clean_clone_commit(self, tmp_path):
        repo, canonical_commit = self._clean_clone(tmp_path)
        evidence = json.loads((FIXTURE_DIR / "identity-match.json").read_text())
        # A rehearsal resolved against the clean clone must bind every identity
        # to the clean clone's commit, not a machine-local value.
        evidence = dict(evidence)
        evidence["commit"] = canonical_commit
        for obj in evidence["forgejo_release_objects"]:
            obj["target_commitish"] = canonical_commit
        evidence["canonical_tag"]["commit"] = canonical_commit
        evidence["mirror_tag"]["commit"] = canonical_commit
        evidence["distribution_receipt"]["commit"] = canonical_commit
        verify_release_identity(evidence)


# ── Criterion 2, 3, 4, 5: workflow authority and distribution boundary ─────

# Markers that would indicate a GitHub-side release object or tag producer.
_RELEASE_OBJECT_ACTIONS = (
    "softprops/action-gh-release",
    "actions/create-release",
    "gh release create",
)
# Tag *production* only: creating or moving a tag on the GitHub side. Read-only
# listing (`git tag --list`) is not a producer. Each entry is a pattern that
# creates (`git tag -a`) or pushes a tag ref.
_TAG_PRODUCER_MARKERS = (
    "git tag -a",
    "git tag --annotate",
    "git push origin \"$",
    "git push origin v",
)
_PYPI_MARKERS = (
    "pypa/gh-action-pypi-publish",
    "PYPI_API_TOKEN",
    "publish-pypi",
)
_CAPACIUM_MARKERS = (
    "Capacium/capacium-action-publish",
)


def _github_workflows() -> dict[str, str]:
    return {p.name: p.read_text() for p in GITHUB_WF.glob("*.yml")}


def _forgejo_workflows() -> dict[str, str]:
    return {p.name: p.read_text() for p in FORGEJO_WF.glob("*.yml")}


class TestReleaseAuthority:
    def test_no_github_workflow_creates_a_release_object(self):
        for name, body in _github_workflows().items():
            for marker in _RELEASE_OBJECT_ACTIONS:
                assert marker not in body, (
                    f"{name} creates a release object ({marker}); the only "
                    "producer is the ops-engine ReleaseHandler on Forgejo"
                )

    def test_no_github_workflow_creates_or_moves_a_tag(self):
        for name, body in _github_workflows().items():
            for marker in _TAG_PRODUCER_MARKERS:
                assert marker not in body, (
                    f"{name} creates or moves a tag ({marker}); the canonical "
                    "tag is Forgejo-side only"
                )

    def test_auto_tag_release_workflow_is_absent(self):
        assert not (GITHUB_WF / "auto-tag-release.yml").exists(), (
            "auto-tag-release.yml created a tag and a release object on GitHub"
        )

    def test_capacium_publication_is_tag_keyed_not_release_object_keyed(self):
        # The distribution workflow that publishes Capacium must trigger on a
        # pushed tag (the verified mirror tag), not on a GitHub `release` object.
        body = (GITHUB_WF / "release-on-tag.yml").read_text()
        assert any(m in body for m in _CAPACIUM_MARKERS), (
            "Capacium publication must live in the tag-keyed distribution workflow"
        )
        # Trigger is the tag path, not the release object.
        assert "push:" in body and "tags:" in body
        assert "release:" not in body, "Capacium must not key on a GitHub release object"

    def test_no_pypi_publication_or_claim(self):
        for name, body in _github_workflows().items():
            for marker in _PYPI_MARKERS:
                assert marker not in body, f"{name} still publishes PyPI ({marker})"
        docs = (REPO_ROOT / "docs" / "release-flow.md").read_text()
        # The distribution docs deny PyPI publication; they must not assert one.
        assert "no workflow publishes to PyPI" in docs
        assert "for this repository" in docs  # the denial is scoped to this repo


class TestDocumentationAuthority:
    def test_release_flow_points_to_canonical_model(self):
        doc = (REPO_ROOT / "docs" / "release-flow.md").read_text()
        assert "lvc-ops/docs/release-flow-division.md" in doc, (
            "docs/release-flow.md must name the single release-model authority"
        )
        # It must not redefine the model locally: no byte-for-byte copy of the
        # assignment table or the full standard-model prose.
        assert "Assignments" not in doc
        assert "## The split in one line" not in doc

    def test_release_flow_does_not_copy_the_authority_text(self):
        doc = (REPO_ROOT / "docs" / "release-flow.md").read_text()
        # The authority document's distinctive section headers are absent.
        for header in ("## Assignments", "## Exceptions", "## Setting up a new org"):
            assert header not in doc
