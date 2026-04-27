import os
import yaml
import logging
from typing import Optional
from datetime import datetime

from .phase_detection import detect_phase

PHASE_MEMBERSHIP: dict[str, list[str]] = {
    "skillweave-blueprint": ["discovery", "blueprint"],
    "skillweave-promptchain-generate": ["blueprint", "design"],
    "skillweave-promptchain-validate": ["blueprint", "design", "build"],
    "skillweave-promptchain-execute": ["build", "release"],
    "skillweave-releasechain": ["build", "release", "launch"],
    "frontend-design": ["design", "build"],
    "last30days": ["discovery"],
}


def check_phase(skill_name: str, project_root: str = ".", override: bool = False) -> dict:
    if override:
        return {"allowed": True, "reason": "override"}

    config_phase = _phase_from_config(project_root)
    if config_phase:
        current_phase = config_phase
    else:
        current_phase, _ = detect_phase(project_root)

    allowed_phases = PHASE_MEMBERSHIP.get(skill_name, [])
    in_phase = current_phase in allowed_phases if allowed_phases else True

    result = {
        "skill": skill_name,
        "current_phase": current_phase,
        "allowed_phases": allowed_phases,
        "in_phase": in_phase,
        "allowed": in_phase,
    }

    if not in_phase:
        result["recommendation"] = (
            f"**Phase Recommendation**: `{skill_name}` is designed for "
            f"{', '.join(allowed_phases)} phase(s), but the project appears to be in "
            f"**{current_phase}**. Phase mismatch recommendations are advisory — "
            f"use `override=true` to proceed."
        )
        result["allowed"] = True
        _log_violation(skill_name, current_phase, project_root)

    return result


def _phase_from_config(project_root: str) -> Optional[str]:
    config_path = os.path.join(project_root, ".skillweave", "config.yaml")
    if not os.path.exists(config_path):
        return None
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return config.get("current_phase")
    except Exception:
        return None


def _log_violation(skill_name: str, current_phase: str, project_root: str):
    log_dir = os.path.join(project_root, ".skillweave", "tracking-log")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "phase-violations.log")
    entry = f"[{datetime.now().isoformat()}] PHASE_VIOLATION: {skill_name} invoked during {current_phase}\n"
    with open(log_path, "a") as f:
        f.write(entry)
