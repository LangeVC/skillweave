"""Bounded semantic preflight repair with automatic redispatch.

A dispatched lane can fail preflight for reasons that are *mechanical* and
grounded in evidence: a ``modifies`` path that does not exist in the target, or
a source path whose language contradicts what the task declares. Those two are
repairable without touching task intent or widening write scope. Everything
else — identity drift, an unbounded loop, a needed capability the acting role
lacks — is HELD, never "fixed".

The repair loop is deliberately strict:

* it edits ONLY the fields named in ``PreflightFailure.implicated_fields``;
* it refuses to run at all if the target digest moved (target drift);
* it stops the second time it sees the same failure fingerprint;
* it stops when the attempt/budget is exhausted;
* it stops when applying the repair would require a capability the role lacks
  (authority expansion);
* every attempt appends a before/after record to the append-only journal.

Nothing here schedules, merges, or releases. It repairs a plan and hands the
repaired plan back for revalidation + redispatch against the *unchanged* target
digest.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from .preflight import (
    AUTO_REPAIR_CAPABILITY,
    FailureClass,
    PreflightFailure,
    PreflightResult,
    Retryability,
    digest_target,
)


class HoldReason(str, Enum):
    """Why the bounded repair loop refused to continue automatically."""

    REPEATED_FINGERPRINT = "repeated_fingerprint"
    TARGET_DRIFT = "target_drift"
    BUDGET_EXHAUSTED = "budget_exhausted"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"
    AUTHORITY_EXPANSION = "authority_expansion"
    NON_REPAIRABLE_CLASS = "non_repairable_class"
    IMPLICATED_FIELD_UNKNOWN = "implicated_field_unknown"


@dataclass(frozen=True)
class RepairAttempt:
    """An append-only record of one repair attempt.

    ``before_digest`` / ``after_digest`` content-address the target plan on
    either side, so the ledger proves exactly what changed. ``dispatch_identity``
    identifies the dispatch that a successful repair was redispatched as.
    """

    attempt: int
    failure_fingerprint: str
    failure_class: str
    implicated_fields: list[str]
    before_digest: str
    after_digest: str
    command: str
    exit_code: int
    outcome: str  # "repaired" | "held"
    hold_reason: Optional[str] = None
    dispatch_identity: Optional[str] = None
    recorded_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "failure_fingerprint": self.failure_fingerprint,
            "failure_class": self.failure_class,
            "implicated_fields": self.implicated_fields,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "command": self.command,
            "exit_code": self.exit_code,
            "outcome": self.outcome,
            "hold_reason": self.hold_reason,
            "dispatch_identity": self.dispatch_identity,
            "recorded_at": self.recorded_at,
        }


@dataclass
class RepairOutcome:
    """Result of a bounded repair run."""

    repaired: bool
    hold_reason: Optional[str] = None
    attempts: list[RepairAttempt] = field(default_factory=list)
    repaired_plan: Optional[dict[str, Any]] = None
    dispatch_identity: Optional[str] = None
    target_digest: str = ""

    @property
    def held(self) -> bool:
        return not self.repaired


#: Candidate-world evidence the repairer is allowed to look at. A path is not
#: invented: only a path that appears in this world may be substituted.
def _offending_path(failure: PreflightFailure) -> Optional[str]:
    """The single declared path the failure is about, from its evidence."""
    for item in failure.evidence:
        if item.get("kind") in ("missing_target", "language_conflict"):
            path = item.get("path")
            if isinstance(path, str) and path:
                return path
    return None


def _candidate_paths(evidence: list[dict[str, Any]]) -> list[str]:
    """Grounded replacement paths, never the offending path itself."""
    paths: list[str] = []
    for item in evidence:
        if item.get("kind") != "grounding_candidate":
            continue
        candidate = item.get("path")
        if isinstance(candidate, str) and candidate:
            paths.append(candidate)
    return paths


#: Legacy alias kept for callers that only need every path mentioned.
def _evidence_paths(evidence: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    for item in evidence:
        candidate = item.get("path") or item.get("resolved") or item.get("candidate")
        if isinstance(candidate, str) and candidate:
            paths.append(candidate)
    return paths


def _lane_field(plan: dict[str, Any], field_name: str) -> Optional[list[str]]:
    """Read a lane's list field (``modifies``/``creates``/...) from a task."""
    lane = plan.get("lane")
    if not isinstance(lane, dict):
        return None
    value = lane.get(field_name)
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value]
    return None


