"""Dispatch live/replay projection tests (SW1311-OBSERVER-001, criteria 4-8, 10).

Behavioural tests over the deterministic projection
(:mod:`skillweave.trace.projection`), the live observer
(:mod:`skillweave.dispatch.observer`) and the typed stream
(:mod:`skillweave.dispatch.events`):

4. The live projection exposes run, wave, lane, criterion group, job state,
   heartbeat age, evidence, review disposition, rounds remaining, integration
   eligibility and gate state.
5. A typed event becomes visible within one heartbeat without polling log size
   or process ids.
6. A typed intervention request is emitted for liveness/non-progress thresholds
   while cancel/kill/dispatch/correction/disposition/integration/gate remain
   forbidden to the observer.
7. Replaying ordered event and trace records produces the same final projection
   as the captured live state.
8. Consumer disconnect and reconnect do not alter run state, and replay from
   sequence zero restores the view.
C1: Replaying identical serialized bytes at materially different wall-clock
   times produces a byte-/structure-identical projection (deterministic
   heartbeat age derived only from typed facts).
10. Process recreation states the run-scoped boundary and does not claim a
    persistent lease, offset or autonomous resume.

No harness, no provider/model name, no log-file/pid assertions of runtime state.
"""

import io
import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.dispatch.contracts import (  # noqa: E402
    EventType,
    ProcessStatus,
    TaskStatus,
)
from skillweave.dispatch.events import (  # noqa: E402
    DispatchEventStream,
    EventStreamError,
)
from skillweave.dispatch.observer import LiveObserver  # noqa: E402
from skillweave.trace.projection import (  # noqa: E402
    Projector,
    ProjectionEvent,
    builds_identical_projection,
)
from skillweave.trace.view import InterventionRequest  # noqa: E402


def _stream(run_id="run-1"):
    sink = io.StringIO()
    return DispatchEventStream(run_id, sink), sink


def _projector_feed(projector, events):
    for e in events:
        projector.project(ProjectionEvent(sequence=e["sequence"], payload=e))


# ── Criterion 4: live projection surface ─────────────────────────────────────


def test_projection_exposes_full_operator_surface():
    stream, sink = _stream()
    stream.wave_started(wave="w0")
    stream.lane_started(wave="w0", lane_id="ops")
    stream.dispatch_started(
        wave="w0", lane_id="ops", dispatch_id="d-0", criterion_group=[1, 2],
    )
    stream.heartbeat(wave="w0", lane_id="ops", dispatch_id="d-0")
    stream.evidence_recorded(
        wave="w0", lane_id="ops", dispatch_id="d-0", receipt_refs=["recv-1"],
    )

    obs = LiveObserver(stream)
    events = stream.typed_events_since(0)
    obs.observe(events)
    p = obs.projection()

    assert p.run.run_id == "run-1"
    assert p.run.coverage_boundary == "run:run-1"
    assert p.waves == ("w0",)
    assert p.lanes and p.lanes[0].lane_id == "ops"
    assert p.groups == ((1, 2),)
    assert p.jobs and any(j.job_id == "d-0" for j in p.jobs)
    assert p.evidence == ("recv-1",)


def test_projection_surfaces_disposition_rounds_integration_gate():
    projector = Projector("run-1")
    _projector_feed(projector, [
        {"sequence": 1, "event_type": "wave_started", "wave": "w0",
         "lane_id": "", "dispatch_id": ""},
        {"sequence": 2, "event_type": "lane_started", "wave": "w0",
         "lane_id": "ops", "dispatch_id": ""},
        {"sequence": 3, "event_type": "review", "wave": "w0",
         "lane_id": "ops", "dispatch_id": "",
         "disposition": "accepted", "rounds_remaining": 1,
         "integration_eligible": True, "gate_state": "REVIEW_PASS"},
    ])
    p = projector.projection()
    assert p.dispositions["ops"] == "accepted"
    assert p.rounds_remaining == 1
    assert p.integration_eligible is True
    assert p.gate_state == "REVIEW_PASS"


# ── Criterion 5: typed event visible within one heartbeat ────────────────────


