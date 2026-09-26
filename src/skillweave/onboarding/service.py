"""Operator onboarding service — single seam for skill and CLI.

This service wraps the lower-level onboarding building blocks and adds:

* **Preview** -- run onboarding in dry-run mode, returning what *would* be
  persisted without writing anything.
* **Durable / generated separation** -- profile choices (authored input) are
  stored in ``skillweave.config/onboarding-profile.yaml``; the onboarding
  result (generated state) is stored in ``.skillweave/onboarding-state.yaml``.
* **Idempotence** -- applying the same profile twice produces the same
  persisted result (digest comparison).
* **Reprofile diff** -- changing a profile field and re-applying shows a
  structured diff against the previously persisted state.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from skillweave.onboarding_cli import (
    PROFILE_CHOICES,
    PROFILE_DEFAULTS,
    PROFILE_FIELDS,
    _build_onboarding_result,
    _extend_choice,
    _profile_rationale,
    _save_state,
    load_onboarding_state,
)
from skillweave.phase_detection import detect_phase_with_detail
from skillweave.workflow_recommendation import recommend

#: Path under ``skillweave.config/`` where the durable authored profile lives.
DURABLE_PROFILE_PATH = "onboarding-profile.yaml"

#: Path under ``.skillweave/`` where the generated onboarding state lives.
GENERATED_STATE_PATH = "onboarding-state.yaml"


@dataclass(frozen=True)
class OnboardingPreview:
    """Preview of what onboarding would produce, without side effects."""

    profile: dict[str, str]
    rationale: str
    next_action: str
    detected_phase: str
    goal: str | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "profile": dict(self.profile),
            "rationale": self.rationale,
            "next_action": self.next_action,
            "detected_phase": self.detected_phase,
            "goal": self.goal,
        }


@dataclass(frozen=True)
class OnboardingState:
    """Previously persisted onboarding state, loaded from disk."""

    profile: dict[str, str]
    rationale: str
    next_action: str
    persisted_at: str  # ISO timestamp from the state file

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> OnboardingState:
        onboarding = raw.get("onboarding", {})
        return cls(
            profile=dict(onboarding.get("profile", {})),
            rationale=str(onboarding.get("rationale", "")),
            next_action=str(onboarding.get("next_action", "")),
            persisted_at=str(raw.get("timestamp", "")),
        )


@dataclass(frozen=True)
class OnboardingDiff:
    """A structured diff between two onboarding results."""

    profile_changed: bool
    rationale_changed: bool
    next_action_changed: bool
    unified_diff: str

    @property
    def has_changes(self) -> bool:
        return self.profile_changed or self.rationale_changed or self.next_action_changed


def _canonical_digest(payload: dict[str, Any]) -> str:
    """Canonical digest of a payload, for idempotence checks."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _profile_payload(profile: dict[str, str]) -> dict[str, str]:
    """Normalise a profile dict for comparison."""
    return {k: profile.get(k, PROFILE_DEFAULTS.get(k, "")) for k in PROFILE_FIELDS}


