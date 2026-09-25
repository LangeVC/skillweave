"""Token limit profiles and threshold assessment for context management (SW-CONTEXT-001).

Acceptance Criteria:
1. Implement context check-pointing in `src/skillweave/core/context/`.
2. Introduce profiles for token limits (e.g. 120k for no new task, 150k for checkpoint, 170k for stop).
3. Ensure the profiles are configurable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Sequence, Union


class TokenThresholdStatus(str, Enum):
    """Execution action/status threshold based on current context token consumption."""

    OK = "ok"
    NO_NEW_TASK = "no_new_task"
    CHECKPOINT_REQUIRED = "checkpoint_required"
    STOP = "stop"


class ProfileConfigurationError(ValueError):
    """Raised when a token limit profile configuration is invalid or malformed."""


@dataclass
class ContextLimitAssessment:
    """The result of evaluating context token consumption against an active profile."""

    status: TokenThresholdStatus
    current_tokens: int
    profile_name: str
    can_accept_new_task: bool
    checkpoint_required: bool
    should_stop: bool
    remaining_to_no_new_task: int
    remaining_to_checkpoint: int
    remaining_to_stop: int
    utilization: float
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize assessment to dict."""
        return {
            "status": self.status.value if isinstance(self.status, TokenThresholdStatus) else str(self.status),
            "current_tokens": self.current_tokens,
            "profile_name": self.profile_name,
            "can_accept_new_task": self.can_accept_new_task,
            "checkpoint_required": self.checkpoint_required,
            "should_stop": self.should_stop,
            "remaining_to_no_new_task": self.remaining_to_no_new_task,
            "remaining_to_checkpoint": self.remaining_to_checkpoint,
            "remaining_to_stop": self.remaining_to_stop,
            "utilization": round(self.utilization, 4),
            "message": self.message,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ContextLimitAssessment:
        """Construct assessment from dict."""
        raw_status = data.get("status", TokenThresholdStatus.OK.value)
        try:
            status = TokenThresholdStatus(raw_status)
        except ValueError:
            status = TokenThresholdStatus.OK

        return cls(
            status=status,
            current_tokens=int(data.get("current_tokens", 0)),
            profile_name=str(data.get("profile_name", "default")),
            can_accept_new_task=bool(data.get("can_accept_new_task", True)),
            checkpoint_required=bool(data.get("checkpoint_required", False)),
            should_stop=bool(data.get("should_stop", False)),
            remaining_to_no_new_task=int(data.get("remaining_to_no_new_task", 0)),
            remaining_to_checkpoint=int(data.get("remaining_to_checkpoint", 0)),
            remaining_to_stop=int(data.get("remaining_to_stop", 0)),
            utilization=float(data.get("utilization", 0.0)),
            message=str(data.get("message", "")),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class TokenLimitProfile:
    """Configurable profile defining token thresholds for context management.

    Thresholds enforce safe execution limits:
    - ``no_new_task_limit``: Beyond this limit, existing work may continue, but no new
      tasks or sub-tasks should be admitted/scheduled (default: 120k).
    - ``checkpoint_limit``: At or beyond this limit, an immediate context checkpoint snapshot
      must be captured (default: 150k).
    - ``stop_limit``: Hard execution stop ceiling to prevent context blowout (default: 170k).
    - ``max_context_limit``: Optional total context window limit (default: 200k).
    """

    name: str = "default"
    no_new_task_limit: int = 120_000
    checkpoint_limit: int = 150_000
    stop_limit: int = 170_000
    max_context_limit: Optional[int] = 200_000
    compact_limit: Optional[int] = None
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate profile thresholds ensuring monotonicity and validity."""
        if not self.name or not isinstance(self.name, str):
            raise ProfileConfigurationError("Profile 'name' must be a non-empty string.")

        if self.no_new_task_limit <= 0:
            raise ProfileConfigurationError(
                f"no_new_task_limit ({self.no_new_task_limit}) must be greater than 0."
            )
        if self.checkpoint_limit <= 0:
            raise ProfileConfigurationError(
                f"checkpoint_limit ({self.checkpoint_limit}) must be greater than 0."
            )
        if self.stop_limit <= 0:
            raise ProfileConfigurationError(
                f"stop_limit ({self.stop_limit}) must be greater than 0."
            )

        if not (self.no_new_task_limit <= self.checkpoint_limit <= self.stop_limit):
            raise ProfileConfigurationError(
                f"Token limits must satisfy: no_new_task_limit ({self.no_new_task_limit}) "
                f"<= checkpoint_limit ({self.checkpoint_limit}) <= stop_limit ({self.stop_limit})."
            )

        if self.max_context_limit is not None:
            if self.max_context_limit < self.stop_limit:
                raise ProfileConfigurationError(
                    f"max_context_limit ({self.max_context_limit}) cannot be less than stop_limit ({self.stop_limit})."
                )

        if self.compact_limit is not None and self.compact_limit <= 0:
            raise ProfileConfigurationError(
                f"compact_limit ({self.compact_limit}) must be greater than 0."
            )

    def evaluate(self, current_tokens: int) -> ContextLimitAssessment:
        """Evaluate current token count against this profile's thresholds."""
        tokens = max(0, int(current_tokens))
        ceiling = self.max_context_limit or self.stop_limit
        utilization = tokens / ceiling if ceiling > 0 else 0.0

        remaining_no_new = max(0, self.no_new_task_limit - tokens)
        remaining_cp = max(0, self.checkpoint_limit - tokens)
        remaining_stop = max(0, self.stop_limit - tokens)

        if tokens >= self.stop_limit:
            status = TokenThresholdStatus.STOP
            can_accept = False
            cp_required = True
            should_stop = True
            msg = (
                f"Token count ({tokens:,}) reached stop limit ({self.stop_limit:,}). "
                f"Halting execution."
            )
        elif tokens >= self.checkpoint_limit:
            status = TokenThresholdStatus.CHECKPOINT_REQUIRED
            can_accept = False
            cp_required = True
            should_stop = False
            msg = (
                f"Token count ({tokens:,}) reached checkpoint limit ({self.checkpoint_limit:,}). "
                f"Checkpoint required before continuing."
            )
        elif tokens >= self.no_new_task_limit:
            status = TokenThresholdStatus.NO_NEW_TASK
            can_accept = False
            cp_required = False
            should_stop = False
            msg = (
                f"Token count ({tokens:,}) reached no-new-task limit ({self.no_new_task_limit:,}). "
                f"No new tasks may be admitted."
            )
        else:
            status = TokenThresholdStatus.OK
            can_accept = True
            cp_required = False
            should_stop = False
            msg = (
                f"Token count ({tokens:,}) is within safe operational limits "
                f"({remaining_no_new:,} tokens remaining before no-new-task threshold)."
            )

        return ContextLimitAssessment(
            status=status,
            current_tokens=tokens,
            profile_name=self.name,
            can_accept_new_task=can_accept,
            checkpoint_required=cp_required,
            should_stop=should_stop,
            remaining_to_no_new_task=remaining_no_new,
            remaining_to_checkpoint=remaining_cp,
            remaining_to_stop=remaining_stop,
            utilization=utilization,
            message=msg,
            metadata=dict(self.metadata),
        )

    def can_accept_task(self, current_tokens: int, estimated_task_tokens: int = 0) -> bool:
        """Check whether a new task with given estimated tokens can be safely accepted."""
        projected = max(0, current_tokens) + max(0, estimated_task_tokens)
        return projected < self.no_new_task_limit

    def should_checkpoint(self, current_tokens: int) -> bool:
        """Return True if token count is at or above checkpoint limit."""
        return current_tokens >= self.checkpoint_limit

    def should_stop(self, current_tokens: int) -> bool:
        """Return True if token count is at or above stop limit."""
        return current_tokens >= self.stop_limit

    def to_dict(self) -> Dict[str, Any]:
        """Serialize profile to dictionary."""
        return {
            "name": self.name,
            "no_new_task_limit": self.no_new_task_limit,
            "checkpoint_limit": self.checkpoint_limit,
            "stop_limit": self.stop_limit,
            "max_context_limit": self.max_context_limit,
            "compact_limit": self.compact_limit,
            "description": self.description,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], name: Optional[str] = None) -> TokenLimitProfile:
        """Construct profile from a dictionary mapping."""
        prof_name = name or str(data.get("name") or data.get("id") or "default")

        def _get_int(key_aliases: Sequence[str], default: int) -> int:
            for k in key_aliases:
                if k in data and data[k] is not None:
                    try:
                        return int(data[k])
                    except (ValueError, TypeError):
                        pass
            return default

        def _get_optional_int(key_aliases: Sequence[str]) -> Optional[int]:
            for k in key_aliases:
                if k in data and data[k] is not None:
                    try:
                        return int(data[k])
                    except (ValueError, TypeError):
                        pass
            return None

        no_new_task = _get_int(
            ["no_new_task_limit", "no_new_task", "no_new_tasks", "task_limit", "soft_limit"],
            120_000,
        )
        cp_limit = _get_int(
            ["checkpoint_limit", "checkpoint", "cp_limit", "snapshot_limit"],
            150_000,
        )
        stop = _get_int(
            ["stop_limit", "stop", "hard_limit", "max_limit", "ceiling"],
            170_000,
        )
        max_context = _get_optional_int(
            ["max_context_limit", "max_context", "context_window", "window_size"]
        )
        compact = _get_optional_int(
            ["compact_limit", "compact", "compaction_limit"]
        )

        desc = str(data.get("description") or data.get("desc") or "")
        metadata = dict(data.get("metadata") or {})

        return cls(
            name=prof_name,
            no_new_task_limit=no_new_task,
            checkpoint_limit=cp_limit,
            stop_limit=stop,
            max_context_limit=max_context,
            compact_limit=compact,
            description=desc,
            metadata=metadata,
        )


# ── Built-in Profile Presets ──────────────────────────────────────────────────

DEFAULT_PROFILE = TokenLimitProfile(
    name="default",
    no_new_task_limit=120_000,
    checkpoint_limit=150_000,
    stop_limit=170_000,
    max_context_limit=200_000,
    description="Default SkillWeave context token limit profile (120k / 150k / 170k / 200k max).",
)

STANDARD_PROFILE = TokenLimitProfile(
    name="standard",
    no_new_task_limit=120_000,
    checkpoint_limit=150_000,
    stop_limit=170_000,
    max_context_limit=200_000,
    description="Standard balanced profile for everyday workflows.",
)

CONSERVATIVE_PROFILE = TokenLimitProfile(
    name="conservative",
    no_new_task_limit=60_000,
    checkpoint_limit=80_000,
    stop_limit=95_000,
    max_context_limit=100_000,
    description="Conservative profile for models or environments with lower context allowances.",
)

EXTENDED_PROFILE = TokenLimitProfile(
    name="extended",
    no_new_task_limit=400_000,
    checkpoint_limit=600_000,
    stop_limit=750_000,
    max_context_limit=1_000_000,
    description="Extended profile for large-context models (1M token windows).",
)

STRICT_PROFILE = TokenLimitProfile(
    name="strict",
    no_new_task_limit=30_000,
    checkpoint_limit=45_000,
    stop_limit=55_000,
    max_context_limit=64_000,
    description="Strict compact profile for low-latency / budget-constrained runs.",
)

FAST_PROFILE = TokenLimitProfile(
    name="fast",
    no_new_task_limit=8_000,
    checkpoint_limit=12_000,
    stop_limit=15_000,
    max_context_limit=16_000,
    description="Fast testing profile with small token boundaries.",
)

BUILTIN_PROFILES: Dict[str, TokenLimitProfile] = {
    "default": DEFAULT_PROFILE,
    "standard": STANDARD_PROFILE,
    "conservative": CONSERVATIVE_PROFILE,
    "extended": EXTENDED_PROFILE,
    "strict": STRICT_PROFILE,
    "fast": FAST_PROFILE,
}


# ── Profile Registry ─────────────────────────────────────────────────────────

class TokenLimitProfileRegistry:
    """Registry for managing and retrieving named token limit profiles."""

    def __init__(self) -> None:
        self._profiles: Dict[str, TokenLimitProfile] = dict(BUILTIN_PROFILES)

    def register(self, profile: TokenLimitProfile, override: bool = True) -> None:
        """Register a new profile."""
        key = profile.name.strip().lower()
        if key in self._profiles and not override:
            raise ProfileConfigurationError(f"Profile '{profile.name}' is already registered.")
        self._profiles[key] = profile

    def get(self, name: Optional[str] = None) -> TokenLimitProfile:
        """Get a profile by name, falling back to 'default'."""
        if not name:
            return self._profiles.get("default", DEFAULT_PROFILE)
        key = name.strip().lower()
        if key in self._profiles:
            return self._profiles[key]
        raise ProfileConfigurationError(
            f"Token limit profile '{name}' not found. Available: {sorted(self._profiles.keys())}"
        )

    def list_profiles(self) -> Dict[str, TokenLimitProfile]:
        """Return all registered profiles."""
        return dict(self._profiles)

    def has_profile(self, name: str) -> bool:
        """Check if a profile exists in the registry."""
        return name.strip().lower() in self._profiles

    def reset(self) -> None:
        """Reset registry to default built-in profiles."""
        self._profiles = dict(BUILTIN_PROFILES)


_GLOBAL_REGISTRY = TokenLimitProfileRegistry()


def get_profile_registry() -> TokenLimitProfileRegistry:
    """Return the global token limit profile registry."""
    return _GLOBAL_REGISTRY


def register_profile(profile: TokenLimitProfile, override: bool = True) -> None:
    """Convenience function to register a profile in the global registry."""
    _GLOBAL_REGISTRY.register(profile, override=override)


def get_profile(name: Optional[str] = None) -> TokenLimitProfile:
    """Convenience function to get a profile from the global registry."""
    return _GLOBAL_REGISTRY.get(name)


def list_profiles() -> Dict[str, TokenLimitProfile]:
    """Convenience function to list all registered profiles."""
    return _GLOBAL_REGISTRY.list_profiles()