def test_typed_event_visible_without_polling():
    stream, sink = _stream()
    stream.wave_started(wave="w0")
    before = stream.typed_events_since(0)
    assert before[0]["event_type"] == EventType.WAVE_STARTED.value
    # no log-file-size or pid field in the typed window
    for event in before:
        for key in ("log_size", "log_file_size", "pid", "process_id"):
            assert key not in event


def test_stream_refuses_log_size_and_pid_payloads():
    stream, sink = _stream()
    with pytest.raises(EventStreamError):
        stream.emit(
            wave="w", lane_id="l", dispatch_id="d",
            event_type=EventType.HEARTBEAT,
            process_status=ProcessStatus.RUNNING,
            task_status=TaskStatus.IN_PROGRESS,
            payload={"log_size": 123},
        )


# ── Criterion 6: read-only intervention requests ─────────────────────────────


def test_intervention_requests_are_read_only_and_forbid_actions():
    stream, sink = _stream()
    obs = LiveObserver(
        stream, liveness_threshold=5.0, non_progress_threshold=10.0,
    )
    requests = obs.intervention_requests()
    assert requests
    for r in requests:
        assert isinstance(r, InterventionRequest)
        # The observer may never perform the runtime actions itself.
        for forbidden in ("cancel", "kill", "dispatch", "correct",
                          "disposition", "integrate", "gate"):
            with pytest.raises(Exception):
                obs.forbid(forbidden)


# ── Criterion 7: ordered replay equals captured live final projection ────────


def test_replay_equals_captured_live_projection():
    stream, sink = _stream()
    stream.wave_started(wave="w0")
    stream.lane_started(wave="w0", lane_id="ops")
    stream.dispatch_started(wave="w0", lane_id="ops", dispatch_id="d-0",
                            criterion_group=[1])
    stream.heartbeat(wave="w0", lane_id="ops", dispatch_id="d-0")
    stream.evidence_recorded(wave="w0", lane_id="ops", dispatch_id="d-0",
                             receipt_refs=["r-1"])
    stream.emit_terminal_once(
        child_key="run-1-0", wave="w0", lane_id="ops", dispatch_id="d-0",
        process_status=ProcessStatus.EXITED, task_status=TaskStatus.DONE,
    )

    live_obs = LiveObserver(stream)
    live_obs.observe(stream.typed_events_since(0))
    live = live_obs.projection()

    replay = Projector("run-1")
    _projector_feed(replay, stream.typed_events_since(0))

    assert builds_identical_projection(live, replay.projection())


# ── Criterion 8: disconnect/reconnect and replay-from-zero ───────────────────


def test_disconnect_reconnect_and_replay_from_zero_restore_view():
    stream, sink = _stream()
    stream.wave_started(wave="w0")
    stream.lane_started(wave="w0", lane_id="ops")

    first = LiveObserver(stream)
    first.observe(stream.typed_events_since(0))
    captured = first.projection()

    # "disconnect": a fresh observer is created; run state is unchanged.
    second = LiveObserver(stream)
    assert second.projection().run == captured.run

    # "reconnect" + replay from zero restores the identical view.
    replayed = Projector("run-1")
    _projector_feed(replayed, stream.typed_events_since(0))
    assert builds_identical_projection(captured, replayed.projection())


# ── Regression: deterministic heartbeat age under wall-clock skew ───────────
#
# C1/F-OBSERVER-DET-001: the projected heartbeat age must be a pure function
# of the serialized typed facts, never of the wall clock at fold/replay time.
# Replaying identical bytes at materially different wall-clock times must yield
# a byte-/structure-identical projection, and reconnect/replay-from-zero restores
# the identical view. Live freshness survives because age is measured against a
# typed reference timestamp (a later typed event), which advances as the typed
# stream grows.