def _is_auto_repairable(failure: PreflightFailure) -> bool:
    return failure.retryability == Retryability.AUTO_REPAIRABLE.value


def _apply_repair(
    plan: dict[str, Any],
    failure: PreflightFailure,
    evidence: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """Apply a bounded edit to ONE implicated field of a plan.

    Returns a NEW plan (never mutates the input) or ``None`` when the failure
    is not one this engine knows how to repair. Only the offending ENTRY inside
    the fields named in ``failure.implicated_fields`` is swapped for grounded
    evidence; every other entry, and every other field — task intent,
    acceptance criteria, write scope — is copied through untouched.
    """
    if failure.failure_class not in (
        FailureClass.NONEXISTENT_MODIFIES_PATH.value,
        FailureClass.WRONG_LANGUAGE_SOURCE_PATH.value,
    ):
        return None

    offending = _offending_path(failure)
    if not offending:
        return None
    replacement = _candidate_paths(evidence)
    if not replacement:
        return None

    for lane_field in failure.implicated_fields:
        declared = _lane_field(plan, lane_field)
        if declared is None:
            continue
        new_field: list[str] = []
        for path in declared:
            if path == offending:
                new_field.extend(replacement)
            else:
                new_field.append(path)
        if new_field == declared:
            continue
        repaired = dict(plan)
        lane = dict(plan.get("lane", {}))
        lane[lane_field] = new_field
        repaired["lane"] = lane
        return repaired
    return None


class BoundedRepairer:
    """Repair + revalidate + redispatch, bounded by fingerprint/budget/authority.

    ``authorize`` is a predicate ``(role, capability, failure) -> bool`` that
    answers whether the acting role may apply this repair. The default is
    deliberately conservative: every repair requires ``can_mutate_run_state``,
    so a read-only role can never cause a repair to be applied.
    """

    def __init__(
        self,
        *,
        max_attempts: int = 1,
        max_correction_rounds: int = 0,
        authorize: Optional[Callable[[str, str, PreflightFailure], bool]] = None,
        journal: Any = None,
        journal_run_id: str = "repair",
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if max_correction_rounds < 0:
            raise ValueError("max_correction_rounds must be >= 0")
        self.max_attempts = max_attempts
        self.max_correction_rounds = max_correction_rounds
        self._authorize = authorize
        self._journal = journal
        self._journal_run_id = journal_run_id
        self.attempts: list[RepairAttempt] = []

    def _authorized(self, role: str, capability: str, failure: PreflightFailure) -> bool:
        if self._authorize is None:
            return False
        return bool(self._authorize(role, capability, failure))

    def _record(self, attempt: RepairAttempt) -> None:
        self.attempts.append(attempt)
        if self._journal is not None:
            self._journal.append(
                run_id=self._journal_run_id,
                event_type="semantic_repair_attempt",
                payload=attempt.to_dict(),
                idempotency_key=(
                    f"repair:{attempt.attempt}:{attempt.failure_fingerprint}"
                ),
            )

    def repair(
        self,
        plan: dict[str, Any],
        failure: Optional[PreflightFailure],
        *,
        role: str,
        current_target_digest: str,
        evidence: Optional[list[dict[str, Any]]] = None,
        command: str = "promptchain-validate",
        revalidate: Optional[Callable[[dict[str, Any]], PreflightResult]] = None,
        redispatch: Optional[Callable[[dict[str, Any]], str]] = None,
    ) -> RepairOutcome:
        """Attempt a bounded repair of ``plan`` for ``failure``.

        ``current_target_digest`` is the digest of the target as it is NOW. If
        it differs from ``failure.target_digest`` the loop holds: repairing
        against a moved target could apply a stale fix.
        """
        evidence = evidence or (failure.evidence if failure else [])
        plan_digest = digest_target(plan)
        target = failure.target_digest if failure else current_target_digest

        if failure is None:
            return RepairOutcome(
                repaired=True, repaired_plan=plan, target_digest=current_target_digest
            )

        # --- target drift: the ground moved under the diagnosis -------------
        if current_target_digest != failure.target_digest:
            self._record(RepairAttempt(
                attempt=len(self.attempts) + 1,
                failure_fingerprint=failure.fingerprint,
                failure_class=failure.failure_class,
                implicated_fields=list(failure.implicated_fields),
                before_digest=plan_digest,
                after_digest=plan_digest,
                command=command,
                exit_code=1,
                outcome="held",
                hold_reason=HoldReason.TARGET_DRIFT.value,
            ))
            return RepairOutcome(
                repaired=False,
                hold_reason=HoldReason.TARGET_DRIFT.value,
                attempts=list(self.attempts),
                target_digest=current_target_digest,
            )

        # --- repeated fingerprint: we already tried this exact fix ----------
        if any(
            a.failure_fingerprint == failure.fingerprint for a in self.attempts
        ):
            self._record(RepairAttempt(
                attempt=len(self.attempts) + 1,
                failure_fingerprint=failure.fingerprint,
                failure_class=failure.failure_class,
                implicated_fields=list(failure.implicated_fields),
                before_digest=plan_digest,
                after_digest=plan_digest,
                command=command,
                exit_code=1,
                outcome="held",
                hold_reason=HoldReason.REPEATED_FINGERPRINT.value,
            ))
            return RepairOutcome(
                repaired=False,
                hold_reason=HoldReason.REPEATED_FINGERPRINT.value,
                attempts=list(self.attempts),
                target_digest=current_target_digest,
            )

        # --- attempts / correction-round budget ------------------------------
        attempt_limit = self.max_attempts
        limit_reason = HoldReason.ATTEMPTS_EXHAUSTED.value
        if self.max_correction_rounds > 0 and self.max_correction_rounds < attempt_limit:
            attempt_limit = self.max_correction_rounds
            limit_reason = HoldReason.BUDGET_EXHAUSTED.value
        if len(self.attempts) >= attempt_limit:
            self._record(RepairAttempt(
                attempt=len(self.attempts) + 1,
                failure_fingerprint=failure.fingerprint,
                failure_class=failure.failure_class,
                implicated_fields=list(failure.implicated_fields),
                before_digest=plan_digest,
                after_digest=plan_digest,
                command=command,
                exit_code=1,
                outcome="held",
                hold_reason=limit_reason,
            ))
            return RepairOutcome(
                repaired=False,
                hold_reason=limit_reason,
                attempts=list(self.attempts),
                target_digest=current_target_digest,
            )

        # --- authority expansion ---------------------------------------------
        required = failure.authority_requirement or AUTO_REPAIR_CAPABILITY
        if not self._authorized(role, required, failure):
            self._record(RepairAttempt(
                attempt=len(self.attempts) + 1,
                failure_fingerprint=failure.fingerprint,
                failure_class=failure.failure_class,
                implicated_fields=list(failure.implicated_fields),
                before_digest=plan_digest,
                after_digest=plan_digest,
                command=command,
                exit_code=1,
                outcome="held",
                hold_reason=HoldReason.AUTHORITY_EXPANSION.value,
            ))
            return RepairOutcome(
                repaired=False,
                hold_reason=HoldReason.AUTHORITY_EXPANSION.value,
                attempts=list(self.attempts),
                target_digest=current_target_digest,
            )

        # --- non-repairable failure class ------------------------------------
        if not _is_auto_repairable(failure):
            self._record(RepairAttempt(
                attempt=len(self.attempts) + 1,
                failure_fingerprint=failure.fingerprint,
                failure_class=failure.failure_class,
                implicated_fields=list(failure.implicated_fields),
                before_digest=plan_digest,
                after_digest=plan_digest,
                command=command,
                exit_code=1,
                outcome="held",
                hold_reason=HoldReason.NON_REPAIRABLE_CLASS.value,
            ))
            return RepairOutcome(
                repaired=False,
                hold_reason=HoldReason.NON_REPAIRABLE_CLASS.value,
                attempts=list(self.attempts),
                target_digest=current_target_digest,
            )

        # --- the actual bounded edit -----------------------------------------
        repaired_plan = _apply_repair(plan, failure, evidence)
        if repaired_plan is None:
            self._record(RepairAttempt(
                attempt=len(self.attempts) + 1,
                failure_fingerprint=failure.fingerprint,
                failure_class=failure.failure_class,
                implicated_fields=list(failure.implicated_fields),
                before_digest=plan_digest,
                after_digest=plan_digest,
                command=command,
                exit_code=1,
                outcome="held",
                hold_reason=HoldReason.IMPLICATED_FIELD_UNKNOWN.value,
            ))
            return RepairOutcome(
                repaired=False,
                hold_reason=HoldReason.IMPLICATED_FIELD_UNKNOWN.value,
                attempts=list(self.attempts),
                target_digest=current_target_digest,
            )

        after_digest = digest_target(repaired_plan)

        # --- revalidate against the UNCHANGED target digest ------------------
        revalidated: Optional[PreflightResult] = None
        if revalidate is not None:
            revalidated = revalidate(repaired_plan)
        if revalidated is not None and not revalidated.passed:
            self._record(RepairAttempt(
                attempt=len(self.attempts) + 1,
                failure_fingerprint=failure.fingerprint,
                failure_class=failure.failure_class,
                implicated_fields=list(failure.implicated_fields),
                before_digest=plan_digest,
                after_digest=after_digest,
                command=command,
                exit_code=1,
                outcome="held",
                hold_reason=HoldReason.NON_REPAIRABLE_CLASS.value,
            ))
            return RepairOutcome(
                repaired=False,
                hold_reason=HoldReason.NON_REPAIRABLE_CLASS.value,
                attempts=list(self.attempts),
                target_digest=current_target_digest,
            )

        dispatch_identity = redispatch(repaired_plan) if redispatch else None
        self._record(RepairAttempt(
            attempt=len(self.attempts) + 1,
            failure_fingerprint=failure.fingerprint,
            failure_class=failure.failure_class,
            implicated_fields=list(failure.implicated_fields),
            before_digest=plan_digest,
            after_digest=after_digest,
            command=command,
            exit_code=0,
            outcome="repaired",
            dispatch_identity=dispatch_identity,
        ))
        return RepairOutcome(
            repaired=True,
            attempts=list(self.attempts),
            repaired_plan=repaired_plan,
            dispatch_identity=dispatch_identity,
            target_digest=target,
        )


# ---------------------------------------------------------------------------
# Grounding evidence for the two auto-repairs
# ---------------------------------------------------------------------------

_SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "venv", "__pycache__"})

