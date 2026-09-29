"""Async run lifecycle: start, inspect, and kill durable background runs.

Reuses the existing ``subprocess`` and process-group patterns from
``runner_adapter`` but writes structured state to
``.skillweave/runs/<run-id>/`` instead of a bare tracking-log.
"""

from __future__ import annotations

import json
import os
import signal as _signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TextIO

from .store import RunMetadata, RunStateStore, StalePidError, RunStateError

# ---------------------------------------------------------------------------
# RunHandle — the versioned, durable handle returned by ``start_async``.
# ---------------------------------------------------------------------------

@dataclass
class RunHandle:
    """Versioned handle for an async run.  Survives launcher exit.

    Attributes
    ----------
    run_id:
        Unique run identifier (uuid hex).
    pid:
        Process ID of the detached child.
    command:
        The command that was started.
    state:
        Current run state (running, succeeded, failed, killed, unknown).
    created_at:
        ISO-8601 timestamp of when the run was started.
    version:
        Monotonically increasing version counter.
    """
    run_id: str
    pid: int
    command: list[str]
    state: str = "running"
    created_at: str = ""
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunHandle":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


# ---------------------------------------------------------------------------
# InspectMode — snapshot or follow
# ---------------------------------------------------------------------------

class InspectMode:
    SNAPSHOT = "snapshot"
    FOLLOW = "follow"


# ---------------------------------------------------------------------------
# Detached wrapper script (similar to observe.py's wrapper but more robust)
# ---------------------------------------------------------------------------

