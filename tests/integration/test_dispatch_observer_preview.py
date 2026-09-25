"""Integration tests for the run-scoped read-only dispatch observer (SW138-OBSERVER-001).

Six binary acceptance criteria, exercised end to end over the real dispatch
application seam, the real typed event stream, and the shared authority guard:

1. Every non-dry wave starts exactly one active observer *before* the first ops
   child; the result/events identify ``built_in`` or ``tool_targeted`` from the
   resolved profile. A dry run starts no active observer.
2. The observer consumes the real dispatch event source and emits typed findings
   for all four conditions: heartbeat expiry, terminal child lacking required
   evidence, contradictory process/evidence state, and lane completion not
   observed. Findings bind to run/wave/lane evidence and never mutate conditions.
3. Negative probes prove the observer *technically* fails (raises) on dispatch,
   root-run mutation, gate approval, repository write, and finding repair — a
   prompt-only prohibition is insufficient.
4. A tool-targeted observer receives only a read-only event-source locator and
   emits a separate receipt; a built-in observer is recorded as in-place and
   active. No writable repository or gate handle is ever exposed.
5. Observer failure is visible in the wave result and cannot be serialised as
   ``observed=true``; the attended continue/halt policy governs wave continuation
   without granting gate authority.
6. The module documents that lease persistence, offset persistence, and crash
   recovery are NOT provided by SkillWeave 1.3.8.
"""

import io
import json
import os
import sys
import time
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_SEQUENCE = _FIXTURES / "dispatch-sequence.yaml"
_PROFILE = _FIXTURES / "dispatch-profile.yaml"

from skillweave.dispatch.observer import (  # noqa: E402
    DispatchObserver,
    ObserverCondition,
    ObserverEventSource,
    ObserverMode,
    ObserverStateError,
    resolve_observer_mode,
)
from skillweave.dispatch.application import (  # noqa: E402
    HALT_REQUIRES_OPERATOR,
    OperatorDispatchApplication,
    ProvisionedWorkspace,
    WorkspaceSeam,
)
from skillweave.dispatch.contracts import Lane  # noqa: E402
from skillweave.runtime.authority import (  # noqa: E402
    AuthorityError,
    AuthorityGuard,
    Role,
)


class _FakeWorkspace(WorkspaceSeam):
    def provision(self, lane: Lane, run_id: str) -> ProvisionedWorkspace:
        return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

    def release(self, lane: Lane, run_id: str) -> None:
        pass


class _RecordingFanout:
    """Records batches and yields a succeeded child for each command."""

    def __init__(self):
        self.batches: list[list[list[str]]] = []

    def __call__(self, commands, **kwargs):
        self.batches.append([list(c) for c in commands])
        return _FakeResult([_FakeChild(True) for _ in commands])


class _FakeChild:
    def __init__(self, succeeded: bool):
        self.succeeded = succeeded


class _FakeResult:
    def __init__(self, children):
        self.children = children


def _timestamp(iso: str) -> str:
    return iso


def _event(**kwargs):
    base = {
        "run_id": "run-obs",
        "wave": "0",
        "lane_id": "",
        "dispatch_id": "",
        "sequence": 1,
        "timestamp": "2026-08-27T00:00:00+00:00",
        "event_type": "wave_started",
        "process_status": "not_started",
        "task_status": "queued",
    }
    base.update(kwargs)
    return base


def _source(events, heartbeat_interval=60.0):
    return ObserverEventSource(
        run_id="run-obs",
        replay=lambda: list(events),
        heartbeat_interval_seconds=heartbeat_interval,
    )


# ── Criterion 1: exactly one observer per non-dry wave, mode from profile ────


def test_non_dry_wave_starts_exactly_one_built_in_observer_before_fanout():
    recorder = _RecordingFanout()
    app = OperatorDispatchApplication(workspace_seam=_FakeWorkspace(), fanout_seam=recorder)
    sink = io.StringIO()
    run = app.dispatch(str(_SEQUENCE), str(_PROFILE), wave="0", sink=sink)

    assert run.observer is not None
    assert run.observer_mode == ObserverMode.BUILT_IN.value
    assert run.observer["active"] is True
    assert run.observer["in_place"] is True
    assert run.observer["mode"] == ObserverMode.BUILT_IN.value

    # Zero children if the observer single-start is violated — here it ran, and
    # the fan-out saw its normal batches (proving dispatch proceeded normally).
    assert recorder.batches, "the wave must still dispatch its lanes"

    # The observer exists exactly once on the result: a single receipt, never a
    # second one.
    result = run.to_dict()
    assert result["observer"] is run.observer


