"""SW138-REM-GATE-001 (C2): focused exception + config regression tests.

These are the *focused* proofs for the second bounded correction round. They pin
the three controller failures called out in the C2 brief:

1. Determinstic cleanup: a fan-out that raises *after* walking the ``started``
   lifecycle callback (so a live :class:`HeartbeatPump` cadence thread exists)
   must stop and join that pump before the original exception propagates — no
   ``sw-heartbeat-*`` thread remains and no heartbeat may appear after the
   application function returns.
2. Config validation: ``heartbeat_interval`` must be a finite positive number.
   ``0``, negatives, ``NaN``, ``+Inf`` and ``-Inf`` are rejected synchronously
   at load/resolution, before workspace provisioning or worker launch — never
   silently coerced to the positive default.
3. Passive observation: an exception from ``on_child_lifecycle`` must never
   leave a started child unreaped. The fan-out reaps every started child and
   only then surfaces a typed :class:`LifecycleObservationError`.

The gate aggregate test still runs the full C1 behaviour; these tests are the
sharp, isolated regression pins for the new paths only.
"""

from __future__ import annotations

import io
import math
import sys
import threading
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.dispatch.application import (  # noqa: E402
    OperatorDispatchApplication,
    ProvisionedWorkspace,
)
from skillweave.dispatch.profile_resolution import (  # noqa: E402
    ProfileResolutionError,
    resolve_limits,
)
from skillweave.fanout.dispatch import (  # noqa: E402
    LifecycleObservationError,
    fan_out_dispatch,
)
from skillweave.routing.profile import Limits, RoutingProfileError  # noqa: E402

_FULL_A = "953aab4ec8f7babf0857c0033fd7731c8dc16e92"


class _NoopWorkspace:
    def provision(self, lane, run_id):
        return ProvisionedWorkspace(base_sha=lane.base or "", path=None)

    def release(self, lane, run_id):
        pass


class _AliveHandle:
    """A minimal live-handle stand-in: ``process.poll()`` returns ``None``."""

    class _Process:
        def poll(self):
            return None

    def __init__(self):
        self.process = self._Process()


def _heartbeat_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.startswith("sw-heartbeat-")]


def _profile(heartbeat_interval=0.3):
    import yaml

    limits = {
        "timeout": 30.0,
        "max_retries": 1,
        "min_models_required": 2,
        "on_model_failure": "skip",
    }
    if heartbeat_interval is not None:
        limits["heartbeat_interval"] = heartbeat_interval
    return yaml.safe_dump(
        {
            "name": "gate-c2",
            "tier": "balanced",
            "limits": limits,
            "roles": {
                "ops": {
                    "model": "faigate/dispatch-fixture-model",
                    "tool": {
                        "name": "marker",
                        "launch_command": "python3 -c 'pass'",
                        "args": [],
                    },
                    "capabilities": {"can_mutate_run_state": True},
                },
            },
        }
    )


def _sequence(prof_path, multi=False):
    import yaml

    lanes = [
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
    ]
    if multi:
        lanes.append(
            {
                "id": "lane-b",
                "role": "ops",
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
            }
        )
    return yaml.safe_dump(
        {
            "session_boundary": "batch",
            "profile": {"path": str(prof_path), "required": True},
            "execution_model": "cold",
            "max_correction_rounds_per_wave": 0,
            "max_parallel": 2,
            "lanes": lanes,
        }
    )


# ── 1. deterministic cleanup: fan-out raises after ``started`` ─────────────


class _StartedThenRaiseFanout:
    """A fan-out seam that walks ``on_child_lifecycle(started)`` then raises.

    This reproduces the exact C1 controller failure: the ``started`` callback
    starts a live ``HeartbeatPump`` cadence thread, then the fan-out raises
    during wait/reap. The application must stop the pump before that exception
    propagates.
    """

    def __init__(self):
        self.calls = 0

    def __call__(self, commands, **kwargs):
        self.calls += 1
        lifecycle = kwargs.get("on_child_lifecycle")
        for index in range(len(commands)):
            lifecycle(
                child_key=f"run-{index}",
                dispatch_id=f"run-{index}",
                phase="started",
                handle=_AliveHandle(),
            )
        raise RuntimeError("fanout boom after started")


class _StartedThenRaiseInline:
    """An inline seam that walks ``on_child_lifecycle(started)`` then raises.

    The serialized single lane travels the *inline* seam, not the fan-out seam.
    This reproduces the same controller failure on that distinct path: the
    ``started`` callback starts a live ``HeartbeatPump`` cadence thread, then
    the seam raises before returning. The application must stop the pump before
    that exception propagates.
    """

    def __init__(self):
        self.calls = 0

    def __call__(self, command, **kwargs):
        self.calls += 1
        lifecycle = kwargs.get("on_child_lifecycle")
        run_id = kwargs.get("run_id")
        lifecycle(
            child_key=f"{run_id}-0",
            dispatch_id=f"{run_id}-0",
            phase="started",
            handle=_AliveHandle(),
        )
        raise RuntimeError("inline boom after started")


def test_single_lane_inline_exception_stops_heartbeat_pump(tmp_path):
    prof = tmp_path / "p.yaml"
    prof.write_text(_profile(), encoding="utf-8")
    seq = tmp_path / "s.yaml"
    seq.write_text(_sequence(prof), encoding="utf-8")

    inline = _StartedThenRaiseInline()
    app = OperatorDispatchApplication(
        workspace_seam=_NoopWorkspace(), inline_seam=inline
    )
    with pytest.raises(RuntimeError) as exc:
        app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())
    assert "inline boom after started" in str(exc.value)
    assert inline.calls == 1
    # No heartbeat cadence thread survives the exception.
    assert _heartbeat_threads() == []


