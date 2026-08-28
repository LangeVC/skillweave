"""Dispatch trace contracts (SW1311-RECEIPT-001).

This module is the canonical home for the trace layer the operator dispatcher
consumes. It replaces exit-code/log inference with a **typed job lifecycle** and
binds every dispatch, correction, review and integration attempt to an
**append-only receipt** and a **terminal envelope**.

It owns four concerns, each mapped to a dispatch criterion:

1. **Append-only rounds** (:class:`AppendOnlyReceiptLog`): every attempt is a
   :class:`JobRecord` whose ``id`` is content-addressed and whose ``parent_id``
   links it to the previous record in the same lineage. Appending a duplicate
   *id* with identical bytes is idempotent; the same *id* with different bytes
   fails closed (criterion 8). Prior digests are immutable (criterion 1).

2. **Separated outcome dimensions** (:class:`JobResult`): process status, task
   verdict, evidence availability and gate verdict are four *separate* fields.
   Exit zero alone can neither verify a task nor pass a gate (criterion 2).

3. **Terminal envelope** (:class:`TerminalEnvelope`): binds the full subject
   SHA, the exact command, and a single machine outcome (exit code *or* signal
   *or* timeout) together with raw artifact references, declared inputs and the
   completion contract (criterion 3). A completion that is missing required
   evidence, carries an unresolvable artifact, or omits subject identity cannot
   mark the task complete (criterion 7).

4. **Deterministic noninteractive lifecycle**: a headless job that requests
   stdin produces a typed ``blocked_input`` result and never waits (criterion
   4); heartbeat expiry, timeout, cancel and launch failure each produce a
   deterministic, distinct :class:`TerminalState` (criterion 5). Every job
   receives a unique run id, working directory and state namespace; a shared
   namespace collision fails preflight as a **technical failure** (criterion 6).

Nothing here launches a worker, names a concrete provider/model/harness, or
bakes a provider default. The module is dependency-light and self-contained so
it can be consumed by the dispatch application and later trace lanes
(review/handoff/observer) without importing the runtime.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Mapping, Optional, Sequence


# ── Exception hierarchy ──────────────────────────────────────────────────────


class TraceContractError(Exception):
    """A trace contract violation (raised fail-closed, never silently folded)."""


class BlockedInputError(TraceContractError):
    """A noninteractive job requested stdin and must never wait indefinitely."""


class NamespaceCollisionError(TraceContractError):
    """Two jobs claimed the same state namespace / run identity.

    A technical failure: it must fail preflight or retry as a technical error,
    never become a ``REVIEW_FAIL``.
    """


class PreflightError(TraceContractError):
    """A job failed preflight (shared state collision or other technical cause)."""


class IncompleteCompletionError(TraceContractError):
    """A completion envelope is missing required evidence, carries an
    unresolvable artifact, or omits subject identity."""


class DuplicateDigestError(TraceContractError):
    """The same record id was appended with different bytes (fail closed)."""


# ── The four separated outcome dimensions (criterion 2) ──────────────────────


class JobStatus(str, Enum):
    """The process-status dimension of a job (how the child process ended).

    Independent of the task verdict, evidence availability and gate verdict:
    a process can exit zero while the task is still ``inconclusive``.
    """

    NOT_STARTED = "not_started"
    RUNNING = "running"
    EXITED = "exited"
    SIGNALED = "signaled"
    TIMED_OUT = "timed_out"
    LAUNCH_FAILED = "launch_failed"
    BLOCKED_INPUT = "blocked_input"
    CANCELLED = "cancelled"
    HEARTBEAT_EXPIRED = "heartbeat_expired"


class TaskVerdict(str, Enum):
    """The task-verdict dimension of a job (whether the task discharged).

    Exit zero alone is not a ``verified`` verdict; a ``failed`` or
    ``inconclusive`` verdict is distinct from a process-status bucket.
    """

    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    BLOCKED = "blocked"


class EvidenceAvailability(str, Enum):
    """The evidence-availability dimension: whether required artifacts exist.

    Availability is a fact about resolvable artifacts, independent of whether
    the task or gate passed.
    """

    UNDECLARED = "undeclared"
    RECORDED = "recorded"
    MISSING = "missing"
    UNRESOLVABLE = "unresolvable"


class GateVerdict(str, Enum):
    """The gate-verdict dimension, derived from the completion contract.

    ``pass`` requires non-empty, check-passing output and an unqualified exit;
    ``inconclusive`` is exit-zero-but-empty; ``fail`` is a non-zero exit, a
    signal, or any non-``exited`` termination. A bare exit zero never passes.
    """

    UNSET = "unset"
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


# ── Deterministic terminal states (criterion 5) ──────────────────────────────


class TerminalState(str, Enum):
    """The deterministic terminal state of a child job.

    Each value is distinct and reproducible: heartbeat expiry, timeout, cancel
    and launch failure never collapse into one ambiguous "failed" bucket, and
    each implies the child was reaped.
    """

    COMPLETED = "completed"
    HEARTBEAT_EXPIRED = "heartbeat_expired"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    LAUNCH_FAILED = "launch_failed"
    BLOCKED_INPUT = "blocked_input"
    PREFLIGHT_FAILED = "preflight_failed"


#: The terminal states that represent a technical, not a task, failure. They
#: must never consume a task correction round and never become ``REVIEW_FAIL``.
TECHNICAL_TERMINAL_STATES: frozenset[str] = frozenset({
    TerminalState.HEARTBEAT_EXPIRED.value,
    TerminalState.TIMED_OUT.value,
    TerminalState.CANCELLED.value,
    TerminalState.LAUNCH_FAILED.value,
    TerminalState.BLOCKED_INPUT.value,
    TerminalState.PREFLIGHT_FAILED.value,
})


# ── Round kinds (criterion 1) ────────────────────────────────────────────────


class RoundKind(str, Enum):
    """The kind of an append-only round: dispatch, correction, review, integrate."""

    DISPATCH = "dispatch"
    CORRECTION = "correction"
    REVIEW = "review"
    INTEGRATION = "integration"


# ── Stable hashing helpers ───────────────────────────────────────────────────


def _canonical_bytes(data: Any) -> bytes:
    """Canonicalise ``data`` into deterministic bytes for digesting.

    Dicts are serialised with sorted keys and a non-lossy JSON encoder, so two
    structurally equal payloads hash identically while ordering-independent.
    """
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    return json.dumps(
        data, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _sha256_hex(data: Any) -> str:
    return hashlib.sha256(_canonical_bytes(data)).hexdigest()


def content_id(*parts: Any) -> str:
    """A content-addressed id over the given parts (stable, collision-resistant)."""
    return _sha256_hex(list(parts))


# ── JobResult: the four separated dimensions (criterion 2) ──────────────────


@dataclass
class JobResult:
    """One job's outcome, with four *separate* dimensions.

    ``job_status`` (process), ``task_verdict`` (did the task discharge),
    ``evidence_available`` (are required artifacts resolvable) and
    ``gate_verdict`` (the completion contract's verdict) are independent.
    Exit zero alone can neither verify a task nor pass a gate: a job's
    ``job_status`` may be ``exited`` while ``task_verdict`` is ``inconclusive``
    and ``gate_verdict`` is ``inconclusive``.
    """

    job_status: JobStatus = JobStatus.NOT_STARTED
    task_verdict: TaskVerdict = TaskVerdict.QUEUED
    evidence_available: EvidenceAvailability = EvidenceAvailability.UNDECLARED
    gate_verdict: GateVerdict = GateVerdict.UNSET

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_status": self.job_status.value,
            "task_verdict": self.task_verdict.value,
            "evidence_available": self.evidence_available.value,
            "gate_verdict": self.gate_verdict.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "JobResult":
        return cls(
            job_status=JobStatus(data["job_status"]),
            task_verdict=TaskVerdict(data["task_verdict"]),
            evidence_available=EvidenceAvailability(data["evidence_available"]),
            gate_verdict=GateVerdict(data["gate_verdict"]),
        )


# ── Terminal envelope (criterion 3, 7) ───────────────────────────────────────


@dataclass
class TerminalEnvelope:
    """The binding terminal envelope of one child job.

    Binds the full subject SHA, the exact command, and exactly one machine
    outcome: an exit code *or* a signal *or* a timeout — plus the raw artifact
    references, the declared inputs, and the completion contract. A completion
    missing required evidence, carrying an unresolvable artifact, or omitting
    subject identity cannot mark the task complete (criterion 7).
    """

    subject_sha: str
    command: List[str]
    terminal_state: TerminalState
    exit_code: Optional[int] = None
    signal: Optional[int] = None
    timed_out: bool = False
    artifact_refs: Optional[List[str]] = None
    declared_inputs: Optional[List[str]] = None
    completion_contract: Optional[dict[str, Any]] = None

    def __post_init__(self) -> None:
        self.command = list(self.command)

    @property
    def outcome(self) -> str:
        """The single machine outcome: ``exit_code`` / ``signal`` / ``timed_out``.

        A terminal envelope carries exactly one of exit code, signal, or
        timeout; the terminal state names which is present.
        """
        if self.terminal_state is TerminalState.TIMED_OUT or self.timed_out:
            return "timed_out"
        if self.signal is not None:
            return "signal"
        if self.terminal_state in (TerminalState.LAUNCH_FAILED, TerminalState.CANCELLED,
                                    TerminalState.HEARTBEAT_EXPIRED,
                                    TerminalState.BLOCKED_INPUT,
                                    TerminalState.PREFLIGHT_FAILED):
            return self.terminal_state.value
        return "exit_code"

    def complete(self, *, required_evidence: Sequence[str] = (), resolver=None) -> bool:
        """Declare the task complete, fail-closed (criterion 7).

        Refuses (``False``) when required evidence is missing, when a referenced
        artifact cannot be resolved, or when subject identity is omitted. A
        caller that needs the failure enumerated may call
        :meth:`completion_error` instead.
        """
        return self.completion_error(
            required_evidence=required_evidence, resolver=resolver
        ) is None

    def completion_error(
        self, *, required_evidence: Sequence[str] = (), resolver=None
    ) -> Optional[str]:
        """Return the first completion-blocking reason, or ``None`` when complete.

        Fail-closed in three directions (criterion 7):

        * subject identity omitted (empty subject SHA);
        * required evidence declared but an artifact reference is missing or
          unresolvable;
        * an artifact reference that cannot be resolved to bytes via ``resolver``.
        """
        if not self.subject_sha:
            return "subject identity omitted"
        refs = self.artifact_refs or []
        if required_evidence:
            if not refs:
                return "required evidence missing"
            if resolver is not None:
                for ref in refs:
                    try:
                        resolver(ref)
                    except Exception:  # noqa: BLE001
                        return f"unresolvable artifact '{ref}'"
        return None

    def verify_outcome(self) -> None:
        """Reject a contradictory envelope (exit code *and* signal, etc.)."""
        outcomes = 0
        if self.signal is not None:
            outcomes += 1
        if self.exit_code is not None and not self.timed_out:
            outcomes += 1
        if self.timed_out:
            outcomes += 1
        if self.terminal_state in (TerminalState.LAUNCH_FAILED,
                                    TerminalState.CANCELLED,
                                    TerminalState.HEARTBEAT_EXPIRED,
                                    TerminalState.BLOCKED_INPUT,
                                    TerminalState.PREFLIGHT_FAILED):
            outcomes += 1
        if outcomes != 1:
            raise TraceContractError(
                f"terminal envelope must carry exactly one machine outcome, "
                f"got {outcomes} (state={self.terminal_state.value})"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_sha": self.subject_sha,
            "command": list(self.command),
            "terminal_state": self.terminal_state.value,
            "exit_code": self.exit_code,
            "signal": self.signal,
            "timed_out": self.timed_out,
            "outcome": self.outcome,
            "artifact_refs": list(self.artifact_refs or []),
            "declared_inputs": list(self.declared_inputs or []),
            "completion_contract": self.completion_contract,
        }


# ── Append-only receipt log (criteria 1, 8) ──────────────────────────────────


@dataclass
class JobRecord:
    """One immutable append-only receipt record.

    ``record_id`` is content-addressed over the record's bytes; ``parent_id``
    links to the previous record in the lineage (``None`` for the root). The
    ``digest`` is the immutable hash of this record's canonical bytes and never
    changes once the record is appended.
    """

    record_id: str
    round: int
    kind: RoundKind
    parent_id: Optional[str]
    digest: str
    job_id: Optional[str] = None
    result: Optional[JobResult] = None
    envelope: Optional[TerminalEnvelope] = None
    payload: Any = None

    def prior_digest(self) -> str:
        """This record's owned digest (immutable, content-addressed)."""
        return self.digest

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "round": self.round,
            "kind": self.kind.value,
            "parent_id": self.parent_id,
            "digest": self.digest,
            "job_id": self.job_id,
            "result": self.result.to_dict() if self.result is not None else None,
            "envelope": self.envelope.to_dict() if self.envelope is not None else None,
            "payload": self.payload,
        }