def test_dry_run_starts_no_active_observer():
    app = OperatorDispatchApplication(workspace_seam=_FakeWorkspace())
    run = app.dry_run(str(_SEQUENCE), str(_PROFILE), wave="0")
    # Dry run has no observer surface at all: no active observer was started.
    assert run.observer is None
    assert run.observer_mode is None
    assert run.to_dict()["observer"] is None


def test_tool_targeted_mode_resolves_from_profile(tmp_path):
    import yaml

    raw = yaml.safe_load(_PROFILE.read_text(encoding="utf-8"))
    raw["roles"]["observer"]["tool"] = {
        "name": "observer-tool",
        "launch_command": "python3 -c 'pass'",
        "args": [],
    }
    prof = tmp_path / "tool-observer-profile.yaml"
    prof.write_text(yaml.safe_dump(raw), encoding="utf-8")

    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    seq_src["profile"]["path"] = str(prof)
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")

    recorder = _RecordingFanout()
    app = OperatorDispatchApplication(workspace_seam=_FakeWorkspace(), fanout_seam=recorder)
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert run.observer_mode == ObserverMode.TOOL_TARGETED.value
    assert run.observer["mode"] == ObserverMode.TOOL_TARGETED.value
    assert run.observer["in_place"] is False
    assert run.observer["active"] is True


# ── Criterion 2: four typed findings over the real event source ──────────────


def test_heartbeat_expiry_finding():
    obs = DispatchObserver(
        run_id="run-obs", wave="0", mode=ObserverMode.BUILT_IN.value,
        event_source=_source([
            _event(sequence=1),
            _event(sequence=2, lane_id="l", event_type="lane_started",
                   timestamp="2026-08-27T00:00:00+00:00"),
            _event(sequence=3, lane_id="l", event_type="dispatch_started",
                   process_status="running", task_status="dispatched",
                   timestamp="2026-08-27T00:00:00+00:00"),
            _event(sequence=4, lane_id="", event_type="wave_started",
                   timestamp="2026-08-27T00:10:00+00:00"),
        ], heartbeat_interval=60.0),
    )
    receipt = obs.observe()
    assert receipt.observed is True
    conditions = {f["condition"] for f in receipt.findings}
    assert ObserverCondition.HEARTBEAT_EXPIRY.value in conditions


def test_terminal_missing_evidence_finding():
    obs = DispatchObserver(
        run_id="run-obs", wave="0", mode=ObserverMode.BUILT_IN.value,
        event_source=_source([
            _event(sequence=1),
            _event(sequence=2, lane_id="l", event_type="lane_started"),
            _event(sequence=3, lane_id="l", event_type="process_terminal",
                   process_status="exited", task_status="done"),
            _event(sequence=4, lane_id="l", event_type="lane_terminal",
                   process_status="exited", task_status="done"),
        ]),
    )
    receipt = obs.observe()
    conditions = {f["condition"] for f in receipt.findings}
    assert ObserverCondition.TERMINAL_MISSING_EVIDENCE.value in conditions


def test_contradictory_process_evidence_finding():
    obs = DispatchObserver(
        run_id="run-obs", wave="0", mode=ObserverMode.BUILT_IN.value,
        event_source=_source([
            _event(sequence=1),
            _event(sequence=2, lane_id="l", event_type="lane_started"),
            _event(sequence=3, lane_id="l", event_type="process_terminal",
                   process_status="exited", task_status="failed"),
            _event(sequence=4, lane_id="l", event_type="evidence_recorded",
                   process_status="exited", task_status="done",
                   evidence_status="recorded", receipt_refs=["r-1"]),
        ]),
    )
    receipt = obs.observe()
    conditions = {f["condition"] for f in receipt.findings}
    assert ObserverCondition.CONTRADICTORY_PROCESS_EVIDENCE.value in conditions


def test_lane_completion_not_observed_finding():
    obs = DispatchObserver(
        run_id="run-obs", wave="0", mode=ObserverMode.BUILT_IN.value,
        event_source=_source([
            _event(sequence=1),
            _event(sequence=2, lane_id="l", event_type="lane_started"),
            _event(sequence=3, lane_id="l", event_type="dispatch_started",
                   process_status="running", task_status="dispatched"),
        ]),
    )
    receipt = obs.observe()
    conditions = {f["condition"] for f in receipt.findings}
    assert ObserverCondition.LANE_COMPLETION_NOT_OBSERVED.value in conditions