#: Fields a plan may declare a language in.
_LANGUAGE_FIELDS = ("language", "source_language")


def language_of(path: str) -> Optional[str]:
    """Return the language a source path belongs to, or ``None`` if unknown."""
    from ..grounding.scanner import GroundingScanner

    suffix = Path(path).suffix.lower()
    return GroundingScanner.LANG_EXTENSIONS.get(suffix)


def collect_grounding_evidence(
    repo_root: Any, *, max_files: int = 2000
) -> list[str]:
    """Bounded, read-only list of repository-relative file paths.

    This is the candidate world a repair may draw from: a replacement path must
    already exist here, it is never invented.
    """
    root = Path(repo_root)
    if not root.is_dir():
        return []
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            rel = Path(dirpath, name).relative_to(root).as_posix()
            found.append(rel)
            if len(found) >= max_files:
                return found
    return found


def _declared_language(task: dict[str, Any]) -> Optional[str]:
    lane = task.get("lane")
    sources = [lane] if isinstance(lane, dict) else []
    sources.append(task)
    for source in sources:
        for field_name in _LANGUAGE_FIELDS:
            value = source.get(field_name) if isinstance(source, dict) else None
            if isinstance(value, str) and value:
                return value
    return None


def _candidates_for_missing(
    path: str, evidence: list[str], *, limit: int = 1
) -> list[str]:
    """Grounded replacements for a missing path, strongest match first.

    A same-basename file anywhere in the repo wins; then a same-suffix file in
    the same directory. Never returns the missing path itself.
    """
    target = Path(path)
    same_name = [p for p in evidence if Path(p).name == target.name and p != path]
    same_dir = [
        p
        for p in evidence
        if Path(p).parent == target.parent
        and Path(p).suffix == target.suffix
        and p != path
    ]
    ordered = list(dict.fromkeys(same_name + same_dir))
    return ordered[:limit]