_WRAPPER_SRC = (
    "import subprocess, sys, json, os, signal\n"
    "run_id = sys.argv[1]\n"
    "store_path = sys.argv[2]\n"
    "start_seq = int(sys.argv[3])\n"
    "cmd = sys.argv[4:]\n"
    "from pathlib import Path\n"
    "store_dir = Path(store_path)\n"
    "store_dir.mkdir(parents=True, exist_ok=True)\n"
    "events = store_dir / 'events.jsonl'\n"
    "meta = store_dir / 'run.json'\n"
    "\n"
    "def _write_event(ev):\n"
    "    with open(events, 'a') as f:\n"
    "        f.write(json.dumps(ev, sort_keys=True) + '\\n')\n"
    "        f.flush()\n"
    "\n"
    "seq = start_seq\n"
    "def _next_seq():\n"
    "    global seq\n"
    "    seq += 1\n"
    "    return seq\n"
    "\n"
    "_write_event({'event': 'started', 'sequence': _next_seq(), 'command': list(cmd), 'run_id': run_id})\n"
    "try:\n"
    "    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)\n"
    "    rc = proc.returncode\n"
    "    stdout_text = proc.stdout.decode('utf-8', errors='replace') if proc.stdout else ''\n"
    "    _write_event({'event': 'finished', 'sequence': _next_seq(), 'returncode': rc, 'stdout_preview': stdout_text[:1024]})\n"
    "    # Update run.json state\n"
    "    import json\n"
    "    if meta.exists():\n"
    "        d = json.loads(meta.read_text('utf-8'))\n"
    "        d['state'] = 'succeeded' if rc == 0 else 'failed'\n"
    "        d['exit_code'] = rc\n"
    "        d['finished_at'] = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()\n"
    "        d['version'] = d.get('version', 1) + 1\n"
    "        meta.write_text(json.dumps(d, sort_keys=True) + '\\n', encoding='utf-8')\n"
    "except Exception as exc:\n"
    "    _write_event({'event': 'error', 'sequence': _next_seq(), 'error': str(exc)})\n"
    "    if meta.exists():\n"
    "        d = json.loads(meta.read_text('utf-8'))\n"
    "        d['state'] = 'failed'\n"
    "        d['exit_code'] = -1\n"
    "        d['version'] = d.get('version', 1) + 1\n"
    "        meta.write_text(json.dumps(d, sort_keys=True) + '\\n', encoding='utf-8')\n"
    "    sys.exit(1)\n"
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_async(
    command: list[str],
    *,
    project_root: Optional[Path] = None,
    run_id: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> RunHandle:
    """Start *command* as a detached background process.

    The child runs in its own session (process group) so it survives the
    launcher's exit.  A structured RunHandle is returned immediately; the
    handle is also persisted under ``.skillweave/runs/<run-id>/run.json``.

    Parameters
    ----------
    command:
        The command and arguments to execute.
    project_root:
        Project root (default: CWD).  State is written relative to this.
    run_id:
        Explicit run ID (default: auto-generated uuid hex).
    cwd:
        Working directory for the child (default: project_root).

    Returns
    -------
    RunHandle
        The versioned handle for the newly started run.
    """
    root = Path(project_root or Path.cwd()).resolve()
    rid = run_id or uuid.uuid4().hex
    child_cwd = str(cwd or root)

    store = RunStateStore(root)
    store_dir = store.run_dir(rid)

    # Launch detached wrapper; pass start_seq=1 so the wrapper's first event
    # gets sequence 2 (after the host's "launched" event at seq=1).
    proc = subprocess.Popen(
        [sys.executable, "-c", _WRAPPER_SRC, rid, str(store_dir), "1", *list(command)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        cwd=child_cwd,
    )

    meta = RunMetadata.create(
        run_id=rid,
        command=list(command),
        pid=proc.pid,
    )
    store.write_metadata(meta)

    # Write the launch event
    store.append_event(rid, {
        "event": "launched",
        "sequence": 1,
        "run_id": rid,
        "pid": proc.pid,
        "command": list(command),
    })

    return RunHandle(
        run_id=rid,
        pid=proc.pid,
        command=list(command),
        state="running",
        created_at=meta.created_at,
        version=meta.version,
    )


def inspect_run(
    run_id: str,
    *,
    project_root: Optional[Path] = None,
    mode: str = InspectMode.SNAPSHOT,
    poll_interval: float = 0.25,
    timeout: Optional[float] = None,
    out: Optional[TextIO] = None,
) -> int:
    """Inspect a run's state and events.

    Parameters
    ----------
    run_id:
        The run ID to inspect.
    project_root:
        Project root (default: CWD).
    mode:
        ``"snapshot"`` dumps current state and exits.  ``"follow"`` tails
        events until the run finishes or *timeout* expires.
    poll_interval:
        Seconds between poll cycles in follow mode.
    timeout:
        Maximum seconds to wait in follow mode.
    out:
        Output stream (default: sys.stdout).

    Returns
    -------
    0 on success, 1 if the run is not found.
    """
    if out is None:
        out = sys.stdout

    store = RunStateStore(project_root)
    meta = store.read_metadata(run_id)
    if meta is None:
        out.write(json.dumps({"error": f"run not found: {run_id}"}) + "\n")
        return 1

    # Snapshot: emit current state
    snapshot = {
        "run_id": meta.run_id,
        "pid": meta.pid,
        "command": meta.command,
        "state": meta.state,
        "exit_code": meta.exit_code,
        "created_at": meta.created_at,
        "finished_at": meta.finished_at,
        "version": meta.version,
    }

    events = store.read_events(run_id)
    lane_states: dict[str, Any] = {}
    for ev in events:
        lane_id = ev.get("lane_id") or ev.get("run_id", run_id)
        if ev.get("event") in ("finished", "error"):
            lane_states[lane_id] = "terminal"
        elif ev.get("event") == "started":
            lane_states[lane_id] = "running"

    snapshot["lane_states"] = lane_states
    snapshot["event_count"] = len(events)

    if mode == InspectMode.SNAPSHOT:
        out.write(json.dumps(snapshot, sort_keys=True) + "\n")
        return 0

    # Follow mode: stream events until terminal
    last_seq = 0
    start_time = time.monotonic()

    # Dump snapshot first
    out.write(json.dumps(snapshot, sort_keys=True) + "\n")
    out.flush()

    while True:
        new_events = store.read_events(run_id, after=last_seq)
        for ev in new_events:
            out.write(json.dumps(ev, sort_keys=True) + "\n")
            out.flush()
            seq = ev.get("sequence", 0)
            if seq > last_seq:
                last_seq = seq
            if ev.get("event") in ("finished", "error"):
                return 0

        if timeout is not None and (time.monotonic() - start_time) >= timeout:
            out.write(json.dumps({"event": "timeout", "run_id": run_id}) + "\n")
            return 1

        # Re-read metadata to detect terminal state written by the wrapper
        current_meta = store.read_metadata(run_id)
        if current_meta and current_meta.state != "running":
            # Drain remaining events
            remaining = store.read_events(run_id, after=last_seq)
            for ev in remaining:
                out.write(json.dumps(ev, sort_keys=True) + "\n")
                out.flush()
            return 0

        time.sleep(poll_interval)


def kill_run(
    run_id: str,
    pid: int,
    *,
    project_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Kill a run by its ID and recorded PID.

    Graceful (SIGTERM) first, then forced (SIGKILL) after a short grace
    period.  Verifies the *pid* matches the recorded PID to prevent killing
    a stale/reused process.

    Parameters
    ----------
    run_id:
        The run ID to kill.
    pid:
        The PID the caller believes is the target.  Must match the recorded
        PID.
    project_root:
        Project root (default: CWD).

    Returns
    -------
    dict with ``run_id``, ``pid``, ``state``, ``result``.

    Raises
    ------
    StalePidError
        When *pid* does not match the recorded PID.
    RunStateError
        When the run is not found or already terminal.
    """
    store = RunStateStore(project_root)

    # Verify the PID matches the recorded one
    store.verify_pid(run_id, pid)

    meta = store.read_metadata(run_id)
    if meta is None:
        raise RunStateError(f"no run found: {run_id}")

    if meta.state != "running":
        return {
            "run_id": run_id,
            "pid": pid,
            "state": meta.state,
            "result": "already_terminal",
        }

    # Graceful kill (SIGTERM) to the process group
    killed_graceful = False
    try:
        os.killpg(pid, _signal.SIGTERM)
        killed_graceful = True
        # Give it a short grace period
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
                time.sleep(0.05)
            except ProcessLookupError:
                break
    except (ProcessLookupError, PermissionError):
        pass

    # Force kill (SIGKILL) to the process group.
    # Note: macOS os.kill(pid, 0) can raise PermissionError for zombies or
    # cross-session processes, so we skip the existence check and attempt
    # SIGKILL directly.
    try:
        os.killpg(pid, _signal.SIGKILL)
        result = "forced_kill"
    except ProcessLookupError:
        result = "graceful_kill" if killed_graceful else "already_dead"
    except PermissionError:
        # macOS: os.killpg may also fail with EPERM for zombies.  Fall back
        # to killing just the tracked PID.
        try:
            os.kill(pid, _signal.SIGKILL)
            result = "forced_kill"
        except (ProcessLookupError, PermissionError):
            result = "graceful_kill" if killed_graceful else "already_dead"

    store.update_metadata(run_id, state="killed", finished_at=_now())

    store.append_event(run_id, {
        "event": "killed",
        "sequence": store.latest_event_sequence(run_id) + 1,
        "run_id": run_id,
        "pid": pid,
        "result": result,
    })

    return {
        "run_id": run_id,
        "pid": pid,
        "state": "killed",
        "result": result,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