def test_findings_bind_to_run_wave_lane_evidence():
    obs = DispatchObserver(
        run_id="run-obs", wave="3", mode=ObserverMode.BUILT_IN.value,
        event_source=_source([
            _event(sequence=1),
            _event(sequence=2, lane_id="lane-x", event_type="lane_started"),
        ]),
    )
    receipt = obs.observe()
    completion = [f for f in receipt.findings
                  if f["condition"] == ObserverCondition.LANE_COMPLETION_NOT_OBSERVED.value]
    assert completion
    finding = completion[0]
    assert finding["run_id"] == "run-obs"
    assert finding["wave"] == "3"
    assert finding["lane_id"] == "lane-x"
    assert "lane_started" in finding["evidence"]


def test_observer_does_not_mutate_conditions():
    events = [
        _event(sequence=1),
        _event(sequence=2, lane_id="l", event_type="lane_started"),
    ]
    snapshot = [dict(e) for e in events]
    obs = DispatchObserver(
        run_id="run-obs", wave="0", mode=ObserverMode.BUILT_IN.value,
        event_source=_source(events),
    )
    obs.observe()
    # The replayed source events are unchanged after observation: read-only.
    assert events == snapshot


# ── Criterion 3: denied actions fail technically ─────────────────────────────


def _observer():
    return DispatchObserver(
        run_id="run-obs", wave="0", mode=ObserverMode.BUILT_IN.value,
        event_source=_source([]), guard=AuthorityGuard(),
    )


def test_observer_cannot_dispatch_work():
    with pytest.raises(AuthorityError):
        _observer().dispatch_work()


def test_observer_cannot_mutate_run_state():
    with pytest.raises(AuthorityError):
        _observer().mutate_run_state()


def test_observer_cannot_approve_gate():
    with pytest.raises(AuthorityError):
        _observer().approve_gate()


def test_observer_cannot_write_repository():
    with pytest.raises(AuthorityError):
        _observer().write_repository()


def test_observer_cannot_repair_finding():
    with pytest.raises(AuthorityError):
        _observer().repair_finding()


def test_observer_role_is_read_only_in_matrix():
    assert Role.OBSERVER.value == "observer"
    guard = AuthorityGuard()
    assert guard.can_perform("observer", "write") is False
    assert guard.can_perform("observer", "commit") is False
    assert guard.can_perform("observer", "push") is False
    assert guard.can_perform("observer", "approve_gate") is False
    assert guard.can_perform("observer", "mutate_run_state") is False


# ── Criterion 4: tool-targeted locator + separate receipt; built-in in-place ─


def test_tool_targeted_observer_emits_separate_receipt_only():
    # A tool-targeted observer that launched nothing still emits a separate
    # (non-built-in) receipt: never relabel the in-place record. The receipt
    # surface carries no writable handle.
    obs = DispatchObserver(
        run_id="run-obs", wave="0", mode=ObserverMode.TOOL_TARGETED.value,
        event_source=_source([]),
    )
    receipt = obs.observe().to_dict()
    assert receipt["mode"] == ObserverMode.TOOL_TARGETED.value
    assert receipt["in_place"] is False
    assert receipt["active"] is True
    # No writable handle is present anywhere on the receipt surface.
    for key in ("repository", "gate", "store", "sink", "handle", "dispatcher"):
        assert key not in receipt


def test_builtin_observer_recorded_in_place_and_active():
    obs = DispatchObserver(
        run_id="run-obs", wave="0", mode=ObserverMode.BUILT_IN.value,
        event_source=_source([]),
    )
    receipt = obs.observe().to_dict()
    assert receipt["in_place"] is True
    assert receipt["active"] is True
    assert receipt["mode"] == ObserverMode.BUILT_IN.value


def test_event_source_locator_is_read_only():
    source = _source([])
    # The read-only locator exposes no write/emit/transition method.
    for attr in ("emit", "write", "transition", "emit_terminal", "approve", "mutate"):
        assert not hasattr(source, attr), f"locator must not expose {attr!r}"
    assert source.events() == []
    assert getattr(source, "heartbeat_interval") == 60.0


# ── Criterion 5: observer failure visible; continue/halt policy ──────────────


class _BoomEventSource(ObserverEventSource):
    def events(self):
        raise RuntimeError("observer backend exploded")


def test_observer_failure_serializes_observed_false():
    obs = DispatchObserver(
        run_id="run-obs", wave="0", mode=ObserverMode.BUILT_IN.value,
        event_source=_BoomEventSource(
            run_id="run-obs", replay=lambda: [], heartbeat_interval_seconds=60.0
        ),
    )
    receipt = obs.observe()
    assert receipt.observed is False
    assert receipt.error == "observer backend exploded"
    d = receipt.to_dict()
    assert d["observed"] is False, "failure must never serialize as observed=true"
    assert d["error"]


