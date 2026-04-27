import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skillweave.execution.batch_planner import BatchPlanner, BatchPlan, BatchSpec
from skillweave.execution.state_machine import (
    RalphLoopStateMachine, RalphLoopState, StatePreflight, StateBatchSelection,
    StateLanePlan, StateImplement, StateVerify, StateReviewGate,
    StateFixRetry, StateIntegrate, StateAdvanceOrStop, run_state_handler,
)
from skillweave.execution.retry import RetryHandler, RetryBudget, RetryBudgetExhaustedError
from skillweave.execution.gate_policy import GatePolicy, BinaryGateResult
from skillweave.execution_checklist import ChecklistLoopEngine
from skillweave.execution_memory import ExecutionMemory, MEMORY_CATEGORIES
from skillweave.observation.event_logger import EventLogger, LogLevel
from skillweave.observation.timing import Timer, TimingContext
from skillweave.observation.report_generator import ReportGenerator
from skillweave.sidecar_manager import SidecarManager, SidecarSpec
from skillweave.execution_integration import ExecutionIntegration


# --- Batch Planner Tests ---

def test_batch_planner_create_plan():
    with tempfile.TemporaryDirectory() as tmpdir:
        planner = BatchPlanner(tmpdir)
        batches = [
            BatchSpec(name="B1", steps=["step1", "step2"], mode="sequential"),
            BatchSpec(name="B2", steps=["step3"], mode="parallel"),
        ]
        plan = planner.create_plan(batches, metadata={"version": "1.0"})
        assert len(plan.batches) == 2
        assert plan.batches[0].name == "B1"
        assert plan.batches[1].steps == ["step3"]


def test_batch_planner_load_plan():
    with tempfile.TemporaryDirectory() as tmpdir:
        planner = BatchPlanner(tmpdir)
        batches = [BatchSpec(name="B1", steps=["a", "b"])]
        planner.create_plan(batches)
        loaded = planner.load_plan()
        assert loaded is not None
        assert loaded.batches[0].name == "B1"


def test_batch_planner_get_current_batch():
    with tempfile.TemporaryDirectory() as tmpdir:
        planner = BatchPlanner(tmpdir)
        batches = [
            BatchSpec(name="B1", steps=["s1"]),
            BatchSpec(name="B2", steps=["s2", "s3"]),
        ]
        planner.create_plan(batches)
        current = planner.get_current_batch([])
        assert current is not None
        assert current.name == "B1"

        current = planner.get_current_batch(["s1"])
        assert current is not None
        assert current.name == "B2"

        current = planner.get_current_batch(["s1", "s2", "s3"])
        assert current is None


def test_batch_plan_json_roundtrip():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "plan.json"
        plan = BatchPlan(batches=[BatchSpec(name="B1", steps=["x"])])
        plan.to_json_file(path)
        loaded = BatchPlan.from_json_file(path)
        assert loaded.batches[0].name == "B1"


# --- State Machine Tests ---

def test_state_machine_initial_state():
    sm = RalphLoopStateMachine()
    assert sm.current_state == RalphLoopState.PREFLIGHT


def test_state_machine_valid_transitions():
    sm = RalphLoopStateMachine()
    assert sm.can_transition_to(RalphLoopState.BATCH_SELECTION)
    assert not sm.can_transition_to(RalphLoopState.ADVANCE_OR_STOP)


def test_state_machine_full_loop():
    sm = RalphLoopStateMachine()
    states = [
        RalphLoopState.PREFLIGHT,
        RalphLoopState.BATCH_SELECTION,
        RalphLoopState.LANE_PLAN,
        RalphLoopState.IMPLEMENT,
        RalphLoopState.VERIFY,
        RalphLoopState.REVIEW_GATE,
        RalphLoopState.INTEGRATE,
        RalphLoopState.ADVANCE_OR_STOP,
    ]
    for s in states:
        if s == RalphLoopState.PREFLIGHT:
            continue
        assert sm.transition_to(s, f"Moving to {s.value}"), f"Failed transition to {s.value}"

    assert sm.is_terminal()
    assert sm.current_state == RalphLoopState.ADVANCE_OR_STOP
    assert len(sm.transitions) == 7


def test_state_machine_invalid_transition():
    sm = RalphLoopStateMachine()
    result = sm.transition_to(RalphLoopState.ADVANCE_OR_STOP)
    assert not result
    assert sm.current_state == RalphLoopState.PREFLIGHT


