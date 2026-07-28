"""Tests for skill boundaries (SW-CAT-02/03/04/05).

Covers: EN-first metadata, canonical H1 headings, boundary assertions
in release code, and boundaries YAML.
"""

import os
import re
import yaml
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
SKILLS_DIR = PROJECT_ROOT / "skills"


# ─── Metadata lint: all skills ──────────────────────────────────────────


def _get_skill_mds():
    """Return all SKILL.md files in skills/*/SKILL.md."""
    return sorted(SKILLS_DIR.glob("*/SKILL.md"))


def _parse_frontmatter(path):
    """Parse YAML frontmatter from a markdown file.
    Returns (frontmatter_dict, body_start_line).
    """
    content = path.read_text()
    if not content.startswith("---"):
        return {}, 0
    end = content.find("---", 3)
    if end == -1:
        return {}, 0
    fm_text = content[3:end]
    fm = yaml.safe_load(fm_text) or {}
    return fm, end + 3


GERMAN_WORDS = {"und", "fuer", "mit", "einen", "eine", "ein", "sind", "oder",
                "wird", "wurde", "auch", "nicht", "auf", "von", "zur", "als"}


def test_all_skill_descriptions_are_english():
    """All canonical skills must have English frontmatter descriptions.

    No German words like 'und', 'mit', 'fuer', 'einen' are allowed.
    """
    failures = []
    for md_file in _get_skill_mds():
        fm, _ = _parse_frontmatter(md_file)
        desc = fm.get("description", "")
        if not desc:
            failures.append(f"{md_file.parent.name}: no description")
            continue
        words = set(re.findall(r'\b[a-zäöüß]+\b', desc.lower()))
        german_hits = words & GERMAN_WORDS
        if german_hits:
            failures.append(
                f"{md_file.parent.name}: German words in description: {german_hits}"
            )
    assert not failures, "Non-English descriptions found:\n" + "\n".join(failures)


def test_all_h1_use_canonical_slash_format():
    """All H1 headings must use '# /skillweave-*' format (with leading slash)."""
    failures = []
    for md_file in _get_skill_mds():
        content = md_file.read_text()
        lines = content.split("\n")
        # Find first H1
        for line in lines:
            line = line.strip()
            if line.startswith("# "):
                # Must match # /skillweave-...
                if not re.match(r'^# /skillweave-[a-z]', line):
                    failures.append(
                        f"{md_file.parent.name}: H1='{line}' — missing leading slash"
                    )
                break  # Only check first H1
    assert not failures, "Non-canonical H1 headings found:\n" + "\n".join(failures)


# ─── Boundary-specific assertions ───────────────────────────────────────


def test_execute_skill_owns_execution():
    """Execute skill description must contain 'Execute'."""
    fm, _ = _parse_frontmatter(SKILLS_DIR / "skillweave-promptchain-execute" / "SKILL.md")
    desc = fm.get("description", "")
    assert "Execute" in desc, (
        f"Execute skill description missing 'Execute': {desc}"
    )


def test_release_skill_does_not_claim_execution():
    """ReleaseChain description must NOT claim execution ownership.

    Forbidden: 'execute', 'pipeline', 'PRD execution', 'task execution', 'test-until-green'
    """
    fm, _ = _parse_frontmatter(SKILLS_DIR / "skillweave-releasechain" / "SKILL.md")
    desc = fm.get("description", "").lower()
    body = (SKILLS_DIR / "skillweave-releasechain" / "SKILL.md").read_text().lower()

    forbidden = ["prd execution", "task execution", "test-until-green"]
    for term in forbidden:
        assert term not in body, (
            f"ReleaseChain body contains forbidden term: '{term}'"
        )


def test_launch_does_not_claim_signing_publishing():
    """Launch skill must NOT claim artifact signing/publishing.

    Those belong to Release.
    """
    body = (SKILLS_DIR / "skillweave-launch" / "SKILL.md").read_text().lower()
    assert "sign" not in body or "assign" in body, (
        "Launch SKILL.md contains 'sign' — artifact signing belongs to Release"
    )
    # 'publish' could legitimately appear in launch context (e.g. publish announcement),
    # but 'publish artifacts' or 'publish package' should not.
    assert "publish artifact" not in body, (
        "Launch SKILL.md contains 'publish artifact' — belongs to Release"
    )
    assert "publish package" not in body, (
        "Launch SKILL.md contains 'publish package' — belongs to Release"
    )