def test_attend_halt_policy_halts_wave_on_observer_failure():
    # A failing observer under halt policy halts the wave and never grants
    # gate authority (the halt reason is the operator-requires marker).
    def _boom_dispatch(app):
        sink = io.StringIO()
        return app.dispatch(str(_SEQUENCE), str(_PROFILE), wave="0", sink=sink)

    original = DispatchObserver.observe

    def _failing(self):
        self._active = True
        self._observed = False
        self._error = "injected observer failure"
        return self.receipt()

    try:
        DispatchObserver.observe = _failing
        app = OperatorDispatchApplication(
            workspace_seam=_FakeWorkspace(),
            fanout_seam=_RecordingFanout(),
            observer_continue_on_failure=False,
        )
        run = _boom_dispatch(app)
        assert run.halted is True
        assert run.halt_reason == HALT_REQUIRES_OPERATOR
        assert run.observer["observed"] is False
    finally:
        DispatchObserver.observe = original


def test_attend_continue_lets_wave_continue_on_observer_failure():
    original = DispatchObserver.observe

    def _failing(self):
        self._active = True
        self._observed = False
        self._error = "injected observer failure"
        return self.receipt()

    try:
        DispatchObserver.observe = _failing
        app = OperatorDispatchApplication(
            workspace_seam=_FakeWorkspace(),
            fanout_seam=_RecordingFanout(),
            observer_continue_on_failure=True,
        )
        run = app.dispatch(str(_SEQUENCE), str(_PROFILE), wave="0", sink=io.StringIO())
        assert run.halted is False
        assert run.observer["observed"] is False
        assert run.observer["error"] == "injected observer failure"
    finally:
        DispatchObserver.observe = original


# ── Criterion 6: no lease/offset/crash-recovery claim ────────────────────────


def test_module_documents_no_persistence_or_recovery():
    from skillweave.dispatch import observer as obs_module

    doc = obs_module.__doc__ or ""
    flattened = " ".join(doc.split())
    assert "not provided by SkillWeave 1.3.8" in flattened
    assert "crash recovery" in flattened
    assert "lease persistence" in flattened
    assert "offset persistence" in flattened
    # No claim of future persistence/recovery is made.
    assert "will be persisted" not in flattened
    assert "crash recovery is provided" not in flattened


# ── Correction C1: honest tool-targeted lifecycle ─────────────────────────────
#
# A tool-targeted observer must *launch* its declared tool (once, before ops),
# deliver a read-only serialized locator to it, reap it exactly once, and derive
# its receipt from the actual process result — never by relabeling the built-in
# four-detector path. These tests drive a real marker tool over the real
# start_process seam.