def test_state_machine_reset():
    sm = RalphLoopStateMachine()
    sm.transition_to(RalphLoopState.BATCH_SELECTION)
    sm.reset()
    assert sm.current_state == RalphLoopState.PREFLIGHT
    assert len(sm.transitions) == 0


def test_state_machine_summary():
    sm = RalphLoopStateMachine()
    sm.transition_to(RalphLoopState.BATCH_SELECTION, "ready")
    summary = sm.summary()
    assert summary["current_state"] == "batch_selection"
    assert summary["transition_count"] == 1
    assert summary["is_terminal"] is False


def test_state_handlers():
    handlers = [
        (StatePreflight(), {"preflight_checks": []}),
        (StateBatchSelection(), {"next_batch": "B1"}),
        (StateLanePlan(), {"lane_steps": ["a", "b"]}),
        (StateImplement(), {"implementation_results": {"ok": True}}),
        (StateVerify(), {"verification_passed": True}),
        (StateReviewGate(), {"gate_passed": True}),
        (StateFixRetry(), {"retry_count": 1}),
        (StateIntegrate(), {"integration_merged": True}),
        (StateAdvanceOrStop(), {"final_state": "stopped"}),
    ]
    for handler, ctx in handlers:
        result = handler.execute(ctx)
        assert "status" in result


def test_run_state_handler():
    from skillweave.execution.state_machine import StatePreflight, RalphLoopState
    handler = StatePreflight()
    result = handler.execute({})
    assert result["status"] == "ready"


def test_run_state_handler_invalid():
    result = run_state_handler("invalid_state", {})
    assert result["status"] == "error"


# --- Retry Tests ---

def test_retry_budget_initial():
    r = RetryBudget(max_retries=3)
    assert r.can_retry()
    assert r.retry_count == 0


def test_retry_budget_exhaustion():
    r = RetryBudget(max_retries=2)
    r.record_attempt(success=False, error="fail 1")
    assert r.can_retry()
    r.record_attempt(success=False, error="fail 2")
    assert not r.can_retry()
    assert r.retry_count == 2
    assert r.last_error == "fail 2"


def test_retry_budget_success():
    r = RetryBudget(max_retries=3)
    r.record_attempt(success=True)
    assert r.can_retry()
    assert r.retry_count == 1
    assert r.last_error is None


def test_retry_budget_reset():
    r = RetryBudget(max_retries=3)
    r.record_attempt(success=False, error="err")
    r.reset()
    assert r.can_retry()
    assert r.retry_count == 0
    assert r.last_error is None


def test_retry_budget_summary():
    r = RetryBudget(max_retries=3)
    r.record_attempt(success=False, error="err")
    summary = r.summary()
    assert summary["max_retries"] == 3
    assert summary["retry_count"] == 1
    assert summary["exhausted"] is False


def test_retry_handler_executes_success():
    handler = RetryHandler(max_retries=3)

    def succeed(_=None):
        return "ok"

    success, result = handler.execute(succeed)
    assert success
    assert result == "ok"


def test_retry_handler_exhausts():
    handler = RetryHandler(max_retries=2)
    call_count = 0

    def always_fail(_=None):
        nonlocal call_count
        call_count += 1
        raise ValueError(f"fail #{call_count}")

    success, result = handler.execute(always_fail)
    assert not success
    assert call_count == 2
    assert isinstance(result, RetryBudgetExhaustedError)


def test_retry_handler_eventual_success():
    handler = RetryHandler(max_retries=3)
    call_count = 0

    def fail_twice(_=None):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError(f"fail #{call_count}")
        return "eventual_ok"

    success, result = handler.execute(fail_twice)
    assert success
    assert result == "eventual_ok"
    assert call_count == 3


# --- Gate Policy Tests ---

def test_gate_policy_binary_all_pass():
    policy = GatePolicy("test")
    result = policy.evaluate_binary([(True, "check1"), (True, "check2")])
    assert result.passed
    assert "passed all" in result.reason


def test_gate_policy_binary_fail():
    policy = GatePolicy("test")
    result = policy.evaluate_binary([(True, "check1"), (False, "check2 failed")])
    assert not result.passed
    assert "check2 failed" in result.reason


def test_gate_policy_history():
    policy = GatePolicy("test")
    policy.evaluate_binary([(True, "ok")])
    policy.evaluate_binary([(False, "not ok")])
    assert len(policy.history) == 2
    assert policy.history[0].passed
    assert not policy.history[1].passed


