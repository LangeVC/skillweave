import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from skillweave.models import PromptSequence, StepSpec
from skillweave.orchestrator import (
    initialize_context, next_step, analyze_dependencies,
    detect_circular_dependencies, get_available_steps,
    get_execution_groups, can_execute_in_parallel,
    get_parallel_execution_plan
)


def test_next_step_returns_first_eligible_step():
    seq = PromptSequence(
        metadata={},
        objective="x",
        success_criteria=[],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=[
            StepSpec(id="step-01", name="A", purpose="p", instructions="do"),
            StepSpec(id="step-02", name="B", purpose="p", instructions="do", depends_on=["step-01"]),
        ],
        final_assembly="done",
        validation_rules=[],
        failure_handling="stop",
        final_deliverable_format="md",
    )
    ctx = initialize_context("seq-1", "execute", {}, {})
    step = next_step(seq, ctx)
    assert step is not None
    assert step.id == "step-01"


def test_analyze_dependencies():
    """Test dependency graph analysis."""
    seq = PromptSequence(
        metadata={},
        objective="Test dependencies",
        success_criteria=[],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=[
            StepSpec(id="step-01", name="A", purpose="p", instructions="do"),
            StepSpec(id="step-02", name="B", purpose="p", instructions="do", depends_on=["step-01"]),
            StepSpec(id="step-03", name="C", purpose="p", instructions="do", depends_on=["step-01", "step-02"]),
        ],
        final_assembly="",
        validation_rules=[],
        failure_handling="",
        final_deliverable_format="",
    )
    
    deps = analyze_dependencies(seq)
    
    assert "step-01" in deps
    assert "step-02" in deps
    assert "step-03" in deps
    assert deps["step-01"] == set()
    assert deps["step-02"] == {"step-01"}
    assert deps["step-03"] == {"step-01", "step-02"}


def test_detect_circular_dependencies():
    """Test circular dependency detection."""
    # No circular dependencies
    deps1 = {
        "step-01": {"step-02"},
        "step-02": {"step-03"},
        "step-03": set()
    }
    cycles1 = detect_circular_dependencies(deps1)
    assert cycles1 == []
    
    # With circular dependency
    deps2 = {
        "step-01": {"step-02"},
        "step-02": {"step-03"},
        "step-03": {"step-01"}  # Circular
    }
    cycles2 = detect_circular_dependencies(deps2)
    assert len(cycles2) > 0
    assert any("step-01" in cycle and "step-02" in cycle and "step-03" in cycle for cycle in cycles2)


def test_get_available_steps():
    """Test getting available steps for execution."""
    seq = PromptSequence(
        metadata={},
        objective="Test available steps",
        success_criteria=[],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=[
            StepSpec(id="step-01", name="A", purpose="p", instructions="do"),
            StepSpec(id="step-02", name="B", purpose="p", instructions="do", depends_on=["step-01"]),
            StepSpec(id="step-03", name="C", purpose="p", instructions="do"),  # Independent
        ],
        final_assembly="",
        validation_rules=[],
        failure_handling="",
        final_deliverable_format="",
    )
    
    ctx = initialize_context("test-seq", "execute", {}, {})
    
    # Initially, steps without dependencies should be available
    available = get_available_steps(seq, ctx)
    available_ids = {step.id for step in available}
    assert "step-01" in available_ids
    assert "step-03" in available_ids
    assert "step-02" not in available_ids  # Depends on step-01
    
    # Mark step-01 as completed
    ctx.completed_steps.append("step-01")
    available = get_available_steps(seq, ctx)
    available_ids = {step.id for step in available}
    assert "step-02" in available_ids  # Now available
    assert "step-03" in available_ids  # Still available


def test_get_execution_groups():
    """Test grouping steps for parallel execution."""
    seq = PromptSequence(
        metadata={},
        objective="Test execution groups",
        success_criteria=[],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=[
            StepSpec(id="step-01", name="A", purpose="p", instructions="do"),
            StepSpec(id="step-02", name="B", purpose="p", instructions="do"),
            StepSpec(id="step-03", name="C", purpose="p", instructions="do", depends_on=["step-01"]),
            StepSpec(id="step-04", name="D", purpose="p", instructions="do", depends_on=["step-02"]),
            StepSpec(id="step-05", name="E", purpose="p", instructions="do", depends_on=["step-03", "step-04"]),
        ],
        final_assembly="",
        validation_rules=[],
        failure_handling="",
        final_deliverable_format="",
    )
    
    groups = get_execution_groups(seq)
    
    # Should have 3 groups:
    # Group 1: step-01, step-02 (parallel)
    # Group 2: step-03, step-04 (parallel after respective deps)
    # Group 3: step-05 (after step-03 and step-04)
    assert len(groups) == 3
    
    group1_ids = {step.id for step in groups[0]}
    group2_ids = {step.id for step in groups[1]}
    group3_ids = {step.id for step in groups[2]}
    
    assert group1_ids == {"step-01", "step-02"}
    assert group2_ids == {"step-03", "step-04"}
    assert group3_ids == {"step-05"}


def test_can_execute_in_parallel():
    """Test parallel execution capability detection."""
    # Sequence with parallel opportunities
    seq_parallel = PromptSequence(
        metadata={},
        objective="Test parallel",
        success_criteria=[],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=[
            StepSpec(id="step-01", name="A", purpose="p", instructions="do"),
            StepSpec(id="step-02", name="B", purpose="p", instructions="do"),
        ],
        final_assembly="",
        validation_rules=[],
        failure_handling="",
        final_deliverable_format="",
    )
    assert can_execute_in_parallel(seq_parallel) is True
    
    # Sequence without parallel opportunities
    seq_sequential = PromptSequence(
        metadata={},
        objective="Test sequential",
        success_criteria=[],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=[
            StepSpec(id="step-01", name="A", purpose="p", instructions="do"),
            StepSpec(id="step-02", name="B", purpose="p", instructions="do", depends_on=["step-01"]),
        ],
        final_assembly="",
        validation_rules=[],
        failure_handling="",
        final_deliverable_format="",
    )
    assert can_execute_in_parallel(seq_sequential) is False


def test_get_parallel_execution_plan():
    """Test parallel execution plan generation."""
    seq = PromptSequence(
        metadata={},
        objective="Test execution plan",
        success_criteria=[],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=[
            StepSpec(id="step-01", name="A", purpose="p", instructions="do"),
            StepSpec(id="step-02", name="B", purpose="p", instructions="do"),
            StepSpec(id="step-03", name="C", purpose="p", instructions="do", depends_on=["step-01"]),
        ],
        final_assembly="",
        validation_rules=[],
        failure_handling="",
        final_deliverable_format="",
    )
    
    plan = get_parallel_execution_plan(seq)
    
    assert "dependency_graph" in plan
    assert "execution_groups" in plan
    assert "circular_dependencies" in plan
    assert "parallelization_opportunities" in plan
    assert "max_concurrent_steps" in plan
    assert "estimated_speedup" in plan
    assert "recommended_mode" in plan
    assert "optimization_suggestions" in plan
    
    # Check specific values
    assert plan["recommended_mode"] == "parallel"
    assert plan["max_concurrent_steps"] == 2  # step-01 and step-02 can run in parallel
    assert plan["parallelization_opportunities"] > 0