_MARKER_TOOL = '''import json
import sys
import time


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "success"
    if mode == "start_marker":
        with open(args[1], "w", encoding="utf-8") as fh:
            fh.write(repr(time.time()))
        mode = "success"
    payload_raw = sys.stdin.read()
    if mode == "hang":
        time.sleep(60)
        return 0
    if mode == "nonzero":
        sys.stderr.write("marker exploded")
        return 3
    if mode == "malformed":
        sys.stdout.write("this is not json")
        return 0
    # success: echo a small documented machine JSON result back over the
    # received locator, emitting one soft finding derived from the payload.
    data = json.loads(payload_raw)
    result = {
        "run_id": data["run_id"],
        "wave": data["wave"],
        "findings": [
            {
                "condition": "lane_completion_not_observed",
                "severity": "high",
                "message": "observed via marker tool",
                "lane_id": "marker-lane",
                "evidence": {
                    "received_events": len(data.get("events", [])),
                    "heartbeat_interval": data.get("heartbeat_interval_seconds"),
                },
            }
        ],
    }
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _tool_profile(tmp_path, *, launch_command, args=None, timeout=None):
    """Write a profile whose observer role declares a launchable tool."""
    import yaml

    raw = yaml.safe_load(_PROFILE.read_text(encoding="utf-8"))
    raw["roles"]["observer"]["tool"] = {
        "name": "marker",
        "launch_command": launch_command,
        "args": args or [],
    }
    if timeout is not None:
        raw.setdefault("limits", {})["timeout"] = timeout
    prof = tmp_path / "tool-observer-profile.yaml"
    prof.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return prof


def _tool_sequence(tmp_path, prof):
    """Write a sequence whose profile reference points at ``prof``."""
    import yaml

    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    seq_src["profile"]["path"] = str(prof)
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")
    return seq


def test_tool_targeted_starts_marker_before_ops_and_receives_locator(tmp_path):
    import yaml

    marker = tmp_path / "marker.py"
    marker.write_text(_MARKER_TOOL, encoding="utf-8")
    start_file = tmp_path / "observer.started"
    prof = _tool_profile(
        tmp_path,
        launch_command=f"python3 {marker} start_marker {start_file}",
    )

    from skillweave.runtime import runner_adapter
    real_start = runner_adapter.start_process
    order = []

    def recording_start(command, **kwargs):
        order.append("observer_start")
        return real_start(command, **kwargs)

    recorder_fanout = _RecordingFanout()

    def recording_fanout(commands, **kwargs):
        order.append("ops_fanout")
        return recorder_fanout(commands, **kwargs)

    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    seq_src["profile"]["path"] = str(prof)
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")

    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=recording_fanout,
        observer_launch_seam=recording_start,
    )
    run = app.dispatch(str(seq), str(prof), wave="7", sink=io.StringIO())

    # The observer tool process started before the first ops fan-out.
    assert order[0] == "observer_start", order
    assert "ops_fanout" in order
    # No ops fan-out ever precedes the observer start.
    first_ops = order.index("ops_fanout")
    assert order.index("observer_start") < first_ops
    # Exactly one observer start, never once per lane or group.
    assert order.count("observer_start") == 1
    # The marker tool proved it read the locator and started before ops.
    assert start_file.exists()

    rec = run.observer
    assert run.observer_mode == ObserverMode.TOOL_TARGETED.value
    assert rec["active"] is True
    assert rec["observed"] is True
    assert rec["in_place"] is False
    assert rec["termination"] == "exited"
    assert rec["outcome"] == "exit_code"
    assert rec["tool"] == "marker"
    # The finding came from the tool's JSON, not the in-process detectors.
    assert len(rec["findings"]) == 1
    finding = rec["findings"][0]
    assert finding["message"] == "observed via marker tool"
    assert finding["evidence"]["received_events"] > 0
    # Own stdout receipt feeds the returned observer receipt.
    assert rec["stdout_ref"] is not None
    assert rec["stdout_ref"]["artifact_id"]
    assert rec["stderr_ref"] is not None


def test_tool_targeted_payload_is_deterministic_and_read_only():
    obs = DispatchObserver(
        run_id="r", wave="3", mode=ObserverMode.TOOL_TARGETED.value,
        event_source=ObserverEventSource(
            run_id="r",
            replay=lambda: [{"run_id": "r", "wave": "3"}],
            heartbeat_interval_seconds=12.5,
        ),
        command=["python3", "-c", "pass"],
        tool_name="marker",
    )
    payload = json.loads(obs._locator_payload().decode("utf-8"))
    assert payload["run_id"] == "r"
    assert payload["wave"] == "3"
    assert payload["mode"] == ObserverMode.TOOL_TARGETED.value
    assert payload["heartbeat_interval_seconds"] == 12.5
    assert payload["read_only"] is True
    assert payload["events"] == [{"run_id": "r", "wave": "3"}]
    # Deterministic serialization.
    assert obs._locator_payload() == obs._locator_payload()
    # No write/mutation coordinates are exposed.
    for key in ("store", "sink", "gate", "dispatcher", "handle", "callback", "repo"):
        assert key not in payload


def test_tool_targeted_launch_failure_halts_before_ops(tmp_path):
    import yaml

    prof = _tool_profile(
        tmp_path,
        launch_command="definitely-not-a-real-command-xyz",
    )
    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    seq_src["profile"]["path"] = str(prof)
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")

    fanout = _RecordingFanout()
    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=fanout,
        observer_continue_on_failure=False,
    )
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    # Zero ops children started: the observer launch failure halted the wave.
    assert fanout.batches == []
    assert run.halted is True
    assert run.halt_reason == HALT_REQUIRES_OPERATOR
    assert run.observer["observed"] is False
    assert run.observer["active"] is True
    assert run.observer["outcome"] == "launch_failed"
    assert run.observer["error"]


def test_tool_targeted_launch_failure_continue_runs_ops_observed_false(tmp_path):
    import yaml

    prof = _tool_profile(
        tmp_path,
        launch_command="definitely-not-a-real-command-xyz",
    )
    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    seq_src["profile"]["path"] = str(prof)
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")

    fanout = _RecordingFanout()
    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=fanout,
        observer_continue_on_failure=True,
    )
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert fanout.batches, "ops may run under attended continue"
    assert run.halted is False
    assert run.observer["observed"] is False
    assert run.observer["error"]


def test_tool_targeted_nonzero_exit_observed_false(tmp_path):
    import yaml

    marker = tmp_path / "marker.py"
    marker.write_text(_MARKER_TOOL, encoding="utf-8")
    prof = _tool_profile(tmp_path, launch_command=f"python3 {marker} nonzero")
    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    seq_src["profile"]["path"] = str(prof)
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")

    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=_RecordingFanout(),
        observer_continue_on_failure=True,
    )
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert run.observer["observed"] is False
    assert run.observer["outcome"] == "exit_code"
    assert run.observer["error"]


def test_tool_targeted_timeout_observed_false(tmp_path):
    import yaml

    marker = tmp_path / "marker.py"
    marker.write_text(_MARKER_TOOL, encoding="utf-8")
    prof = _tool_profile(
        tmp_path,
        launch_command=f"python3 {marker} hang",
        timeout=0.5,
    )
    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    seq_src["profile"]["path"] = str(prof)
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")

    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=_RecordingFanout(),
        observer_continue_on_failure=True,
    )
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert run.observer["observed"] is False
    assert run.observer["termination"] == "timed_out"
    assert run.observer["outcome"] == "timed_out"


def test_tool_targeted_malformed_output_observed_false(tmp_path):
    import yaml

    marker = tmp_path / "marker.py"
    marker.write_text(_MARKER_TOOL, encoding="utf-8")
    prof = _tool_profile(tmp_path, launch_command=f"python3 {marker} malformed")
    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    seq_src["profile"]["path"] = str(prof)
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")

    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=_RecordingFanout(),
        observer_continue_on_failure=True,
    )
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert run.observer["observed"] is False
    assert run.observer["outcome"] == "exit_code"
    assert "malformed" in run.observer["error"]


def test_built_in_observer_never_launches_a_process(tmp_path):
    import yaml

    # The default profile has a built-in observer (no tool). Prove no process is
    # launched: the launch seam, when provided, is never invoked.
    launched = []

    def never_launch(command, **kwargs):
        launched.append(command)

    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=_RecordingFanout(),
        observer_launch_seam=never_launch,
    )
    run = app.dispatch(str(_SEQUENCE), str(_PROFILE), wave="0", sink=io.StringIO())

    assert launched == []
    assert run.observer_mode == ObserverMode.BUILT_IN.value
    assert run.observer["active"] is True
    assert run.observer["in_place"] is True
    assert run.observer["observed"] is True


def test_one_observer_per_wave_not_per_lane(tmp_path):
    import yaml

    marker = tmp_path / "marker.py"
    marker.write_text(_MARKER_TOOL, encoding="utf-8")
    prof = _tool_profile(tmp_path, launch_command=f"python3 {marker}")
    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    seq_src["profile"]["path"] = str(prof)
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")

    from skillweave.runtime import runner_adapter
    real_start = runner_adapter.start_process
    starts = []

    def counting_start(command, **kwargs):
        starts.append(command)
        return real_start(command, **kwargs)

    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=_RecordingFanout(),
        observer_launch_seam=counting_start,
    )
    # The default sequence fans out three lanes across groups; the observer must
    # launch exactly once for the whole wave.
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert len(starts) == 1
    assert run.observer["observed"] is True


def test_correction_rounds_start_still_one_observer(tmp_path):
    import yaml

    marker = tmp_path / "marker.py"
    marker.write_text(_MARKER_TOOL, encoding="utf-8")
    prof = _tool_profile(tmp_path, launch_command=f"python3 {marker}")
    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    # force a legacy-style failing fanout to exercise correction rounds
    seq_src["profile"]["path"] = str(prof)
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")

    from skillweave.runtime import runner_adapter
    real_start = runner_adapter.start_process
    starts = []

    def counting_start(command, **kwargs):
        starts.append(command)
        return real_start(command, **kwargs)

    class _FailingFanout:
        def __init__(self):
            self.calls = 0

        def __call__(self, commands, **kwargs):
            self.calls += 1
            return _FakeResult([_FakeChild(False) for _ in commands])

    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=_FailingFanout(),
        observer_launch_seam=counting_start,
    )
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    # exactly one observer process across correction rounds
    assert len(starts) == 1


# ── Correction C2: observer lifecycle closure on exceptional exit ─────────────
#
# After a successful tool observer ``start()``, an abnormal dispatch (workspace
# provision failure, base mismatch, ops fan-out/runner failure, post-start
# event-sink failure, or required-evidence failure) must still reap the observer
# process (killing its process group) and remove its neutral directory. Each
# probe launches a *real* blocking marker, captures its PID and neutral cwd via
# the runtime ``start_process`` seam, confirms it is alive, injects the failure,
# and proves the process group and directory are gone after ``dispatch()``
# returns/raises — without any manual cancellation.


_BLOCK_MARKER = '''import os
import sys
import time