def _record_payload_bytes(record: JobRecord) -> bytes:
    """The canonical bytes a record's *digest* covers (identity + parent + body).

    ``record_id`` is content-addressed; the ``parent_id`` is threaded through the
    digest so the lineage is tamper-evident end to end.
    """
    body = {
        "round": record.round,
        "kind": record.kind.value,
        "parent_id": record.parent_id,
        "job_id": record.job_id,
        "result": record.result.to_dict() if record.result is not None else None,
        "envelope": record.envelope.to_dict() if record.envelope is not None else None,
        "payload": record.payload,
    }
    return _canonical_bytes(body)


class AppendOnlyReceiptLog:
    """An append-only, content-addressed receipt log (criteria 1, 8).

    Every appended record is immutable: its ``digest`` and ``parent_id`` are
    fixed at append time and cannot change. Appending a duplicate ``record_id``
    with identical bytes is idempotent (the existing record is returned, no new
    record is created); the same ``record_id`` with *different* bytes fails
    closed with :class:`DuplicateDigestError`.
    """

    def __init__(self) -> None:
        self._records: List[JobRecord] = []
        self._by_id: dict[str, JobRecord] = {}
        self._by_digest: dict[str, JobRecord] = {}

    def __len__(self) -> int:
        return len(self._records)

    def resolve_id(self, record_id: str) -> Optional[JobRecord]:
        """Return the record with the given id, or ``None`` (resolvable id)."""
        return self._by_id.get(record_id)

    def resolve_digest(self, digest: str) -> Optional[JobRecord]:
        """Return the record whose digest matches, or ``None``."""
        return self._by_digest.get(digest)

    def append(self, record: JobRecord) -> JobRecord:
        """Append one record, enforcing idempotency and immutability.

        Idempotent: a duplicate ``record_id`` whose canonical bytes hash to the
        same digest returns the already-appended record without creating a new
        entry. A duplicate ``record_id`` with different bytes raises
        :class:`DuplicateDigestError` (fail closed).
        """
        digest = _sha256_hex(_record_payload_bytes(record))
        existing = self._by_id.get(record.record_id)
        if existing is not None:
            if existing.digest != digest:
                raise DuplicateDigestError(
                    f"record id '{record.record_id}' already appended with a "
                    f"different digest ({existing.digest[:12]} != {digest[:12]})"
                )
            return existing
        if record.digest and record.digest != digest:
            raise DuplicateDigestError(
                f"record id '{record.record_id}' declares digest "
                f"{record.digest[:12]} but its bytes hash to {digest[:12]}"
            )
        record.digest = digest
        self._records.append(record)
        self._by_id[record.record_id] = record
        self._by_digest[digest] = record
        return record

    def records(self) -> List[JobRecord]:
        """All records in append order (immutable snapshots)."""
        return list(self._records)

    def latest(self) -> Optional[JobRecord]:
        """The most recently appended record, or ``None`` when empty."""
        return self._records[-1] if self._records else None


