import enum
import json
import os
from dataclasses import dataclass, asdict
from typing import Optional

from .scanner import InventoryItem


class Classification(enum.Enum):
    ACTIVE_CORE = "active_core"
    CONSOLIDATION = "consolidation"
    LEGACY = "legacy"
    DEPRECATED = "deprecated"
    NEEDS_REVIEW = "needs_review"


@dataclass
class ClassifiedItem:
    item: InventoryItem
    classification: Classification
    reason: str
    confidence: float


DEPRECATED_PATTERNS = {"__pycache__", ".DS_Store", "node_modules", ".mypy_cache", ".pytest_cache", ".egg-info"}
LEGACY_PATTERNS = {"migrations", "backup", "old", "bak", "backup", "legacy", "vendor", ".terraform"}
CONSOLIDATION_PATTERNS = {".gitkeep", "readme", "readme.md", "readme.txt", "makefile", "docker-compose.override.yml"}
ACTIVE_CORE_DIRS = {"src", "tests", "lib", "app", "components", "pages", "api", "routes"}
NEEDS_REVIEW_PATTERNS = {"TODO", "FIXME", "HACK", "XXX", ".patch", ".diff"}


def _classify_single(item: InventoryItem) -> tuple[Classification, str, float]:
    rel = item.path.lower()
    name = os.path.basename(item.path).lower()
    ext = item.file_type
    parent = os.path.basename(os.path.dirname(item.path)).lower()

    # Deprecated — cache/build artefacts
    if parent in DEPRECATED_PATTERNS or name in DEPRECATED_PATTERNS:
        return Classification.DEPRECATED, f"Cache/build directory: {parent}", 1.0
    if ext == "pyc":
        return Classification.DEPRECATED, "Compiled bytecode (regeneratable)", 1.0

    # Legacy — old/backup/migration
    for pat in LEGACY_PATTERNS:
        if pat in rel or pat in parent:
            return Classification.LEGACY, f"Legacy indicator: {pat}", 0.9

    # Consolidation — meta/doc
    if name in CONSOLIDATION_PATTERNS:
        return Classification.CONSOLIDATION, "Meta/doc file (can consolidate)", 0.9
    if ext in {"md", "rst", "txt"} and item.size_bytes < 5000:
        return Classification.CONSOLIDATION, "Small documentation file", 0.7

    # Active Core
    dir_parts = rel.split(os.sep)
    if any(d in ACTIVE_CORE_DIRS for d in dir_parts):
        if ext in {"py", "js", "ts", "tsx", "jsx", "go", "rs", "java", "kt"}:
            return Classification.ACTIVE_CORE, f"Source in core directory", 0.95
        if ext in {"yaml", "yml", "json", "toml", "cfg", "ini"}:
            return Classification.ACTIVE_CORE, "Config in core directory", 0.8

    # Needs Review markers
    for pat in NEEDS_REVIEW_PATTERNS:
        if pat in name:
            return Classification.NEEDS_REVIEW, f"Marker found: {pat}", 0.8

    # Fallback: source files in root → Active Core
    if ext in {"py", "js", "ts", "go", "rs"}:
        return Classification.ACTIVE_CORE, "Source file (no subdir)", 0.7

    return Classification.NEEDS_REVIEW, "Could not classify automatically", 0.4


def classify_items(items: list[InventoryItem]) -> list[ClassifiedItem]:
    return [ClassifiedItem(item=i, classification=c, reason=r, confidence=conf)
            for i in items
            for c, r, conf in [_classify_single(i)]]


def write_classification_report(classified: list[ClassifiedItem], path: str):
    data = []
    for c in classified:
        entry = asdict(c)
        entry["classification"] = c.classification.value
        entry["item"] = asdict(c.item)
        data.append(entry)

    with open(path, "w") as f:
        json.dump(data, f, indent=2)