def test_gate_policy_summary():
    policy = GatePolicy("test")
    policy.evaluate_binary([(True, "ok")])
    summary = policy.summary()
    assert summary["name"] == "test"
    assert summary["total_evaluations"] == 1


def test_binary_gate_result_to_dict():
    result = BinaryGateResult(passed=True, reason="all good", details=["detail1"])
    d = result.to_dict()
    assert d["passed"] is True
    assert d["reason"] == "all good"


# --- Checklist Loop Engine Tests ---

def test_checklist_loop_parse_nested():
    engine = ChecklistLoopEngine()
    md = "- [ ] Item 1\n  - [ ] Sub 1.1\n- [x] Item 2\n- [ ] Item 3"
    parsed = engine.parse_nested_markdown(md)
    assert len(parsed["items"]) == 3
    assert parsed["items"][0]["checked"] is False
    assert parsed["items"][1]["checked"] is True
    assert len(parsed["items"][0]["children"]) == 1


def test_checklist_loop_find_next_unchecked():
    engine = ChecklistLoopEngine()
    md = "- [x] Item 1\n- [ ] Item 2\n  - [ ] Sub 2.1\n- [ ] Item 3"
    parsed = engine.parse_nested_markdown(md)
    next_item = engine.find_next_unchecked(parsed)
    assert next_item is not None
    assert next_item["text"] == "Sub 2.1"  # depth-first: Item 2's children before Item 3


def test_checklist_loop_find_next_unchecked_nested():
    engine = ChecklistLoopEngine()
    md = "- [x] Item 1\n- [x] Item 2\n  - [ ] Sub 2.1\n- [ ] Item 3"
    parsed = engine.parse_nested_markdown(md)
    next_item = engine.find_next_unchecked(parsed)
    assert next_item is not None
    assert next_item["text"] == "Sub 2.1"


def test_checklist_loop_mark_complete():
    engine = ChecklistLoopEngine()
    md = "- [ ] Item 1\n- [ ] Item 2"
    result = engine.mark_complete(md, "Item 1")
    assert "[x] Item 1" in result
    assert "[ ] Item 2" in result


def test_checklist_loop_mark_failed():
    engine = ChecklistLoopEngine()
    md = "- [ ] Item 1"
    result = engine.mark_failed(md, "Item 1", "test error")
    assert "FAILED: test error" in result


def test_checklist_loop_blocker_detection():
    engine = ChecklistLoopEngine()
    md = "- [ ] BLOCKER: dependency missing\n- [ ] Item 2"
    parsed = engine.parse_nested_markdown(md)
    blocker = engine.check_for_blocker(parsed)
    assert blocker is not None
    assert blocker.get("is_blocker")


def test_checklist_loop_flatten_items():
    engine = ChecklistLoopEngine()
    md = "- [ ] Item 1\n  - [ ] Sub 1.1\n    - [ ] Sub 1.1.1\n- [ ] Item 2"
    parsed = engine.parse_nested_markdown(md)
    flat = engine.flatten_items(parsed)
    assert len(flat) == 4
    assert flat[0]["depth"] == 0
    assert flat[1]["depth"] == 1
    assert flat[2]["depth"] == 2


def test_checklist_loop_execute():
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ChecklistLoopEngine(tmpdir)
        md = "- [ ] Task 1\n- [ ] Task 2"
        md_path = Path(tmpdir) / ".skillweave" / "checklists" / "test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md)

        executed = []

        def executor(item_text, item_context):
            executed.append(item_text)
            return True

        result = engine.execute_loop(executor, filename="test.md")
        assert result["status"] == "complete"
        assert result["completed"] == 2
        assert "Task 1" in executed
        assert "Task 2" in executed


# --- Memory Tests ---

def test_memory_write_and_read():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ExecutionMemory(tmpdir)
        entry = mem.write_entry("decisions", "Use YAML for config", source="test")
        assert entry["content"] == "Use YAML for config"
        assert entry["source"] == "test"

        all_data = mem.read_all()
        assert "decisions" in all_data
        assert len(all_data["decisions"]) == 1


def test_memory_category_filter():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ExecutionMemory(tmpdir)
        mem.write_entry("rules", "Rule 1", tags=["important"])
        mem.write_entry("decisions", "Decision 1")
        mem.write_entry("rules", "Rule 2", tags=["important"])

        rules = mem.read_category("rules")
        assert len(rules) == 2

        decisions = mem.read_category("decisions")
        assert len(decisions) == 1


