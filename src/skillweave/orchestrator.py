from typing import List, Dict, Set, Tuple, Optional, Any
from .models import WorkflowContext, PromptSequence, StepSpec


def initialize_context(
    sequence_id: str, 
    mode: str, 
    inputs: dict, 
    usage_notes: dict,
    project_root: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> WorkflowContext:
    """Initialize workflow context with optional Next Level integration.
    
    Args:
        sequence_id: Unique identifier for the sequence
        mode: Execution mode (maps to RiskMode)
        inputs: Input data for the workflow
        usage_notes: Usage notes for the sequence
        project_root: Optional project root for Next Level features
        metadata: Optional additional metadata
    
    Returns:
        WorkflowContext with optional Next Level instance in metadata
    """
    metadata_dict = metadata or {}
    
    # If project_root provided, try to create SkillWeaveNextLevel instance
    if project_root:
        try:
            from .next_level import SkillWeaveNextLevel
            next_level = SkillWeaveNextLevel(project_root)
            metadata_dict["next_level"] = next_level
            # Update mode from next_level configuration (if different)
            mode = next_level.get_mode().value
        except ImportError:
            # Next Level not available, continue without it
            pass
    
    return WorkflowContext(
        sequence_id=sequence_id,
        mode=mode,
        status="running",
        inputs=inputs,
        usage_notes=usage_notes,
        metadata=metadata_dict,
    )


def next_step(sequence: PromptSequence, context: WorkflowContext) -> Optional[StepSpec]:
    """Get the next step that can be executed (legacy sequential mode)."""
    completed = set(context.completed_steps)
    for step in sequence.sequence_steps:
        deps = set(step.depends_on)
        if step.id not in completed and deps.issubset(completed):
            return step
    return None


def analyze_dependencies(sequence: PromptSequence) -> Dict[str, Set[str]]:
    """
    Analyze dependencies and build dependency graph.
    
    Returns:
        Dict mapping step_id to set of steps it depends on.
    """
    dependency_graph = {}
    for step in sequence.sequence_steps:
        dependency_graph[step.id] = set(step.depends_on)
    return dependency_graph


def detect_circular_dependencies(dependency_graph: Dict[str, Set[str]]) -> List[List[str]]:
    """
    Detect circular dependencies in the graph using DFS.
    
    Returns:
        List of cycles found (each cycle as list of step IDs).
    """
    def dfs(node: str, path: List[str], visited: Set[str], in_stack: Set[str]) -> List[List[str]]:
        if node in in_stack:
            # Found a cycle
            start_index = path.index(node)
            return [path[start_index:]]
        
        if node in visited:
            return []
        
        visited.add(node)
        in_stack.add(node)
        path.append(node)
        
        cycles = []
        for neighbor in dependency_graph.get(node, set()):
            cycles.extend(dfs(neighbor, path.copy(), visited, in_stack.copy()))
        
        in_stack.remove(node)
        path.pop()
        return cycles
    
    visited = set()
    all_cycles = []
    
    for node in dependency_graph:
        if node not in visited:
            cycles = dfs(node, [], visited, set())
            all_cycles.extend(cycles)
    
    return all_cycles


def get_available_steps(sequence: PromptSequence, context: WorkflowContext) -> List[StepSpec]:
    """
    Get all steps that are available for execution (can run in parallel).
    
    Returns:
        List of StepSpec objects that can be executed now.
    """
    completed = set(context.completed_steps)
    available = []
    
    for step in sequence.sequence_steps:
        if step.id in completed:
            continue
        
        deps = set(step.depends_on)
        if deps.issubset(completed):
            available.append(step)
    
    return available


def get_execution_groups(sequence: PromptSequence) -> List[List[StepSpec]]:
    """
    Group steps by their dependencies to identify parallel execution opportunities.
    
    Returns:
        List of step groups, where steps in the same group can run in parallel.
    """
    # Build dependency graph
    dependency_graph = analyze_dependencies(sequence)
    
    # Map step IDs to StepSpec objects
    step_map = {step.id: step for step in sequence.sequence_steps}
    
    # Calculate in-degree for each node
    in_degree = {step_id: 0 for step_id in step_map}
    for step_id, deps in dependency_graph.items():
        in_degree[step_id] = len(deps)
    
    # Kahn's algorithm for topological sort with level grouping
    levels = []
    current_level = []
    
    # Initialize queue with nodes having in-degree 0
    queue = [step_id for step_id, degree in in_degree.items() if degree == 0]
    
    while queue:
        next_level = []
        
        for step_id in queue:
            current_level.append(step_map[step_id])
            
            # Reduce in-degree of neighbors
            for neighbor_id, deps in dependency_graph.items():
                if step_id in deps:
                    in_degree[neighbor_id] -= 1
                    if in_degree[neighbor_id] == 0:
                        next_level.append(neighbor_id)
        
        # Add current level to levels
        if current_level:
            levels.append(current_level)
        
        # Prepare for next level
        queue = next_level
        current_level = []
    
    return levels


def can_execute_in_parallel(sequence: PromptSequence) -> bool:
    """
    Check if sequence has opportunities for parallel execution.
    
    Returns:
        True if there are independent steps that can run in parallel.
    """
    execution_groups = get_execution_groups(sequence)
    
    # If any group has more than 1 step, parallel execution is possible
    for group in execution_groups:
        if len(group) > 1:
            return True
    
    return False


def get_parallel_execution_plan(sequence: PromptSequence) -> Dict:
    """
    Create a detailed parallel execution plan.
    
    Returns:
        Dict with execution plan including groups, dependencies, and optimization suggestions.
    """
    dependency_graph = analyze_dependencies(sequence)
    execution_groups = get_execution_groups(sequence)
    cycles = detect_circular_dependencies(dependency_graph)
    
    # Calculate parallelization metrics
    total_steps = len(sequence.sequence_steps)
    parallelizable_groups = sum(1 for group in execution_groups if len(group) > 1)
    max_parallel_steps = max((len(group) for group in execution_groups), default=0)
    
    # Estimate execution time (simplified)
    sequential_time = total_steps * 1.0  # Assuming 1 unit per step
    parallel_time = len(execution_groups) * 1.0  # Assuming 1 unit per group
    speedup = sequential_time / parallel_time if parallel_time > 0 else 1.0
    
    return {
        "total_steps": total_steps,
        "dependency_graph": {k: list(v) for k, v in dependency_graph.items()},
        "execution_groups": [[step.id for step in group] for group in execution_groups],
        "circular_dependencies": cycles,
        "parallelization_opportunities": parallelizable_groups,
        "max_concurrent_steps": max_parallel_steps,
        "estimated_speedup": round(speedup, 2),
        "recommended_mode": "parallel" if can_execute_in_parallel(sequence) else "sequential",
        "optimization_suggestions": _generate_optimization_suggestions(sequence, dependency_graph, execution_groups)
    }


def _generate_optimization_suggestions(sequence: PromptSequence, 
                                       dependency_graph: Dict[str, Set[str]], 
                                       execution_groups: List[List[StepSpec]]) -> List[str]:
    """Generate optimization suggestions based on dependency analysis."""
    suggestions = []
    
    # Check for steps with many dependencies
    for step_id, deps in dependency_graph.items():
        if len(deps) > 3:
            suggestions.append(f"Step '{step_id}' has {len(deps)} dependencies - consider splitting or simplifying")
    
    # Check for large sequential chains
    for group in execution_groups:
        if len(group) == 1:
            # Check if this single step has many dependents
            step = group[0]
            dependents = 0
            for other_id, deps in dependency_graph.items():
                if step.id in deps:
                    dependents += 1
            
            if dependents > 2:
                suggestions.append(f"Step '{step.id}' is a bottleneck with {dependents} dependent steps")
    
    # Check for independent steps that could be grouped
    independent_steps = []
    for step in sequence.sequence_steps:
        if not step.depends_on:
            independent_steps.append(step.id)
    
    if len(independent_steps) > 1:
        suggestions.append(f"Multiple independent steps ({len(independent_steps)}) - good candidate for parallel execution")
    
    return suggestions
