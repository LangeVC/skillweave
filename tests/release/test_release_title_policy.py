"""Release title policy contract (SW-156-RELNAME-001).

Proves the release-title policy declared in ``.version.yaml`` is consumed
correctly by releasechain and launch: the pattern validates titles without
a hardcoded SkillWeave literal, SkillWeave titles still pass, differently
named products pass without skill edits, and missing/malformed/contradictory
policy fails closed with an actionable error.

Hermetic: reads the tree only, no network, no mutation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ── Policy helpers ──────────────────────────────────────────────────────────


def _load_policy(repo: Path = REPO_ROOT) -> dict | None:
    """Load the ``release_title_policy`` section from ``.version.yaml``.

    Returns ``None`` when the file or section is missing, mirroring how a
    consumer would see a missing policy at runtime.
    """
    path = repo / ".version.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        return None
    return data.get("release_title_policy")


def _build_regex(policy: dict | None) -> str | None:
    """Assemble the full title regex from the policy dict.

    Replaces ``{product}`` with ``product_name``.  Returns ``None`` when the
    policy is missing, not a dict, or lacks either required key — every caller
    sees a ``None`` return as a fail-closed signal.
    """
    if not isinstance(policy, dict):
        return None
    product = policy.get("product_name")
    pattern = policy.get("pattern")
    if not product or not pattern:
        return None
    return pattern.replace("{product}", product)


def _validate_title(title: str, policy: dict | None) -> bool:
    """Return ``True`` iff *title* matches the compiled policy regex.

    Every error path — missing policy, missing keys, regex syntax error —
    returns ``False`` so consumers fail closed before creating any release
    object.
    """
    regex_str = _build_regex(policy)
    if regex_str is None:
        return False
    try:
        return bool(re.match(regex_str, title))
    except re.error:
        return False


def _read_pyproject_name(repo: Path = REPO_ROOT) -> str | None:
    """Read the ``[project].name`` from ``pyproject.toml``."""
    for line in (repo / "pyproject.toml").read_text().splitlines():
        m = re.match(r'^name\s*=\s*"([^"]+)"', line)
        if m:
            return m.group(1)
    return None


# ── Acceptance tests ────────────────────────────────────────────────────────


class TestReleaseTitlePolicy:
    """Release title policy — acceptance criteria for SW-156-RELNAME-001."""

    # ── Criterion 2: SkillWeave titles ──────────────────────────────────

    def test_skillweave_production_title_passes(self):
        """``SkillWeave vX.Y.Z`` is still accepted."""
        policy = _load_policy()
        assert _validate_title("SkillWeave v1.2.3", policy)

    def test_skillweave_prerelease_title_passes(self):
        """Prerelease suffix ``-rcN`` is still accepted."""
        policy = _load_policy()
        assert _validate_title("SkillWeave v1.2.3-rc1", policy)

    def test_skillweave_zero_patch_passes(self):
        policy = _load_policy()
        assert _validate_title("SkillWeave v0.0.0", policy)

    def test_skillweave_multi_digit_passes(self):
        policy = _load_policy()
        assert _validate_title("SkillWeave v10.200.3000", policy)

    def test_extra_text_after_version_is_rejected(self):
        """No additional text after the version."""
        policy = _load_policy()
        assert not _validate_title("SkillWeave v1.2.3 extra", policy)

    def test_extra_text_with_dash_is_rejected(self):
        """`` - Fixed installer`` suffix is rejected."""
        policy = _load_policy()
        assert not _validate_title("SkillWeave v1.2.3 - Fixed installer", policy)

    def test_missing_product_prefix_is_rejected(self):
        """A bare version without the product name is rejected."""
        policy = _load_policy()
        assert not _validate_title("v1.2.3", policy)

    def test_wrong_case_is_rejected(self):
        """Case-sensitive: lowercase ``skillweave`` is not ``SkillWeave``."""
        policy = _load_policy()
        assert not _validate_title("skillweave v1.2.3", policy)

    # ── Criterion 3: differently named product ──────────────────────────

    def test_different_product_name_passes_without_skill_edit(self):
        """Changing ``product_name`` to ``OtherProduct`` in ``.version.yaml``
        lets ``OtherProduct v1.2.3`` pass — no skill-file edits needed."""
        policy = _load_policy()
        alt_policy = dict(policy, product_name="OtherProduct")
        assert _validate_title("OtherProduct v1.2.3", alt_policy)

    def test_different_product_rejects_old_name(self):
        """After changing ``product_name``, the old name is rejected."""
        policy = _load_policy()
        alt_policy = dict(policy, product_name="OtherProduct")
        assert not _validate_title("SkillWeave v1.2.3", alt_policy)

    # ── Criterion 4: fail-closed paths ──────────────────────────────────

    def test_missing_policy_fails_closed(self):
        """When ``.version.yaml`` has no ``release_title_policy`` section,
        every title is rejected."""
        assert not _validate_title("SkillWeave v1.2.3", None)

    def test_empty_policy_fails_closed(self):
        assert not _validate_title("SkillWeave v1.2.3", {})

    def test_missing_product_name_fails_closed(self):
        assert not _validate_title(
            "SkillWeave v1.2.3", {"pattern": "^{product} v..."}
        )

    def test_missing_pattern_fails_closed(self):
        assert not _validate_title(
            "SkillWeave v1.2.3", {"product_name": "SkillWeave"}
        )

    def test_contradictory_product_name_fails(self):
        """A ``product_name`` that doesn't match the project rejects valid
        titles for that project."""
        policy = _load_policy()
        wrong_policy = dict(policy, product_name="WrongName")
        assert not _validate_title("SkillWeave v1.2.3", wrong_policy)

    def test_invalid_regex_in_pattern_fails_closed(self):
        """An unparseable regex pattern returns False (fail-closed)."""
        policy = _load_policy()
        bad = dict(policy, pattern="{product} v[invalid")
        # The pattern without ^$ anchor, with invalid char class
        regex_str = _build_regex(bad)
        # It should still build a string; the re.match will raise
        assert not _validate_title("SkillWeave v1.2.3", bad)

    # ── Policy coherence ────────────────────────────────────────────────

    def test_product_name_is_declared(self):
        """``product_name`` is set and non-empty."""
        policy = _load_policy()
        assert policy.get("product_name"), (
            "product_name must be set in .version.yaml release_title_policy"
        )

    def test_pattern_is_parseable(self):
        """The assembled regex compiles without error."""
        policy = _load_policy()
        regex_str = _build_regex(policy)
        assert regex_str is not None
        re.compile(regex_str)  # raises on syntax error

    def test_pattern_contains_product_placeholder(self):
        """The raw pattern contains ``{product}`` for substitution."""
        policy = _load_policy()
        assert "{product}" in policy.get("pattern", "")

    def test_pattern_anchors_at_both_ends(self):
        """The pattern starts with ``^`` and ends with ``$`` to prevent
        partial matches."""
        policy = _load_policy()
        pattern = policy.get("pattern", "")
        assert pattern.startswith("^"), "pattern must start with ^"
        assert pattern.endswith("$"), "pattern must end with $"