def test_memory_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ExecutionMemory(tmpdir)
        mem.write_entry("decisions", "Use Python type hints everywhere")
        mem.write_entry("rules", "No circular imports")

        results = mem.search("Python")
        assert len(results) >= 1
        assert results[0]["category"] == "decisions"


def test_memory_search_by_tag():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ExecutionMemory(tmpdir)
        mem.write_entry("rules", "Rule 1", tags=["high-priority"])
        mem.write_entry("decisions", "Decision 1", tags=["low-priority"])

        results = mem.search_by_tag("high-priority")
        assert len(results) == 1
        assert results[0]["category"] == "rules"


def test_memory_count_entries():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ExecutionMemory(tmpdir)
        mem.write_entry("rules", "Rule 1")
        mem.write_entry("rules", "Rule 2")
        mem.write_entry("decisions", "Decision 1")

        counts = mem.count_entries()
        assert counts["rules"] == 2
        assert counts["decisions"] == 1


def test_memory_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ExecutionMemory(tmpdir)
        mem.write_entry("rules", "Rule 1")
        summary = mem.summary()
        assert summary["total_entries"] == 1
        assert summary["categories"] == MEMORY_CATEGORIES


def test_memory_invalid_category():
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ExecutionMemory(tmpdir)
        try:
            mem.write_entry("invalid_cat", "content")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass


# --- Event Logger Tests ---

def test_event_logger_info():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = EventLogger(tmpdir)
        entry = logger.info("test message", step_id="step1")
        assert entry.level == LogLevel.INFO
        assert entry.message == "test message"
        assert entry.step_id == "step1"


def test_event_logger_levels():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = EventLogger(tmpdir)
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warn msg")
        logger.error("error msg")

        entries = logger.get_entries()
        assert len(entries) == 4

        errors = logger.get_entries(level=LogLevel.ERROR)
        assert len(errors) == 1


def test_event_logger_metric():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = EventLogger(tmpdir)
        entry = logger.metric("execution_time", 1.5, step_id="step1", tags={"unit": "s"})
        assert entry.level == LogLevel.METRIC
        assert entry.context["metric_name"] == "execution_time"
        assert entry.context["metric_value"] == 1.5


def test_event_logger_filter():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = EventLogger(tmpdir)
        logger.info("step 1", step_id="s1")
        logger.info("step 2", step_id="s2")
        logger.info("step 1 again", step_id="s1")

        s1_entries = logger.get_entries(step_id="s1")
        assert len(s1_entries) == 2


# --- Timer Tests ---

def test_timer_start_stop():
    timer = Timer()
    timer.start("test")
    time.sleep(0.01)
    elapsed = timer.stop()
    assert elapsed > 0.005
    assert elapsed < 1.0


def test_timer_lap():
    timer = Timer()
    timer.start("first")
    time.sleep(0.01)
    timer.lap("second")
    time.sleep(0.01)
    timer.stop()
    assert len(timer.records) == 2


def test_timing_context():
    timer = Timer()
    with TimingContext(timer, "context_test"):
        time.sleep(0.01)
    assert len(timer.records) == 1
    assert timer.records[0].name == "context_test"
    assert timer.records[0].elapsed is not None


def test_timer_summary():
    timer = Timer()
    with TimingContext(timer, "task"):
        time.sleep(0.01)
    summary = timer.summary()
    assert summary["total_records"] == 1
    assert summary["total_elapsed"] > 0


# --- Report Generator Tests ---

def test_report_generates():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = EventLogger(tmpdir)
        timer = Timer()
        reporter = ReportGenerator(tmpdir)

        logger.info("started", step_id="s1")
        logger.error("failed", step_id="s2")
        logger.metric("speed", 10.0, step_id="s1")

        with TimingContext(timer, "session"):
            time.sleep(0.01)

        report = reporter.generate_report("test-session", timer, logger)
        assert report["session_id"] == "test-session"
        assert report["event_counts"]["total"] == 3
        assert report["event_counts"]["error"] == 1
        assert report["event_counts"]["metric"] == 1
        assert report["timing"]["total_records"] == 1


def test_metrics_yaml_generated():
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = EventLogger(tmpdir)
        reporter = ReportGenerator(tmpdir)

        logger.metric("time", 5.0, step_id="s1")
        logger.metric("tokens", 100, step_id="s1")

        path = reporter.generate_metrics_yaml(logger)
        assert path.exists()
        content = path.read_text()
        assert "time" in content


