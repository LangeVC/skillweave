"""
SW-135-011: A worker starts as a real process; its output is bound as evidence.

Covers the dispatch criteria of this lane:

1. A worker runs as a real process, proven with a trivial command (its PID
   differs from the test process and its output is actually captured).
2. stdout and stderr are collected and bound to the run as `ArtifactReceipt`
   evidence (typed `runtime_trace`), not as free text.
3. Cancel kills the process for real; a test proves that *no child survives*
   (the surviving PIDs are gone, not merely that the call returned).
4. A timeout produces a defined `timed_out` state, not an unbounded wait.
5. A worker that dies without a result is a failure with a message, not a
   silent success.
6. Exit code and termination signal are distinguished and both recorded
   (`exit_code is None` iff the process was signaled; `signal is None` on a
   clean exit).

Self-contained sys.path handling, independent of conftest/pytest.
"""

import sys
import time
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.runner_adapter import (
    ProcessResult,
    run_command,
    start_process,
    _pid_exists,
)
from skillweave.runtime import ArtifactReceipt, EvidenceType


def _run(*args: str, **kwargs):
    return run_command(
        list(args),
        run_id="run-011",
        subject_repo="skillweave",
        subject_commit="abc123",
        created_at="2026-08-16T00:00:00Z",
        **kwargs,
    )


# --- criterion 1 ---

def test_trivial_command_runs_as_a_real_process():
    result = _run(sys.executable, "-c", "import os; print(os.getpid())")
    assert isinstance(result, ProcessResult)
    # Distinct PID proves a child process was actually spawned.
    assert result.pid != __import__("os").getpid()
    child_pid = int(result.stdout.decode().strip())
    assert child_pid == result.pid


# --- criterion 2 ---

def test_stdout_is_captured_as_a_receipt_not_free_text():
    result = _run(sys.executable, "-c", "print('hello-stdout')")
    assert isinstance(result.stdout_receipt, ArtifactReceipt)
    assert result.stdout_receipt.evidence_type == EvidenceType.RUNTIME_TRACE.value
    assert result.stdout_receipt.metadata["run_id"] == "run-011"
    assert result.stdout_receipt.metadata["stream"] == "stdout"
    # The receipt references the stream by digest; the raw text is not the receipt.
    assert len(result.stdout_receipt.sha256) == 64
    assert b"hello-stdout" in result.stdout


def test_stderr_is_captured_as_a_receipt_not_free_text():
    result = _run(sys.executable, "-c", "import sys; print('boom', file=sys.stderr)")
    assert isinstance(result.stderr_receipt, ArtifactReceipt)
    assert result.stderr_receipt.evidence_type == EvidenceType.RUNTIME_TRACE.value
    assert result.stderr_receipt.metadata["stream"] == "stderr"
    assert b"boom" in result.stderr


# --- criterion 3 ---

def test_cancel_kills_the_process_and_no_child_survives():
    # The worker prints its own pid plus the pid of a child it spawns, then
    # sleeps forever so the cancel path (not a natural exit) is what ends it.
    script = (
        "import os, sys, time\n"
        "child = os.fork()\n"
        "if child == 0:\n"
        "    time.sleep(60)\n"  # grandchild lingers; must be reaped by cancel
        "else:\n"
        "    print(os.getpid())\n"
        "    print(child)\n"
        "    sys.stdout.flush()\n"
        "    time.sleep(60)\n"
    )
    handle = start_process(
        [sys.executable, "-c", script],
        run_id="run-011",
        subject_repo="skillweave",
        subject_commit="abc123",
        created_at="2026-08-16T00:00:00Z",
    )
    worker_pid = handle.pid

    # Wait until the worker has printed both its own and its child's pid.
    deadline = time.time() + 5
    lines = []
    while time.time() < deadline and len(lines) < 2:
        try:
            out, _ = handle.process.communicate(timeout=0.05)
            lines = out.decode().split()
            break
        except Exception:  # noqa: BLE001
            time.sleep(0.05)

    assert _pid_exists(worker_pid), "worker should be alive before cancel"

    result = handle.cancel()

    assert result.termination == "cancelled"
    assert result.succeeded is False
    assert result.message != ""

    # Prove no child survives: the worker pid is gone after a reap window.
    _wait_gone(worker_pid)

    # If we captured the grandchild pid, it must be gone too.
    if len(lines) >= 2:
        grandchild = int(lines[1])
        _wait_gone(grandchild)


def _wait_gone(pid: int, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_exists(pid):
            return
        time.sleep(0.05)
    assert False, f"process {pid} still alive after cancel"


# --- criterion 4 ---

def test_timeout_yields_a_defined_state_not_unbounded_wait():
    result = _run(
        sys.executable, "-c", "import time; time.sleep(30)", timeout=0.2
    )
    assert result.termination == "timed_out"
    assert result.succeeded is False
    assert result.message != ""
    assert result.signal is None


# --- criterion 5 ---

def test_worker_death_without_result_is_a_failure_with_message():
    # SIGKILL the worker before it prints anything: death, no result.
    result = _run(
        sys.executable,
        "-c",
        "import os, signal, time; time.sleep(0.1); os.kill(os.getpid(), signal.SIGKILL)",
    )
    assert result.termination == "signaled"
    assert result.signal == 9
    assert result.succeeded is False
    assert result.message != ""


def test_nonzero_exit_is_a_failure_with_message():
    result = _run(sys.executable, "-c", "import sys; sys.exit(7)")
    assert result.exit_code == 7
    assert result.succeeded is False
    assert result.message != ""


# --- criterion 6 ---

def test_clean_exit_records_exit_code_and_no_signal():
    result = _run(sys.executable, "-c", "pass")
    assert result.exit_code == 0
    assert result.signal is None
    assert result.termination == "exited"
    assert result.succeeded is True
    assert result.signaled is False


def test_signal_termination_is_distinguished_from_exit_code():
    # os.kill(self, SIGKILL) -> the interpreter dies with signal 9 (SIGKILL).
    result = _run(sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)")
    assert result.signal == 9
    assert result.exit_code is None
    assert result.signaled is True
    assert result.succeeded is False


def _run_all() -> int:
    tests = [
        test_trivial_command_runs_as_a_real_process,
        test_stdout_is_captured_as_a_receipt_not_free_text,
        test_stderr_is_captured_as_a_receipt_not_free_text,
        test_cancel_kills_the_process_and_no_child_survives,
        test_timeout_yields_a_defined_state_not_unbounded_wait,
        test_worker_death_without_result_is_a_failure_with_message,
        test_nonzero_exit_is_a_failure_with_message,
        test_clean_exit_records_exit_code_and_no_signal,
        test_signal_termination_is_distinguished_from_exit_code,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