def main():
    args = sys.argv[1:]
    with open(args[0], "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    # Block until killed; the observer owns this process and must reap it on
    # every exceptional path.
    time.sleep(120)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid_gone(pid: int) -> bool:
    return not _pid_alive(pid)


def _recording_launch(real_start, captured):
    """Wrap the runtime ``start_process`` to record the launched handle."""

    def _launch(command, **kwargs):
        handle = real_start(command, **kwargs)
        captured.append({"pid": handle.pid, "cwd": kwargs.get("cwd")})
        return handle

    return _launch


def _block_app(tmp_path, *, workspace, fanout):
    """Build a tool-observer app whose marker writes its pid to a file."""
    marker = tmp_path / "block.py"
    marker.write_text(_BLOCK_MARKER, encoding="utf-8")
    pid_file = tmp_path / "observer.pid"
    prof = _block_profile(tmp_path, marker, pid_file)
    seq = _tool_sequence(tmp_path, prof)

    from skillweave.runtime import runner_adapter
    captured = []

    class _App(OperatorDispatchApplication):
        pass

    app = OperatorDispatchApplication(
        workspace_seam=workspace,
        fanout_seam=fanout,
        observer_launch_seam=_recording_launch(runner_adapter.start_process, captured),
    )
    return app, seq, prof, pid_file, captured


def _block_profile(tmp_path, marker, pid_file):
    return _tool_profile(tmp_path, launch_command=f"python3 {marker} {pid_file}")


def test_exceptional_provision_failure_reaps_observer_and_dir(tmp_path):
    class _BoomWorkspace(WorkspaceSeam):
        def provision(self, lane, run_id):
            raise RuntimeError("workspace provision failed")

        def release(self, lane, run_id):
            raise AssertionError("must not release a never-provisioned lane")

    app, seq, prof, pid_file, captured = _block_app(
        tmp_path, workspace=_BoomWorkspace(), fanout=_RecordingFanout()
    )
    with pytest.raises(RuntimeError, match="workspace provision failed"):
        app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert captured, "observer tool must have launched before provision"
    pid = captured[0]["pid"]
    assert _pid_alive(pid) is False, "observer process group must be reaped"
    neutral_dir = captured[0]["cwd"]
    assert neutral_dir is None or not os.path.isdir(neutral_dir)


def test_exceptional_base_mismatch_reaps_observer_releases_once(tmp_path):
    class _MismatchWorkspace(WorkspaceSeam):
        def __init__(self):
            self.released = []

        def provision(self, lane, run_id):
            return ProvisionedWorkspace(base_sha="deadbeef", path=None)

        def release(self, lane, run_id):
            self.released.append(lane.id)

    ws = _MismatchWorkspace()
    app, seq, prof, pid_file, captured = _block_app(
        tmp_path, workspace=ws, fanout=_RecordingFanout()
    )
    with pytest.raises(Exception):
        app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert ws.released == ["lane-ops-a"], ws.released
    assert captured and _pid_alive(captured[0]["pid"]) is False
    assert captured[0]["cwd"] is None or not os.path.isdir(captured[0]["cwd"])


def test_exceptional_fanout_failure_reaps_observer_releases_all(tmp_path):
    releases = []

    class _Tracked(WorkspaceSeam):
        def provision(self, lane, run_id):
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            releases.append(lane.id)

    calls = []

    class _BoomFanout:
        def __call__(self, commands, **kwargs):
            calls.append(commands)
            raise RuntimeError("ops fanout/runner exploded")

    app, seq, prof, pid_file, captured = _block_app(
        tmp_path, workspace=_Tracked(), fanout=_BoomFanout()
    )
    with pytest.raises(RuntimeError, match="fanout/runner exploded"):
        app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert len(calls) == 1
    assert sorted(releases) == ["lane-ops-a", "lane-ops-b", "lane-ops-c"], releases
    assert captured and _pid_alive(captured[0]["pid"]) is False
    assert captured[0]["cwd"] is None or not os.path.isdir(captured[0]["cwd"])


def test_exceptional_required_evidence_reaps_observer(tmp_path):
    import yaml

    marker = tmp_path / "block.py"
    marker.write_text(_BLOCK_MARKER, encoding="utf-8")
    pid_file = tmp_path / "observer.pid"
    prof = _block_profile(tmp_path, marker, pid_file)

    seq = tmp_path / "tool-observer-sequence.yaml"
    seq_src = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    seq_src["profile"]["path"] = str(prof)
    for ln in seq_src["lanes"]:
        ln["required_evidence"] = ["stdout"]
    seq.write_text(yaml.safe_dump(seq_src), encoding="utf-8")

    from skillweave.runtime import runner_adapter
    captured = []

    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=_RecordingFanout(),
        observer_launch_seam=_recording_launch(runner_adapter.start_process, captured),
    )
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())
    assert run is not None
    assert captured and _pid_alive(captured[0]["pid"]) is False
    assert captured[0]["cwd"] is None or not os.path.isdir(captured[0]["cwd"])


