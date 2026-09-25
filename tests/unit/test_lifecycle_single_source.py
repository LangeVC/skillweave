"""The lifecycle has one canonical source; generator and consumer agree.

SW-LC-001. The seven-phase lifecycle used to be declared twice — in
``.skillweave/phases.yaml`` and ``.skillweave/lifecycle/phases.yaml`` — and the
two copies drifted (one named ``last30days``, a skill that does not ship). The
fix is one canonical source: :mod:`skillweave.lifecycle`. Everything else
either *generates* from it (the ``.skillweave/*.yaml`` mirror) or *consumes* it
(``phase_enforcement.PHASE_MEMBERSHIP``, ``workflow_recommendation.BUNDLE_MAP``).

These tests prove identical semantics from one source:

1. The generator (``to_yaml`` / the checked-in ``.skillweave`` YAML) and the
   consumer (:mod:`skillweave.lifecycle`) describe the same phases and bundles.

2. ``phase_enforcement`` and ``workflow_recommendation`` import from the
   canonical module rather than carrying their own copies — and the copies they
   expose equal the canonical data.

3. Every skill id named in the canonical source resolves to a directory under
   ``skills/``; ``last30days`` is gone, and no capability name leaks into a
   skills list.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# The repository's own .skillweave/ is git-excluded (docs/substrate-map.md,
# invariant 5). The generated mirror is kept as a checked-in fixture so the
# drift guard below still compares the generator against a stored snapshot.
SUBSTRATE = os.path.join(
    REPO_ROOT, "tests", "fixtures", "substrate-root", ".skillweave"
)

from skillweave import lifecycle
from skillweave.phase_enforcement import PHASE_MEMBERSHIP
from skillweave.workflow_recommendation import BUNDLE_MAP


def _all_skill_ids_under_skills() -> set[str]:
    skills_dir = os.path.join(REPO_ROOT, "skills")
    if not os.path.isdir(skills_dir):
        return set()
    return {
        name
        for name in os.listdir(skills_dir)
        if os.path.isdir(os.path.join(skills_dir, name))
    }


# ── Generator / consumer singleness ──────────────────────────────────────

def test_generator_and_consumer_agree_on_phases():
    """The YAML generator and the canonical module describe the same phases."""
    text = lifecycle.to_yaml()
    phases, bundles = lifecycle.load_skillweave_yaml(text)

    canonical_phases = {
        p["id"]: list(p["skills"]) for p in lifecycle.PHASES
    }
    generated_phases = {
        p["id"]: list(p["skills"]) for p in phases
    }
    assert generated_phases == canonical_phases


def test_generator_and_consumer_agree_on_bundles():
    """The YAML generator and the canonical module describe the same bundles."""
    text = lifecycle.to_yaml()
    _phases, bundles = lifecycle.load_skillweave_yaml(text)

    canonical_bundles = {b["id"]: list(b["phases"]) for b in lifecycle.BUNDLES}
    generated_bundles = {b["id"]: list(b["phases"]) for b in bundles}
    assert generated_bundles == canonical_bundles


def test_checked_in_yaml_matches_the_generator():
    """The checked-in substrate fixture is a faithful mirror of the module."""
    text = lifecycle.to_yaml()
    gen_phases, gen_bundles = lifecycle.load_skillweave_yaml(text)

    import yaml

    with open(os.path.join(SUBSTRATE, "phases.yaml")) as f:
        disk_phases = yaml.safe_load(f)["phases"]
    with open(os.path.join(SUBSTRATE, "bundles.yaml")) as f:
        disk_bundles = yaml.safe_load(f)["bundles"]

    assert [p["id"] for p in disk_phases] == [p["id"] for p in gen_phases]
    assert [b["id"] for b in disk_bundles] == [b["id"] for b in gen_bundles]
    for disk, gen in zip(disk_phases, gen_phases):
        assert disk["skills"] == gen["skills"]


# ── Consumers import, not duplicate ──────────────────────────────────────

def test_phase_membership_equals_canonical_skill_membership():
    """phase_enforcement.PHASE_MEMBERSHIP is the canonical membership."""
    assert PHASE_MEMBERSHIP == lifecycle.skill_membership()


def test_bundle_map_equals_canonical_bundle_map():
    """workflow_recommendation.BUNDLE_MAP is the canonical bundle map."""
    expected = {b["id"]: b for b in lifecycle.BUNDLES}
    assert BUNDLE_MAP == expected


def test_last30days_is_gone():
    """The nonexistent ``last30days`` skill no longer appears anywhere."""
    assert "last30days" not in PHASE_MEMBERSHIP
    assert "last30days" not in lifecycle.skill_membership()


# ── Validation: skills resolve, capabilities are separate ────────────────

def test_every_named_skill_resolves_to_a_dir():
    """Every skill id in the canonical source maps to a shipped or external skill."""
    shipped = _all_skill_ids_under_skills()
    named = set(lifecycle.skill_membership().keys()) | set(lifecycle.GLOBAL_SKILLS.keys())
    # External skills (e.g. ``frontend-design``) are declared explicitly and are
    # expected NOT to be under skills/. Anything else must resolve to a directory.
    unknown = named - shipped - lifecycle.EXTERNAL_SKILLS
    assert named, "canonical source names no skills"
    assert not unknown, f"unknown skill ids: {sorted(unknown)}"


def test_capabilities_never_leak_into_skill_lists():
    """No phase's skills list carries a capability name (e.g. 'testing')."""
    capabilities = {
        cap for p in lifecycle.PHASES for cap in p["capabilities"]
    }
    for skill in lifecycle.skill_membership():
        assert skill not in capabilities, f"capability '{skill}' listed as a skill"
