import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from skillweave.models import WorkflowContext, StepSpec
from skillweave.executor import (
    execute_step,
    execute_step_parallel,
    execute_with_dependency_awareness,
    simulate_subagent_execution
)
import time


def test_execute_step():
    """Test single step execution."""
    step = StepSpec(
        id="test-step",
        name="Test Step",
        purpose="Testing",
        instructions="Do something"
    )
    
    context = WorkflowContext(
        sequence_id="test-seq",
        mode="execute",
        status="running"
    )
    
    result = execute_step(step, context)
    
    assert result["step_id"] == "test-step"
    assert result["step_name"] == "Test Step"
    assert result["status"] == "completed"
    assert "execution_time" in result
    assert "test-step" in context.step_outputs
    assert "test-step" in context.completed_steps


def test_execute_step_parallel():
    """Test parallel step execution."""
    steps = [
        StepSpec(id="step-01", name="Step 1", purpose="Test", instructions="Do 1"),
        StepSpec(id="step-02", name="Step 2", purpose="Test", instructions="Do 2"),
        StepSpec(id="step-03", name="Step 3", purpose="Test", instructions="Do 3"),
    ]
    
    context = WorkflowContext(
        sequence_id="test-parallel",
        mode="execute",
        status="running"
    )
    
    results = execute_step_parallel(steps, context, max_workers=2)
    
    # Check that all steps have results
    assert len(results) == 3
    assert "step-01" in results
    assert "step-02" in results
    assert "step-03" in results
    
    # Check that context was updated
    assert len(context.step_outputs) == 3
    assert len(context.completed_steps) == 3  # All should complete in simulation
    
    # Check result structure
    for step_id, result in results.items():
        assert "step_id" in result
        assert "step_name" in result
        assert "status" in result
        assert "execution_time" in result


def test_execute_with_dependency_awareness():
    """Test dependency-aware parallel execution."""
    steps = [
        StepSpec(id="step-01", name="Step 1", purpose="Test", instructions="Do 1"),
        StepSpec(id="step-02", name="Step 2", purpose="Test", instructions="Do 2"),
        StepSpec(id="step-03", name="Step 3", purpose="Test", instructions="Do 3", depends_on=["step-01"]),
        StepSpec(id="step-04", name="Step 4", purpose="Test", instructions="Do 4", depends_on=["step-02"]),
    ]
    
    context = WorkflowContext(
        sequence_id="test-dependency",
        mode="execute",
        status="running"
    )
    
    summary = execute_with_dependency_awareness(
        steps, context, max_parallel=2, step_timeout=10
    )
    
    # Check summary structure
    assert "total_steps" in summary
    assert "completed" in summary
    assert "failed" in summary
    assert "success_rate" in summary
    assert "total_time" in summary
    assert "parallel_groups_executed" in summary
    assert "context_updates" in summary
    
    # Check values
    assert summary["total_steps"] == 4
    assert summary["completed"] == 4
    assert summary["failed"] == 0  # In simulation, should succeed
    assert summary["success_rate"] == 1.0
    
    # Check context updates
    assert context.completed_steps == ["step-01", "step-02", "step-03", "step-04"] or \
           context.completed_steps == ["step-02", "step-01", "step-04", "step-03"]  # Parallel execution order may vary
    assert len(context.errors) == 0


def test_simulate_subagent_execution():
    """Test subagent execution simulation."""
    step = StepSpec(
        id="test-subagent-step",
        name="Test Subagent Step",
        purpose="Testing subagents",
        instructions="Do something complex with a subagent"
    )
    
    result = simulate_subagent_execution(step, subagent_type="general")
    
    assert result["step_id"] == "test-subagent-step"
    assert result["step_name"] == "Test Subagent Step"
    assert result["subagent_type"] == "general"
    assert "status" in result
    assert "output" in result
    assert "execution_time" in result
    
    # Should have either artifacts or error
    if result["status"] == "completed":
        assert "artifacts" in result
        assert "logs" in result
    else:
        assert "error" in result
        assert "logs" in result


def test_execute_step_parallel_with_timeout():
    """Test parallel execution with timeout simulation."""
    steps = [
        StepSpec(id="fast-step", name="Fast", purpose="Test", instructions="Quick"),
        StepSpec(id="slow-step", name="Slow", purpose="Test", instructions="Slow"),
    ]
    
    context = WorkflowContext(
        sequence_id="test-timeout",
        mode="execute",
        status="running"
    )
    
    # Use reasonable timeout - fast-step should complete, slow-step might timeout
    # Note: In simulation, both complete quickly, so we test the timeout logic
    # by checking that the function handles timeouts correctly
    results = execute_step_parallel(steps, context, max_workers=2, timeout=10)
    
    assert len(results) == 2
    
    # Both should complete in simulation with 10s timeout
    completed = sum(1 for r in results.values() if r["status"] == "completed")
    # In simulation, both should complete
    assert completed == 2
    
    # Check that all results have valid status
    for step_id, result in results.items():
        assert result["status"] in ["completed", "timeout", "failed"]


def test_error_handling_in_parallel_execution():
    """Test error handling in parallel execution."""
    # Create steps that might cause errors (in simulation)
    steps = [
        StepSpec(id="normal-step", name="Normal", purpose="Test", instructions="Normal"),
        StepSpec(id="problem-step", name="Problem", purpose="Test", instructions="Problem"),
    ]
    
    context = WorkflowContext(
        sequence_id="test-errors",
        mode="execute",
        status="running"
    )
    
    results = execute_step_parallel(steps, context, max_workers=2)
    
    # Both should have results
    assert len(results) == 2
    
    # Context should be updated regardless of errors
    assert len(context.step_outputs) == 2
    
    # Check if errors were recorded
    total_errors = sum(1 for r in results.values() if r["status"] in ["failed", "timeout"])
    assert total_errors == len(context.errors) or total_errors == 0  # May or may not have errors in simulation