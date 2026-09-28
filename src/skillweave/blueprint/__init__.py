"""SkillWeave blueprint surface.

The discovery trace graph contract (SW-159-BP-TRACE-001) turns applicable
discovery Markdown into a digest-bound trace graph: every used statement is
recorded with its source path, digest, heading and stable problem ID, and every
problem is linked — through a versioned TraceLink — to an epic, a task, or a
named deferral. Nothing here launches a worker or changes non-discovery
blueprint behavior; the contract is opt-in and standard-library only.
"""

from .discovery_trace import (  # noqa: F401
    SCHEMA_VERSION,
    TRACE_LINK_VERSION,
    DISPOSITION_EPIC,
    DISPOSITION_TASK,
    DISPOSITION_DEFERRED,
    DiscoveryTraceError,
    MissingMandatoryProblemError,
    UnlinkedProblemError,
    DigestDriftError,
    UnresolvedConflictError,
    InvalidDeferralError,
    DiscoverySource,
    Deferral,
    TraceLink,
    DiscoveryTraceGraph,
    parse_discovery_markdown,
    detect_conflicts,
    build_trace_graph,
    compute_digest,
    seal,
    canonicalize,
    validate,
    verify_grounding,
    machine_mapping,
    to_machine,
    render_human,
    parse_human_mapping,
    load_schema,
)

__all__ = [
    "SCHEMA_VERSION",
    "TRACE_LINK_VERSION",
    "DISPOSITION_EPIC",
    "DISPOSITION_TASK",
    "DISPOSITION_DEFERRED",
    "DiscoveryTraceError",
    "MissingMandatoryProblemError",
    "UnlinkedProblemError",
    "DigestDriftError",
    "UnresolvedConflictError",
    "InvalidDeferralError",
    "DiscoverySource",
    "Deferral",
    "TraceLink",
    "DiscoveryTraceGraph",
    "parse_discovery_markdown",
    "detect_conflicts",
    "build_trace_graph",
    "compute_digest",
    "seal",
    "canonicalize",
    "validate",
    "verify_grounding",
    "machine_mapping",
    "to_machine",
    "render_human",
    "parse_human_mapping",
    "load_schema",
]
