import os
import subprocess
import yaml
from typing import List, Optional

from .phase_detection import detect_phase_with_detail
from .workflow_recommendation import recommend


ONBOARDING_STATE_PATH = ".skillweave/onboarding-state.yaml"

# The substrate exclusion entry, kept in sync with the one that
# SkillWeavePersistence._ensure_gitignore writes (see docs/substrate-map.md,
# invariant 5). Anchored so a nested fixture root is not swallowed.
GITIGNORE_ENTRY = "/.skillweave/"

# The public mirror host. A repository whose ``origin`` remote resolves here is
# the read-only GitHub mirror of this tool and must never carry substrate
# content (docs/substrate-map.md, invariant 5).
PUBLIC_HOST = "github.com"

# The substrate rule, taught during onboarding. It is stated verbatim so a new
# project ends up configured correctly without the operator explaining it.
SUBSTRATE_RULE = (
    "The substrate rule: what lives under `.skillweave/` (PRDs, specs, "
    "sequences, discovery findings, handover records) is generated project "
    "intellectual property, not open content. Direction, durability and "
    "disclosure are declared per area, and git answers none of them on its "
    "own. A public repository never carries substrate content; it is tracked "
    "only in the private per-org planning repository. A dispatched lane "
    "receives its PRD by injection, so committing the substrate to make it "
    "reachable trades an IP boundary for a convenience the dispatcher already "
    "provides."
)

# ---------------------------------------------------------------------------
# Role / purpose / autonomy / risk-boundary vocabulary
# ---------------------------------------------------------------------------
#
# Onboarding asks four questions beyond phase and goal: a role, a purpose, a
# desired autonomy and a risk boundary. Each is a CLOSED choice with a usable
# default, never free text. Free text was rejected deliberately: an open field
# invites a person to type a name or an email address, and unlike a closed
# choice that text has nowhere defined to go once collected. A closed choice
# keeps the profile a statement of capability and working style, so no name,
# email address or other personal identifier is ever solicited, stored or
# required (a blank answer is always valid - it takes the default).
#
# The four fields are ordered as they are asked, and each has a parallel
# ``_meaning`` map so the rationale can say what a choice means rather than
# only echoing its token.

PROFILE_FIELDS = ("role", "purpose", "autonomy", "risk_boundary")

ROLE_CHOICES = ("operator", "developer", "reviewer", "researcher")
PURPOSE_CHOICES = ("build", "review", "research", "operate")
AUTONOMY_CHOICES = ("guided", "supervised", "autonomous")
# The risk boundary reuses the canonical risk-mode vocabulary (RiskMode in
# persistence.py, RiskModeStr in risk_mode_resolver.py) rather than inventing
# a parallel scale. A drift test pins the two together.
RISK_BOUNDARY_CHOICES = ("conservative", "medium", "unicorn")

ROLE_MEANINGS = {
    "operator": "run and supervise a project lifecycle end to end",
    "developer": "implement and maintain code in an existing project",
    "reviewer": "assess and gate work produced elsewhere",
    "researcher": "gather and validate information before committing to a build",
}

PURPOSE_MEANINGS = {
    "build": "produce new artifacts",
    "review": "assess existing artifacts",
    "research": "reduce uncertainty before building",
    "operate": "keep an existing system running",
}

AUTONOMY_MEANINGS = {
    "guided": "confirm each step before it runs",
    "supervised": "run and pause at the gates",
    "autonomous": "run without per-step confirmation",
}

RISK_BOUNDARY_MEANINGS = {
    "conservative": "no destructive or irreversible action without approval",
    "medium": "destructive action only after confirmation",
    "unicorn": "destructive action allowed with a warning",
}

# Defaults are the safe, least-committing choice in each vocabulary. Because
# every question has a default, pressing Enter is always a complete answer and
# a non-interactive caller can rely on the defaults entirely.
ROLE_DEFAULT = "developer"
PURPOSE_DEFAULT = "build"
AUTONOMY_DEFAULT = "guided"
RISK_BOUNDARY_DEFAULT = "conservative"

PROFILE_CHOICES = {
    "role": ROLE_CHOICES,
    "purpose": PURPOSE_CHOICES,
    "autonomy": AUTONOMY_CHOICES,
    "risk_boundary": RISK_BOUNDARY_CHOICES,
}

PROFILE_DEFAULTS = {
    "role": ROLE_DEFAULT,
    "purpose": PURPOSE_DEFAULT,
    "autonomy": AUTONOMY_DEFAULT,
    "risk_boundary": RISK_BOUNDARY_DEFAULT,
}

