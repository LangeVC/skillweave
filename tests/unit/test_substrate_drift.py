"""Substrate map and drift detection tests (SW-SUBSTRATE-DOC-001).

Proves that:
1. ``docs/substrate-map.md`` exists, is well-formed, and documents all 26 canonical
   substrate areas under ``.skillweave/``.
2. Every item currently on disk in ``.skillweave/`` is documented (no undocumented drift).
3. Each area entry includes required metadata: owner skill/subsystem and lifecycle phase.
4. A synthetic undocumented area is properly detected and flagged as drift.
"""

import os
import re
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOC_PATH = REPO_ROOT / "docs" / "substrate-map.md"
DOT_SKILLWEAVE = REPO_ROOT / ".skillweave"

#: The 26 canonical substrate areas under .skillweave/
CANONICAL_26_AREAS = [
    "archive",
    "bundles.yaml",
    "checklists",
    "cleanup",
    "config.yaml",
    "design",
    "discovery",
    "handover",
    "hooks",
    "lenses",
    "lib",
    "licenses",
    "lifecycle",
    "manifesto",
    "memory",
    "onboarding-state.yaml",
    "phases.yaml",
    "planning",
    "prds",
    "prompts",
    "release",
    "reports",
    "sequences",
    "specs",
    "templates",
    "tracking-log",
]


def extract_documented_areas(doc_text: str) -> set[str]:
    """Extract all documented .skillweave/ top-level area names from docs/substrate-map.md."""
    documented = set()
    
    # 1. Parse markdown table rows: | # | `area` | Kind | Owner | Phase | ...
    table_pattern = re.compile(r'\|\s*\d+\s*\|\s*`([^`/]+)(?:/)?`\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|')
    for match in table_pattern.finditer(doc_text):
        area_name = match.group(1).strip()
        documented.add(area_name)

    # 2. Parse section headers: ### 3.X `area/`
    header_pattern = re.compile(r'###\s*\d+\.\d+\s*`([^`/]+)(?:/)?`')
    for match in header_pattern.finditer(doc_text):
        area_name = match.group(1).strip()
        documented.add(area_name)

    return documented


def get_disk_substrate_areas(dot_skillweave_dir: Path) -> set[str]:
    """List all actual top-level files and directories in .skillweave/."""
    if not dot_skillweave_dir.exists():
        return set()
    return {
        item for item in os.listdir(dot_skillweave_dir)
        if not item.startswith(".") and item != "__pycache__"
    }


def check_substrate_drift(doc_path: Path = DOC_PATH, dot_skillweave_dir: Path = DOT_SKILLWEAVE) -> list[str]:
    """Detect any undocumented areas in .skillweave/ relative to docs/substrate-map.md.
    
    Returns a list of error messages (empty if no drift).
    """
    if not doc_path.exists():
        return [f"Documentation missing: {doc_path}"]

    doc_text = doc_path.read_text(encoding="utf-8")
    documented = extract_documented_areas(doc_text)
    on_disk = get_disk_substrate_areas(dot_skillweave_dir)

    errors = []
    
    # Check if any item on disk is missing from documentation
    undocumented_on_disk = on_disk - documented
    if undocumented_on_disk:
        errors.append(
            f"Undocumented .skillweave area(s) detected on disk: {sorted(undocumented_on_disk)}. "
            f"Please register and document them in docs/substrate-map.md."
        )

    # Check that all canonical 26 areas are documented
    missing_canonical = set(CANONICAL_26_AREAS) - documented
    if missing_canonical:
        errors.append(
            f"Canonical area(s) missing from docs/substrate-map.md: {sorted(missing_canonical)}"
        )

    return errors


class TestSubstrateDocumentationAndDrift:
    """Test suite for .skillweave substrate map and drift detection."""

    def test_doc_exists_and_is_non_empty(self):
        """Verify docs/substrate-map.md exists and is substantive."""
        assert DOC_PATH.exists(), f"Missing required documentation: {DOC_PATH}"
        text = DOC_PATH.read_text(encoding="utf-8")
        assert len(text) > 1000, "docs/substrate-map.md is too short or empty"
        assert "# SkillWeave Substrate Map" in text

    def test_all_26_canonical_areas_documented(self):
        """Verify all 26 canonical areas are explicitly documented."""
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        documented = extract_documented_areas(doc_text)
        
        for area in CANONICAL_26_AREAS:
            assert area in documented, f"Canonical area '{area}' is missing from docs/substrate-map.md"

        assert len(documented.intersection(set(CANONICAL_26_AREAS))) == 26

    def test_no_disk_drift(self):
        """Verify that every entry currently on disk in .skillweave/ is documented."""
        drift_errors = check_substrate_drift(DOC_PATH, DOT_SKILLWEAVE)
        assert not drift_errors, "\n".join(drift_errors)

    def test_ownership_and_lifecycle_metadata_present(self):
        """Verify that each canonical area has documented ownership and lifecycle phase."""
        doc_text = DOC_PATH.read_text(encoding="utf-8")
        
        # Check table entries
        table_pattern = re.compile(
            r'\|\s*\d+\s*\|\s*`([^`/]+)(?:/)?`\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|'
        )
        matches = list(table_pattern.finditer(doc_text))
        assert len(matches) == 26, f"Expected exactly 26 table rows, found {len(matches)}"

        for match in matches:
            area = match.group(1).strip()
            kind = match.group(2).strip()
            owner = match.group(3).strip()
            phase = match.group(4).strip()
            mutability = match.group(5).strip()
            purpose = match.group(6).strip()

            assert kind, f"Missing kind for area '{area}'"
            assert owner, f"Missing owner skill for area '{area}'"
            assert phase, f"Missing lifecycle phase for area '{area}'"
            assert mutability, f"Missing mutability for area '{area}'"
            assert purpose, f"Missing purpose description for area '{area}'"

    def test_drift_detector_catches_synthetic_undocumented_area(self, tmp_path):
        """Verify the drift test logic correctly catches newly created undocumented areas."""
        # Create a mock .skillweave directory with an extra undocumented area
        mock_skillweave = tmp_path / ".skillweave"
        mock_skillweave.mkdir()
        
        # Copy existing disk items
        for item in get_disk_substrate_areas(DOT_SKILLWEAVE):
            (mock_skillweave / item).mkdir(exist_ok=True)
            
        # Add synthetic undocumented area
        (mock_skillweave / "undocumented_new_feature_dir").mkdir()
        (mock_skillweave / "undocumented_config.json").touch()

        errors = check_substrate_drift(DOC_PATH, mock_skillweave)
        assert errors, "Drift detector should have flagged undocumented items"
        assert "undocumented_new_feature_dir" in errors[0]
        assert "undocumented_config.json" in errors[0]