def new_append_only_round(
    log: AppendOnlyReceiptLog,
    *,
    parent_id: Optional[str],
    round_: int,
    kind: RoundKind,
    job_id: Optional[str] = None,
    result: Optional[JobResult] = None,
    envelope: Optional[TerminalEnvelope] = None,
    payload: Any = None,
    record_id: Optional[str] = None,
) -> JobRecord:
    """Build and append one immutable round record, linking its parent.

    ``record_id`` defaults to a content-addressed id over the parent, round,
    kind and a fresh random nonce (so concurrent peers never collide); the
    caller may supply a stable id for idempotent re-append.
    """
    if record_id is None:
        record_id = content_id(parent_id, round_, kind.value, uuid.uuid4().hex)
    if result is not None and not isinstance(result, JobResult):
        result = JobResult(**result) if isinstance(result, dict) else result
    if envelope is not None and not isinstance(envelope, TerminalEnvelope):
        envelope = TerminalEnvelope(**envelope) if isinstance(envelope, dict) else envelope
    record = JobRecord(
        record_id=record_id,
        round=round_,
        kind=kind,
        parent_id=parent_id,
        digest="",
        job_id=job_id,
        result=result,
        envelope=envelope,
        payload=payload,
    )
    return log.append(record)


# ── Per-job state namespace (criterion 6) ────────────────────────────────────


