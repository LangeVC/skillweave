"""The single canonical source of the SkillWeave lifecycle.

Phases, phase skills, bundles, and the skill→phase membership live HERE, in
one module, and nowhere else. ``phase_enforcement`` and
``workflow_recommendation`` import from this module; the ``.skillweave`` YAML
files are a generated, human-readable mirror of this module — never a second
source of truth (SW-LC-001).

A phase's ``skills`` list names only real skill ids (a directory under
``skills/``). Capabilities are a separate concern and live under
``capabilities``; a capability name in a ``skills`` list is a defect the
validation test rejects. A phase with no skills is explicit (empty list), never
implicit absence.
"""

from __future__ import annotations

# Canonical phase order. ``order`` is 1-based and stable; consumers that need
# sequence use this list, not the YAML file order.
PHASES: list[dict] = [
    {
        "id": "discovery",
        "order": 1,
        "skills": ["skillweave-discovery", "skillweave-blueprint", "skillweave-council"],
        "capabilities": ["planning", "research"],
        "phase_type": "optional",
    },
    {
        "id": "blueprint",
        "order": 2,
        "skills": ["skillweave-blueprint", "skillweave-promptchain-generate", "skillweave-promptchain-validate"],
        "capabilities": ["planning", "architecture"],
        "phase_type": "recommended",
    },
    {
        "id": "design",
        "order": 3,
        "skills": ["skillweave-design", "frontend-design"],
        "capabilities": ["design", "architecture"],
        "phase_type": "optional",
    },
    {
        "id": "build",
        "order": 4,
        "skills": ["skillweave-promptchain-execute", "skillweave-releasechain", "skillweave-observe"],
        "capabilities": ["code_generation", "testing", "infrastructure"],
        "phase_type": "core",
    },
    {
        "id": "release",
        "order": 5,
        "skills": ["skillweave-releasechain", "skillweave-observe"],
        "capabilities": ["release", "testing"],
        "phase_type": "core",
    },
    {
        "id": "launch",
        "order": 6,
        "skills": ["skillweave-launch"],
        "capabilities": ["deployment", "communication"],
        "phase_type": "optional",
    },
    {
        "id": "post-release",
        "order": 7,
        "skills": ["skillweave-post-release", "skillweave-repo-health", "skillweave-observe", "skillweave-discovery"],
        "capabilities": ["analysis", "planning"],
        "phase_type": "optional",
    },
]

# Skills that ship but belong to no single phase; they are available across the
# lifecycle and are declared here (not silently absent).
GLOBAL_SKILLS: dict[str, dict] = {
    "skillweave-lifecycle": {
        "id": "skillweave-lifecycle",
        "type": "plan",
        "description": "Navigation, Bundle-Auswahl, Phasen-Status",
    },
    "skillweave-repo-health": {
        "id": "skillweave-repo-health",
        "type": "plan",
        "description": "Repo-Hygiene jederzeit ausführbar",
    },
    "skillweave-observe": {
        "id": "skillweave-observe",
        "type": "plan",
        "description": "Reports, Metriken, Memory — nur Lesezugriff",
    },
}

# Skills named by a phase but shipped outside this repository (independent
# skills in separate packages/installs). Declared explicitly so the validation
# can tell "external, expected reference" from "dead id" (``last30days`` was the
# latter and is gone).
EXTERNAL_SKILLS = frozenset({"frontend-design"})

BUNDLES: list[dict] = [
    {
        "id": "full-lifecycle",
        "name": "Full Lifecycle",
        "phases": ["discovery", "blueprint", "design", "build", "release", "launch", "post-release"],
        "entry_requires": ["Project idea or problem statement"],
    },
    {
        "id": "discovery-to-blueprint",
        "name": "Discovery to Blueprint",
        "phases": ["discovery", "blueprint"],
        "entry_requires": ["Problem or opportunity to explore"],
    },
    {
        "id": "design-and-build",
        "name": "Design and Build",
        "phases": ["design", "build"],
        "entry_requires": ["Valid PRD or clear requirements"],
    },
    {
        "id": "release-and-launch",
        "name": "Release and Launch",
        "phases": ["release", "launch"],
        "entry_requires": ["Working code in releasable state"],
    },
    {
        "id": "post-release-improvement",
        "name": "Post-Release Improvement",
        "phases": ["post-release", "blueprint", "build"],
        "entry_requires": ["System is live in production"],
    },
]


def phase_ids() -> list[str]:
    """Return the phases in canonical order."""
    return [p["id"] for p in PHASES]


def skill_membership() -> dict[str, list[str]]:
    """Return ``{skill_id: [phase ids]}` for every phase-assigned skill.

    This is the canonical replacement for the hardcoded
    ``phase_enforcement.PHASE_MEMBERSHIP``. Skills that ship only as
    ``GLOBAL_SKILLS`` are intentionally absent here: they are not bound to a
    phase.
    """
    membership: dict[str, list[str]] = {}
    for phase in PHASES:
        for skill in phase["skills"]:
            membership.setdefault(skill, []).append(phase["id"])
    return membership


def bundle_map() -> dict[str, dict]:
    """Return the canonical bundle map consumed by ``workflow_recommendation``.

    Keys are bundle ids; values carry ``name``, ``phases`` and
    ``entry_requires`` so the recommender never needs its own copy.
    """
    return {b["id"]: b for b in BUNDLES}


def to_yaml() -> str:
    """Serialize the canonical lifecycle to the public YAML representation.

    This is the generator half of the contract: ``to_yaml`` produces
    ``phases.yaml``/``bundles.yaml`` content, and ``load_skillweave_yaml`` (or
    any YAML consumer) parses it back. The single-source test asserts the two
    sides agree.
    """
    import yaml

    phases_payload = {
        "phases": [
            {
                "id": p["id"],
                "order": p["order"],
                "skills": list(p["skills"]),
                "capabilities": list(p["capabilities"]),
                "phase_type": p["phase_type"],
            }
            for p in PHASES
        ],
        "global_skills": list(GLOBAL_SKILLS.values()),
    }
    bundles_payload = {
        "bundles": [
            {"id": b["id"], "name": b["name"], "phases": list(b["phases"]), "entry_requires": list(b["entry_requires"])}
            for b in BUNDLES
        ]
    }
    return yaml.safe_dump(phases_payload, sort_keys=False, default_flow_style=False) + "\n---\n" + yaml.safe_dump(
        bundles_payload, sort_keys=False, default_flow_style=False
    )


def load_skillweave_yaml(text: str) -> tuple[list[dict], list[dict]]:
    """Parse a ``to_yaml`` payload back into (phases, bundles).

    This is the consumer half of the contract. It accepts the exact document
    ``to_yaml`` emits (two YAML documents separated by ``---``) and returns the
    structured lists so a test can compare them against the module's own
    ``PHASES``/``BUNDLES``.
    """
    import yaml

    docs = [d for d in yaml.safe_load_all(text) if d]
    phases = docs[0]["phases"]
    bundles = docs[1]["bundles"]
    return phases, bundles
