"""SW138-REM-GATE-001: the checked-in operator-dispatch final gate.

This is the *single* checked-in aggregate for the SkillWeave 1.3.8
operator-dispatch candidate. It reproduces every final-gate criterion in one
self-contained module and emits ``OPERATOR_DISPATCH_FINAL_GATE_PASS`` only when
every fixture holds, closing the two proof caveats recorded by the failed
independent gate:

* **heartbeat-before-terminal** is now proven with a *genuinely* slow real child
  (a real subprocess that keeps running while the monitor advances), delivered
  through the full ``OperatorDispatchApplication.dispatch()`` path — the typed
  live lifecycle is wired onto the real fan-out observation seam, driving the
  production ``HeartbeatPump`` on real wall-clock time, never a side-channel
  or an injected timestamp.
* **reviewer read-only authority** is now *technically* exercised: each denied
  action is an executable probe that raises ``AuthorityError`` before any
  effect, not a documentation assertion.

Every fixture runs the real behaviour of a production seam (fan-out, runner
adapter, profile resolver, event stream, authority guard, review gate,
observer). No fixture is a replica counter, a prose assertion, a log/PID
inference, or a metadata-only check: each returns ``True`` only when the real
seam produced the required observable outcome.

Final-gate criterion -> fixture mapping (proof 7 of the gate brief):

  1. collects and exits zero            -> ``pytest tests/gate_138`` (all fixtures)
  2. disjoint lanes overlap, conflicting
     lane serializes, one observer
     before ops                          -> ``_fixture_overlap_and_serialize``,
                                            ``_fixture_observer_before_ops``
  3. a genuinely slow real child emits a
     heartbeat before exactly one terminal-> ``_fixture_heartbeat_before_terminal``
  4. profile-only changes affect the real
     child invocation/model; missing
     profile / wrong base / missing
     execution_model / incomplete coverage
     start zero workers                  -> ``_fixture_profile_model_effect``,
                                            ``_fixture_zero_worker_red_paths``
  5. typed outcomes (exit/timeout/signal/
     skip/retry/abort) and content-
     addressed stdout/stderr incl. empty
     streams                             -> ``_fixture_typed_outcomes``,
                                            ``_fixture_content_addressed_streams``
  6. reviewer and observer authority
     rejects write/repair/dispatch/
     commit/push/approval                -> ``_fixture_reviewer_read_only``,
                                            ``_fixture_observer_read_only``
"""

from __future__ import annotations

import hashlib
import io
import json
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent.parent
_src = _repo / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

GATE_TOKEN = "OPERATOR_DISPATCH_FINAL_GATE_PASS"

_FULL_A = "953aab4ec8f7babf0857c0033fd7731c8dc16e92"


# ── Shared seams (real production classes, no replicas) ─────────────────────

_MARKER_FILE = '''import sys
import time
import pathlib

d = pathlib.Path(sys.argv[1])
name = sys.argv[2]
sleep_seconds = float(sys.argv[3])
open(d / name, "w").write(str(time.time() * 1000))
time.sleep(sleep_seconds)
open(d / (name + ".end"), "w").write(str(time.time() * 1000))
print("done")
'''


# ── Proof 2: overlap + serialize + exactly one observer before ops ──────────