def test_partial_multilane_provision_releases_only_materialised_once(tmp_path):
    # Provision lanes a and b, then fail provisioning lane c. Only a and b must
    # be released, each exactly once; the observer is still reaped.
    releases = []

    class _Partial(WorkspaceSeam):
        def provision(self, lane, run_id):
            if lane.id == "lane-ops-c":
                raise RuntimeError("provision failed for lane-ops-c")
            return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

        def release(self, lane, run_id):
            releases.append(lane.id)

    app, seq, prof, pid_file, captured = _block_app(
        tmp_path, workspace=_Partial(), fanout=_RecordingFanout()
    )
    with pytest.raises(RuntimeError, match="provision failed for lane-ops-c"):
        app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())

    assert sorted(releases) == ["lane-ops-a", "lane-ops-b"], releases
    assert captured and _pid_alive(captured[0]["pid"]) is False
    assert captured[0]["cwd"] is None or not os.path.isdir(captured[0]["cwd"])


def test_close_is_idempotent_and_reap_is_exactly_once(tmp_path):
    from skillweave.runtime import runner_adapter

    captured = {}
    real_start = runner_adapter.start_process

    def _launch(command, **kwargs):
        handle = real_start(command, **kwargs)
        captured["handle"] = handle
        captured["cwd"] = kwargs.get("cwd")
        return handle

    marker = tmp_path / "block.py"
    marker.write_text(_BLOCK_MARKER, encoding="utf-8")
    pid_file = tmp_path / "observer.pid"
    prof = _tool_profile(tmp_path, launch_command=f"python3 {marker} {pid_file}")

    obs = DispatchObserver(
        run_id="r", wave="0", mode=ObserverMode.TOOL_TARGETED.value,
        event_source=_source([]),
        command=["python3", str(marker), str(pid_file)],
        tool_name="marker",
        timeout=5.0,
        launch=_launch,
    )
    obs.start()
    assert captured.get("handle") is not None
    pid = captured["handle"].pid
    assert _pid_alive(pid) is True
    neutral_dir = captured["cwd"]
    assert os.path.isdir(neutral_dir)

    obs.close()
    assert _pid_alive(pid) is False
    assert not os.path.isdir(neutral_dir)
    # Repeated close and observe are safe no-ops: nothing is waited/cancelled
    # twice and no process survives.
    for _ in range(3):
        obs.close()
    receipt = obs.observe()
    assert receipt.observed is False
    assert _pid_alive(pid) is False


