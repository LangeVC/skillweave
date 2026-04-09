#!/usr/bin/env python3
"""
Example demonstrating SkillWeave parallel execution capabilities.

This example shows how to use the new parallel execution functions
in orchestrator.py and executor.py for dependency-aware parallel
execution of prompt sequence steps.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from skillweave.models import PromptSequence, StepSpec, WorkflowContext
from skillweave.orchestrator import (
    get_execution_groups, 
    get_parallel_execution_plan,
    can_execute_in_parallel,
    analyze_dependencies
)
from skillweave.executor import execute_with_dependency_awareness


def create_example_sequence() -> PromptSequence:
    """Create an example sequence with parallel execution opportunities."""
    return PromptSequence(
        metadata={
            "id": "parallel-example",
            "title": "Parallel Execution Example",
            "version": "1.0"
        },
        objective="Demonstrate parallel execution capabilities",
        success_criteria=[
            "All steps completed successfully",
            "Parallel execution used where possible",
            "Dependencies respected"
        ],
        assumptions=["System has sufficient resources for parallel execution"],
        usage_notes={
            "parallel_execution": True,
            "max_concurrent_steps": 3,
            "timeout_per_step": 300
        },
        inputs_required=["project_context"],
        outputs_required=["execution_report", "performance_metrics"],
        sequence_steps=[
            # Independent steps that can run in parallel
            StepSpec(
                id="market-research",
                name="Market Research",
                purpose="Research target market and competitors",
                instructions="Analyze market size, trends, and competitors",
                depends_on=[],
                expected_output=["market_analysis_report.md"],
                validation=["Contains competitor analysis", "Includes market size data"],
                completion_rule=["Report generated", "Data validated"]
            ),
            StepSpec(
                id="user-research",
                name="User Research",
                purpose="Research user needs and pain points",
                instructions="Conduct user interviews and surveys",
                depends_on=[],
                expected_output=["user_personas.md", "user_journeys.md"],
                validation=["Personas created", "Journey maps complete"],
                completion_rule=["Research completed", "Insights documented"]
            ),
            StepSpec(
                id="tech-assessment",
                name="Technical Assessment",
                purpose="Evaluate technical feasibility",
                instructions="Assess technology stack and architecture options",
                depends_on=[],
                expected_output=["tech_stack_recommendation.md"],
                validation=["Multiple options evaluated", "Recommendation justified"],
                completion_rule=["Assessment complete", "Recommendation made"]
            ),
            # Steps that depend on research
            StepSpec(
                id="product-strategy",
                name="Product Strategy",
                purpose="Develop product strategy based on research",
                instructions="Create product vision, roadmap, and positioning",
                depends_on=["market-research", "user-research"],
                expected_output=["product_strategy.md", "roadmap.md"],
                validation=["Strategy aligns with research", "Roadmap prioritized"],
                completion_rule=["Strategy document complete", "Stakeholder buy-in"]
            ),
            StepSpec(
                id="architecture-design",
                name="Architecture Design",
                purpose="Design system architecture",
                instructions="Design system architecture and components",
                depends_on=["tech-assessment"],
                expected_output=["architecture_diagram.md", "component_specs.md"],
                validation=["Architecture scalable", "Components well-defined"],
                completion_rule=["Design complete", "Reviewed by team"]
            ),
            # Final step depends on both strategy and architecture
            StepSpec(
                id="implementation-plan",
                name="Implementation Plan",
                purpose="Create detailed implementation plan",
                instructions="Develop phased implementation plan with milestones",
                depends_on=["product-strategy", "architecture-design"],
                expected_output=["implementation_plan.md", "milestone_timeline.md"],
                validation=["Plan actionable", "Timeline realistic"],
                completion_rule=["Plan approved", "Resources allocated"]
            )
        ],
        final_assembly="Combine all outputs into comprehensive product development plan",
        validation_rules=[
            "All research validated by domain experts",
            "Technical design reviewed by architects",
            "Implementation plan approved by stakeholders"
        ],
        failure_handling="continue_on_error",
        final_deliverable_format="markdown"
    )


def demonstrate_parallel_analysis(sequence: PromptSequence):
    """Demonstrate parallel execution analysis."""
    print("=" * 60)
    print("PARALLEL EXECUTION ANALYSIS")
    print("=" * 60)
    
    # Analyze dependencies
    dependency_graph = analyze_dependencies(sequence)
    print(f"\nDependency Graph:")
    for step_id, deps in dependency_graph.items():
        if deps:
            print(f"  {step_id} depends on: {', '.join(deps)}")
        else:
            print(f"  {step_id} has no dependencies")
    
    # Check if parallel execution is possible
    can_parallel = can_execute_in_parallel(sequence)
    print(f"\nCan execute in parallel: {can_parallel}")
    
    # Get execution groups
    execution_groups = get_execution_groups(sequence)
    print(f"\nExecution Groups ({len(execution_groups)} groups):")
    for i, group in enumerate(execution_groups, 1):
        group_ids = [step.id for step in group]
        print(f"  Group {i}: {', '.join(group_ids)} ({len(group)} steps)")
    
    # Get detailed execution plan
    plan = get_parallel_execution_plan(sequence)
    print(f"\nParallel Execution Plan:")
    print(f"  Max concurrent steps: {plan['max_concurrent_steps']}")
    print(f"  Parallelization opportunities: {plan['parallelization_opportunities']}")
    print(f"  Estimated speedup: {plan['estimated_speedup']}x")
    print(f"  Recommended mode: {plan['recommended_mode']}")
    
    if plan['optimization_suggestions']:
        print(f"\nOptimization Suggestions:")
        for suggestion in plan['optimization_suggestions']:
            print(f"  • {suggestion}")


def demonstrate_execution(sequence: PromptSequence):
    """Demonstrate actual execution with dependency awareness."""
    print("\n" + "=" * 60)
    print("EXECUTION DEMONSTRATION")
    print("=" * 60)
    
    # Create workflow context
    context = WorkflowContext(
        sequence_id=sequence.metadata["id"],
        mode="execute",
        status="running",
        inputs={"project_context": "Example project for parallel execution demo"}
    )
    
    # Execute with dependency awareness
    print("\nExecuting sequence with dependency awareness...")
    summary = execute_with_dependency_awareness(
        sequence_steps=sequence.sequence_steps,
        context=context,
        max_parallel=3,
        step_timeout=10
    )
    
    print(f"\nExecution Summary:")
    print(f"  Total steps: {summary['total_steps']}")
    print(f"  Completed: {summary['completed']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Success rate: {summary['success_rate']:.1%}")
    print(f"  Total time: {summary['total_time']:.2f}s")
    print(f"  Parallel groups executed: {summary['parallel_groups_executed']}")
    
    print(f"\nContext Updates:")
    print(f"  Completed steps: {len(context.completed_steps)}")
    print(f"  Errors: {len(context.errors)}")
    print(f"  Step outputs: {len(context.step_outputs)}")
    
    if context.errors:
        print(f"\nErrors encountered:")
        for error in context.errors:
            print(f"  • {error}")


def main():
    """Main demonstration function."""
    print("SkillWeave Parallel Execution Example")
    print("=" * 60)
    
    # Create example sequence
    sequence = create_example_sequence()
    print(f"Created sequence: {sequence.metadata['title']}")
    print(f"Total steps: {len(sequence.sequence_steps)}")
    
    # Demonstrate analysis
    demonstrate_parallel_analysis(sequence)
    
    # Demonstrate execution (simulated)
    demonstrate_execution(sequence)
    
    print("\n" + "=" * 60)
    print("EXAMPLE COMPLETE")
    print("=" * 60)
    print("\nKey takeaways:")
    print("1. Dependency analysis identifies parallel execution opportunities")
    print("2. Execution groups steps that can run simultaneously")
    print("3. Parallel execution significantly reduces total execution time")
    print("4. Error handling maintains execution flow even with failures")
    print("5. Context tracking provides visibility into execution progress")


if __name__ == "__main__":
    main()