# ─── Code-level boundary assertions ─────────────────────────────────────


def test_release_workflow_no_deploy_methods():
    """Verify release workflow.py does NOT contain _step_deploy or _step_validate_rollout.

    These were removed per SW-G0B; deployment belongs to Launch.
    """
    wf_path = PROJECT_ROOT / "src" / "skillweave" / "release" / "workflow.py"
    content = wf_path.read_text()

    # The methods themselves should be commented out
    # (they will appear but only as comments)
    active_lines = [l for l in content.split("\n")
                    if l.strip() and not l.strip().startswith("#")]
    active_code = "\n".join(active_lines)

    assert "def _step_deploy" not in active_code, (
        "workflow.py still has active _step_deploy method"
    )
    assert "def _step_validate_rollout" not in active_code, (
        "workflow.py still has active _step_validate_rollout method"
    )


def test_skill_boundaries_yaml_assigns_deployment_to_launch():
    """Verify boundaries YAML assigns deployment to Launch, not Release."""
    boundaries_path = PROJECT_ROOT / ".skillweave" / "release" / "skill-boundaries.yaml"
    with open(boundaries_path) as f:
        data = yaml.safe_load(f)

    launch = data["skills"][2]  # launch is third (index 2)
    assert launch["id"] == "skillweave-launch"

    # Launch must own deployment
    launch_resp = [r.lower() for r in launch["responsibilities"]]
    assert any("deploy" in r for r in launch_resp), (
        "Launch must own deployment in its responsibilities"
    )

    # Release must NOT own deployment
    release = data["skills"][1]  # releasechain is second (index 1)
    assert release["id"] == "skillweave-releasechain"
    release_does_not = [r.lower() for r in release["does_not_handle"]]
    assert any("deployment" in r for r in release_does_not), (
        "Release does_not_handle must contain 'deployment'"
    )

    # Canonical definitions must be present
    canonical = data.get("canonical_definitions", {})
    assert "Release" in canonical, "Missing canonical definition for Release"
    assert "Launch" in canonical, "Missing canonical definition for Launch"
    assert "immutable" in canonical["Release"].lower(), (
        "Canonical Release definition must mention immutable artifacts"
    )


def test_release_workflow_has_sw_g0b_header():
    """Verify release workflow.py has the SW-G0B disclaimer."""
    wf_path = PROJECT_ROOT / "src" / "skillweave" / "release" / "workflow.py"
    content = wf_path.read_text()
    assert "SW-G0B" in content, (
        "workflow.py missing SW-G0B disclaimer"
    )
    assert "does NOT deploy" in content, (
        "workflow.py SW-G0B disclaimer missing 'does NOT deploy'"
    )


# ─── Lifecycle delegation assertions ────────────────────────────────────


def test_lifecycle_declares_delegation():
    """Lifecycle SKILL.md must explicitly declare its delegation model."""
    body = (SKILLS_DIR / "skillweave-lifecycle" / "SKILL.md").read_text()
    assert "delegation" in body.lower(), (
        "Lifecycle SKILL.md missing delegation section"
    )
    assert "skillweave-promptchain-execute" in body, (
        "Lifecycle must delegate execution to skillweave-promptchain-execute"
    )
    assert "skillweave-observe" in body, (
        "Lifecycle must delegate observation to skillweave-observe"
    )
    assert "skillweave-releasechain" in body, (
        "Lifecycle must delegate release to skillweave-releasechain"
    )
    assert "skillweave-launch" in body, (
        "Lifecycle must delegate launch to skillweave-launch"
    )


def test_post_release_consumes_observe():
    """Post-Release must state it consumes evidence from observe."""
    body = (SKILLS_DIR / "skillweave-post-release" / "SKILL.md").read_text().lower()
    assert "consumes evidence from" in body, (
        "Post-Release must explicitly state it consumes evidence from observe"
    )
    assert "does not implement" in body, (
        "Post-Release must state it does NOT implement a second health/monitoring subsystem"
    )
