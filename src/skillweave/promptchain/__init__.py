"""SkillWeave promptchain execution surface.

``execute`` is the executor for ``sequences/*.yaml`` orchestration files: it
loads a sequence, refuses one that does not declare ``session_boundary``, and
turns lanes marked ``parallel_lanes`` into subagent dispatches while leaving
``serialized_lanes`` inline.
"""

from .execute import (
    SequenceDeclaration,
    Lane,
    DispatchPlan,
    DispatchEntry,
    SUBAGENT,
    INLINE,
    MissingSessionBoundaryError,
    TopologyGateError,
    load_sequence,
    build_dispatch_plan,
    derive_topologies,
    gate_topology,
    execute_sequence,
    BatchCommand,
    SessionState,
    SessionRun,
    Session,
    SessionConsumedError,
    SessionExecutionError,
    load_state_file,
)

__all__ = [
    "SequenceDeclaration",
    "Lane",
    "DispatchPlan",
    "DispatchEntry",
    "SUBAGENT",
    "INLINE",
    "MissingSessionBoundaryError",
    "TopologyGateError",
    "load_sequence",
    "build_dispatch_plan",
    "derive_topologies",
    "gate_topology",
    "execute_sequence",
    "BatchCommand",
    "SessionState",
    "SessionRun",
    "Session",
    "SessionConsumedError",
    "SessionExecutionError",
    "load_state_file",
]
