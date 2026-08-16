"""
SW-135-011: A worker starts as a real process; its output is bound as evidence.

Covers the three dispatch criteria:

1. A worker runs as a real process, proven with a trivial command (its PID
   differs from the test process and its output is actually captured).
2. stdout and stderr are collected and bound to the run as `ArtifactReceipt`
   evidence (typed `runtime_trace`), not as free text.
6. Exit code and termination signal are distinguished and both recorded
   (`exit_code is None` iff the process was signaled; `signal is None` on a
   clean exit).

Self-contained sys.path handling, independent of conftest/pytest.
"""

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.runner_adapter import (
    ProcessResult,
    run_command,
    _split_returncode,  # noqa: F401  (provided for direct spec coverage)
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


def test_trivial_command_runs_as_a_real_process():
    result = _run(sys.executable, "-c", "import os; print(os.getpid())")
    assert isinstance(result, ProcessResult)
    # Distinct PID proves a child process was actually spawned.
    assert result.pid != __import__("os").getpid()
    child_pid = int(result.stdout.decode().strip())
    assert child_pid == result.pid


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


def test_clean_exit_records_exit_code_and_no_signal():
    result = _run(sys.executable, "-c", "pass")
    assert result.exit_code == 0
    assert result.signal is None
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