@dataclass
class JobStateNamespace:
    """A job's unique run id, working directory and state namespace.

    Every child receives a *unique* run id, a *unique* working directory and a
    *unique* state namespace. :meth:`preflight` fails closed when the run id or
    state namespace collides with a live peer (a simulated shared SQLite/state
    collision), surfacing a technical failure — never ``REVIEW_FAIL``.
    """

    run_id: str
    working_directory: str
    state_namespace: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "working_directory": self.working_directory,
            "state_namespace": self.state_namespace,
        }


class StateNamespaceRegistry:
    """A registry that arbitrates unique state namespaces across jobs.

    A collision (two jobs claiming the same run id or state namespace) fails
    preflight with :class:`NamespaceCollisionError` — a technical failure that
    must be retried, never folded into a ``REVIEW_FAIL``.
    """

    def __init__(self) -> None:
        self._run_ids: set[str] = set()
        self._namespaces: set[str] = set()

    def is_free(self, ns: JobStateNamespace) -> bool:
        return (
            ns.run_id not in self._run_ids and ns.state_namespace not in self._namespaces
        )

    def claim(self, ns: JobStateNamespace) -> bool:
        """Claim a namespace or fail preflight on collision.

        Returns ``True`` on a successful claim; raises
        :class:`NamespaceCollisionError` on a run-id or state-namespace
        collision.
        """
        if ns.run_id in self._run_ids:
            raise NamespaceCollisionError(
                f"run id '{ns.run_id}' is already claimed by another job"
            )
        if ns.state_namespace in self._namespaces:
            raise NamespaceCollisionError(
                f"state namespace '{ns.state_namespace}' is already claimed"
            )
        self._run_ids.add(ns.run_id)
        self._namespaces.add(ns.state_namespace)
        return True

    def retry_after_collision(self, *, base_run_id: str, base_namespace: str) -> JobStateNamespace:
        """Derive a fresh namespace after a collision (bounded retry path).

        Produces a new, unique run id and namespace derived with a nonce, so a
        caller can retry a technical collision without a human in the loop and
        without consuming a task correction round.
        """
        nonce = uuid.uuid4().hex
        return JobStateNamespace(
            run_id=f"{base_run_id}-{nonce[:8]}",
            working_directory=f"{base_namespace}-{nonce[:8]}",
            state_namespace=f"{base_namespace}-{nonce[:8]}",
        )


