"""Process runner that turns a worker invocation into bound evidence.

This module is the half of the runtime that ``dagscheduler`` (010) deliberately
does not own: actually starting a process. Scheduling builds ordered batches of
tasks; this adapter executes one of them and collects what came back.

Concerns, each mapped to a dispatch criterion:

1. The worker runs as a *real* process (``subprocess``), never in-process, so a
   test can prove that a trivial command really executed (a distinct PID and
   captured output, not a mocked return value).

2. stdout and stderr are captured and bound to the run as ``ArtifactReceipt``
   evidence (the type introduced by 005), never as free text. The adapter
   hashes the raw byte streams and produces one receipt per stream, typed
   ``EvidenceType.RUNTIME_TRACE``, carrying the run id and the stream identity
   in ``metadata``. A caller can persist them wholesale via
   ``SQLiteRunStore.save_evidence`` without any text reconstruction.

3. Cancel kills the process for real, and a test may prove *no child survives*:
   the child runs in its own process group, and cancel (or timeout) kills that
   entire group and reaps it, so no descendant is left behind.

4. A timeout produces a *defined state* (``termination == "timed_out"`` on the
   returned ``ProcessResult``), never an unbounded wait and never a bare
   ``TimeoutExpired`` escaping the adapter.

5. A worker that dies without a result (signaled, cancelled, timed out, or a
   non-zero exit) is a *failure with a message*, never a silent success:
   ``ProcessResult.succeeded`` is ``False`` and ``message`` explains it.

6. Exit code and termination signal are distinguished, not conflated. POSIX
   reports a signal-terminated process as a negative returncode; the adapter
   splits that into an explicit ``exit_code`` (``None`` when signaled) and
   ``signal`` (``None`` on a clean exit).

This module imports from ``registry`` (receipt types) only. It does not touch
``dagscheduler`` (010's file) and does not modify ``store``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence

import hashlib
import os
import signal as _signal
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


def _pid_exists(pid: int) -> bool:
    """Return ``True`` if a process with ``pid`` still exists.

    ``os.kill(pid, 0)`` raises ``ProcessLookupError`` once the process is gone
    (or ``PermissionError`` when it exists but belongs to another user, which
    still means it *exists*). Used by tests to assert that a cancelled worker
    left no surviving child behind.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass
class ProcessResult:
    """The collected result of one worker invocation.

    ``stdout_receipt`` and ``stderr_receipt`` are ``ArtifactReceipt`` evidence,
    not raw text. ``exit_code`` and ``signal`` are mutually exclusive: exactly
    one of them is ``None`` after a completed process.

    ``termination`` records *how* the process ended, one of ``"exited"``,
    ``"signaled"``, ``"cancelled"``, or ``"timed_out"``. ``message`` is a
    human-readable failure explanation, and is ``""`` on success only.
    """

    command: List[str]
    exit_code: Optional[int]
    signal: Optional[int]
    termination: str
    pid: int
    stdout_receipt: Optional[ArtifactReceipt]
    stderr_receipt: Optional[ArtifactReceipt]
    message: str = ""
    stdout: bytes = b""
    stderr: bytes = b""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        """True only when the worker exited cleanly with code 0 and produced.

        A cancelled, timed-out, or signal-killed worker never succeeds, even if
        by chance its process happened to exit 0 at the last instant."""
        return (
            self.termination == "exited"
            and self.exit_code == 0
            and self.signal is None
        )

    @property
    def signaled(self) -> bool:
        return self.signal is not None


def _make_stream_receipt(
    stream: str,
    data: bytes,
    *,
    run_id: str,
    command: List[str],
    subject_repo: str,
    subject_commit: str,
    created_at: str,
    exit_code: Optional[int],
    signal: Optional[int],
    purpose: str,
) -> ArtifactReceipt:
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


