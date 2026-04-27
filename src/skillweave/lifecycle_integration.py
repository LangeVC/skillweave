import os
import yaml
from typing import Optional

from .phase_detection import detect_phase, phase_from_config, detect_phase_with_detail
from .workflow_recommendation import recommend
from .onboarding_cli import load_onboarding_state


def enrich_config(project_root: str = "."):
    config_path = os.path.join(project_root, ".skillweave", "config.yaml")
    if not os.path.exists(config_path):
        return None

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    changed = False
    lifecycle = config.setdefault("lifecycle", {})

    if "current_phase" not in lifecycle:
        phase, confidence = detect_phase(project_root)
        lifecycle["current_phase"] = phase
        lifecycle["phase_confidence"] = round(confidence, 2)
        changed = True

    if "active_bundle" not in lifecycle:
        ob_state = load_onboarding_state(project_root)
        if ob_state and ob_state.get("recommended_bundle"):
            lifecycle["active_bundle"] = ob_state["recommended_bundle"]
        else:
            rec = recommend(project_root=project_root)
            if rec.get("recommended_bundle"):
                lifecycle["active_bundle"] = rec["recommended_bundle"]
        changed = True

    if changed:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

    return config


def get_lifecycle_context(project_root: str = ".") -> dict:
    config_path = os.path.join(project_root, ".skillweave", "config.yaml")
    context = {
        "phase_system_configured": False,
        "current_phase": None,
        "active_bundle": None,
        "phase_confidence": None,
    }

    if os.path.exists(config_path):
        with open(config_path) as f:
            config = yaml.safe_load(f) or {}
        lifecycle = config.get("lifecycle", {})
        if lifecycle:
            context["phase_system_configured"] = True
            context["current_phase"] = lifecycle.get("current_phase")
            context["active_bundle"] = lifecycle.get("active_bundle")
            context["phase_confidence"] = lifecycle.get("phase_confidence")

    return context
