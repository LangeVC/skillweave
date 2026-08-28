"""SkillWeave dispatch trace contracts (SW1311-RECEIPT-001).

Append-only multi-round receipts, a typed child-job terminal contract, a
binding terminal envelope, and a per-job state namespace. These are the
*contracts* the operator dispatcher consumes; nothing here launches a worker,
names a concrete provider/model/harness, or bakes a provider default.
"""

from .contracts import (  # noqa: F401
    AppendOnlyReceiptLog,
    JobStatus,
    TaskVerdict,
    EvidenceAvailability,
    GateVerdict,
    TerminalState,
    JobResult,
    TerminalEnvelope,
    JobStateNamespace,
    StateNamespaceRegistry,
    JobRecord,
    RoundKind,
    BlockedInputError,
    NamespaceCollisionError,
    PreflightError,
    IncompleteCompletionError,
    DuplicateDigestError,
)

__all__ = [
    "AppendOnlyReceiptLog",
    "JobStatus",
    "TaskVerdict",
    "EvidenceAvailability",
    "GateVerdict",
    "TerminalState",
    "JobResult",
    "TerminalEnvelope",
    "JobStateNamespace",
    "StateNamespaceRegistry",
    "JobRecord",
    "RoundKind",
    "BlockedInputError",
    "NamespaceCollisionError",
    "PreflightError",
    "IncompleteCompletionError",
    "DuplicateDigestError",
]