PROFILE_MEANINGS = {
    "role": ROLE_MEANINGS,
    "purpose": PURPOSE_MEANINGS,
    "autonomy": AUTONOMY_MEANINGS,
    "risk_boundary": RISK_BOUNDARY_MEANINGS,
}

# Each question names the axis, not the person. None asks for an identifier.
PROFILE_QUESTIONS = {
    "role": "What is your role on this project?",
    "purpose": "What is the purpose of this onboarding?",
    "autonomy": "How much autonomy should SkillWeave have?",
    "risk_boundary": "What risk boundary should it hold?",
}


def _is_git_project(root: str) -> bool:
    """True when ``root`` lives inside a git work tree."""
    dotgit = os.path.join(root, ".git")
    # A worktree uses a ``.git`` *file*; a normal checkout uses a directory.
    if os.path.isdir(dotgit) or os.path.isfile(dotgit):
        return True
    return _git_top_level(root) is not None


def _git_top_level(root: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _git_origin_url(root: str) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _is_public_remote(url: Optional[str]) -> bool:
    """True when the ``origin`` remote points at a public host.

    The public GitHub mirror is the only host the product itself treats as
    public (this repository is mirrored read-only to ``github.com``). A local
    or self-hosted forge is not assumed public.
    """
    if not url:
        return False
    return PUBLIC_HOST in url


def _git_tracked_substrate(root: str) -> List[str]:
    """Paths under `.skillweave/` that git is currently tracking."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", ".skillweave"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if out.returncode != 0:
        return []
    return [line for line in out.stdout.splitlines() if line.strip()]


def _ensure_gitignore_exclusion(root: str) -> bool:
    """Add the anchored substrate exclusion to ``.gitignore``, if absent.

    Returns True when the file was written. An absent ``.gitignore`` is
    created so that a git project can never silently leave the substrate
    tracked.
    """
    path = os.path.join(root, ".gitignore")
    content = ""
    if os.path.exists(path):
        with open(path) as f:
            content = f.read()
    lines = content.splitlines()
    if GITIGNORE_ENTRY in lines:
        return False
    lines.append("")
    lines.append("# SkillWeave substrate (auto-generated by onboarding)")
    lines.append(GITIGNORE_ENTRY)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return True


def _ask_yes_no(prompt: str) -> bool:
    while True:
        answer = input(prompt).strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def _ask_choice(field: str) -> str:
    """Ask one closed-choice profile question and return a validated value.

    The question always has a default, so a blank answer and an exhausted input
    stream both resolve to the default rather than looping forever or raising.
    An exhausted stream is either EOF (no interactive stdin at all) or an
    automated answer list that has run out; both mean "take the default", which
    is what makes non-interactive onboarding possible. Looping is reserved for
    a genuinely interactive user who typed something that is neither blank nor
    a listed choice: they are re-shown the menu.
    """
    choices = PROFILE_CHOICES[field]
    default = PROFILE_DEFAULTS[field]
    prompt = (
        f"\n{PROFILE_QUESTIONS[field]}\n"
        f"Choose one (custom: type a listed value). Default: {default}\n"
        f"Options: {', '.join(choices)}"
    )
    while True:
        try:
            raw = input(f"{prompt}\nEnter {field} (blank = {default}): ")
        except (EOFError, StopIteration):
            return default
        answer = raw.strip().lower()
        if not answer:
            return default
        if answer in choices:
            return answer
        # Unrecognized: re-offer rather than guess, so the recorded value is
        # always one of the declared choices.
        print(f"Please choose one of: {', '.join(choices)} (or blank for {default}).")


def _extend_choice(field: str, value: str) -> str:
    """Validate a caller-supplied profile value, falling back to the default.

    This is the custom extension point: a caller (or a future non-interactive
    entry point) may pass any of the four fields directly, without driving the
    prompts. A value outside the closed vocabulary is not accepted silently;
    it falls back to the documented default so the profile is always valid.
    """
    if not isinstance(value, str):
        return PROFILE_DEFAULTS[field]
    normalized = value.strip().lower()
    if normalized in PROFILE_CHOICES[field]:
        return normalized
    return PROFILE_DEFAULTS[field]


def _collect_profile(**overrides) -> dict:
    """Collect the four profile fields, asking only for those not overridden.

    Accepting overrides is what makes onboarding scriptable and testable: a
    caller can supply any subset and only the remaining fields are asked.
    """
    profile = {}
    for field in PROFILE_FIELDS:
        override = overrides.get(field, None)
        if override is None:
            profile[field] = _ask_choice(field)
        else:
            profile[field] = _extend_choice(field, override)
    return profile


def _profile_rationale(profile: dict) -> str:
    """One sentence stating what the profile asserts and why it is coherent.

    The rationale composes the declared meanings rather than restating tokens,
    so it reads as a justification of the configuration, not a transcript of
    the answers.
    """
    role = profile["role"]
    purpose = profile["purpose"]
    autonomy = profile["autonomy"]
    boundary = profile["risk_boundary"]
    return (
        f"Role '{role}' means to {PROFILE_MEANINGS['role'][role]}; purpose "
        f"'{purpose}' means to {PROFILE_MEANINGS['purpose'][purpose]}. Autonomy "
        f"'{autonomy}' means to {PROFILE_MEANINGS['autonomy'][autonomy]}, bounded "
        f"by '{boundary}': {PROFILE_MEANINGS['risk_boundary'][boundary]}. This "
        f"holds because the declared purpose and the role agree on what this "
        f"project is for, and the autonomy never exceeds the risk boundary."
    )


def _build_onboarding_result(profile: dict, next_action: str) -> dict:
    """Assemble the nested onboarding result: one profile, rationale, action.

    Exactly one of each is emitted, under the ``onboarding`` key, so the shape
    is stable and a caller can rely on ``result['onboarding']['next_action']``
    without searching the state. ``next_action`` is passed in because it is the
    lifecycle recommendation already computed for this run.
    """
    return {
        "profile": dict(profile),
        "rationale": _profile_rationale(profile),
        "next_action": next_action,
    }


def _teach_substrate_rule(root: str, state: dict) -> Optional[dict]:
    """Teach the substrate rule and enforce the git side of it.

    Returns a refusal dict when the substrate must not be left tracked (a
    public repository whose substrate git is currently tracking), and
    mutates ``state`` with the recorded answers otherwise.
    """
    print("\n" + SUBSTRATE_RULE + "\n")

    if not _is_git_project(root):
        state["substrate"] = {"is_git_project": False}
        return None

    state["substrate"] = {"is_git_project": True}

    wrote = _ensure_gitignore_exclusion(root)
    state["substrate"]["gitignore_exclusion_written"] = wrote

    public = _is_public_remote(_git_origin_url(root))
    state["substrate"]["origin_is_public"] = public

    if public:
        tracked = _git_tracked_substrate(root)
        if tracked:
            return {
                "substrate_refused": True,
                "substrate_reason": (
                    "This repository's origin remote is public, but git is "
                    "already tracking substrate content under `.skillweave/`. "
                    "A public repository must never carry substrate content; "
                    "it belongs in the private per-org planning repository. "
                    "Untrack it with `git rm -r --cached .skillweave` and "
                    "re-run onboarding."
                ),
                "substrate_tracked": tracked,
            }

    return None


def run_onboarding(project_root: str = ".", skip: bool = False, **profile_overrides) -> dict:
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

    # The substrate rule is taught, not only enforced: state it, and for a git
    # project write the .gitignore exclusion. A public repository that is
    # already tracking substrate content is refused rather than left in that
    # state.
    refusal = _teach_substrate_rule(root, state)
    if refusal is not None:
        print("\n" + refusal["substrate_reason"])
        return refusal

    # Ask whether an org planning repository exists, rather than assuming the
    # substrate is durable where it stands. The answer is recorded so dispatch
    # knows where planner-owned content lives.
    planning_repo_exists = _ask_yes_no(
        "Does a private per-org planning repository exist for this project? (y/n): "
    )
    state["planning_repo_exists"] = planning_repo_exists

    # Role, purpose, autonomy and risk boundary extend the earlier phase/goal
    # questions. Each is a closed choice with a default, and any of them may be
    # supplied by the caller instead of asked, which is the custom extension
    # point. They are asked last so the questions above keep their established
    # order.
    profile = _collect_profile(**profile_overrides)

    # One profile, one rationale and one next action. The profile's next action
    # is the lifecycle recommendation for this run; it is nested under its own
    # key so it is not confused with the top-level ``next_action``, which is a
    # recommended skill.
    onboarding_result = _build_onboarding_result(profile, result["next_action"])
    state["onboarding"] = onboarding_result

    print(f"\nProfile: {profile['role']} / {profile['purpose']} / "
          f"{profile['autonomy']} autonomy / {profile['risk_boundary']} boundary")
    print(f"Rationale: {onboarding_result['rationale']}")
    print(f"Next action: {onboarding_result['next_action']}")

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
