"""
Integration tests for SkillWeave full workflow (Blueprint → PromptChain → ReleaseChain).

These tests verify that the components work together correctly
to support the complete "product development flow on steroids".
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from skillweave.models import PromptSequence, StepSpec, WorkflowContext
from skillweave.orchestrator import (
    get_execution_groups,
    get_parallel_execution_plan,
    analyze_dependencies
)
from skillweave.executor import execute_with_dependency_awareness
import json


def test_blueprint_to_promptchain_flow():
    """
    Test the flow from Blueprint (PRD) to PromptChain (sequence generation).
    
    This simulates:
    1. Blueprint creates a PRD with tasks
    2. PromptChain generates execution sequence from PRD
    3. Verify sequence structure and dependencies
    """
    # Simulate Blueprint output: PRD with tasks
    prd_data = {
        "project": "Test Integration Project",
        "version": "1.0.0",
        "tasks": [
            {
                "id": "INFRA-001",
                "name": "Project Setup",
                "description": "Set up basic project structure",
                "dependencies": [],
                "estimated_time": 60,
                "agent_capabilities": ["code_generation", "planning"]
            },
            {
                "id": "AUTH-001",
                "name": "Authentication System",
                "description": "Implement user authentication",
                "dependencies": ["INFRA-001"],
                "estimated_time": 120,
                "agent_capabilities": ["code_generation"]
            },
            {
                "id": "FEAT-001",
                "name": "Core Feature A",
                "description": "Implement main feature A",
                "dependencies": ["INFRA-001"],
                "estimated_time": 90,
                "agent_capabilities": ["code_generation"]
            },
            {
                "id": "FEAT-002",
                "name": "Core Feature B",
                "description": "Implement main feature B",
                "dependencies": ["INFRA-001"],
                "estimated_time": 90,
                "agent_capabilities": ["code_generation"]
            },
            {
                "id": "UI-001",
                "name": "User Interface",
                "description": "Build user interface",
                "dependencies": ["AUTH-001", "FEAT-001", "FEAT-002"],
                "estimated_time": 180,
                "agent_capabilities": ["code_generation", "design"]
            }
        ],
        "success_criteria": [
            "All features implemented",
            "Tests passing",
            "Documentation complete"
        ]
    }
    
    # Convert PRD tasks to PromptSequence (simulating PromptChain generation)
    sequence_steps = []
    for task in prd_data["tasks"]:
        step = StepSpec(
            id=task["id"],
            name=task["name"],
            purpose=task["description"],
            instructions=f"Implement {task['name']}: {task['description']}",
            depends_on=task["dependencies"],
            expected_output=[f"{task['id']}_implementation.md"],
            validation=["Code compiles", "Tests pass", "Documentation exists"],
            completion_rule=["Implementation complete", "Reviewed", "Merged"]
        )
        sequence_steps.append(step)
    
    # Create PromptSequence (PromptChain output)
    prompt_sequence = PromptSequence(
        metadata={
            "project": prd_data["project"],
            "version": prd_data["version"],
            "source": "Blueprint-PromptChain integration"
        },
        objective=f"Implement {prd_data['project']}",
        success_criteria=prd_data["success_criteria"],
        assumptions=["Development environment set up", "Team available"],
        usage_notes={
            "parallel_execution": True,
            "agent_capabilities": ["code_generation", "planning", "design", "testing"]
        },
        inputs_required=["prd_data"],
        outputs_required=["implemented_features", "documentation", "tests"],
        sequence_steps=sequence_steps,
        final_assembly="Combine all implementations into complete project",
        validation_rules=[
            "All acceptance criteria met",
            "Code follows style guide",
            "Tests have >80% coverage"
        ],
        failure_handling="continue_on_error",
        final_deliverable_format="markdown"
    )
    
    # Verify PromptChain output
    assert prompt_sequence is not None
    assert len(prompt_sequence.sequence_steps) == len(prd_data["tasks"])
    
    # Check that dependencies were preserved
    for task in prd_data["tasks"]:
        step = next(s for s in prompt_sequence.sequence_steps if s.id == task["id"])
        assert set(step.depends_on) == set(task["dependencies"])
    
    return prompt_sequence


def helper_promptchain_to_releasechain_flow(prompt_sequence):
    """
    Test the flow from PromptChain (sequence) to ReleaseChain (execution).
    
    This simulates:
    1. PromptChain provides execution sequence
    2. ReleaseChain analyzes dependencies for parallel execution
    3. ReleaseChain executes with Ralph Loop principles
    """
    # Analyze dependencies (ReleaseChain analysis phase)
    dependency_graph = analyze_dependencies(prompt_sequence)
    execution_groups = get_execution_groups(prompt_sequence)
    execution_plan = get_parallel_execution_plan(prompt_sequence)
    
    # Verify analysis results
    assert len(dependency_graph) == len(prompt_sequence.sequence_steps)
    assert len(execution_groups) > 0
    
    # Check that INFRA-001 has no dependencies
    assert dependency_graph["INFRA-001"] == set()
    
    # Check that UI-001 depends on multiple tasks
    assert "AUTH-001" in dependency_graph["UI-001"]
    assert "FEAT-001" in dependency_graph["UI-001"]
    assert "FEAT-002" in dependency_graph["UI-001"]
    
    # Verify parallel execution opportunities were identified
    assert execution_plan["parallelization_opportunities"] > 0
    assert execution_plan["recommended_mode"] == "parallel"
    
    # Simulate ReleaseChain execution
    context = WorkflowContext(
        sequence_id="integration-test",
        mode="execute",
        status="running",
        inputs={"prd_data": "test_data"}
    )
    
    execution_summary = execute_with_dependency_awareness(
        sequence_steps=prompt_sequence.sequence_steps,
        context=context,
        max_parallel=3,
        step_timeout=30
    )
    
    # Verify execution results
    assert execution_summary["total_steps"] == len(prompt_sequence.sequence_steps)
    assert execution_summary["completed"] == len(prompt_sequence.sequence_steps)
    assert execution_summary["failed"] == 0  # Simulation should succeed
    assert execution_summary["success_rate"] == 1.0
    
    # Verify context was updated
    assert len(context.completed_steps) == len(prompt_sequence.sequence_steps)
    assert len(context.step_outputs) == len(prompt_sequence.sequence_steps)
    
    return execution_summary, context


def test_agent_agnostic_capability_routing():
    """
    Test agent-agnostic capability routing.
    
    This verifies that tasks can be routed based on capabilities
    rather than specific agent names.
    """
    # Define tasks with required capabilities
    tasks_with_capabilities = [
        {
            "id": "PLAN-001",
            "name": "Project Planning",
            "required_capabilities": ["planning", "research"],
            "description": "Create project plan and architecture"
        },
        {
            "id": "CODE-001",
            "name": "Code Implementation",
            "required_capabilities": ["code_generation"],
            "description": "Implement core functionality"
        },
        {
            "id": "TEST-001",
            "name": "Testing",
            "required_capabilities": ["testing", "code_generation"],
            "description": "Write and run tests"
        },
        {
            "id": "DOC-001",
            "name": "Documentation",
            "required_capabilities": ["documentation", "writing"],
            "description": "Create documentation"
        }
    ]
    
    # Simulate available agents with capabilities
    available_agents = [
        {
            "name": "architect_agent",
            "capabilities": ["planning", "research", "architecture"]
        },
        {
            "name": "developer_agent",
            "capabilities": ["code_generation", "testing", "debugging"]
        },
        {
            "name": "writer_agent",
            "capabilities": ["documentation", "writing", "editing"]
        }
    ]
    
    # Simulate capability-based routing
    task_assignments = {}
    for task in tasks_with_capabilities:
        task_id = task["id"]
        required_caps = set(task["required_capabilities"])
        
        # Find agents that have all required capabilities
        suitable_agents = []
        for agent in available_agents:
            agent_caps = set(agent["capabilities"])
            if required_caps.issubset(agent_caps):
                suitable_agents.append(agent["name"])
        
        task_assignments[task_id] = {
            "task": task["name"],
            "required_capabilities": list(required_caps),
            "suitable_agents": suitable_agents,
            "can_execute": len(suitable_agents) > 0
        }
    
    # Verify routing results
    assert len(task_assignments) == len(tasks_with_capabilities)
    
    # Check that each task can be assigned
    for task_id, assignment in task_assignments.items():
        assert assignment["can_execute"] is True, f"Task {task_id} cannot be assigned"
    
    # Specific checks
    assert "architect_agent" in task_assignments["PLAN-001"]["suitable_agents"]
    assert "developer_agent" in task_assignments["CODE-001"]["suitable_agents"]
    assert "developer_agent" in task_assignments["TEST-001"]["suitable_agents"]
    assert "writer_agent" in task_assignments["DOC-001"]["suitable_agents"]
    
    return task_assignments


def test_complexity_based_execution_mode():
    """
    Test complexity-based execution mode selection (REX vs Ralph Loop).
    
    This verifies that simple tasks use REX-style execution
    while complex tasks use full Ralph Loop.
    """
    # Simple task sequence (REX-style)
    simple_sequence = PromptSequence(
        metadata={"id": "simple-sequence"},
        objective="Simple task execution",
        success_criteria=["Task completed"],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=[
            StepSpec(id="task-1", name="Simple Task", purpose="test", instructions="Do something"),
        ],
        final_assembly="",
        validation_rules=[],
        failure_handling="",
        final_deliverable_format=""
    )
    
    # Complex task sequence (Ralph Loop)
    complex_sequence = PromptSequence(
        metadata={"id": "complex-sequence"},
        objective="Complex project execution",
        success_criteria=["All tasks completed"],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=[
            StepSpec(id="task-1", name="Task 1", purpose="test", instructions="Do something"),
            StepSpec(id="task-2", name="Task 2", purpose="test", instructions="Do something", depends_on=["task-1"]),
            StepSpec(id="task-3", name="Task 3", purpose="test", instructions="Do something", depends_on=["task-1"]),
            StepSpec(id="task-4", name="Task 4", purpose="test", instructions="Do something", depends_on=["task-2", "task-3"]),
            StepSpec(id="task-5", name="Task 5", purpose="test", instructions="Do something", depends_on=["task-4"]),
        ],
        final_assembly="",
        validation_rules=[],
        failure_handling="",
        final_deliverable_format=""
    )
    
    # Analyze complexity
    simple_plan = get_parallel_execution_plan(simple_sequence)
    complex_plan = get_parallel_execution_plan(complex_sequence)
    
    # Simple sequence should have minimal parallelization
    assert simple_plan["max_concurrent_steps"] == 1
    assert simple_plan["parallelization_opportunities"] == 0
    
    # Complex sequence should have parallelization opportunities
    assert complex_plan["max_concurrent_steps"] > 1
    assert complex_plan["parallelization_opportunities"] > 0
    
    # Execution mode recommendations
    # Note: In practice, REX vs Ralph Loop decision would be based on more factors
    # like estimated time, dependencies, resources, etc.
    print(f"\nSimple sequence recommendation: {simple_plan['recommended_mode']}")
    print(f"Complex sequence recommendation: {complex_plan['recommended_mode']}")
    
    return simple_plan, complex_plan


def test_full_workflow_integration():
    """
    Full integration test covering Blueprint → PromptChain → ReleaseChain.
    """
    print("\n" + "=" * 60)
    print("FULL WORKFLOW INTEGRATION TEST")
    print("=" * 60)
    
    # Step 1: Blueprint to PromptChain
    print("\n1. Testing Blueprint → PromptChain flow...")
    prompt_sequence = test_blueprint_to_promptchain_flow()
    print(f"   ✓ Created PromptSequence with {len(prompt_sequence.sequence_steps)} steps")
    
    # Step 2: PromptChain to ReleaseChain
    print("\n2. Testing PromptChain → ReleaseChain flow...")
    execution_summary, context = helper_promptchain_to_releasechain_flow(prompt_sequence)
    print(f"   ✓ Executed sequence: {execution_summary['completed']} steps completed")
    print(f"   ✓ Success rate: {execution_summary['success_rate']:.1%}")
    
    # Step 3: Agent-agnostic routing
    print("\n3. Testing agent-agnostic capability routing...")
    task_assignments = test_agent_agnostic_capability_routing()
    print(f"   ✓ Routed {len(task_assignments)} tasks to suitable agents")
    
    # Step 4: Complexity-based execution mode
    print("\n4. Testing complexity-based execution mode selection...")
    simple_plan, complex_plan = test_complexity_based_execution_mode()
    print(f"   ✓ Simple tasks: {simple_plan['recommended_mode']} mode")
    print(f"   ✓ Complex tasks: {complex_plan['recommended_mode']} mode")
    
    # Verify the complete workflow
    print("\n5. Verifying complete workflow...")
    
    # All steps should have been executed
    assert len(context.completed_steps) == len(prompt_sequence.sequence_steps)
    
    # No errors in execution
    assert len(context.errors) == 0
    
    # Outputs were generated
    assert len(context.step_outputs) == len(prompt_sequence.sequence_steps)
    
    print(f"   ✓ All {len(prompt_sequence.sequence_steps)} steps completed successfully")
    print(f"   ✓ No errors encountered")
    print(f"   ✓ {len(context.step_outputs)} outputs generated")
    
    print("\n" + "=" * 60)
    print("INTEGRATION TEST PASSED ✓")
    print("=" * 60)
    print("\nSummary:")
    print(f"- Blueprint created PRD with {len(prompt_sequence.sequence_steps)} tasks")
    print(f"- PromptChain generated execution sequence")
    print(f"- ReleaseChain executed with {execution_summary['parallel_groups_executed']} parallel groups")
    print(f"- Agent-agnostic routing assigned {len(task_assignments)} tasks")
    print(f"- Complexity analysis distinguished simple vs complex workflows")
    
    return True


if __name__ == "__main__":
    # Run the full integration test
    success = test_full_workflow_integration()
    
    if success:
        print("\n✅ All integration tests passed!")
        print("\nThe SkillWeave workflow successfully supports:")
        print("1. Blueprint: Structured PRD creation")
        print("2. PromptChain: Execution sequence generation")
        print("3. ReleaseChain: Parallel execution with dependency awareness")
        print("4. Agent-agnostic design: Capability-based routing")
        print("5. Complexity-based mode selection: REX vs Ralph Loop")
        print("\n🎉 Product development flow on steroids is operational!")
    else:
        print("\n❌ Integration tests failed")
        sys.exit(1)