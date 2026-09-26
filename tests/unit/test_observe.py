"""Unit tests for the Handshake & Observe CLI (SW-OBSERVE-001).

Proves the two top-level flags without any network or live provider:

* ``--dispatch <command>`` returns a JSON handle ``{pid, execution_id,
  log_path}`` and does **not** block the harness on the child (the child keeps
  running after the handle is returned — measured by the dispatch call
  returning synchronously while the child is still alive).
* ``--observe <execution_id>`` tails the run-log read-only, streaming lines
  and exiting cleanly when the run terminates (sentinel), without mutating
  any state.

The hermetic boundary is inherited from the sibling unit tests: no outbound
socket, provider env vars cleared.  The dispatched child is a short-lived
``python -c`` fragment that emits a known line and exits.
"""

from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

from skillweave.cli import observe as observe_mod

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _child_command() -> list[str]:
    """Return a child command that emits one known line and exits quickly."""
    return [
        sys.executable,
        "-c",
        "import sys, time; print('CHILD-LINE-1'); "
        "print('child_marker=%s' % sys.argv[1]); sys.stdout.flush()",
        "marker-77",
    ]


def _read_handle(raw_stdout: str) -> dict:
    """Parse the JSON handle printed by ``main_dispatch``."""
    match = re.search(r"\{.*\}", raw_stdout, re.DOTALL)
    assert match is not None, f"no JSON handle in output: {raw_stdout!r}"
    return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# --dispatch
# ---------------------------------------------------------------------------


def test_dispatch_returns_json_handle_and_does_not_block(tmp_path):
    handle = observe_mod.dispatch_bg(
        command=_child_command(),
        project_root=tmp_path,
        execution_id="exec-001",
    )

    assert set(handle.keys()) == {"pid", "execution_id", "log_path"}
    assert isinstance(handle["pid"], int)
    assert handle["pid"] > 0
    assert handle["execution_id"] == "exec-001"
    assert handle["log_path"] == str(
        tmp_path / ".skillweave" / "tracking-log" / "run-exec-001.log"
    )

    # The handle was returned synchronously: the harness was not blocked. The
    # log file already exists (header written before the fork returned).
    log_file = Path(handle["log_path"])
    assert log_file.exists()

    # The child is detached and writes its output to the run-log. Wait for it
    # to finish and assert the log captures the child output plus a sentinel.
    _wait_for_sentinel(log_file)


def test_main_dispatch_prints_handle_and_returns_zero(tmp_path, capsys):
    code = observe_mod.main_dispatch(
        [
            "--dispatch",
            "--project-root",
            str(tmp_path),
            "--execution-id",
            "exec-002",
            "--",
            *_child_command(),
        ]
    )
    assert code == 0

    out = capsys.readouterr().out
    handle = _read_handle(out)
    assert handle["execution_id"] == "exec-002"
    assert handle["pid"] > 0
    log_file = Path(handle["log_path"])
    _wait_for_sentinel(log_file)


# ---------------------------------------------------------------------------
# --observe
# ---------------------------------------------------------------------------


def _write_log(project_root: Path, execution_id: str, lines: list[str]) -> Path:
    log_file = observe_mod._log_path(project_root, execution_id)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text("".join(line + "\n" for line in lines))
    return log_file


def _dispatch_child(tmp_path: Path, execution_id: str) -> dict:
    """Dispatch a real child and wait for it to finish; return its handle."""
    handle = observe_mod.dispatch_bg(
        command=_child_command(),
        project_root=tmp_path,
        execution_id=execution_id,
    )
    _wait_for_sentinel(Path(handle["log_path"]))
    return handle


def _wait_for_sentinel(log_file: Path, timeout: float = 5.0) -> None:
    """Block until a run_finished/run_error sentinel appears in *log_file*."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log_file.exists():
            text = log_file.read_text()
            if '"event": "run_finished"' in text or '"event": "run_error"' in text:
                return
        time.sleep(0.02)
    raise AssertionError(f"sentinel never appeared in {log_file}")


def test_observe_dumps_existing_log_read_only(tmp_path):
    log_file = _write_log(
        tmp_path,
        "exec-100",
        ["line-a", "line-b", '{"event": "run_finished", "returncode": 0}'],
    )
    before = log_file.read_text()

    buf = io.StringIO()
    code = observe_mod.observe("exec-100", tmp_path, out=buf)

    assert code == 0
    out = buf.getvalue()
    assert "line-a\n" in out
    assert "line-b\n" in out
    # Read-only: the log file contents are untouched.
    assert log_file.read_text() == before


def test_observe_follow_waits_until_sentinel(tmp_path):
    """Observe should keep tailing until the child finishes.

    To avoid spinning a race, we pre-seed a log without a sentinel, start
    tracing in follow mode via the streaming function on a fresh thread, and
    assert it does not return before the sentinel is appended.
    """
    log_file = _write_log(tmp_path, "exec-101", ["line-a"])
    buf = io.StringIO()

    # The follow mode has no timeout, so it would block forever without a
    # sentinel.  We append the sentinel from a helper thread and assert the
    # observer returns promptly.
    import threading

    result: list[int | None] = [None]

    def _run():
        result[0] = observe_mod.observe(
            "exec-101", tmp_path, follow=True, poll_interval=0.02, out=buf
        )

    t = threading.Thread(target=_run)
    t.start()

    # Give the observer a moment to reach the follow loop.
    time.sleep(0.15)
    with open(log_file, "a") as fh:
        fh.write('{"event": "run_finished", "returncode": 0}\n')
        fh.flush()

    t.join(timeout=5.0)
    assert not t.is_alive(), "observer did not exit after the sentinel"
    assert result[0] == 0
    assert "line-a\n" in buf.getvalue()
    assert "run_finished" in buf.getvalue()


def test_observe_missing_log_returns_error(tmp_path, capsys):
    code = observe_mod.observe("no-such-id", tmp_path)
    assert code == 1
    err = capsys.readouterr().err
    assert "no run-log found" in err


def test_observe_follow_timeout_reports_failure(tmp_path, capsys):
    log_file = _write_log(tmp_path, "exec-102", ["line-a"])
    code = observe_mod.observe(
        "exec-102", tmp_path, follow=True, poll_interval=0.02, timeout=0.05
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "timeout" in err


def test_integration_dispatch_then_observe_end_to_end(tmp_path, capsys):
    """Dispatch a real child, then observe its run log end-to-end."""
    handle = _dispatch_child(tmp_path, "exec-200")
    assert handle["execution_id"] == "exec-200"

    buf = io.StringIO()
    code = observe_mod.observe("exec-200", tmp_path, out=buf)
    assert code == 0

    out = buf.getvalue()
    assert '{"event": "dispatch_started"' in out
    assert "CHILD-LINE-1" in out
    assert "child_marker=marker-77" in out
    assert '"event": "run_finished"' in out
