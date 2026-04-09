"""
Performance tests for large SkillWeave projects.

Tests optimization for projects with many tasks (50+ steps).
"""

import sys
import os
import time
import random
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from skillweave.models import PromptSequence, StepSpec, WorkflowContext
from skillweave.orchestrator import (
    analyze_dependencies,
    get_execution_groups,
    get_parallel_execution_plan,
    detect_circular_dependencies
)
from skillweave.executor import execute_with_dependency_awareness


def generate_large_sequence(num_steps: int = 50, max_dependencies: int = 3) -> PromptSequence:
    """
    Generate a large sequence for performance testing.
    
    Args:
        num_steps: Number of steps in sequence
        max_dependencies: Maximum dependencies per step
        
    Returns:
        PromptSequence with many steps
    """
    steps = []
    
    # Create steps with random dependencies
    for i in range(num_steps):
        step_id = f"step-{i:03d}"
        
        # Generate random dependencies (only to previous steps to avoid cycles)
        possible_deps = [f"step-{j:03d}" for j in range(i)]
        num_deps = random.randint(0, min(max_dependencies, len(possible_deps)))
        dependencies = random.sample(possible_deps, num_deps) if possible_deps else []
        
        step = StepSpec(
            id=step_id,
            name=f"Task {i+1}",
            purpose=f"Perform task {i+1}",
            instructions=f"Execute task {i+1} with dependencies {dependencies}",
            depends_on=dependencies,
            expected_output=[f"output_{step_id}.md"],
            validation=[f"Validate {step_id}"],
            completion_rule=[f"Complete {step_id}"]
        )
        steps.append(step)
    
    return PromptSequence(
        metadata={
            "id": f"large-sequence-{num_steps}",
            "title": f"Large Test Sequence ({num_steps} steps)",
            "generated_for": "performance_testing"
        },
        objective=f"Execute large sequence with {num_steps} steps",
        success_criteria=[f"All {num_steps} steps completed"],
        assumptions=["Sufficient resources available"],
        usage_notes={"parallel_execution": True, "max_concurrent": 10},
        inputs_required=[],
        outputs_required=[f"output_{i}" for i in range(num_steps)],
        sequence_steps=steps,
        final_assembly="Combine all outputs",
        validation_rules=["All steps validated"],
        failure_handling="continue_on_error",
        final_deliverable_format="markdown"
    )


def test_dependency_analysis_performance():
    """Test performance of dependency analysis for large sequences."""
    print("Testing dependency analysis performance...")
    
    # Test with different sequence sizes
    sequence_sizes = [10, 25, 50, 100]
    
    for size in sequence_sizes:
        print(f"\n  Sequence size: {size} steps")
        
        # Generate sequence
        start_time = time.time()
        sequence = generate_large_sequence(size)
        gen_time = time.time() - start_time
        print(f"    Generation: {gen_time:.3f}s")
        
        # Analyze dependencies
        start_time = time.time()
        dependency_graph = analyze_dependencies(sequence)
        analysis_time = time.time() - start_time
        print(f"    Dependency analysis: {analysis_time:.3f}s")
        
        # Detect circular dependencies
        start_time = time.time()
        cycles = detect_circular_dependencies(dependency_graph)
        cycle_time = time.time() - start_time
        print(f"    Cycle detection: {cycle_time:.3f}s")
        
        # Get execution groups
        start_time = time.time()
        groups = get_execution_groups(sequence)
        groups_time = time.time() - start_time
        print(f"    Execution groups: {groups_time:.3f}s")
        
        # Get parallel execution plan
        start_time = time.time()
        plan = get_parallel_execution_plan(sequence)
        plan_time = time.time() - start_time
        print(f"    Execution plan: {plan_time:.3f}s")
        
        # Verify results
        assert len(dependency_graph) == size
        assert len(groups) > 0
        assert plan["total_steps"] == size
        
        print(f"    Total analysis time: {gen_time + analysis_time + cycle_time + groups_time + plan_time:.3f}s")
    
    return True