# ── Noninteractive stdin refusal (criterion 4) ───────────────────────────────


def blocked_input_result(command: Sequence[str]) -> JobResult:
    """Return the typed ``blocked_input`` result for a headless stdin request.

    A noninteractive job that requests stdin must fail with a typed
    ``blocked_input`` result and never wait indefinitely.
    """
    return JobResult(
        job_status=JobStatus.BLOCKED_INPUT,
        task_verdict=TaskVerdict.BLOCKED,
        evidence_available=EvidenceAvailability.MISSING,
        gate_verdict=GateVerdict.FAIL,
    )


# ── Completion-contract gate derivation (criterion 2, 7) ─────────────────────


def derive_gate_verdict(
    *,
    exit_code: Optional[int],
    signal: Optional[int],
    termination: str,
    stdout: bytes,
    check_output: Optional[Any] = None,
) -> GateVerdict:
    """Derive the gate verdict from the completion contract, never exit alone.

    A bare exit zero is *not* pass: empty output is ``inconclusive``, a non-exit
    termination or signal is ``fail``, and only a clean exit with non-empty,
    check-passing output is ``pass``.
    """
    if termination != "exited" or signal is not None:
        return GateVerdict.FAIL
    if exit_code != 0:
        return GateVerdict.FAIL
    if not stdout or not stdout.strip():
        return GateVerdict.INCONCLUSIVE
    if check_output is not None and not check_output(stdout):
        return GateVerdict.INCONCLUSIVE
    return GateVerdict.PASS