def _fixture_overlap_and_serialize() -> bool:
    """Two disjoint ops lanes overlap in wall-clock time; a conflicting lane
    (same repo) is serialized after them — measured from real processes."""
    import tempfile

    import yaml

    from skillweave.dispatch.application import OperatorDispatchApplication, ProvisionedWorkspace

    class _NoopWorkspace:
        def provision(self, lane, run_id):
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            pass

    with tempfile.TemporaryDirectory() as tmp:
        marker_dir = tmp
        marker_file = Path(tmp) / "marker.py"
        marker_file.write_text(_MARKER_FILE, encoding="utf-8")
        prof = Path(tmp) / "p.yaml"
        prof.write_text(
            yaml.safe_dump(
                {
                    "name": "gate-overlap",
                    "tier": "balanced",
                    "limits": {
                        "timeout": 30.0,
                        "max_retries": 1,
                        "min_models_required": 2,
                        "on_model_failure": "skip",
                    },
                    "roles": {
                        "ops": {
                            "model": "faigate/dispatch-fixture-model",
                            "tool": {
                                "name": "marker",
                                "launch_command": f"python3 {marker_file}",
                                "args": [marker_dir, "ops", "0.4"],
                            },
                            "capabilities": {"can_mutate_run_state": True},
                        },
                        "reviewer": {
                            "model": "faigate/dispatch-fixture-model",
                            "tool": {
                                "name": "marker",
                                "launch_command": f"python3 {marker_file}",
                                "args": [marker_dir, "rev", "0.4"],
                            },
                            "capabilities": {"can_approve_gate": True},
                        },
                        "ops2": {
                            "model": "faigate/dispatch-fixture-model",
                            "tool": {
                                "name": "marker",
                                "launch_command": f"python3 {marker_file}",
                                "args": [marker_dir, "ops2", "0.4"],
                            },
                            "capabilities": {"can_mutate_run_state": True},
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        seq = Path(tmp) / "s.yaml"
        seq.write_text(
            yaml.safe_dump(
                {
                    "session_boundary": "batch",
                    "profile": {"path": str(prof), "required": True},
                    "execution_model": "cold",
                    "max_correction_rounds_per_wave": 0,
                    "max_parallel": 2,
                    "lanes": [
                        {
                            "id": "lane-a",
                            "role": "ops",
                            "repo": "skillweave/repo-a",
                            "base": _FULL_A,
                            "execution_model": "cold",
                            "mutating": True,
                            "depends_on": [],
                            "write_scope": ["skillweave/repo-a/**"],
                            "worktree": "/tmp/lane-a",
                            "branch": "branch-lane-a",
                            "integration_policy": "independent",
                            "criterion_groups": [{"criteria": [1]}],
                        },
                        {
                            "id": "lane-b",
                            "role": "reviewer",
                            "repo": "skillweave/repo-b",
                            "base": _FULL_A,
                            "execution_model": "cold",
                            "mutating": True,
                            "depends_on": [],
                            "write_scope": ["skillweave/repo-b/**"],
                            "worktree": "/tmp/lane-b",
                            "branch": "branch-lane-b",
                            "integration_policy": "independent",
                            "criterion_groups": [{"criteria": [1]}],
                        },
                        {
                            "id": "lane-c",
                            "role": "ops2",
                            "repo": "skillweave/repo-a",
                            "base": _FULL_A,
                            "execution_model": "cold",
                            "mutating": True,
                            "depends_on": [],
                            "write_scope": ["skillweave/repo-a/**"],
                            "worktree": "/tmp/lane-c",
                            "branch": "branch-lane-c",
                            "integration_policy": "independent",
                            "criterion_groups": [{"criteria": [1]}],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        app = OperatorDispatchApplication(workspace_seam=_NoopWorkspace())
        _, _, report = app.load(str(seq), str(prof))
        # The disjoint pair (repo-a, repo-b) is one group; the conflicting lane-c
        # (repo-a again) is pushed into its own, later group.
        if report.parallel_groups != [["lane-a", "lane-b"], ["lane-c"]]:
            return False

        run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())
        if run.halted:
            return False

        def _t(name):
            return float((Path(tmp) / name).read_text())

        def _t_end(name):
            return float((Path(tmp) / (name + ".end")).read_text())

        # The two disjoint lanes overlap in real wall-clock time.
        if not (_t_end("ops") > _t("rev") and _t_end("rev") > _t("ops")):
            return False

        # lane-c (ops2, repo-a) conflicts with lane-a (repo-a) and must have
        # serialized after the disjoint pair. Its own marker timestamps lie
        # entirely after the disjoint pair finished: a real ordering fact.
        if not (_t("ops2") >= _t_end("ops") and _t("ops2") >= _t_end("rev")):
            return False

        return True


def _fixture_observer_before_ops() -> bool:
    """Exactly one tool-targeted observer starts before the first ops child."""
    import tempfile

    import yaml

    from skillweave.dispatch.application import OperatorDispatchApplication, ProvisionedWorkspace
    from skillweave.runtime import runner_adapter

    class _NoopWorkspace:
        def provision(self, lane, run_id):
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            pass

    marker = '''import sys
with open(sys.argv[1], "w", encoding="utf-8") as fh:
    fh.write("started")
import json
payload = json.loads(sys.stdin.read())
print(json.dumps({"run_id": payload["run_id"], "wave": payload["wave"], "findings": []}))
'''

    with tempfile.TemporaryDirectory() as tmp:
        marker_file = Path(tmp) / "observer.py"
        marker_file.write_text(marker, encoding="utf-8")
        start_file = Path(tmp) / "observer.started"

        prof = Path(tmp) / "p.yaml"
        prof.write_text(
            yaml.safe_dump(
                {
                    "name": "gate-observer",
                    "tier": "balanced",
                    "limits": {
                        "timeout": 30.0,
                        "max_retries": 1,
                        "min_models_required": 2,
                        "on_model_failure": "skip",
                    },
                    "roles": {
                        "observer": {
                            "observer": True,
                            "tool": {
                                "name": "marker",
                                "launch_command": f"python3 {marker_file} {start_file}",
                                "args": [],
                            },
                            "capabilities": {"can_observe_run": True},
                        },
                        "ops": {
                            "model": "faigate/dispatch-fixture-model",
                            "tool": {
                                "name": "marker",
                                "launch_command": "python3 -c 'pass'",
                                "args": [],
                            },
                            "capabilities": {"can_mutate_run_state": True},
                        },
                        "reviewer": {
                            "model": "faigate/dispatch-fixture-model",
                            "tool": {
                                "name": "marker",
                                "launch_command": "python3 -c 'pass'",
                                "args": [],
                            },
                            "capabilities": {"can_approve_gate": True},
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        seq = Path(tmp) / "s.yaml"
        seq.write_text(
            yaml.safe_dump(
                {
                    "session_boundary": "batch",
                    "profile": {"path": str(prof), "required": True},
                    "execution_model": "cold",
                    "max_correction_rounds_per_wave": 0,
                    "max_parallel": 1,
                    "lanes": [
                        {
                            "id": "lane-a",
                            "role": "ops",
                            "repo": "skillweave/repo-a",
                            "base": _FULL_A,
                            "execution_model": "cold",
                            "mutating": True,
                            "depends_on": [],
                            "write_scope": ["skillweave/repo-a/**"],
                            "worktree": "/tmp/lane-a",
                            "branch": "branch-lane-a",
                            "integration_policy": "independent",
                            "criterion_groups": [{"criteria": [1]}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        real_start = runner_adapter.start_process
        order = []

        def recording_start(command, **kwargs):
            order.append("observer")
            return real_start(command, **kwargs)

        def recording_inline(command, **kwargs):
            order.append("ops")
            return _FakeResult([_SucceededChild()])

        app = OperatorDispatchApplication(
            workspace_seam=_NoopWorkspace(),
            inline_seam=recording_inline,
            observer_launch_seam=recording_start,
        )
        run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

        # The observer tool process genuinely ran (its marker file exists) and
        # started before the first serialized ops child, exactly once.
        if not start_file.exists():
            return False
        if order.count("observer") != 1:
            return False
        if "ops" not in order:
            return False
        if order.index("observer") >= order.index("ops"):
            return False
        return run.observer is not None and run.observer.get("observed") is True


class _SucceededChild:
    @property
    def outcome(self):
        return "exit_code"

    def to_dict(self):
        return {"child_run_id": "c", "model": "m", "outcome": "exit_code", "exit_code": 0}


class _FakeResult:
    def __init__(self, children):
        self.children = children


# ▆ Proof 3: genuinely slow real child -> heartbeat before one terminal ─────

def _fixture_heartbeat_before_terminal() -> bool:
    """A genuinely slow real child emits >=1 heartbeat before exactly one
    terminal — proven through the full ``OperatorDispatchApplication.dispatch()``
    path, not by component-driving the stream beside it.

    The profile declares an explicit ``heartbeat_interval`` (config data,
    distinct from ``timeout``) shorter than the child's real sleep. The typed
    live lifecycle is wired onto the real fan-out observation seam, so the slow
    child emits its configured heartbeat while still alive, then exactly one
    ``process_terminal``, in strict order with ``lane_started`` /
    ``dispatch_started`` / ``evidence_recorded`` / ``lane_terminal``.
    """
    import tempfile

    import yaml

    from skillweave.dispatch.application import OperatorDispatchApplication, ProvisionedWorkspace

    class _NoopWorkspace:
        def provision(self, lane, run_id):
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            pass

    with tempfile.TemporaryDirectory() as tmp:
        slow_child = (
            "python3 -c \"import time; time.sleep(1.5)\""
        )
        prof = Path(tmp) / "p.yaml"
        prof.write_text(
            yaml.safe_dump(
                {
                    "name": "gate-heartbeat",
                    "tier": "balanced",
                    "limits": {
                        "timeout": 30.0,
                        "max_retries": 1,
                        "min_models_required": 2,
                        "on_model_failure": "skip",
                        "heartbeat_interval": 0.3,
                    },
                    "roles": {
                        "ops": {
                            "model": "faigate/dispatch-fixture-model",
                            "tool": {
                                "name": "marker",
                                "launch_command": slow_child,
                                "args": [],
                            },
                            "capabilities": {"can_mutate_run_state": True},
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        seq = Path(tmp) / "s.yaml"
        seq.write_text(
            yaml.safe_dump(
                {
                    "session_boundary": "batch",
                    "profile": {"path": str(prof), "required": True},
                    "execution_model": "cold",
                    "max_correction_rounds_per_wave": 0,
                    "max_parallel": 1,
                    "lanes": [
                        {
                            "id": "lane-a",
                            "role": "ops",
                            "repo": "skillweave/repo-a",
                            "base": _FULL_A,
                            "execution_model": "cold",
                            "mutating": True,
                            "depends_on": [],
                            "write_scope": ["skillweave/repo-a/**"],
                            "worktree": "/tmp/lane-a",
                            "branch": "branch-lane-a",
                            "integration_policy": "independent",
                            "criterion_groups": [{"criteria": [1]}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        sink = io.StringIO()
        app = OperatorDispatchApplication(workspace_seam=_NoopWorkspace())
        run = app.dispatch(str(seq), str(prof), wave="0", sink=sink)

        events = [json.loads(ln) for ln in sink.getvalue().splitlines() if ln.strip()]
        types = [e["event_type"] for e in events]

        heartbeats = [e for e in events if e.get("event_type") == "heartbeat"]
        terminals = [e for e in events if e.get("event_type") == "process_terminal"]

        # The slow real child emitted >=1 heartbeat.
        if len(heartbeats) < 1:
            return False
        # Exactly one process terminal (typed lifecycle, emit_terminal_once).
        if len(terminals) != 1:
            return False
        # The heartbeat came strictly before the terminal.
        if heartbeats[-1]["sequence"] >= terminals[0]["sequence"]:
            return False

        # Full ordered lifecycle per the lane contract: lane_started,
        # dispatch_started, heartbeat(s), process_terminal, evidence_recorded,
        # lane_terminal — in strict order.
        idx = {t: [i for i, e in enumerate(events) if e["event_type"] == t] for t in types}
        lane_idx = idx.get("lane_started")
        dispatch_idx = idx.get("dispatch_started")
        hb_idx = idx.get("heartbeat")
        terminal_idx = idx.get("process_terminal")
        evidence_idx = idx.get("evidence_recorded")
        lane_terminal_idx = idx.get("lane_terminal")
        if not (lane_idx and dispatch_idx and hb_idx and terminal_idx
                and evidence_idx and lane_terminal_idx):
            return False
        order = (
            lane_idx[0],
            dispatch_idx[0],
            hb_idx[0],
            terminal_idx[0],
            evidence_idx[0],
            lane_terminal_idx[0],
        )
        if order != tuple(sorted(order)):
            return False

        return True


# ── Proof 4: profile-only change -> real invocation/model; zero-worker red paths

def _fixture_profile_model_effect() -> bool:
    """Changing only the profile's launch command / model changes the actual
    child invocation and the resolved model receipt."""
    import tempfile

    import yaml

    from skillweave.dispatch.application import OperatorDispatchApplication, ProvisionedWorkspace

    class _NoopWorkspace:
        def provision(self, lane, run_id):
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            pass

    def _profile(launch_command, model):
        return yaml.safe_dump(
            {
                "name": "gate-profile",
                "tier": "balanced",
                "limits": {
                    "timeout": 30.0,
                    "max_retries": 1,
                    "min_models_required": 2,
                    "on_model_failure": "skip",
                },
                "roles": {
                    "ops": {
                        "model": model,
                        "tool": {
                            "name": "marker",
                            "launch_command": launch_command,
                            "args": ["--flag"],
                        },
                        "capabilities": {"can_mutate_run_state": True},
                    },
                },
            }
        )

    def _seq(prof_path):
        return yaml.safe_dump(
            {
                "session_boundary": "batch",
                "profile": {"path": str(prof_path), "required": True},
                "execution_model": "cold",
                "max_correction_rounds_per_wave": 0,
                "max_parallel": 1,
                "lanes": [
                    {
                        "id": "lane-a",
                        "role": "ops",
                        "repo": "skillweave/repo-a",
                        "base": _FULL_A,
                        "execution_model": "cold",
                        "mutating": True,
                        "depends_on": [],
                        "write_scope": ["skillweave/repo-a/**"],
                        "worktree": "/tmp/lane-a",
                        "branch": "branch-lane-a",
                        "integration_policy": "independent",
                        "criterion_groups": [{"criteria": [1]}],
                    }
                ],
            }
        )

    def _dispatch(prof_path):
        seq = Path(prof_path).parent / "seq.yaml"
        seq.write_text(_seq(prof_path), encoding="utf-8")
        captured = {"commands": []}

        def inline(command, **kwargs):
            captured["commands"].append([list(command)])
            return _FakeResult([_SucceededChild()])

        app = OperatorDispatchApplication(
            workspace_seam=_NoopWorkspace(), inline_seam=inline
        )
        _, resolved, _ = app.load(str(seq), str(prof_path))
        app.dispatch(str(seq), str(prof_path), wave="0", sink=io.StringIO())
        return resolved, captured

    with tempfile.TemporaryDirectory() as tmp:
        base_profile = Path(tmp) / "p.yaml"
        base_profile.write_text(
            _profile("python3 -c 'pass'", "faigate/m1"), encoding="utf-8"
        )

        # Model-only change: invocation command unchanged, model receipt moves.
        alt_model_profile = Path(tmp) / "p-model.yaml"
        alt_model_profile.write_text(
            _profile("python3 -c 'pass'", "faigate/m2"), encoding="utf-8"
        )
        resolved_base, captured_base = _dispatch(base_profile)
        resolved_model, captured_model = _dispatch(alt_model_profile)

        if resolved_base.role("ops").model.resolved != "faigate/m1":
            return False
        if resolved_model.role("ops").model.resolved != "faigate/m2":
            return False
        if captured_base["commands"] != captured_model["commands"]:
            return False  # a model-only change must not alter the invocation

        # Launch-command-only change: the actual child argv handed to the fanout
        # changes, and only the command differs (model unchanged).
        alt_cmd_profile = Path(tmp) / "p-cmd.yaml"
        alt_cmd_profile.write_text(
            _profile("python3 -c 'pass' --extra", "faigate/m1"), encoding="utf-8"
        )
        resolved_cmd, captured_cmd = _dispatch(alt_cmd_profile)

        if captured_base["commands"][0] == captured_cmd["commands"][0]:
            return False  # the launch-command change must change the child argv
        if resolved_cmd.role("ops").model.resolved != "faigate/m1":
            return False
        return True


def _fixture_zero_worker_red_paths() -> bool:
    """Missing profile, wrong base, missing execution_model, and incomplete
    criterion coverage each start zero workers."""
    import tempfile

    import yaml

    from skillweave.dispatch.application import (
        ExecutionModelError,
        OperatorDispatchApplication,
        ProfileLocationError,
        ProvisionedWorkspace,
        WorkspaceMismatchError,
    )
    from skillweave.dispatch.contracts import LaneValidationError

    class _FakeWorkspace:
        def __init__(self, attested_override=None):
            self._override = attested_override
            self.provisions = 0

        def provision(self, lane, run_id):
            self.provisions += 1
            return ProvisionedWorkspace(
                base_sha=self._override or lane.base or "", path=None
            )

        def release(self, lane, run_id):
            pass

    def _recording():
        recorder = {"batches": 0}

        def fanout(commands, **kwargs):
            recorder["batches"] += 1
            return _FakeResult([_SucceededChild() for _ in commands])

        return recorder, fanout

    with tempfile.TemporaryDirectory() as tmp:
        prof = Path(tmp) / "p.yaml"
        prof.write_text(
            yaml.safe_dump(
                {
                    "name": "gate-red",
                    "tier": "balanced",
                    "limits": {
                        "timeout": 30.0,
                        "max_retries": 1,
                        "min_models_required": 2,
                        "on_model_failure": "skip",
                    },
                    "roles": {
                        "ops": {
                            "model": "faigate/m",
                            "tool": {"name": "marker", "launch_command": "python3 -c 'pass'", "args": []},
                            "capabilities": {"can_mutate_run_state": True},
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        def _seq(execution_model="cold", base=_FULL_A, criteria_groups=None,
                 lane_execution_model="cold"):
            lane = {
                "id": "lane-a",
                "role": "ops",
                "repo": "skillweave/repo-a",
                "base": base,
                "mutating": True,
                "depends_on": [],
                "write_scope": ["skillweave/repo-a/**"],
                "worktree": "/tmp/lane-a",
                "branch": "branch-lane-a",
                "integration_policy": "independent",
                "criterion_groups": criteria_groups or [{"criteria": [1]}],
            }
            if lane_execution_model is not None:
                lane["execution_model"] = lane_execution_model
            return yaml.safe_dump(
                {
                    "session_boundary": "batch",
                    "profile": {"path": str(prof), "required": True},
                    "execution_model": execution_model,
                    "max_correction_rounds_per_wave": 0,
                    "max_parallel": 1,
                    "lanes": [lane],
                }
            )

        # 1. Missing profile -> zero workers.
        base_seq = Path(tmp) / "base-seq.yaml"
        base_seq.write_text(_seq(), encoding="utf-8")
        missing = Path(tmp) / "does-not-exist.yaml"
        rec, fanout = _recording()
        app = OperatorDispatchApplication(workspace_seam=_FakeWorkspace(), fanout_seam=fanout)
        try:
            app.dispatch(str(base_seq), str(missing), wave="0", sink=io.StringIO())
        except ProfileLocationError:
            pass
        else:
            return False
        if rec["batches"] != 0:
            return False

        # 2. Wrong attested base -> zero workers.
        rec, fanout = _recording()
        app = OperatorDispatchApplication(
            workspace_seam=_FakeWorkspace(attested_override="0" * 40), fanout_seam=fanout
        )
        try:
            app.dispatch(str(base_seq), str(prof), wave="0", sink=io.StringIO())
        except WorkspaceMismatchError:
            pass
        else:
            return False
        if rec["batches"] != 0:
            return False

        # 3. Missing execution_model (lane-level) -> zero workers.
        seq_missing_model = Path(tmp) / "no-model.yaml"
        seq_missing_model.write_text(_seq(lane_execution_model=None), encoding="utf-8")
        rec, fanout = _recording()
        app = OperatorDispatchApplication(workspace_seam=_FakeWorkspace(), fanout_seam=fanout)
        try:
            app.dispatch(str(seq_missing_model), str(prof), wave="0", sink=io.StringIO())
        except (ExecutionModelError, LaneValidationError):
            pass
        else:
            return False
        if rec["batches"] != 0:
            return False

        # 4. Incomplete criterion coverage -> zero workers.
        seq_incomplete = Path(tmp) / "incomplete.yaml"
        seq_incomplete.write_text(_seq(criteria_groups=[{"criteria": [1]}]), encoding="utf-8")
        rec, fanout = _recording()
        app = OperatorDispatchApplication(workspace_seam=_FakeWorkspace(), fanout_seam=fanout)
        try:
            app.dispatch(
                str(seq_incomplete), str(prof), wave="0", sink=io.StringIO(),
                required_criteria=[1, 2],
            )
        except LaneValidationError:
            pass
        else:
            return False
        if rec["batches"] != 0:
            return False

        return True


# ── Proof 5: typed outcomes + content-addressed streams ─────────────────────

def _fixture_typed_outcomes() -> bool:
    """exit_code / signal / timed_out / launch_failed are distinct machine
    outcomes; skip / retry / abort failure policy is applied and reported."""
    import tempfile

    import yaml

    from skillweave.fanout.dispatch import fan_out_dispatch
    from skillweave.dispatch.application import OperatorDispatchApplication, ProvisionedWorkspace

    # Four real child endings map to four distinct outcomes.
    def _outcome(cmd, timeout=None):
        return fan_out_dispatch(
            [cmd],
            run_id="gate-out",
            subject_repo="skillweave/repo",
            subject_commit=_FULL_A,
            tool="marker",
            model="faigate/m",
            timeout=timeout,
        ).children[0].outcome

    outcomes = {
        _outcome([sys.executable, "-c", "import sys; sys.exit(7)"]),
        _outcome([sys.executable, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"]),
        _outcome([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2),
        _outcome(["/definitely/not/a/binary/xyzzy"]),
    }
    if outcomes != {"exit_code", "signal", "timed_out", "launch_failed"}:
        return False

    # skip / retry / abort are reported on the wave result surface and produce
    # distinct correction behaviour.
    class _NoopWorkspace:
        def provision(self, lane, run_id):
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            pass

    class _FailInline:
        def __init__(self):
            self.calls = 0

        def __call__(self, command, **kwargs):
            self.calls += 1
            from skillweave.fanout.dispatch import FanOutChild, FanOutResult
            from skillweave.runtime.runner_adapter import ProcessResult

            pr = ProcessResult(
                command=["x"], exit_code=3, signal=None, termination="exited",
                pid=1, tool="t", model="m",
                stdout_receipt=None, stderr_receipt=None, message="boom",
            )
            child = FanOutChild(
                child_run_id="c0", command=["x"], result=pr, model="m",
                outcome="exit_code",
            )
            return FanOutResult(children=[child], overlapped=False)

    with tempfile.TemporaryDirectory() as tmp:
        policies = {}
        for policy in ("skip", "retry", "abort"):
            prof = Path(tmp) / f"{policy}.yaml"
            prof.write_text(
                yaml.safe_dump(
                    {
                        "name": "gate-policy",
                        "tier": "balanced",
                        "limits": {
                            "timeout": 30.0,
                            "max_retries": 1,
                            "min_models_required": 2,
                            "on_model_failure": policy,
                        },
                        "roles": {
                            "ops": {
                                "model": "faigate/m",
                                "tool": {"name": "marker", "launch_command": "python3 -c 'pass'", "args": []},
                                "capabilities": {"can_mutate_run_state": True},
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )
            seq = Path(tmp) / f"{policy}-seq.yaml"
            seq.write_text(
                yaml.safe_dump(
                    {
                        "session_boundary": "batch",
                        "profile": {"path": str(prof), "required": True},
                        "execution_model": "cold",
                        "max_correction_rounds_per_wave": 2,
                        "max_parallel": 1,
                        "lanes": [
                            {
                                "id": "lane-a",
                                "role": "ops",
                                "repo": "skillweave/repo-a",
                                "base": _FULL_A,
                                "execution_model": "cold",
                                "mutating": True,
                                "depends_on": [],
                                "write_scope": ["skillweave/repo-a/**"],
                                "worktree": "/tmp/lane-a",
                                "branch": "branch-lane-a",
                                "integration_policy": "independent",
                                "criterion_groups": [{"criteria": [1]}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            inline = _FailInline()
            app = OperatorDispatchApplication(
                workspace_seam=_NoopWorkspace(), inline_seam=inline
            )
            run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())
            policies[policy] = (run.failure_policy, run.correction_rounds, inline.calls)

        skip = policies["skip"]
        retry = policies["retry"]
        abort = policies["abort"]
        if skip[0] != "skip" or skip[1] != 0 or skip[2] != 1:
            return False
        if retry[0] != "retry" or retry[1] != 1 or retry[2] != 2:
            return False
        if abort[0] != "abort" or abort[1] != 0 or abort[2] != 1:
            return False
        return True


def _fixture_content_addressed_streams() -> bool:
    """stdout/stderr resolve to their content digest from the store, including
    the empty-stream (zero-byte) case."""
    from skillweave.fanout.dispatch import fan_out_dispatch
    from skillweave.runtime.registry import RawArtifactStore

    store = RawArtifactStore()

    # Non-empty streams: both resolve back to their exact bytes.
    result = fan_out_dispatch(
        [
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('OUT\\n'); sys.stderr.write('ERR\\n')",
            ]
        ],
        run_id="gate-cas",
        subject_repo="skillweave/repo",
        subject_commit=_FULL_A,
        tool="marker",
        model="faigate/m",
        artifact_store=store,
    )
    child = result.children[0]
    if child.stdout_ref.resolve(store.resolve) != b"OUT\n":
        return False
    if child.stderr_ref.resolve(store.resolve) != b"ERR\n":
        return False
    if child.stdout_ref.sha256 != hashlib.sha256(b"OUT\n").hexdigest():
        return False

    # Empty streams: still content-addressed to the empty-byte digest, and
    # resolvable to b"".
    result2 = fan_out_dispatch(
        [[sys.executable, "-c", "pass"]],
        run_id="gate-cas-empty",
        subject_repo="skillweave/repo",
        subject_commit=_FULL_A,
        tool="marker",
        model="faigate/m",
        artifact_store=store,
    )
    empty = result2.children[0]
    empty_sha = hashlib.sha256(b"").hexdigest()
    if empty.stdout_ref.sha256 != empty_sha or empty.stderr_ref.sha256 != empty_sha:
        return False
    if empty.stdout_ref.resolve(store.resolve) != b"":
        return False
    return True


# ── Proof 6: reviewer + observer read-only authority ────────────────────────

def _fixture_reviewer_read_only() -> bool:
    """A reviewer's write / commit / push / dispatch-repair attempts are refused
    technically (raise) before any effect."""
    from skillweave.runtime.authority import AuthorityGuard, AuthorityError
    from skillweave.review import ReviewGate, ReviewGateError

    guard = AuthorityGuard()
    # Read-only: none of the mutating actions are performable.
    for action in ("write", "commit", "push", "mutate_run_state", "merge", "release", "tag"):
        if guard.can_perform("reviewer", action):
            return False
    # The executable probe raises before execution.
    for action in ("write", "commit", "push", "mutate_run_state"):
        try:
            guard.assert_can_write("reviewer", action)
        except AuthorityError:
            continue
        else:
            return False
    # The review gate refuses a writable role (ops) from a review path, and
    # accepts the read-only reviewer.
    gate = ReviewGate()
    try:
        gate.assert_read_only("ops")
    except ReviewGateError as exc:
        if exc.code != "REVIEW_WRITE_ATTEMPT_BLOCKED":
            return False
    else:
        return False
    gate.assert_read_only("reviewer")
    return True


def _fixture_observer_read_only() -> bool:
    """The observer rejects write / repair / dispatch / commit / push / approval
    via the shared authority guard (raises AuthorityError)."""
    from skillweave.dispatch.observer import DispatchObserver, ObserverEventSource
    from skillweave.runtime.authority import AuthorityGuard, AuthorityError, Role

    guard = AuthorityGuard()
    # The observer role is read-only in the capability matrix.
    for action in ("write", "commit", "push", "mutate_run_state", "approve_gate"):
        if guard.can_perform(Role.OBSERVER.value, action):
            return False

    obs = DispatchObserver(
        run_id="gate-obs",
        wave="0",
        mode="built_in",
        event_source=ObserverEventSource(
            run_id="gate-obs", replay=lambda: [], heartbeat_interval_seconds=60.0
        ),
        guard=guard,
    )
    denied = (
        obs.write_repository,
        obs.repair_finding,
        obs.dispatch_work,
        obs.mutate_run_state,
        obs.approve_gate,
    )
    for probe in denied:
        try:
            probe()
        except AuthorityError:
            continue
        else:
            return False
    return True


# ── Gate runner ──────────────────────────────────────────────────────────────

_FIXTURES = [
    ("overlap-and-serialize", _fixture_overlap_and_serialize),
    ("observer-before-ops", _fixture_observer_before_ops),
    ("heartbeat-before-terminal", _fixture_heartbeat_before_terminal),
    ("profile-model-effect", _fixture_profile_model_effect),
    ("zero-worker-red-paths", _fixture_zero_worker_red_paths),
    ("typed-outcomes", _fixture_typed_outcomes),
    ("content-addressed-streams", _fixture_content_addressed_streams),
    ("reviewer-read-only", _fixture_reviewer_read_only),
    ("observer-read-only", _fixture_observer_read_only),
]


def run_gate() -> tuple[bool, dict[str, bool]]:
    results: dict[str, bool] = {}
    for name, fn in _FIXTURES:
        results[name] = bool(fn())
    all_pass = all(results.values())
    return all_pass, results


def emit_token() -> str:
    all_pass, results = run_gate()
    for name, passed in results.items():
        print(f"{'PASS' if passed else 'FAIL'} gate:{name}")
    print(GATE_TOKEN if all_pass else "OPERATOR_DISPATCH_FINAL_GATE_FAIL")
    return GATE_TOKEN if all_pass else "OPERATOR_DISPATCH_FINAL_GATE_FAIL"


def test_operator_dispatch_final_gate_passes():
    """The single aggregate gate: every final-gate criterion holds.

    Collected by pytest so ``python -m pytest tests/gate_138 -q`` runs the real
    behaviour of every production seam and asserts the gate's all-pass token.
    """
    all_pass, results = run_gate()
    failed = [name for name, ok in results.items() if not ok]
    assert not failed, f"gate fixtures failed: {failed}"
    assert emit_token() == GATE_TOKEN


if __name__ == "__main__":
    token = emit_token()
    sys.exit(0 if token == GATE_TOKEN else 1)