class OnboardingService:
    """Single service for operator onboarding.

    Shared by the ``skillweave-onboarding`` skill and the CLI ``onboard``
    subcommand. Every method accepts ``profile_overrides`` so that callers
    may supply any subset of the four profile fields without driving the
    interactive prompts.
    """

    def __init__(self, project_root: str | os.PathLike[str] | None = None) -> None:
        self._root = Path(project_root).resolve() if project_root else Path.cwd().resolve()

    # ── Public API ──────────────────────────────────────────────────────────

    def preview(
        self,
        **profile_overrides: str,
    ) -> OnboardingPreview:
        """Preview the onboarding result without persisting anything.

        Returns a frozen :class:`OnboardingPreview` describing what *would*
        be written. No filesystem mutation occurs.
        """
        result = self._compute(**profile_overrides)
        return self._to_preview(result)

    def apply(
        self,
        **profile_overrides: str,
    ) -> OnboardingPreview:
        """Run onboarding and persist results.

        Durable authored input (profile) goes to
        ``skillweave.config/onboarding-profile.yaml``. Generated state goes to
        ``.skillweave/onboarding-state.yaml``. If a profile was already
        persisted with the same values, the write is idempotent (no change).
        """
        result = self._compute(**profile_overrides)

        # Persist durable profile to skillweave.config/
        profile = self._collect_profile(profile_overrides)
        self._save_durable_profile(profile)

        # Persist generated state to .skillweave/onboarding-state.yaml
        _save_state(str(self._root), result)

        return self._to_preview(result)

    def load(self) -> OnboardingState | None:
        """Load previously persisted onboarding state, or ``None``."""
        raw = load_onboarding_state(str(self._root))
        if raw is None:
            return None
        return OnboardingState.from_raw(raw)

    def load_durable_profile(self) -> dict[str, str] | None:
        """Load the durable authored profile from ``skillweave.config/``."""
        path = self._durable_profile_path()
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return dict(yaml.safe_load(f) or {})
        except Exception:
            return None

    def diff(
        self,
        **profile_overrides: str,
    ) -> OnboardingDiff | None:
        """Show a structured diff between current state and a re-run.

        Returns ``None`` when no onboarding state has been persisted yet.
        Returns an empty diff (``has_changes == False``) when the re-run
        produces identical results.
        """
        current = self.load()
        if current is None:
            return None

        new_result = self._compute(**profile_overrides)
        new_onboarding = new_result.get("onboarding", {})
        new_profile = dict(new_onboarding.get("profile", {}))
        new_rationale = str(new_onboarding.get("rationale", ""))
        new_next = str(new_onboarding.get("next_action", ""))

        old_lines = json.dumps(
            {
                "profile": current.profile,
                "rationale": current.rationale,
                "next_action": current.next_action,
            },
            indent=2,
            sort_keys=True,
        ).splitlines(keepends=True)

        new_lines = json.dumps(
            {
                "profile": new_profile,
                "rationale": new_rationale,
                "next_action": new_next,
            },
            indent=2,
            sort_keys=True,
        ).splitlines(keepends=True)

        unified = "".join(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile="current",
                tofile="reprofile",
            )
        )

        return OnboardingDiff(
            profile_changed=current.profile != new_profile,
            rationale_changed=current.rationale != new_rationale,
            next_action_changed=current.next_action != new_next,
            unified_diff=unified,
        )

    def is_idempotent(self, **profile_overrides: str) -> bool:
        """Check if re-running with the given overrides would change nothing.

        Returns ``True`` when there is no persisted state OR when the re-run
        produces byte-identical results.
        """
        result = self.diff(**profile_overrides)
        if result is None:
            return True  # Nothing persisted yet: first run is always idempotent
        return not result.has_changes

    # ── Internal: computation ──────────────────────────────────────────────

    def _compute(self, **profile_overrides: str) -> dict[str, Any]:
        """Compute the full onboarding result non-interactively.

        Uses :func:`detect_phase_with_detail`, :func:`recommend` and the
        profile building blocks directly, skipping all interactive prompts
        (``input()``, ``print()``, ``_ask_yes_no()``).
        """
        root = str(self._root)

        detection = detect_phase_with_detail(root)
        detected_phase = str(detection.get("phase", "discovery"))
        goal = None  # Non-interactive: no goal prompt

        rec = recommend(project_root=root, override_phase=detected_phase, goal=goal)

        profile = self._collect_profile(profile_overrides)
        rationale = _profile_rationale(profile)
        onboarding_result = _build_onboarding_result(profile, str(rec.get("next_action", "")))

        state: dict[str, Any] = {
            "phase": detected_phase,
            "goal": goal,
            "recommended_bundle": rec.get("recommended_bundle"),
            "next_action": rec.get("next_action"),
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "onboarding": onboarding_result,
        }
        return state

    def _to_preview(self, result: dict[str, Any]) -> OnboardingPreview:
        onboarding = result.get("onboarding", {})
        return OnboardingPreview(
            profile=dict(onboarding.get("profile", {})),
            rationale=str(onboarding.get("rationale", "")),
            next_action=str(onboarding.get("next_action", "")),
            detected_phase=str(result.get("phase", "")),
            goal=result.get("goal"),
        )

    # ── Internal: helpers ──────────────────────────────────────────────────

    def _durable_profile_path(self) -> Path:
        return self._root / "skillweave.config" / DURABLE_PROFILE_PATH

    def _generated_state_path(self) -> Path:
        return self._root / ".skillweave" / GENERATED_STATE_PATH

    def _collect_profile(self, overrides: dict[str, str]) -> dict[str, str]:
        """Collect the four profile fields from overrides or defaults.

        Never drives interactive prompts -- resolves each field from the
        override, or falls back to the declared default.
        """
        profile = {}
        for field in PROFILE_FIELDS:
            override = overrides.get(field)
            if override is not None:
                profile[field] = _extend_choice(field, override)
            else:
                profile[field] = PROFILE_DEFAULTS[field]
        return profile

    def _save_durable_profile(self, profile: dict[str, str]) -> None:
        """Persist the authored profile to ``skillweave.config/``."""
        path = self._durable_profile_path()
        path.parent.mkdir(exist_ok=True, parents=True)
        with open(path, "w") as f:
            yaml.dump(
                _profile_payload(profile),
                f,
                default_flow_style=False,
                sort_keys=False,
            )