def build_job_result_for_terminal(
    *,
    terminal_state: TerminalState,
    exit_code: Optional[int],
    signal: Optional[int],
    termination: Optional[str],
    stdout: bytes,
    required_evidence: Optional[Sequence[str]] = None,
    artifact_refs: Optional[Sequence[str]] = None,
) -> JobResult:
    """Assemble a :class:`JobResult` from a terminal machine outcome.

    Maps the deterministic terminal state onto the four separated dimensions:
    a technical terminal state (timeout, cancel, launch failure, heartbeat
    expiry, blocked input) yields a ``failed``/``blocked`` task verdict and a
    ``fail`` gate verdict, never a ``done``/``pass`` on the strength of exit
    zero alone.
    """
    if terminal_state is TerminalState.BLOCKED_INPUT:
        return blocked_input_result([])

    if terminal_state in (TerminalState.TIMED_OUT, TerminalState.CANCELLED,
                          TerminalState.HEARTBEAT_EXPIRED,
                          TerminalState.LAUNCH_FAILED,
                          TerminalState.PREFLIGHT_FAILED):
        return JobResult(
            job_status=_terminal_to_status(terminal_state),
            task_verdict=TaskVerdict.FAILED,
            evidence_available=(
                EvidenceAvailability.RECORDED
                if artifact_refs else EvidenceAvailability.MISSING
            ),
            gate_verdict=GateVerdict.FAIL,
        )

    status = JobStatus.SIGNALED if signal is not None else JobStatus.EXITED
    gate = derive_gate_verdict(
        exit_code=exit_code,
        signal=signal,
        termination=termination or ("exited" if signal is None else "signaled"),
        stdout=stdout,
    )
    evidence = _evidence_for(refs=artifact_refs, required=required_evidence)
    if gate is GateVerdict.PASS:
        task = TaskVerdict.DONE
    elif gate is GateVerdict.INCONCLUSIVE:
        task = TaskVerdict.INCONCLUSIVE
    else:
        task = TaskVerdict.FAILED
    return JobResult(
        job_status=status,
        task_verdict=task,
        evidence_available=evidence,
        gate_verdict=gate,
    )


def _terminal_to_status(terminal_state: TerminalState) -> JobStatus:
    return {
        TerminalState.HEARTBEAT_EXPIRED: JobStatus.HEARTBEAT_EXPIRED,
        TerminalState.TIMED_OUT: JobStatus.TIMED_OUT,
        TerminalState.CANCELLED: JobStatus.CANCELLED,
        TerminalState.LAUNCH_FAILED: JobStatus.LAUNCH_FAILED,
        TerminalState.BLOCKED_INPUT: JobStatus.BLOCKED_INPUT,
        TerminalState.PREFLIGHT_FAILED: JobStatus.LAUNCH_FAILED,
    }[terminal_state]


def _evidence_for(
    *, refs: Optional[Sequence[str]], required: Optional[Sequence[str]]
) -> EvidenceAvailability:
    if required is None:
        return EvidenceAvailability.UNDECLARED
    if not required:
        return EvidenceAvailability.RECORDED
    if not refs:
        return EvidenceAvailability.MISSING
    return EvidenceAvailability.RECORDED


__all__ = [
    "TraceContractError",
    "BlockedInputError",
    "NamespaceCollisionError",
    "PreflightError",
    "IncompleteCompletionError",
    "DuplicateDigestError",
    "JobStatus",
    "TaskVerdict",
    "EvidenceAvailability",
    "GateVerdict",
    "TerminalState",
    "TECHNICAL_TERMINAL_STATES",
    "RoundKind",
    "JobResult",
    "TerminalEnvelope",
    "JobRecord",
    "AppendOnlyReceiptLog",
    "new_append_only_round",
    "JobStateNamespace",
    "StateNamespaceRegistry",
    "blocked_input_result",
    "derive_gate_verdict",
    "build_job_result_for_terminal",
    "content_id",
]