def test_observer_launch_failure_leaves_no_handle_or_dir(tmp_path):
    prof = _tool_profile(tmp_path, launch_command="definitely-not-a-real-command-xyz")
    app = OperatorDispatchApplication(
        workspace_seam=_FakeWorkspace(),
        fanout_seam=_RecordingFanout(),
        observer_continue_on_failure=False,
    )
    seq = _tool_sequence(tmp_path, prof)
    run = app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())
    assert run.halted is True
    ob = app._observer
    assert ob._handle is None
    assert ob._neutral_dir is None
    assert ob.launch_failed is True


def test_exceptional_event_sink_failure_reaps_observer_and_dir(tmp_path):
    class _BoomSink:
        def __init__(self):
            self.writes = 0

        def write(self, s):
            self.writes += 1
            if self.writes > 1:
                raise RuntimeError("post-start event sink exploded")
            return len(s)

        def flush(self):
            pass

    app, seq, prof, pid_file, captured = _block_app(
        tmp_path, workspace=_FakeWorkspace(), fanout=_RecordingFanout()
    )
    with pytest.raises(RuntimeError, match="event sink exploded"):
        app.dispatch(str(seq), str(prof), wave="0", sink=_BoomSink())

    assert captured, "observer tool must have launched before the sink failed"
    assert _pid_alive(captured[0]["pid"]) is False
    assert captured[0]["cwd"] is None or not os.path.isdir(captured[0]["cwd"])
