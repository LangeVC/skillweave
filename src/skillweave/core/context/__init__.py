"""SkillWeave Core Context Management and Checkpointing (SW-CONTEXT-001).

Provides:
- Token limit profiles with configurable thresholds (120k no new task, 150k checkpoint, 170k stop).
- Context checkpoint snapshotting, serialization, and storage.
- Active context management with admission gating, token estimation, and compaction.
"""

from .checkpoint import (
    CheckpointError,
    CheckpointIntegrityError,
    CheckpointNotFoundError,
    CheckpointStore,
    ContextBlock,
    ContextCheckpoint,
    FileCheckpointStore,
    InMemoryCheckpointStore,
)
from .config import (
    load_profile_from_dict,
    load_profile_from_env,
    load_profile_from_yaml,
    load_profiles_from_yaml_file,
    resolve_profile,
)
from .limits import (
    BUILTIN_PROFILES,
    CONSERVATIVE_PROFILE,
    DEFAULT_PROFILE,
    EXTENDED_PROFILE,
    FAST_PROFILE,
    STANDARD_PROFILE,
    STRICT_PROFILE,
    ContextLimitAssessment,
    ProfileConfigurationError,
    TokenLimitProfile,
    TokenLimitProfileRegistry,
    TokenThresholdStatus,
    get_profile,
    get_profile_registry,
    list_profiles,
    register_profile,
)
from .manager import (
    ContextLimitError,
    ContextManager,
    ContextStopLimitExceeded,
    TaskAdmissionRejected,
    estimate_tokens,
)

__all__ = [
    # Limits & Profiles
    "TokenLimitProfile",
    "TokenThresholdStatus",
    "ContextLimitAssessment",
    "TokenLimitProfileRegistry",
    "ProfileConfigurationError",
    "DEFAULT_PROFILE",
    "STANDARD_PROFILE",
    "CONSERVATIVE_PROFILE",
    "EXTENDED_PROFILE",
    "STRICT_PROFILE",
    "FAST_PROFILE",
    "BUILTIN_PROFILES",
    "get_profile_registry",
    "register_profile",
    "get_profile",
    "list_profiles",
    # Config & Resolvers
    "load_profile_from_dict",
    "load_profile_from_yaml",
    "load_profiles_from_yaml_file",
    "load_profile_from_env",
    "resolve_profile",
    # Checkpointing
    "ContextBlock",
    "ContextCheckpoint",
    "CheckpointStore",
    "InMemoryCheckpointStore",
    "FileCheckpointStore",
    "CheckpointError",
    "CheckpointIntegrityError",
    "CheckpointNotFoundError",
    # Context Manager & Exceptions
    "ContextManager",
    "estimate_tokens",
    "ContextLimitError",
    "ContextStopLimitExceeded",
    "TaskAdmissionRejected",
]