def _candidates_for_language(
    path: str, declared_language: str, evidence: list[str], *, limit: int = 1
) -> list[str]:
    """Grounded same-stem files whose language matches what the task declares."""
    stem = Path(path).stem
    parent = Path(path).parent
    same_stem = [
        p
        for p in evidence
        if Path(p).stem == stem and language_of(p) == declared_language
    ]
    same_dir = [
        p
        for p in evidence
        if Path(p).parent == parent and language_of(p) == declared_language
    ]
    ordered = list(dict.fromkeys(same_stem + same_dir))
    return ordered[:limit]


def detect_surface_failure(
    task: dict[str, Any],
    repo_root: Any,
    *,
    target_digest: str,
    evidence: Optional[list[str]] = None,
) -> Optional[PreflightFailure]:
    """Diagnose a task's lane surfaces against real grounding evidence.

    Returns a :class:`PreflightFailure` for the first grounded, repairable
    problem — a nonexistent ``modifies`` path or a wrong-language source path —
    or ``None`` when the surfaces are consistent with the repository.
    """
    lane = task.get("lane")
    if not isinstance(lane, dict):
        return None
    root = Path(repo_root)
    world = evidence if evidence is not None else collect_grounding_evidence(root)
    task_id = str(task.get("id", "<no-id>"))

    # 1. wrong-language source path (declared language contradicts the path)
    declared = _declared_language(task)
    if declared:
        for field_name in ("modifies", "creates"):
            for raw in _lane_field(task, field_name) or []:
                actual = language_of(raw)
                if actual is None or actual == declared:
                    continue
                candidates = _candidates_for_language(raw, declared, world)
                grounding = [
                    {
                        "kind": "grounding_candidate",
                        "path": cand,
                        "language": language_of(cand),
                        "source": "grounding_scan",
                    }
                    for cand in candidates
                ]
                return PreflightFailure(
                    failure_class=FailureClass.WRONG_LANGUAGE_SOURCE_PATH.value,
                    target_digest=target_digest,
                    evidence=[
                        {
                            "kind": "language_conflict",
                            "path": raw,
                            "task_id": task_id,
                            "expected_language": declared,
                            "actual_language": actual,
                        },
                        *grounding,
                    ],
                    implicated_fields=[field_name],
                    retryability=Retryability.AUTO_REPAIRABLE.value,
                    authority_requirement=AUTO_REPAIR_CAPABILITY,
                    detail=(
                        f"task {task_id!r} expects {declared!r} but {raw!r} is "
                        f"{actual!r}"
                    ),
                )

    # 2. nonexistent modifies path
    for raw in _lane_field(task, "modifies") or []:
        if (root / raw).is_file():
            continue
        candidates = _candidates_for_missing(raw, world)
        grounding = [
            {"kind": "grounding_candidate", "path": cand, "source": "grounding_scan"}
            for cand in candidates
        ]
        return PreflightFailure(
            failure_class=FailureClass.NONEXISTENT_MODIFIES_PATH.value,
            target_digest=target_digest,
            evidence=[
                {
                    "kind": "missing_target",
                    "path": raw,
                    "task_id": task_id,
                    "detail": f"resolved={(root / raw).as_posix()}",
                },
                *grounding,
            ],
            implicated_fields=["modifies"],
            retryability=Retryability.AUTO_REPAIRABLE.value,
            authority_requirement=AUTO_REPAIR_CAPABILITY,
            detail=f"task {task_id!r} modifies missing path {raw!r}",
        )

    return None


def repair_plan_from_grounding(
    plan: dict[str, Any],
    repo_root: Any,
    *,
    role: str,
    current_target_digest: str,
    authorize: Optional[Callable[[str, str, PreflightFailure], bool]] = None,
    revalidate: Optional[Callable[[dict[str, Any]], PreflightResult]] = None,
    redispatch: Optional[Callable[[dict[str, Any]], str]] = None,
    journal: Any = None,
    journal_run_id: str = "repair",
    max_attempts: int = 1,
) -> RepairOutcome:
    """Diagnose + repair a task plan from grounding evidence in one call.

    This is the integration seam: it grounds the failure from the repository,
    then runs :class:`BoundedRepairer` with the same evidence.
    """
    target = current_target_digest
    failure = detect_surface_failure(plan, repo_root, target_digest=target)
    repairer = BoundedRepairer(
        max_attempts=max_attempts,
        authorize=authorize,
        journal=journal,
        journal_run_id=journal_run_id,
    )
    evidence = failure.evidence if failure else []
    return repairer.repair(
        plan,
        failure,
        role=role,
        current_target_digest=current_target_digest,
        evidence=evidence,
        revalidate=revalidate,
        redispatch=redispatch,
    )
