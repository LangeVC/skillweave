from typing import Optional

from .phase_detection import detect_phase, detect_phase_with_detail
from .lifecycle import bundle_map

# The bundle definitions are the canonical lifecycle source; they are imported,
# not duplicated here (SW-LC-001).
BUNDLE_MAP = bundle_map()

# The phase→bundle resolution is recommendation POLICY (which bundle to offer for
# a detected phase), not a declaration of the lifecycle. It stays explicit so the
# recommender's ordering — the first candidate wins — is not silently reordered
# by the canonical bundle list.
DETECTED_PHASE_TO_BUNDLE: dict[str, list[str]] = {
    "discovery": ["discovery-to-blueprint", "full-lifecycle"],
    "blueprint": ["design-and-build", "full-lifecycle"],
    "design": ["design-and-build", "full-lifecycle"],
    "build": ["release-and-launch", "full-lifecycle"],
    "release": ["release-and-launch", "post-release-improvement"],
    "launch": ["post-release-improvement"],
    "post-release": ["post-release-improvement"],
}


def recommend(
    project_root: str = ".",
    goal: Optional[str] = None,
    override_phase: Optional[str] = None,
) -> dict:
    if override_phase:
        detected_phase = override_phase
        confidence = 1.0
    else:
        detection = detect_phase_with_detail(project_root)
        detected_phase = detection["phase"]
        confidence = detection["confidence"]

    if confidence < 0.5 and not override_phase:
        return {
            "recommended_bundle": None,
            "next_action": "onboarding",
            "gap_analysis": {"issue": "confidence_too_low", "phase": detected_phase, "confidence": confidence},
            "message": "Cannot reliably detect project phase. Please run interactive onboarding.",
        }

    goal_lower = (goal or "").lower()

    explicit_request = _match_goal_to_bundle(goal_lower)
    if explicit_request:
        bundle_id = explicit_request
    else:
        candidates = DETECTED_PHASE_TO_BUNDLE.get(detected_phase, ["full-lifecycle"])
        bundle_id = candidates[0]

    bundle = BUNDLE_MAP.get(bundle_id)
    if not bundle:
        bundle = BUNDLE_MAP["full-lifecycle"]
        bundle_id = "full-lifecycle"

    gap_analysis = _compute_gap(detected_phase, bundle_id, project_root)

    next_skill = _next_skill_for_phase(detected_phase, bundle_id)

    return {
        "recommended_bundle": bundle_id,
        "bundle_name": bundle["name"],
        "next_action": next_skill,
        "gap_analysis": gap_analysis,
        "detected_phase": detected_phase,
        "confidence": round(confidence, 2),
        "message": _build_message(detected_phase, bundle_id, gap_analysis),
    }


def _match_goal_to_bundle(goal: str) -> Optional[str]:
    if not goal:
        return None
    if any(kw in goal for kw in ["build an app", "full lifecycle", "from scratch", "new project"]):
        return "full-lifecycle"
    if any(kw in goal for kw in ["research", "explore", "discover", "validate"]):
        return "discovery-to-blueprint"
    if any(kw in goal for kw in ["ship", "release", "deploy", "publish"]):
        return "release-and-launch"
    if any(kw in goal for kw in ["finish", "implement", "build feature", "code"]):
        return "design-and-build"
    if any(kw in goal for kw in ["iterate", "improve", "post-release", "feedback"]):
        return "post-release-improvement"
    return None


def _compute_gap(detected_phase: str, bundle_id: str, project_root: str) -> dict:
    bundle = BUNDLE_MAP.get(bundle_id)
    if not bundle:
        return {"issue": "unknown_bundle"}

    phases = bundle["phases"]
    try:
        phase_idx = phases.index(detected_phase)
        missing = phases[phase_idx + 1:]
    except ValueError:
        missing = phases

    if missing:
        return {"missing_phases": missing, "severity": "warning"}
    return {"missing_phases": [], "severity": "ok"}


def _next_skill_for_phase(phase: str, bundle_id: str) -> str:
    mapping = {
        "discovery": "skillweave-blueprint",
        "blueprint": "skillweave-promptchain-generate",
        "design": "frontend-design",
        "build": "skillweave-promptchain-execute",
        "release": "skillweave-releasechain",
        "launch": "skillweave-releasechain",
        "post-release": "skillweave-promptchain-generate",
    }
    return mapping.get(phase, "skillweave-blueprint")


def _build_message(phase: str, bundle_id: str, gap: dict) -> str:
    bundle = BUNDLE_MAP.get(bundle_id, {})
    msg = f"Detected phase: **{phase}**. Recommended bundle: **{bundle.get('name', bundle_id)}**."

    if gap.get("missing_phases"):
        missing = ", ".join(gap["missing_phases"])
        msg += f" Upcoming phases: {missing}."

    return msg
