"""Tests for PhaseContext and HookResult dataclasses."""

import json
import pytest
from skillweave.studio.hooks.models import (
    PhaseContext, HookResult, Phase, Position,
)


class TestPhaseContext:
    def test_create_minimal(self):
        ctx = PhaseContext(phase=Phase.BUILD, position=Position.PRE)
        assert ctx.phase == Phase.BUILD
        assert ctx.position == Position.PRE
        assert ctx.gate_decision is None
        assert ctx.project_root == "."

    def test_create_full(self):
        ctx = PhaseContext(
            phase=Phase.TEST,
            position=Position.POST,
            gate_decision=True,
            project_root="/tmp/project",
            config={"mode": "medium"},
            hook_config={"timeout_sec": 30},
        )
        assert ctx.gate_decision is True
        assert ctx.config["mode"] == "medium"
        assert ctx.hook_config["timeout_sec"] == 30

    def test_immutable(self):
        ctx = PhaseContext(phase=Phase.BUILD, position=Position.PRE)
        with pytest.raises(AttributeError):
            ctx.phase = Phase.TEST  # type: ignore[misc]

    def test_to_dict(self):
        ctx = PhaseContext(phase=Phase.DISCOVERY, position=Position.PRE, gate_decision=False)
        d = ctx.to_dict()
        assert d["phase"] == "discovery"
        assert d["position"] == "pre"
        assert d["gate_decision"] is False

    def test_to_json_roundtrip(self):
        ctx = PhaseContext(
            phase=Phase.RELEASE,
            position=Position.POST,
            gate_decision=True,
            project_root="/app",
            config={"tier": "studio"},
            hook_config={"retry": 3},
        )
        j = ctx.to_json()
        data = json.loads(j)
        ctx2 = PhaseContext.from_dict(data)
        assert ctx2.phase == ctx.phase
        assert ctx2.position == ctx.position
        assert ctx2.gate_decision == ctx.gate_decision
        assert ctx2.project_root == ctx.project_root
        assert ctx2.config == ctx.config
        assert ctx2.hook_config == ctx.hook_config

    def test_from_dict_minimal(self):
        ctx = PhaseContext.from_dict({"phase": "build", "position": "pre"})
        assert ctx.phase == Phase.BUILD
        assert ctx.project_root == "."

    def test_as_env(self):
        ctx = PhaseContext(phase=Phase.LAUNCH, position=Position.POST, gate_decision=True, project_root="/srv")
        env = ctx.as_env()
        assert env["SKILLWEAVE_PHASE"] == "launch"
        assert env["SKILLWEAVE_POSITION"] == "post"
        assert env["SKILLWEAVE_GATE_DECISION"] == "True"
        assert env["SKILLWEAVE_PROJECT_ROOT"] == "/srv"

    def test_as_env_no_gate(self):
        ctx = PhaseContext(phase=Phase.BUILD, position=Position.PRE)
        env = ctx.as_env()
        assert env["SKILLWEAVE_GATE_DECISION"] == ""


class TestHookResult:
    def test_pass(self):
        r = HookResult(status="pass", message="All good")
        assert r.passed
        assert not r.failed
        assert r.gate_override is None

    def test_fail(self):
        r = HookResult(status="fail", message="Broken")
        assert r.failed
        assert not r.passed

    def test_skip(self):
        r = HookResult(status="skip")
        assert not r.passed
        assert not r.failed

    def test_gate_override_true(self):
        r = HookResult(status="pass", gate_override=True)
        assert r.gate_override is True

    def test_gate_override_false(self):
        r = HookResult(status="fail", gate_override=False)
        assert r.gate_override is False

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="Invalid HookStatus"):
            HookResult(status="maybe")  # type: ignore[arg-type]

    def test_invalid_gate_override_raises(self):
        with pytest.raises(TypeError, match="gate_override must be bool"):
            HookResult(status="pass", gate_override="yes")  # type: ignore[arg-type]

    def test_artifacts(self):
        r = HookResult(status="pass", artifacts=["/tmp/report.html", "/tmp/coverage.xml"])
        assert len(r.artifacts) == 2

    def test_to_dict(self):
        r = HookResult(status="fail", message="timeout", gate_override=False)
        d = r.to_dict()
        assert d == {"status": "fail", "message": "timeout", "artifacts": [], "gate_override": False}