@dataclass
class RunningProcess:
    """A live worker process the caller may wait on or cancel.

    Starts the command in its own session/process group so that cancelling it
    kills every descendant the worker spawned, leaving no surviving child.
    """

    process: subprocess.Popen
    command: List[str]
    _run_id: str
    _subject_repo: str
    _subject_commit: str
    _created_at: Optional[str] = None
    _cancelled: bool = False

    @property
    def pid(self) -> int:
        return self.process.pid

    def _kill_group(self) -> None:
        """Terminate the child's whole process group, then reap it.

        SIGTERM first (graceful), then SIGKILL after a short grace period for
        workers that ignored the polite ask. Killing by *group* is what lets the
        cancel test assert that no descendant survives.
        """
        try:
            os.killpg(self.process.pid, _signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            self.process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, _signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            self.process.wait()
        except ProcessLookupError:
            pass

    def cancel(self) -> ProcessResult:
        """Cancel the worker and return an explicit ``cancelled`` result.

        Always kills the process group and reaps the child, so after this
        returns there is no surviving child (criterion 3)."""
        self._cancelled = True
        self._kill_group()

        from datetime import datetime, timezone

        created_at = self._created_at or datetime.now(timezone.utc).isoformat()

        stdout_bytes = b""
        stderr_bytes = b""
        if self.process.stdout is not None:
            stdout_bytes = self.process.stdout.read()
        if self.process.stderr is not None:
            stderr_bytes = self.process.stderr.read()

        return self._build_result(
            exit_code=None,
            signal=None,
            termination="cancelled",
            created_at=created_at,
            stdout_bytes=stdout_bytes,
            stderr_bytes=stderr_bytes,
            message=f"worker cancelled by request ({' '.join(self.command)})",
        )

    def wait(
        self,
        timeout: Optional[float] = None,
        input_bytes: Optional[bytes] = None,
    ) -> ProcessResult:
        """Wait for the worker to finish, honouring an optional timeout.

        On timeout the worker's whole process group is killed and a definite
        ``timed_out`` result is returned (criterion 4) instead of raising.
        """
        from datetime import datetime, timezone

        timed_out = False
        try:
            stdout_bytes, stderr_bytes = self.process.communicate(
                input=input_bytes, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group()
            stdout_bytes, stderr_bytes = self.process.communicate()

        returncode = self.process.returncode
        created_at = self._created_at or datetime.now(timezone.utc).isoformat()

        if timed_out:
            return self._build_result(
                exit_code=None,
                signal=None,
                termination="timed_out",
                created_at=created_at,
                stdout_bytes=stdout_bytes or b"",
                stderr_bytes=stderr_bytes or b"",
                message=(
                    f"worker timed out after {timeout}s "
                    f"({' '.join(self.command)})"
                ),
            )

        exit_code, signal = _split_returncode(returncode)
        termination = "signaled" if signal is not None else "exited"
        message = ""
        if termination == "signaled":
            message = (
                f"worker died on signal {signal} without a result "
                f"({' '.join(self.command)})"
            )
        elif exit_code != 0:
            message = (
                f"worker exited with code {exit_code} without success "
                f"({' '.join(self.command)})"
            )

        return self._build_result(
            exit_code=exit_code,
            signal=signal,
            termination=termination,
            created_at=created_at,
            stdout_bytes=stdout_bytes or b"",
            stderr_bytes=stderr_bytes or b"",
            message=message,
        )

    def _build_result(
        self,
        *,
        exit_code: Optional[int],
        signal: Optional[int],
        termination: str,
        created_at: str,
        stdout_bytes: bytes,
        stderr_bytes: bytes,
        message: str,
    ) -> ProcessResult:
        stdout_bytes = stdout_bytes if stdout_bytes is not None else b""
        stderr_bytes = stderr_bytes if stderr_bytes is not None else b""

        stdout_receipt = _make_stream_receipt(
            "stdout",
            stdout_bytes,
            run_id=self._run_id,
            command=self.command,
            subject_repo=self._subject_repo,
            subject_commit=self._subject_commit,
            created_at=created_at,
            exit_code=exit_code,
            signal=signal,
            purpose=f"stdout of run '{self._run_id}'",
        )
        stderr_receipt = _make_stream_receipt(
            "stderr",
            stderr_bytes,
            run_id=self._run_id,
            command=self.command,
            subject_repo=self._subject_repo,
            subject_commit=self._subject_commit,
            created_at=created_at,
            exit_code=exit_code,
            signal=signal,
            purpose=f"stderr of run '{self._run_id}'",
        )

        return ProcessResult(
            command=self.command,
            exit_code=exit_code,
            signal=signal,
            termination=termination,
            pid=self.pid,
            stdout_receipt=stdout_receipt,
            stderr_receipt=stderr_receipt,
            message=message,
            stdout=stdout_bytes,
            stderr=stderr_bytes,
            metadata={
                "run_id": self._run_id,
                "subject_repo": self._subject_repo,
                "subject_commit": self._subject_commit,
                "created_at": created_at,
            },
        )


def start_process(
    command: Sequence[str],
    *,
    run_id: str,
    subject_repo: str,
    subject_commit: str,
    created_at: Optional[str] = None,
    cwd: Optional[str] = None,
) -> RunningProcess:
    """Start ``command`` as a real process and return a live handle.

    The worker runs in its own session (process group) so ``cancel()`` and
    ``wait(timeout=...)`` can kill every descendant it spawned. Use
    ``start_process`` when the caller needs cancel/timeout semantics;
    ``run_command`` is the blocking convenience wrapper over it.
    """
    proc = subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        start_new_session=True,
    )
    return RunningProcess(
        process=proc,
        command=list(command),
        _run_id=run_id,
        _subject_repo=subject_repo,
        _subject_commit=subject_commit,
        _created_at=created_at,
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
    """Run ``command`` to completion and return bound evidence.

    A blocking convenience over ``start_process``. ``timeout``, when set, yields
    a defined ``termination == "timed_out"`` result rather than raising; a
    worker that dies without producing a result is reported as a failure with a
    message, never a silent success.
    """
    handle = start_process(
        command,
        run_id=run_id,
        subject_repo=subject_repo,
        subject_commit=subject_commit,
        created_at=created_at,
        cwd=cwd,
    )
    return handle.wait(timeout=timeout, input_bytes=input_bytes)