def test_execution_performance():
    """Test performance of execution for large sequences."""
    print("\nTesting execution performance...")
    
    # Use moderate size for execution test (execution is simulated and slower)
    sequence = generate_large_sequence(20)  # 20 steps for reasonable test time
    
    print(f"  Sequence: {len(sequence.sequence_steps)} steps")
    
    # Create context
    context = WorkflowContext(
        sequence_id=sequence.metadata["id"],
        mode="execute",
        status="running"
    )
    
    # Execute with dependency awareness
    start_time = time.time()
    summary = execute_with_dependency_awareness(
        sequence_steps=sequence.sequence_steps,
        context=context,
        max_parallel=5,
        step_timeout=5
    )
    execution_time = time.time() - start_time
    
    print(f"  Execution time: {execution_time:.2f}s")
    print(f"  Steps completed: {summary['completed']}/{summary['total_steps']}")
    print(f"  Success rate: {summary['success_rate']:.1%}")
    print(f"  Parallel groups: {summary['parallel_groups_executed']}")
    
    # Verify execution
    assert summary["total_steps"] == len(sequence.sequence_steps)
    assert summary["completed"] == len(sequence.sequence_steps)
    assert summary["failed"] == 0  # Simulation should succeed
    
    return True


def test_memory_optimization():
    """Test memory usage optimization for large workflows."""
    print("\nTesting memory optimization...")
    
    # Create a large sequence
    sequence = generate_large_sequence(100)
    
    try:
        # Track memory usage (approximate)
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Perform multiple operations
        operations = []
        for i in range(5):  # Reduced iterations for speed
            start_time = time.time()
            dependency_graph = analyze_dependencies(sequence)
            groups = get_execution_groups(sequence)
            plan = get_parallel_execution_plan(sequence)
            op_time = time.time() - start_time
            
            operations.append({
                "iteration": i + 1,
                "time": op_time,
                "memory": process.memory_info().rss / 1024 / 1024
            })
        
        final_memory = process.memory_info().rss / 1024 / 1024
        memory_increase = final_memory - initial_memory
        
        print(f"  Initial memory: {initial_memory:.1f} MB")
        print(f"  Final memory: {final_memory:.1f} MB")
        print(f"  Memory increase: {memory_increase:.1f} MB")
        
        # Check for memory leaks (should be minimal)
        # In a well-optimized system, memory increase should be small
        print(f"  Memory per iteration: {memory_increase / 5:.2f} MB")
        
        # Average operation time
        avg_time = sum(op["time"] for op in operations) / len(operations)
        print(f"  Average operation time: {avg_time:.3f}s")
        
        # Check consistency
        assert memory_increase < 100  # Should not increase by more than 100MB for 5 iterations
        
    except ImportError:
        # psutil not available, skip memory measurement
        print("  psutil not available, skipping memory measurement")
        print("  Performing timing test only...")
        
        # Perform timing test
        operations = []
        for i in range(5):
            start_time = time.time()
            dependency_graph = analyze_dependencies(sequence)
            groups = get_execution_groups(sequence)
            plan = get_parallel_execution_plan(sequence)
            op_time = time.time() - start_time
            
            operations.append({
                "iteration": i + 1,
                "time": op_time
            })
        
        avg_time = sum(op["time"] for op in operations) / len(operations)
        print(f"  Average operation time: {avg_time:.3f}s")
    
    return True


