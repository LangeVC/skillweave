import os
import yaml
from typing import Optional

from .phase_detection import detect_phase_with_detail
from .workflow_recommendation import recommend


ONBOARDING_STATE_PATH = ".skillweave/onboarding-state.yaml"


def run_onboarding(project_root: str = ".", skip: bool = False) -> dict:
    if skip:
        return {"skipped": True}

    root = os.path.abspath(project_root)

    detection = detect_phase_with_detail(root)
    detected_phase = detection["phase"]
    confidence = detection["confidence"]
    print(f"Detected phase: {detected_phase} (confidence: {confidence:.0%})")

    if confidence >= 0.5:
        print(f"Based on project artifacts, you appear to be in the **{detected_phase}** phase.")
    else:
        print("Could not automatically detect your project phase.")
        detected_phase = _ask_phase()

    goal = input("What is your goal? (e.g. 'build an app', 'ship it', 'research'): ").strip()
    if not goal:
        goal = None

    result = recommend(project_root=root, override_phase=detected_phase, goal=goal)

    print(f"\nRecommended bundle: **{result['bundle_name']}**")
    print(f"Next action: {result['next_action']}")
    if result["gap_analysis"].get("missing_phases"):
        print(f"Upcoming phases: {', '.join(result['gap_analysis']['missing_phases'])}")
    print(f"\n{result['message']}")

    state = {
        "phase": detected_phase,
        "goal": goal,
        "recommended_bundle": result["recommended_bundle"],
        "next_action": result["next_action"],
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }
    _save_state(root, state)

    return state


def load_onboarding_state(project_root: str = ".") -> Optional[dict]:
    path = os.path.join(os.path.abspath(project_root), ONBOARDING_STATE_PATH)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _save_state(project_root: str, state: dict):
    path = os.path.join(project_root, ONBOARDING_STATE_PATH)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(state, f, default_flow_style=False)


def _ask_phase() -> str:
    phases = ["discovery", "blueprint", "design", "build", "release", "launch", "post-release"]
    print("\nSelect your current phase:")
    for i, p in enumerate(phases, 1):
        print(f"  {i}. {p}")
    while True:
        try:
            choice = int(input(f"Enter number (1-{len(phases)}): "))
            if 1 <= choice <= len(phases):
                return phases[choice - 1]
        except ValueError:
            pass
        print("Invalid choice. Try again.")
