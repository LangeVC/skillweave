from typing import List, Dict, Any, Optional, Callable
import time
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError
from .models import WorkflowContext, StepSpec, PromptSequence


def _get_next_level_from_context(context: WorkflowContext) -> Optional[Any]:
    """Extract SkillWeaveNextLevel instance from context metadata if available."""
    next_level = context.metadata.get("next_level")
    if next_level and hasattr(next_level, 'get_max_parallel_tasks'):
        return next_level
    return None


def simulate_step(step: StepSpec, context: WorkflowContext) -> dict:
    """Simulate a single step (sequential mode)."""
    context.current_step_id = step.id
    # Placeholder execution. In a real runtime, this would call the model/tools.
    result = {
        "step_id": step.id,
        "step_name": step.name,
        "status": "completed",
        "output": f"Executed step: {step.name}",
        "execution_time": 1.0,  # Simulated execution time
    }
    context.step_outputs[step.id] = result
    context.completed_steps.append(step.id)
    return result


def simulate_step_parallel(steps: List[StepSpec], context: WorkflowContext, 
                          max_workers: int = 3, timeout: int = 300) -> Dict[str, Dict]:
    """
    Simulate multiple steps in parallel using thread pool.
    
    Note: In a real implementation, this would use Task tool subagents.
    This is a simulation for demonstration purposes.
    
    Args:
        steps: List of StepSpec objects to execute in parallel
        context: Workflow context
        max_workers: Maximum number of concurrent workers
        timeout: Timeout in seconds for each step
        
    Returns:
        Dict mapping step_id to execution result
    """
    results = {}
    
    def _execute_single(step: StepSpec) -> Dict[str, Any]:
        """Execute a single step with timeout handling."""
        try:
            # Simulate step execution with variable time
            execution_time = 0.5 + (hash(step.id) % 10) / 20.0  # 0.5-1.0 seconds
            
            # In real implementation, this would trigger a subagent via Task tool
            time.sleep(execution_time)
            
            result = {
                "step_id": step.id,
                "step_name": step.name,
                "status": "completed",
                "output": f"Parallel executed step: {step.name}",
                "execution_time": execution_time,
            }
            
            # Update context in thread-safe manner (simplified)
            # In real implementation, would need proper synchronization
            return result
            
        except Exception as e:
            return {
                "step_id": step.id,
                "step_name": step.name,
                "status": "failed",
                "output": f"Error executing step {step.name}: {str(e)}",
                "error": str(e),
                "execution_time": 0.0,
            }
    
    # Execute steps in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_step = {executor.submit(_execute_single, step): step for step in steps}
        
        # Collect results as they complete
        for future in future_to_step:
            try:
                result = future.result(timeout=timeout)
                step_id = result["step_id"]
                results[step_id] = result
                
                # Update context
                context.step_outputs[step_id] = result
                if result["status"] == "completed":
                    context.completed_steps.append(step_id)
                    
            except TimeoutError:
                step = future_to_step[future]
                error_result = {
                    "step_id": step.id,
                    "step_name": step.name,
                    "status": "timeout",
                    "output": f"Step {step.name} timed out after {timeout} seconds",
                    "execution_time": timeout,
                }
                results[step.id] = error_result
                context.step_outputs[step.id] = error_result
                context.errors.append(f"Step {step.id} timed out")
                
            except Exception as e:
                step = future_to_step[future]
                error_result = {
                    "step_id": step.id,
                    "step_name": step.name,
                    "status": "failed",
                    "output": f"Error executing step {step.name}: {str(e)}",
                    "error": str(e),
                    "execution_time": 0.0,
                }
                results[step.id] = error_result
                context.step_outputs[step.id] = error_result
                context.errors.append(f"Step {step.id} failed: {str(e)}")
    
    return results


