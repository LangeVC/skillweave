"""Operator dispatch surface (contract, profile resolution, and live events).

Exports the sequence/event contract, the practice task validation, and the
typed live event stream. The worker-launch mechanics are not part of this
lane: the dispatcher itself is SW138-DISPATCH-001, which consumes these
contracts and feeds the event stream.
"""

from .contracts import (  # noqa: F401
    ContractError,
    SequenceBoundaryError,
    LaneValidationError,
    PracticeTaskError,
    ProfileReference,
    CriterionGroup,
    Lane,
    SequenceDeclaration,
    EventType,
    ProcessStatus,
    TaskStatus,
    DispatchEvent,
    SESSION_BOUNDARY_BATCH,
    FIBONACCI_POINTS,
    load_sequence,
    validate_mutating_lane,
    validate_for_dispatch,
    validate_practice_task,
)

# Authoritative profile resolution (SW138-PROFILE-001): the single seam that
# turns an explicit profile path and required roles into a launchable intent.
from .profile_resolution import (  # noqa: F401
    ProfileResolutionError,
    ResolvedModel,
    ResolvedRole,
    ResolvedDispatch,
    resolve_limits,
    resolve_dispatch_profile,
)

from .events import (  # noqa: F401
    DispatchEventStream,
    HeartbeatMonitor,
    EventStreamError,
)

__all__ = [
    "ContractError",
    "SequenceBoundaryError",
    "LaneValidationError",
    "PracticeTaskError",
    "ProfileReference",
    "CriterionGroup",
    "Lane",
    "SequenceDeclaration",
    "EventType",
    "ProcessStatus",
    "TaskStatus",
    "DispatchEvent",
    "SESSION_BOUNDARY_BATCH",
    "FIBONACCI_POINTS",
    "load_sequence",
    "validate_mutating_lane",
    "validate_for_dispatch",
    "validate_practice_task",
    "ProfileResolutionError",
    "ResolvedModel",
    "ResolvedRole",
    "ResolvedDispatch",
    "resolve_limits",
    "resolve_dispatch_profile",
    "DispatchEventStream",
    "HeartbeatMonitor",
    "EventStreamError",
]
