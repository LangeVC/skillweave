# Complexity Analysis for PRD-based Sequence Generation

Guide for analyzing PRD complexity and generating appropriate execution sequences in PromptChain Generate.

## Overview

When PromptChain Generate receives a PRD (`prd.json`), it performs complexity analysis to determine the optimal execution strategy (REX-style simple vs Ralph Loop standard/complex). This analysis ensures that simple tasks get lightweight execution while complex projects get full Ralph Loop benefits.

## Analysis Process

### 1. PRD Loading & Validation
```python
def load_and_validate_prd(prd_path):
    """Load PRD and validate against schema"""
    prd = read_json(prd_path)
    validate_against_schema(prd, "prd.schema.json")
    
    # Check for execution_recommendation
    if "execution_recommendation" in prd:
        return prd, prd["execution_recommendation"]
    else:
        # Calculate if missing
        recommendation = calculate_complexity_recommendation(prd)
        prd["execution_recommendation"] = recommendation
        return prd, recommendation
```

### 2. Complexity Assessment
If `execution_recommendation` exists, use it. Otherwise calculate:

**Primary Factors:**
1. **Task Count**: Number of tasks in PRD
2. **Estimated Duration**: Sum of `estimated_minutes` across all tasks
3. **Dependency Complexity**: Depth and cycles in dependency graph
4. **Agent Diversity**: Different `target_agent` values or `agent_type` requirements
5. **Risk Level**: Based on `risks` array in PRD
6. **Task Type Variety**: Different `type` values (infrastructure, api, ui, etc.)

**Scoring Algorithm:**
```python
def calculate_complexity_score(prd):
    tasks = prd.get("tasks", [])
    
    scores = {
        "task_count": min(len(tasks) * 10, 100),
        "duration": calculate_duration_score(tasks),
        "dependencies": calculate_dependency_complexity(tasks),
        "agents": calculate_agent_diversity(tasks),
        "risks": calculate_risk_score(prd.get("risks", [])),
        "types": calculate_type_variety(tasks)
    }
    
    weights = {
        "task_count": 0.20,
        "duration": 0.25,
        "dependencies": 0.25,
        "agents": 0.15,
        "risks": 0.10,
        "types": 0.05
    }
    
    total_score = sum(scores[factor] * weights[factor] for factor in scores)
    return min(total_score, 100), scores
```

### 3. Mode Determination
Based on complexity score:

| Score Range | Mode | Workflow | Description |
|-------------|------|----------|-------------|
| 0-30 | `simple` | `rex-simple` | 1-3 tasks, <60 min, simple dependencies |
| 31-70 | `standard` | `ralph-loop-attended` | 4-10 tasks, 1-4 hours, moderate complexity |
| 71-100 | `complex` | `ralph-loop-overnight` | 10+ tasks, >4 hours, complex dependencies |

### 4. Dependency Graph Analysis
```python
def analyze_dependencies(tasks):
    """Build dependency graph and find parallel opportunities"""
    graph = {task["id"]: set(task.get("dependencies", [])) for task in tasks}
    
    # Find parallel execution opportunities
    parallel_groups = []
    completed = set()
    
    while len(completed) < len(tasks):
        # Find ready tasks (all dependencies satisfied)
        ready = [
            task for task in tasks
            if task["id"] not in completed and
            all(dep in completed for dep in graph[task["id"]])
        ]
        
        if not ready:
            break  # Deadlock or circular dependency
        
        # Group by task type for parallel execution
        parallel_groups.append({
            "tasks": [task["id"] for task in ready],
            "count": len(ready),
            "types": list(set(task["type"] for task in ready))
        })
        
        completed.update(task["id"] for task in ready)
    
    return graph, parallel_groups
```

## Sequence Generation Based on Mode

### Simple Mode (REX-style)
For 1-3 simple tasks with minimal dependencies:

```yaml
sequence:
  mode: "simple"
  workflow: "rex-simple"
  description: "Quick execution with plan-implement-review workflow"
  
  steps:
    - id: "plan"
      type: "analysis"
      description: "Analyze requirements and create implementation plan"
      outputs: ["implementation_plan.md"]
      
    - id: "implement"
      type: "execution"
      description: "Implement solution based on plan"
      depends_on: ["plan"]
      outputs: ["code_changes", "implementation_report.md"]
      
    - id: "review"
      type: "verification"
      description: "Review implementation and verify acceptance criteria"
      depends_on: ["implement"]
      outputs: ["verification_report.md", "completion_status"]
      
    - id: "complete"
      type: "finalization"
      description: "Finalize and deliver solution"
      depends_on: ["review"]
      outputs: ["final_deliverable", "summary_report.md"]
      
  revision_loop:
    enabled: true
    max_revisions: 2
    triggers: ["verification_failed", "acceptance_criteria_not_met"]
```

### Standard Mode (Ralph Loop Attended)
For 4-10 tasks with moderate complexity:

```yaml
sequence:
  mode: "standard"
  workflow: "ralph-loop-attended"
  checkpoint_interval: 5
  description: "Ralph Loop execution with human checkpoints"
  
  phases:
    - name: "initialization"
      tasks: ["INFRA-001", "DB-001"]
      description: "Project setup and infrastructure"
      verification: ["typecheck", "lint", "build"]
      
    - name: "core-development"
      tasks: ["API-001", "UI-001", "FEAT-001"]
      depends_on: ["initialization"]
      parallel: true
      description: "Core feature implementation"
      verification: ["tests", "integration_tests"]
      
    - name: "testing"
      tasks: ["TEST-001", "TEST-002"]
      depends_on: ["core-development"]
      parallel: true
      description: "Comprehensive testing"
      verification: ["test_coverage", "e2e_tests"]
      
    - name: "finalization"
      tasks: ["DOC-001", "DEPLOY-001"]
      depends_on: ["testing"]
      description: "Documentation and deployment preparation"
      verification: ["documentation_complete", "deployment_ready"]
      
  memory_system:
    short_term: "progress-structured.yaml"
    long_term: "agents-enhanced.md"
    update_frequency: "per_iteration"
    
  verification:
    levels: ["code", "functional", "system"]
    gates: ["pre_commit", "pre_merge", "pre_deploy"]
```