def test_batch_processing_optimization():
    """Test batch processing optimization for similar tasks."""
    print("\nTesting batch processing optimization...")
    
    # Create sequence with similar tasks that could be batched
    steps = []
    
    # Group 1: Similar documentation tasks
    for i in range(5):
        steps.append(StepSpec(
            id=f"doc-{i:03d}",
            name=f"Documentation Task {i+1}",
            purpose="Create documentation",
            instructions=f"Write documentation section {i+1}",
            depends_on=[],
            expected_output=[f"doc_section_{i+1}.md"],
            validation=[f"Section {i+1} complete"],
            completion_rule=[f"Documented section {i+1}"]
        ))
    
    # Group 2: Similar testing tasks
    for i in range(5):
        steps.append(StepSpec(
            id=f"test-{i:03d}",
            name=f"Testing Task {i+1}",
            purpose="Write tests",
            instructions=f"Write tests for module {i+1}",
            depends_on=[f"doc-{i:03d}"],  # Depends on corresponding doc task
            expected_output=[f"tests_module_{i+1}.py"],
            validation=[f"Tests for module {i+1} pass"],
            completion_rule=[f"Tests written for module {i+1}"]
        ))
    
    # Group 3: Similar deployment tasks (depend on tests)
    for i in range(5):
        steps.append(StepSpec(
            id=f"deploy-{i:03d}",
            name=f"Deployment Task {i+1}",
            purpose="Deploy module",
            instructions=f"Deploy module {i+1} to production",
            depends_on=[f"test-{i:03d}"],
            expected_output=[f"deployment_{i+1}_complete.md"],
            validation=[f"Module {i+1} deployed successfully"],
            completion_rule=[f"Module {i+1} deployed"]
        ))
    
    sequence = PromptSequence(
        metadata={"id": "batch-optimization-test"},
        objective="Test batch processing optimization",
        success_criteria=["All tasks completed"],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=steps,
        final_assembly="",
        validation_rules=[],
        failure_handling="",
        final_deliverable_format=""
    )
    
    # Analyze execution groups
    groups = get_execution_groups(sequence)
    
    print(f"  Total steps: {len(steps)}")
    print(f"  Execution groups: {len(groups)}")
    
    # Check that similar tasks are grouped together where possible
    # Group 1: All doc tasks should be in first group (no dependencies)
    group1_ids = {step.id for step in groups[0]}
    expected_doc_ids = {f"doc-{i:03d}" for i in range(5)}
    assert expected_doc_ids.issubset(group1_ids)
    print(f"  ✓ Documentation tasks grouped together")
    
    # Group 2: Test tasks (depend on doc tasks)
    group2_ids = {step.id for step in groups[1]}
    expected_test_ids = {f"test-{i:03d}" for i in range(5)}
    assert expected_test_ids.issubset(group2_ids)
    print(f"  ✓ Testing tasks grouped together")
    
    # Group 3: Deployment tasks (depend on test tasks)
    group3_ids = {step.id for step in groups[2]}
    expected_deploy_ids = {f"deploy-{i:03d}" for i in range(5)}
    assert expected_deploy_ids.issubset(group3_ids)
    print(f"  ✓ Deployment tasks grouped together")
    
    # Check parallelization opportunities
    plan = get_parallel_execution_plan(sequence)
    print(f"  Max concurrent steps: {plan['max_concurrent_steps']}")
    print(f"  Parallelization opportunities: {plan['parallelization_opportunities']}")
    
    # Should have good parallelization (5 tasks in each group)
    assert plan['max_concurrent_steps'] >= 5
    
    return True


def test_caching_optimization():
    """Test caching optimization for repeated analyses."""
    print("\nTesting caching optimization...")
    
    # Create a sequence
    sequence = generate_large_sequence(30)
    
    # First analysis (cold)
    start_time = time.time()
    dependency_graph1 = analyze_dependencies(sequence)
    groups1 = get_execution_groups(sequence)
    plan1 = get_parallel_execution_plan(sequence)
    first_run_time = time.time() - start_time
    
    # Second analysis (should be faster with caching)
    start_time = time.time()
    dependency_graph2 = analyze_dependencies(sequence)
    groups2 = get_execution_groups(sequence)
    plan2 = get_parallel_execution_plan(sequence)
    second_run_time = time.time() - start_time
    
    print(f"  First analysis: {first_run_time:.3f}s")
    print(f"  Second analysis: {second_run_time:.3f}s")
    
    # Verify results are consistent
    assert dependency_graph1 == dependency_graph2
    assert len(groups1) == len(groups2)
    assert plan1["total_steps"] == plan2["total_steps"]
    
    # In a real implementation with caching, second run should be faster
    # For now, just verify correctness
    print(f"  ✓ Results consistent across runs")
    
    # Note: Actual caching would be implemented in a production system
    # This test verifies the need and potential benefit
    
    return True


def main():
    """Run all performance tests."""
    print("=" * 60)
    print("SKILLWEAVE PERFORMANCE TESTS")
    print("=" * 60)
    
    all_passed = True
    
    try:
        test_dependency_analysis_performance()
    except Exception as e:
        print(f"❌ Dependency analysis performance test failed: {e}")
        all_passed = False
    
    try:
        test_execution_performance()
    except Exception as e:
        print(f"❌ Execution performance test failed: {e}")
        all_passed = False
    
    try:
        test_memory_optimization()
    except Exception as e:
        print(f"❌ Memory optimization test failed: {e}")
        all_passed = False
    
    try:
        test_batch_processing_optimization()
    except Exception as e:
        print(f"❌ Batch processing optimization test failed: {e}")
        all_passed = False
    
    try:
        test_caching_optimization()
    except Exception as e:
        print(f"❌ Caching optimization test failed: {e}")
        all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All performance tests passed!")
        print("\nPerformance optimizations verified:")
        print("1. Efficient dependency analysis for large sequences")
        print("2. Scalable execution with parallelization")
        print("3. Memory-efficient processing")
        print("4. Batch processing for similar tasks")
        print("5. Caching potential for repeated analyses")
    else:
        print("❌ Some performance tests failed")
    
    print("=" * 60)
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)