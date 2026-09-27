from .store import RunStore, SQLiteRunStore, RunRecord, RunStateModel
from .errors import InvalidTransitionError, VersionConflictError, StoreError
from .journal import EventJournal, JournalEvent, EventType
from .schema.vocabulary import StatusVocabulary, StatusSchema, AmendmentRecord, validate_status, StatusRejectedError
from .authority import (
    Role, RoleAssignment, HumanApproval, DelegationRecord,
    ROLE_CAPABILITY_MATRIX, AuthorityGuard, AuthorityError,
)
from .registry import (
    EvidenceType, EvidenceQualityAxis, EvidenceQuality,
    ArtifactReceipt, EvidenceFinding, EvidenceRegistry,
    MerkleSegment, _compute_merkle_root, _compute_segment_hash,
    RawArtifactStore, ArtifactIntegrityError,
)
from .preflight import SessionEnvelope, PreflightResult, run_preflight
from .handoff import ColdStartBundle, HandoffBroker, HandoffOffer, HandoffError
from .observer import (
    OutputType, ObserverOutput, ObserverState, ObserverLease,
    Detector, ObserverRuntime,
)
from .wireframe import (
    assert_gate_discipline, assert_write_scope, assert_non_polling,
    assert_no_foreign_repos, validate_summary, WireframeError,
)
from . import context
from .checkpoint import (
    EnvironmentFingerprint, Checkpoint, ResumeRevalidationRequired,
    capture_environment, create_checkpoint, validate_resume,
)

# ── Human-coupling gate for irreversible change surfaces ────────────────────

IRREVERSIBLE_SURFACES: frozenset[str] = frozenset({
    "organization",
    "human",
    "finance",
    "legal",
    "public_channel",
})

# Human-coupling levels that already embed human oversight. These levels are
# allowed to modify irreversible surfaces without additional gating because a
# human is already in the loop.
_HUMAN_IN_THE_LOOP: frozenset[str] = frozenset({
    "approval_required",
    "collaborative",
    "human_led",
})


def assert_human_coupling_gate(
    human_coupling: str,
    change_surfaces: list[str],
) -> list[dict[str, str]]:
    """Check that *human_coupling* gates every irreversible *change_surface*.

    Returns a list of violation dicts (one per un-gated irreversible surface)
    or an empty list when all surfaces are properly gated. The check is
    category-independent: it inspects the human-coupling level alone, never
    the category name — a ``build`` profile with ``humanCoupling: autonomous``
    is gated exactly as hard as a ``research`` profile with the same coupling.
    """
    violations: list[dict[str, str]] = []
    if human_coupling in _HUMAN_IN_THE_LOOP:
        return violations
    for surface in change_surfaces:
        if surface in IRREVERSIBLE_SURFACES:
            violations.append({
                "surface": surface,
                "human_coupling": human_coupling,
                "reason": (
                    f"surface '{surface}' is irreversible and requires "
                    f"human coupling 'approval_required', 'collaborative', "
                    f"or 'human_led', got '{human_coupling}'"
                ),
            })
    return violations
from .planning_sync import (
    PlanningSyncBackingStore,
    SyncReport,
    discover_planning_repo,
    discover_planning_root,
    runtime_has_git,
    resolve_runtime_store,
    classify_runtime,
)
from .preflight import PreflightInterceptor, PreflightError as PreflightGateError
from .substrate import (
    BackingStore,
    GitBackingStore,
    LocalOnlyBackingStore,
    ResolvedArea,
    UnclassifiedAreaError,
    resolve_store,
    classify_area,
    classify_substrate,
)

__all__ = [
    "RunStore",
    "SQLiteRunStore",
    "RunRecord",
    "RunStateModel",
    "InvalidTransitionError",
    "VersionConflictError",
    "StoreError",
    "EventJournal",
    "JournalEvent",
    "EventType",
    "StatusVocabulary",
    "StatusSchema",
    "AmendmentRecord",
    "validate_status",
    "StatusRejectedError",
    "Role",
    "RoleAssignment",
    "HumanApproval",
    "DelegationRecord",
    "ROLE_CAPABILITY_MATRIX",
    "AuthorityGuard",
    "AuthorityError",
    "EvidenceType",
    "EvidenceQualityAxis",
    "EvidenceQuality",
    "ArtifactReceipt",
    "EvidenceFinding",
    "EvidenceRegistry",
    "MerkleSegment",
    "_compute_merkle_root",
    "_compute_segment_hash",
    "RawArtifactStore",
    "ArtifactIntegrityError",
    "SessionEnvelope",
    "PreflightResult",
    "run_preflight",
    "ColdStartBundle",
    "HandoffBroker",
    "HandoffOffer",
    "HandoffError",
    "OutputType",
    "ObserverOutput",
    "ObserverState",
    "ObserverLease",
    "Detector",
    "ObserverRuntime",
    "assert_gate_discipline",
    "assert_write_scope",
    "assert_non_polling",
    "assert_no_foreign_repos",
    "validate_summary",
    "WireframeError",
    "BackingStore",
    "GitBackingStore",
    "LocalOnlyBackingStore",
    "ResolvedArea",
    "UnclassifiedAreaError",
    "resolve_store",
    "classify_area",
    "classify_substrate",
    "PlanningSyncBackingStore",
    "SyncReport",
    "discover_planning_repo",
    "discover_planning_root",
    "runtime_has_git",
    "resolve_runtime_store",
    "classify_runtime",
    "IRREVERSIBLE_SURFACES",
    "assert_human_coupling_gate",
]
