"""Process runner that turns a worker invocation into bound evidence.

This module is the half of the runtime that ``dagscheduler`` (010) deliberately
does not own: actually starting a process. Scheduling builds ordered batches of
tasks; this adapter executes one of them and collects what came back.

Three concerns, each mapped to a dispatch criterion:

1. The worker runs as a *real* process (``subprocess``), never in-process, so a
   test can prove that a trivial command really executed (a distinct PID and
   captured output, not a mocked return value).

2. stdout and stderr are captured and bound to the run as ``ArtifactReceipt``
   evidence (the type introduced by 005), never as free text. The adapter
   hashes the raw byte streams and produces one receipt per stream, typed
   ``EvidenceType.RUNTIME_TRACE``, carrying the run id and the stream identity
   in ``metadata``. A caller can persist them wholesale via
   ``SQLiteRunStore.save_evidence`` without any text reconstruction.

3. Exit code and termination signal are distinguished, not conflated. POSIX
   reports a signal-terminated process as a negative returncode; the adapter
   splits that into an explicit ``exit_code`` (``None`` when signaled) and
   ``signal`` (``None`` on a clean exit), so a consumer never has to decode the
   sign convention itself.

This module imports from ``registry`` (receipt types) only. It does not touch
``dagscheduler`` (010's file) and does not modify ``store``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import hashlib
import subprocess

from .registry import ArtifactReceipt, EvidenceQuality, EvidenceType


def _hash_bytes(data: bytes) -> str:
    """Return the hex sha256 of ``data`` (empty input hashes to a stable value)."""
    return hashlib.sha256(data).hexdigest()


def _split_returncode(returncode: int) -> tuple[Optional[int], Optional[int]]:
    """Split a POSIX returncode into (exit_code, signal).

    A non-negative returncode is a process exit code (``signal`` is ``None``).
    A negative returncode is a low-word signal termination: ``-N`` means the
    process was killed by signal ``N`` (``exit_code`` is ``None``).

    The two are kept distinct so a consumer records both without decoding the
    sign convention itself (dispatch criterion 6).
    """
    if returncode < 0:
        return None, -returncode
    return returncode, None


@dataclass
class ProcessResult:
    """The collected result of one worker invocation.

    ``stdout_receipt`` and ``stderr_receipt`` are ``ArtifactReceipt`` evidence,
    not raw text. ``exit_code`` and ``signal`` are mutually exclusive: exactly
    one of them is ``None`` after a completed process.
    """

    command: list[str]
    exit_code: Optional[int]
    signal: Optional[int]
    pid: int
    stdout_receipt: Optional[ArtifactReceipt]
    stderr_receipt: Optional[ArtifactReceipt]
    stdout: bytes = b""
    stderr: bytes = b""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        """True only on a clean exit with code 0 (not on a signal)."""
        return self.exit_code == 0 and self.signal is None

    @property
    def signaled(self) -> bool:
        return self.signal is not None


def _make_stream_receipt(
    stream: str,
    data: bytes,
    *,
    run_id: str,
    command: list[str],
    subject_repo: str,
    subject_commit: str,
    created_at: str,
    exit_code: Optional[int],
    signal: Optional[int],
    purpose: str,
) -> Optional[ArtifactReceipt]:
    """Build an ``ArtifactReceipt`` for one captured byte stream.

    The receipt is bound to the run through ``metadata["run_id"]`` and the
    originating ``subject_commit``. ``stream`` is one of ``"stdout"``,
    ``"stderr"``. The bytes themselves are hashed into ``sha256``; they are not
    stored as free text, only referenced by digest.
    """
    return ArtifactReceipt(
        artifact_id=f"trace-{run_id}-{stream}",
        sha256=_hash_bytes(data),
        schema_version="1",
        producer_command=" ".join(command),
        subject_repo=subject_repo,
        subject_commit=subject_commit,
        created_at=created_at,
        evidence_type=EvidenceType.RUNTIME_TRACE.value,
        purpose=purpose,
        method="subprocess",
        system_source="runner_adapter",
        quality=EvidenceQuality(
            relevance="high",
            sufficiency="high",
            reliability="high",
            integrity="high",
        ),
        metadata={
            "run_id": run_id,
            "stream": stream,
            "byte_length": len(data),
            "exit_code": exit_code,
            "signal": signal,
        },
    )


def run_command(
    command: Sequence[str],
    *,
    run_id: str,
    subject_repo: str,
    subject_commit: str,
    created_at: Optional[str] = None,
    input_bytes: Optional[bytes] = None,
    timeout: Optional[float] = None,
    cwd: Optional[str] = None,
) -> ProcessResult:
    """Run ``command`` as a real process and return bound evidence.

    Parameters
    ----------
    command:
        The argv list to execute (already split; no shell interpretation).
    run_id:
        The owning run. Recorded on both stream receipts so the captured output
        stays attributable after persistence.
    subject_repo, subject_commit:
        The repo/commit the run operates on; carried onto the receipts.
    created_at:
        ISO timestamp for the receipts; defaults to the actual completion time.
    input_bytes:
        Optional bytes fed to the process's stdin.
    timeout:
        Optional wall-clock timeout; a ``subprocess.TimeoutExpired`` propagates
        to the caller unchanged.
    cwd:
        Optional working directory for the child process.
    """
    from datetime import datetime, timezone

    # Popen, not run(): we need the child PID to prove a real process started.
    proc = subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
    )

    stdout_bytes, stderr_bytes = proc.communicate(input=input_bytes, timeout=timeout)

    # capture the pid and returncode before they are lost; keep pid even though
    # ``communicate`` already waited, because the child is what carried it.
    child_pid = proc.pid
    returncode = proc.returncode

    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()

    stdout_bytes = stdout_bytes if stdout_bytes is not None else b""
    stderr_bytes = stderr_bytes if stderr_bytes is not None else b""

    exit_code, signal = _split_returncode(returncode)

    stdout_receipt = _make_stream_receipt(
        "stdout",
        stdout_bytes,
        run_id=run_id,
        command=list(command),
        subject_repo=subject_repo,
        subject_commit=subject_commit,
        created_at=created_at,
        exit_code=exit_code,
        signal=signal,
        purpose=f"stdout of run '{run_id}'",
    )
    stderr_receipt = _make_stream_receipt(
        "stderr",
        stderr_bytes,
        run_id=run_id,
        command=list(command),
        subject_repo=subject_repo,
        subject_commit=subject_commit,
        created_at=created_at,
        exit_code=exit_code,
        signal=signal,
        purpose=f"stderr of run '{run_id}'",
    )

    return ProcessResult(
        command=list(command),
        exit_code=exit_code,
        signal=signal,
        pid=child_pid,
        stdout_receipt=stdout_receipt,
        stderr_receipt=stderr_receipt,
        stdout=stdout_bytes,
        stderr=stderr_bytes,
        metadata={
            "run_id": run_id,
            "subject_repo": subject_repo,
            "subject_commit": subject_commit,
            "created_at": created_at,
        },
    )