def execute_with_dependency_awareness(sequence_steps: List[StepSpec], context: WorkflowContext,
                                      max_parallel: int = 3, step_timeout: int = 300) -> Dict[str, Any]:
    """
    Execute steps with dependency awareness and parallelization.
    
    This is a higher-level function that orchestrates parallel execution
    based on dependencies between steps.
    
    Args:
        sequence_steps: List of all steps in sequence
        context: Workflow context
        max_parallel: Maximum parallel steps at once
        step_timeout: Timeout per step in seconds
        
    Returns:
        Execution summary with statistics
    """
    from .orchestrator import get_execution_groups
    
    # Adjust max_parallel based on Next Level mode if available
    next_level = _get_next_level_from_context(context)
    if next_level:
        max_parallel = min(max_parallel, next_level.get_max_parallel_tasks())
    
    # Create a minimal PromptSequence for dependency analysis
    dummy_sequence = PromptSequence(
        metadata={"id": "parallel_execution"},
        objective="Parallel step execution",
        success_criteria=["All steps completed"],
        assumptions=[],
        usage_notes={},
        inputs_required=[],
        outputs_required=[],
        sequence_steps=sequence_steps,
        final_assembly="",
        validation_rules=[],
        failure_handling="continue",
        final_deliverable_format=""
    )
    
    # Get execution groups (steps that can run in parallel)
    execution_groups = get_execution_groups(dummy_sequence)
    
    total_steps = len(sequence_steps)
    completed_steps = 0
    failed_steps = 0
    execution_start = time.time()
    
    # Execute groups sequentially, steps within groups in parallel
    for group_idx, group in enumerate(execution_groups):
        group_start = time.time()
        
        # Skip already completed steps
        ready_steps = [step for step in group if step.id not in context.completed_steps]
        
        if not ready_steps:
            continue
        
        print(f"Executing group {group_idx + 1}/{len(execution_groups)}: {len(ready_steps)} steps")
        
        # Execute steps in this group in parallel
        group_results = simulate_step_parallel(
            ready_steps, context, 
            max_workers=min(max_parallel, len(ready_steps)),
            timeout=step_timeout
        )
        
        # Update statistics
        for step_id, result in group_results.items():
            completed_steps += 1
            if result["status"] in ["failed", "timeout"]:
                failed_steps += 1
        
        group_time = time.time() - group_start
        print(f"Group {group_idx + 1} completed in {group_time:.2f}s")
    
    total_time = time.time() - execution_start
    
    return {
        "total_steps": total_steps,
        "completed": completed_steps,
        "failed": failed_steps,
        "success_rate": (completed_steps - failed_steps) / completed_steps if completed_steps > 0 else 0,
        "total_time": total_time,
        "parallel_groups_executed": len(execution_groups),
        "context_updates": {
            "completed_steps": len(context.completed_steps),
            "errors": len(context.errors),
            "step_outputs": len(context.step_outputs)
        }
    }


def simulate_subagent_execution(step: StepSpec, subagent_type: str = "general") -> Dict[str, Any]:
    """
    Simulate subagent execution via Task tool.
    
    In a real implementation, this would use:
        task = Task(
            description=f"Execute step: {step.name}",
            prompt=f"Execute the following step: {step.instructions}",
            subagent_type=subagent_type
        )
    
    Args:
        step: Step to execute
        subagent_type: Type of subagent to use ("explore" or "general")
        
    Returns:
        Simulated execution result
    """
    # Simulate different execution times based on step complexity
    complexity_score = len(step.instructions) / 100.0
    execution_time = 1.0 + complexity_score * 2.0
    
    # Simulate success/failure based on step ID (deterministic for testing)
    success = hash(step.id) % 10 != 0  # 90% success rate
    
    if success:
        return {
            "step_id": step.id,
            "step_name": step.name,
            "subagent_type": subagent_type,
            "status": "completed",
            "output": f"Subagent ({subagent_type}) executed: {step.name}",
            "execution_time": execution_time,
            "artifacts": [f"output_{step.id}.md"],
            "logs": [f"Started execution", f"Completed in {execution_time:.2f}s"],
        }
    else:
        return {
            "step_id": step.id,
            "step_name": step.name,
            "subagent_type": subagent_type,
            "status": "failed",
            "output": f"Subagent ({subagent_type}) failed on: {step.name}",
            "execution_time": execution_time,
            "error": "Simulated failure for testing",
            "logs": [f"Started execution", f"Failed after {execution_time:.2f}s"],
        }