# --- Sidecar Manager Tests ---

def test_sidecar_launch_and_complete():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SidecarManager(tmpdir)

        def worker(data):
            return {"result": data.get("x", 0) * 2}

        spec = SidecarSpec(name="double", fn=worker, input_data={"x": 21})
        result = manager.launch(spec)
        assert result.status == "running"

        completed = manager.wait_for("double", timeout=5.0)
        assert completed is not None
        assert completed.status == "completed"
        assert completed.output == {"result": 42}


def test_sidecar_failure():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SidecarManager(tmpdir)

        def failing_worker(data):
            raise RuntimeError("sidecar error")

        spec = SidecarSpec(name="failer", fn=failing_worker)
        manager.launch(spec)
        result = manager.wait_for("failer", timeout=5.0)
        assert result is not None
        assert result.status == "failed"
        assert "sidecar error" in result.error


def test_sidecar_timeout():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SidecarManager(tmpdir)

        def slow_worker(data):
            time.sleep(10)

        spec = SidecarSpec(name="slow", fn=slow_worker, timeout=0.1)
        manager.launch(spec)
        result = manager.wait_for("slow", timeout=2.0)
        assert result is not None
        assert result.status == "timeout"


def test_sidecar_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SidecarManager(tmpdir)

        def worker(data):
            return {"ok": True}

        manager.launch(SidecarSpec(name="w1", fn=worker, timeout=5.0))
        manager.wait_for("w1", timeout=5.0)

        summary = manager.summary()
        assert summary["total"] == 1
        assert summary["completed"] == 1


# --- Integration Tests ---

def test_integration_disabled_by_default():
    with tempfile.TemporaryDirectory() as tmpdir:
        integration = ExecutionIntegration(tmpdir, enabled=False)
        result = integration.run_batch(BatchSpec(name="B1", steps=["s1"]), lambda s, c: True)
        assert result["status"] == "disabled"


def test_integration_batch_all_pass():
    with tempfile.TemporaryDirectory() as tmpdir:
        integration = ExecutionIntegration(tmpdir, enabled=True)
        executed = []

        def executor(step_id, context):
            executed.append(step_id)
            return True

        result = integration.run_batch(BatchSpec(name="B1", steps=["s1", "s2"]), executor)
        assert result["gate_result"]["passed"] is True
        assert len(executed) == 2


def test_integration_batch_with_failure():
    with tempfile.TemporaryDirectory() as tmpdir:
        integration = ExecutionIntegration(tmpdir, enabled=True)

        def executor(step_id, context):
            return step_id != "s2"

        result = integration.run_batch(BatchSpec(name="B1", steps=["s1", "s2", "s3"]), executor)
        assert result["gate_result"]["passed"] is False
        assert "s2" in result["gate_result"]["reason"]


def test_integration_memory():
    with tempfile.TemporaryDirectory() as tmpdir:
        integration = ExecutionIntegration(tmpdir, enabled=True)
        entry = integration.record_memory("decisions", "test decision", source="test")
        assert entry["content"] == "test decision"

        results = integration.query_memory("test", category="decisions")
        assert len(results) == 1


def test_integration_checklist():
    with tempfile.TemporaryDirectory() as tmpdir:
        integration = ExecutionIntegration(tmpdir, enabled=True)
        md = "- [ ] Step A\n- [ ] Step B"
        md_path = Path(tmpdir) / ".skillweave" / "checklists" / "integ-test.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(md)

        executed = []

        def executor(item, ctx):
            executed.append(item)
            return True

        result = integration.run_checklist_loop(executor, filename="integ-test.md")
        assert result["status"] == "complete"
        assert len(executed) == 2


def test_integration_sidecar():
    with tempfile.TemporaryDirectory() as tmpdir:
        integration = ExecutionIntegration(tmpdir, enabled=True)

        def worker(data):
            return {"processed": True}

        result = integration.launch_sidecar("test-sc", worker, timeout=5.0)
        assert result["status"] in ("running", "completed")


def test_integration_report():
    with tempfile.TemporaryDirectory() as tmpdir:
        integration = ExecutionIntegration(tmpdir, enabled=True)

        def executor(s, c):
            return True

        integration.run_batch(BatchSpec(name="test", steps=["a"]), executor)
        report = integration.generate_report("integration-test")
        assert report["session_id"] == "integration-test"