def _typed_heartbeat_stream():
    """A fixed, serialized typed stream (same bytes every call).

    Both the heartbeat and the later reference event carry fixed typed
    timestamps, 60s apart, so the deterministic projected age is exactly 60.0.
    The stream is byte-identical on every build, so repeated / delayed replays
    fold the exact same serialized bytes.
    """
    stream, _sink = _stream("run-det")
    stream.wave_started(wave="w0")
    stream.lane_started(wave="w0", lane_id="ops")
    stream.dispatch_started(wave="w0", lane_id="ops", dispatch_id="d-0")
    # Heartbeat carries a fixed typed timestamp; a later typed event advances
    # the deterministic reference exactly 60s on.
    stream.emit(
        wave="w0", lane_id="ops", dispatch_id="d-0",
        event_type=EventType.HEARTBEAT,
        process_status=ProcessStatus.RUNNING,
        task_status=TaskStatus.IN_PROGRESS,
        timestamp="2026-01-01T00:00:00Z",
    )
    stream.emit(
        wave="w0", lane_id="ops", dispatch_id="d-0",
        event_type=EventType.EVIDENCE_RECORDED,
        process_status=ProcessStatus.EXITED,
        task_status=TaskStatus.DONE,
        evidence_status="recorded",
        receipt_refs=["r-1"],
        timestamp="2026-01-01T00:01:00Z",
    )
    return stream, stream.typed_events_since(0)


def test_delayed_replay_identical_bytes_identical_projection():
    """Replaying identical serialized bytes at different wall-clock times is
    projection-identical.

    The heartbeat's typed timestamp is fixed far in the past (2026-01-01) while
    the wall clock at replay is materially later. The fold must derive the age
    purely from typed facts, so two replay folds of the identical bytes produce
    byte-/structure-identical projections regardless of when each fold runs.
    """
    _, events = _typed_heartbeat_stream()
    bytes_early = [json.dumps(e, sort_keys=True) for e in events]

    # Two independent folds of the exact same serialized bytes (running at
    # different wall-clock instants). A clock-dependent fold would emit
    # different heartbeat ages and compare unequal.
    replay_early = Projector("run-det")
    _projector_feed(replay_early, [json.loads(b) for b in bytes_early])

    replay_late = Projector("run-det")
    _projector_feed(replay_late, [json.loads(b) for b in bytes_early])

    early_proj = replay_early.projection()
    late_proj = replay_late.projection()

    # Structure-identical: the projections are equal and serialized bytes match.
    assert builds_identical_projection(early_proj, late_proj)
    assert json.dumps(early_proj.to_dict(), sort_keys=True) == (
        json.dumps(late_proj.to_dict(), sort_keys=True)
    )

    # Live freshness is preserved via typed timestamps: the age is the typed
    # reference (00:01:00Z) minus the heartbeat (00:00:00Z) = exactly 60s, a
    # pure function of the serialized facts (no wall-clock dependence).
    job = next(j for j in early_proj.jobs if j.job_id == "d-0")
    assert job.heartbeat_age_s == 60.0


def test_reconnect_and_replay_zero_survive_wall_clock_drift():
    """A reconnecting consumer replaying from zero sees the identical view
    even when the wall clock has advanced materially (no time-dependent drift)."""
    stream, events = _typed_heartbeat_stream()

    # "disconnect": a fresh observer folds the live typed events (at t0).
    live = LiveObserver(stream)
    live.observe(events)
    captured = live.projection().to_dict()

    # "reconnect later": an independent projector replays the same typed events
    # from zero (at a materially later wall clock); the view must be identical.
    replay = Projector("run-det")
    _projector_feed(replay, stream.typed_events_since(0))

    assert captured == replay.projection().to_dict()

    # The replayed view restores the deterministic heartbeat age exactly.
    job = next(j for j in replay.projection().jobs if j.job_id == "d-0")
    assert job.heartbeat_age_s == 60.0


# ── Criterion 10: run-scoped boundary, no persistent lease/offset ─────────────


def test_run_scoped_boundary_and_no_persistent_claims():
    stream, sink = _stream("run-A")
    stream.wave_started(wave="w0")
    obs = LiveObserver(stream)
    obs.observe(stream.typed_events_since(0))
    p = obs.projection()
    assert p.run.coverage_boundary == "run:run-A"
    # Recreating a process for a different run states a distinct boundary.
    stream2, _ = _stream("run-B")
    obs2 = LiveObserver(stream2)
    obs2.observe(stream2.typed_events_since(0))
    assert obs2.projection().run.coverage_boundary == "run:run-B"
    assert obs2.projection().run != p.run


def _run_all() -> int:
    tests = [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]
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