def test_parallel_group_fanout_exception_stops_heartbeat_pumps(tmp_path):
    prof = tmp_path / "p.yaml"
    prof.write_text(_profile(), encoding="utf-8")
    seq = tmp_path / "s.yaml"
    seq.write_text(_sequence(prof, multi=True), encoding="utf-8")

    app = OperatorDispatchApplication(
        workspace_seam=_NoopWorkspace(), fanout_seam=_StartedThenRaiseFanout()
    )
    with pytest.raises(RuntimeError) as exc:
        app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())
    assert "fanout boom after started" in str(exc.value)
    assert _heartbeat_threads() == []


# ── 2. config validation: heartbeat_interval is finite + positive ───────────


@pytest.mark.parametrize(
    "bad",
    [0, -1, -0.5, float("nan"), float("inf"), float("-inf")],
)
def test_limits_from_dict_rejects_invalid_heartbeat_interval(bad):
    with pytest.raises(RoutingProfileError):
        Limits.from_dict({"heartbeat_interval": bad})


def test_limits_from_dict_accepts_finite_positive_heartbeat_interval():
    limits = Limits.from_dict({"heartbeat_interval": 0.25})
    assert limits.heartbeat_interval == 0.25
    # The default remains positive and finite.
    assert math.isfinite(Limits().heartbeat_interval)
    assert Limits().heartbeat_interval > 0


@pytest.mark.parametrize(
    "bad",
    [0, -1, float("nan"), float("inf"), float("-inf")],
)
def test_resolve_limits_rejects_invalid_heartbeat_override(bad):
    override = Limits(heartbeat_interval=bad)
    with pytest.raises(ProfileResolutionError):
        resolve_limits(Limits(), override)


def test_dispatch_rejects_invalid_heartbeat_before_provision(tmp_path):
    """An invalid explicit heartbeat_interval fails before provisioning/launch.

    The invalid value is refused at profile load (``Limits.from_dict``), which
    surfaces through the profile loader as the precise ``ProfileLocationError``
    product error — always synchronously, before any workspace is provisioned
    and before any worker launches.
    """
    from skillweave.dispatch.application import ProfileLocationError

    prof = tmp_path / "p.yaml"
    prof.write_text(_profile(heartbeat_interval=float("nan")), encoding="utf-8")
    seq = tmp_path / "s.yaml"
    seq.write_text(_sequence(prof), encoding="utf-8")

    class _RecordingWorkspace(_NoopWorkspace):
        def __init__(self):
            self.provisions = 0

        def provision(self, lane, run_id):
            self.provisions += 1
            return super().provision(lane, run_id)

    ws = _RecordingWorkspace()
    calls = {"n": 0}

    def fanout(commands, **kwargs):
        calls["n"] += 1
        return None

    app = OperatorDispatchApplication(workspace_seam=ws, fanout_seam=fanout)
    with pytest.raises(ProfileLocationError) as exc:
        app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())
    assert "heartbeat_interval" in str(exc.value)
    assert ws.provisions == 0
    assert calls["n"] == 0


def test_dispatch_rejects_zero_heartbeat_before_provision(tmp_path):
    from skillweave.dispatch.application import ProfileLocationError

    prof = tmp_path / "p.yaml"
    prof.write_text(_profile(heartbeat_interval=0), encoding="utf-8")
    seq = tmp_path / "s.yaml"
    seq.write_text(_sequence(prof), encoding="utf-8")

    app = OperatorDispatchApplication(workspace_seam=_NoopWorkspace())
    with pytest.raises(ProfileLocationError) as exc:
        app.dispatch(str(seq), str(prof), wave="0", sink=io.StringIO())
    assert "heartbeat_interval" in str(exc.value)


# ── 3. passive observation: callback failure never leaks a started child ────


def test_fanout_lifecycle_callback_failure_reaps_and_surfaces_typed_error():
    """An ``on_child_lifecycle`` that raises on ``started`` must not leave the
    started child unreaped: the fan-out still waits on the real process and
    raises ``LifecycleObservationError`` only after the reap loop finishes."""
    phases = {"seen_started": False, "reaped": False}

    def cb(child_key, dispatch_id, phase, handle):
        if phase == "started":
            phases["seen_started"] = True
            raise RuntimeError("observation failed")

    with pytest.raises(LifecycleObservationError) as exc:
        fan_out_dispatch(
            [[sys.executable, "-c", "import time; time.sleep(0.2)"]],
            run_id="gate-c2-lifecycle",
            subject_repo="skillweave/repo",
            subject_commit=_FULL_A,
            tool="marker",
            model="faigate/m",
            on_child_lifecycle=cb,
        )
    assert phases["seen_started"] is True
    assert "observation failed" in str(exc.value)


def test_fanout_lifecycle_callback_terminal_failure_surfaces_typed_error():
    """A failure on ``terminal`` (after the child was already reaped) is also a
    typed observation error, never a leaked child and never a silent success."""
    seen_terminal = {"value": False}

    def cb(child_key, dispatch_id, phase, handle):
        if phase == "terminal":
            seen_terminal["value"] = True
            raise RuntimeError("terminal observation failed")

    with pytest.raises(LifecycleObservationError):
        fan_out_dispatch(
            [[sys.executable, "-c", "pass"]],
            run_id="gate-c2-terminal",
            subject_repo="skillweave/repo",
            subject_commit=_FULL_A,
            tool="marker",
            model="faigate/m",
            on_child_lifecycle=cb,
        )
    assert seen_terminal["value"] is True
