import os
import yaml
from pathlib import Path
from typing import Optional

PHASE_INDICATORS = {
    "discovery": {
        "files": [],
        "patterns": [],
        "description": "No formal project artifacts exist yet",
        "confidence_if_empty": 0.9,
    },
    "blueprint": {
        "files": [".skillweave/prds/", ".skillweave/sequences/"],
        "patterns": ["prd.md", "prd.json"],
        "description": "PRD or planning artifacts present, no source code",
        "confidence_if_empty": 0.0,
    },
    "design": {
        "files": [],
        "patterns": [],
        "description": "Design artifacts or frontend planning exists",
        "confidence_if_empty": 0.0,
    },
    "build": {
        "files": ["src/", "tests/"],
        "patterns": [".py", ".js", ".ts", ".rs", ".go"],
        "description": "Source code and tests present",
        "confidence_if_empty": 0.0,
    },
    "release": {
        "files": [".skillweave/release/", "CHANGELOG.md"],
        "patterns": ["CHANGELOG.md"],
        "description": "Release artifacts, changelog, version tags",
        "confidence_if_empty": 0.0,
    },
    "launch": {
        "files": [],
        "patterns": [],
        "description": "Deployment config, launch checklists",
        "confidence_if_empty": 0.0,
    },
    "post-release": {
        "files": [],
        "patterns": [],
        "description": "Monitoring, retrospective, feedback collection",
        "confidence_if_empty": 0.0,
    },
}


def _check_file_exists(root: str, pattern: str) -> bool:
    path = os.path.join(root, pattern)
    if pattern.endswith("/"):
        return os.path.isdir(path)
    return os.path.exists(path)


def _check_pattern_exists(root: str, ext: str) -> bool:
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.endswith(ext):
                return True
    return False


def _check_any_file(root: str, paths: list[str]) -> bool:
    for p in paths:
        if _check_file_exists(root, p):
            return True
    return False


def _check_any_pattern(root: str, patterns: list[str]) -> bool:
    if _check_pattern_exists(root, ".py"):
        return True
    for p in patterns:
        if _check_pattern_exists(root, p):
            return True
    return False


def detect_phase(project_root: str = ".") -> tuple[str, float]:
    root = os.path.abspath(project_root)
    scores: dict[str, float] = {}

    for phase_id, indicators in PHASE_INDICATORS.items():
        score = 0.0
        if indicators["files"]:
            score += 0.5 if _check_any_file(root, indicators["files"]) else 0.0
        if indicators["patterns"]:
            score += 0.5 if _check_any_pattern(root, indicators["patterns"]) else 0.0

        if score == 0.0 and phase_id == "discovery":
            score = indicators["confidence_if_empty"]
        elif score == 0.0 and indicators["confidence_if_empty"] > 0:
            score = indicators["confidence_if_empty"]

        scores[phase_id] = score

    if not scores or all(s == 0.0 for s in scores.values()):
        return "discovery", 0.85

    detected = max(scores, key=scores.get)
    confidence = scores[detected]

    for phase_id in ["discovery", "blueprint", "design", "build", "release", "launch", "post-release"]:
        if phase_id == detected:
            break
        if scores.get(phase_id, 0) > 0:
            pass

    return detected, min(confidence, 1.0)


def detect_phase_with_detail(project_root: str = ".") -> dict:
    phase, confidence = detect_phase(project_root)
    root = os.path.abspath(project_root)

    evidence = {}
    for phase_id, indicators in PHASE_INDICATORS.items():
        evidence[phase_id] = {
            "files_found": [f for f in indicators["files"] if _check_file_exists(root, f)],
            "patterns_found": [p for p in indicators["patterns"] if _check_pattern_exists(root, p)],
        }

    return {
        "phase": phase,
        "confidence": round(confidence, 2),
        "evidence": evidence,
        "project_root": root,
    }


def phase_from_config(project_root: str = ".") -> Optional[str]:
    config_path = os.path.join(project_root, ".skillweave", "config.yaml")
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return config.get("current_phase")
    except Exception:
        return None