### Complex Mode (Ralph Loop Overnight)
For 10+ tasks with complex dependencies:

```yaml
sequence:
  mode: "complex"
  workflow: "ralph-loop-overnight"
  max_iterations: 50
  timeout_minutes: 480
  description: "Fully autonomous overnight execution"
  
  execution_strategy:
    parallel_execution: true
    max_parallel_tasks: 3
    agent_routing: "capability_based"
    fallback_strategy: "retry_then_escalate"
    
  phases:
    # Dynamically generated based on dependency graph
    - phase: "phase_1"
      tasks: ["INFRA-001", "INFRA-002", "DB-001"]
      parallel: true
      agent_capabilities: ["infrastructure", "code_generation"]
      
    - phase: "phase_2"
      tasks: ["API-001", "API-002", "API-003"]
      depends_on: ["phase_1"]
      parallel: true
      agent_capabilities: ["code_generation", "testing"]
      
    # ... additional phases based on dependency analysis
    
  quality_gates:
    - gate: "code_quality"
      checks: ["typecheck", "lint", "complexity_analysis"]
      threshold: "must_pass"
      
    - gate: "test_coverage"
      checks: ["unit_tests", "integration_tests", "e2e_tests"]
      threshold: ">80%"
      
    - gate: "performance"
      checks: ["load_testing", "response_time", "memory_usage"]
      threshold: "meets_sla"
      
  monitoring:
    notifications: true
    progress_tracking: "real_time"
    error_escalation: "after_3_attempts"
```

## Capability Mapping

Instead of specifying concrete agents (opencode, claude-code, etc.), PromptChain uses capability-based routing:

### Task Type to Capability Mapping
```python
TASK_TYPE_TO_CAPABILITIES = {
    "infrastructure": ["infrastructure", "code_generation"],
    "database": ["database", "code_generation"],
    "api": ["code_generation", "testing"],
    "ui": ["code_generation", "ui_design"],
    "integration": ["code_generation", "automation"],
    "testing": ["testing", "code_generation"],
    "documentation": ["documentation", "research"],
    "devops": ["infrastructure", "automation"],
    "security": ["security", "review"],
    "performance": ["performance", "review"]
}
```

### Agent Assignment
Generated sequences include capability requirements, not specific agents:
```yaml
agent_assignments:
  INFRA-001:
    required_capabilities: ["infrastructure", "code_generation"]
    recommended_agents: ["any_with_capabilities"]
    estimated_tokens: 1500
    estimated_minutes: 15
    
  API-001:
    required_capabilities: ["code_generation", "testing"]
    recommended_agents: ["any_with_capabilities"]
    estimated_tokens: 2000
    estimated_minutes: 25
```

## Output Files

PromptChain Generate creates these output files:

### Primary Outputs
1. **`execution-sequences.yaml`**: Main execution plan with phases, dependencies, and verification
2. **`agent-assignments.json`**: Task-to-capability mapping (agent-agnostic)
3. **`dependency-graph.dot`**: Visual dependency graph (Graphviz format)
4. **`complexity-analysis.md`**: Detailed complexity assessment report

### Supporting Files
5. **`workflow-recommendation.md`**: REX vs Ralph Loop recommendation with rationale
6. **`parallel-opportunities.json`**: Identified parallel execution opportunities
7. **`risk-assessment.md`**: Risk analysis and mitigation strategies
8. **`verification-plan.md`**: Detailed verification steps for each task

## Integration with Other Skills

### From Blueprint
```bash
# Blueprint creates PRD
/skillweave-blueprint idea="Project idea" domain="saas"

# PromptChain generates execution sequences
/skillweave-promptchain-generate inputs='{"prd": "generated/prd.json"}' mode="auto"
```

### To Execute
```bash
# Execute the generated sequences
/skillweave-promptchain-execute sequence="execution-sequences.yaml" inputs='{"prd": "generated/prd.json"}'
```

### To ReleaseChain
```bash
# For build components, execute with Ralph Loop
/skillweave-releasechain inputs='{"prd": "generated/prd.json", "sequences": "execution-sequences.yaml"}' mode="attended"
```

## Best Practices

1. **Always check `execution_recommendation` first**: Use pre-calculated recommendation if available
2. **Validate dependency graph**: Ensure no circular dependencies before generating sequences
3. **Consider parallel opportunities**: Identify tasks that can run concurrently
4. **Map to capabilities, not agents**: Keep sequences agent-agnostic
5. **Include revision loops**: Allow for fixes and improvements
6. **Document assumptions**: Clearly state what the sequence assumes
7. **Provide fallback strategies**: Plan for failure scenarios
8. **Optimize for target audience**: Adjust output format based on `target` parameter

## Troubleshooting

### Common Issues

**Issue**: Circular dependencies in PRD
**Solution**: Detect during analysis and report error with specific task IDs

**Issue**: Missing `execution_recommendation`
**Solution**: Calculate complexity score and add recommendation to output

**Issue**: Unrealistic time estimates
**Solution**: Flag tasks with extreme estimates (>8 hours) for review

**Issue**: No parallel opportunities
**Solution**: Suggest task restructuring to enable parallelism

**Issue**: High-risk tasks without mitigation
**Solution**: Add risk mitigation steps to sequence