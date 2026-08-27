# Complexity Assessment Guide

Guidelines for assessing project complexity and recommending appropriate execution strategies in SkillWeave Blueprint.

## Assessment Criteria

### 1. Task Count
- **Low (1-3 tasks)**: Simple Mode (REX-style) recommended
- **Medium (4-10 tasks)**: Standard Mode (Ralph Loop Attended)
- **High (10+ tasks)**: Complex Mode (Ralph Loop Overnight)

### 2. Estimated Duration
- **Short (<60 minutes)**: Simple Mode
- **Medium (1-4 hours)**: Standard Mode  
- **Long (>4 hours)**: Complex Mode

### 3. Dependency Complexity
```python
# Dependency complexity scoring
def calculate_dependency_complexity(tasks):
    total_dependencies = sum(len(task.get("dependencies", [])) for task in tasks)
    max_depth = calculate_dependency_depth(tasks)
    has_cycles = detect_dependency_cycles(tasks)
    
    score = 0
    if total_dependencies == 0:
        score = 10
    elif total_dependencies <= len(tasks) * 0.5:
        score = 30
    elif total_dependencies <= len(tasks):
        score = 50
    else:
        score = 70
    
    if max_depth > 3:
        score += 20
    if has_cycles:
        score += 30
    
    return min(score, 100)
```

### 4. Agent Diversity
- **Low (1 agent type)**: Simple execution
- **Medium (2-3 agent types)**: Standard execution with agent routing
- **High (4+ agent types)**: Complex execution with coordination

### 5. Risk Level
- **Low**: All tasks low priority, few assumptions, minimal risks
- **Medium**: Mix of priorities, some assumptions, identified risks
- **High**: Critical tasks, many assumptions, high-impact risks

### 6. Task Type Variety
- **Homogeneous**: All tasks same type (e.g., all API endpoints)
- **Mixed**: 2-3 different types (e.g., API + UI + database)
- **Diverse**: 4+ different types (e.g., infrastructure, API, UI, testing, security)

## Scoring Algorithm

```python
def assess_complexity(prd):
    """Calculate complexity score and recommend execution mode"""
    
    tasks = prd.get("tasks", [])
    risks = prd.get("risks", [])
    
    # Component scores (0-100 each)
    task_count_score = min(len(tasks) * 10, 100)
    duration_score = calculate_duration_score(tasks)
    dependency_score = calculate_dependency_complexity(tasks)
    agent_score = calculate_agent_diversity(tasks)
    risk_score = calculate_risk_score(risks)
    type_score = calculate_type_variety(tasks)
    
    # Weighted average
    weights = {
        "task_count": 0.20,
        "duration": 0.25,
        "dependencies": 0.25,
        "agents": 0.15,
        "risks": 0.10,
        "types": 0.05
    }
    
    total_score = (
        task_count_score * weights["task_count"] +
        duration_score * weights["duration"] +
        dependency_score * weights["dependencies"] +
        agent_score * weights["agents"] +
        risk_score * weights["risks"] +
        type_score * weights["types"]
    )
    
    # Recommendation
    if total_score < 30:
        mode = "simple"
        workflow = "rex-simple"
    elif total_score < 70:
        mode = "standard"
        workflow = "ralph-loop-attended"
    else:
        mode = "complex"
        workflow = "ralph-loop-overnight"
    
    return {
        "mode": mode,
        "workflow": workflow,
        "score": total_score,
        "component_scores": {
            "task_count": task_count_score,
            "duration": duration_score,
            "dependencies": dependency_score,
            "agents": agent_score,
            "risks": risk_score,
            "types": type_score
        }
    }
```

## Helper Functions

### Duration Score Calculation
```python
def calculate_duration_score(tasks):
    total_minutes = sum(task.get("estimated_minutes", 30) for task in tasks)
    
    if total_minutes < 60:
        return 20  # Simple
    elif total_minutes < 240:  # 4 hours
        return 50  # Medium
    elif total_minutes < 480:  # 8 hours
        return 75  # High
    else:
        return 100  # Very high
```

### Agent Diversity Calculation
```python
def calculate_agent_diversity(tasks):
    capabilities = set()
    for task in tasks:
        # Diversity is measured by required capabilities, not concrete hosts.
        caps = task.get("required_capabilities") or ["any"]
        capabilities.update(caps)

    diversity = len(capabilities)
    if diversity == 1:
        return 20
    elif diversity == 2:
        return 40
    elif diversity == 3:
        return 60
    elif diversity == 4:
        return 80
    else:
        return 100
```

### Risk Score Calculation
```python
def calculate_risk_score(risks):
    if not risks:
        return 10
    
    risk_values = {
        "low": 10,
        "medium": 50,
        "high": 80,
        "critical": 100
    }
    
    impact_values = {
        "low": 10,
        "medium": 40,
        "high": 70,
        "critical": 100
    }
    
    total_score = 0
    for risk in risks:
        probability = risk.get("probability", "low")
        impact = risk.get("impact", "low")
        total_score += risk_values.get(probability, 10) * 0.4
        total_score += impact_values.get(impact, 10) * 0.6
    
    return min(total_score / len(risks), 100)
```

### Type Variety Calculation
```python
def calculate_type_variety(tasks):
    types = set(task.get("type", "unknown") for task in tasks)
    
    if len(types) == 1:
        return 20
    elif len(types) == 2:
        return 40
    elif len(types) == 3:
        return 60
    elif len(types) == 4:
        return 80
    else:
        return 100
```

## Execution Mode Details

### Simple Mode (REX-style)
**Characteristics**:
- 1-3 atomic tasks
- <60 minutes total estimated time
- Simple or no dependencies
- Single agent type sufficient
- Low risk profile

**Workflow**:
```
Plan → Implement → Review → Done
       ↖_________↙
          (if issues)
```

**Best Used For**:
- Quick bug fixes
- Small feature additions
- Prototype validation
- Documentation updates
- Configuration changes

**SkillWeave Integration**:
- Uses `skillweave-promptchain-execute` directly
- Minimal memory system (simple progress tracking)
- Single-pass execution with optional review loop

### Standard Mode (Ralph Loop Attended)
**Characteristics**:
- 4-10 tasks
- 1-4 hours total estimated time
- Moderate dependency complexity
- 2-3 agent types needed
- Medium risk profile

**Workflow**:
```
Initialize → Task Selection → Execution → Verification → Memory Update
    ↑                                                            ↓
    └─────────────────── Completion Check ───────────────────────┘
```

**Best Used For**:
- Feature development
- Moderate refactoring
- API endpoint implementation
- UI component development
- Database migrations

**SkillWeave Integration**:
- Uses `skillweave-releasechain` with `mode="attended"`
- Full memory system (`progress-structured.yaml`, `agents-enhanced.md`)
- Human checkpoints every 5 iterations
- Multi-agent coordination

### Complex Mode (Ralph Loop Overnight)
**Characteristics**:
- 10+ tasks
- >4 hours total estimated time
- Complex dependency graph
- 3+ agent types required
- High risk profile

**Workflow**:
```
Full autonomous Ralph Loop execution
- Parallel task execution where possible
- Comprehensive verification gates
- Automatic error recovery
- Notification system for completion
```

**Best Used For**:
- Major feature development
- System architecture changes
- New project creation
- Complete application builds
- Production deployment preparation

**SkillWeave Integration**:
- Uses `skillweave-releasechain` with `mode="overnight"`
- Advanced memory system with cross-project learning
- Parallel execution engine
- Automated quality gates
- Morning review reports

## Parallel Execution Opportunities

### Detection Algorithm
```python
def find_parallel_opportunities(tasks):
    """Identify tasks that can run in parallel"""
    
    completed = set()
    ready_tasks = []
    parallel_groups = []
    
    # Build dependency graph
    graph = {task["id"]: set(task.get("dependencies", [])) for task in tasks}
    
    while len(completed) < len(tasks):
        # Find tasks with all dependencies satisfied
        ready = [
            task for task in tasks 
            if task["id"] not in completed and
            all(dep in completed for dep in graph[task["id"]])
        ]
        
        if not ready:
            # Deadlock or circular dependency
            break
        
        # Group by target for parallel execution; the neutral default lets the
        # runtime map to any available capability/runtime rather than pinning a host.
        by_agent = {}
        for task in ready:
            agent = task.get("target_agent", "any")
            by_agent.setdefault(agent, []).append(task["id"])
        
        # Add parallel group if multiple tasks can run concurrently
        parallel_count = sum(len(tasks) for tasks in by_agent.values() if len(tasks) > 1)
        if parallel_count > 1:
            parallel_groups.append({
                "agents": by_agent,
                "task_count": len(ready),
                "parallel_savings": len(ready) - len(by_agent)  # Approximate time saving
            })
        
        # Mark as completed (simulate execution)
        completed.update(task["id"] for task in ready)
    
    return parallel_groups
```

### Parallel Execution Benefits
- **Time Savings**: Up to 40% reduction in total execution time
- **Resource Utilization**: Better use of multiple agent capabilities
- **Faster Feedback**: Early discovery of integration issues
- **Load Distribution**: Avoids agent rate limiting

## Decision Tree

```
Start
  ↓
Analyze PRD tasks
  ↓
Count tasks
  ↓
<4 tasks? → Yes → Simple Mode (REX)
  ↓ No
Calculate total estimated time
  ↓
<4 hours? → Yes → Standard Mode (Attended)
  ↓ No  
Check dependency complexity
  ↓
Low complexity? → Yes → Standard Mode (Attended)
  ↓ No
Check risk level
  ↓
High risk? → Yes → Complex Mode (Overnight with human oversight)
  ↓ No
Complex Mode (Overnight)
```

## Integration with SkillWeave Skills

### Blueprint Skill
- Performs initial complexity assessment
- Adds `execution_recommendation` to `prd.json`
- Provides guidance on next steps

### PromptChain Skill
- Uses recommendation to generate appropriate sequences
- For simple mode: Generates direct execution plan
- For standard/complex: Generates Ralph Loop sequences

### ReleaseChain Skill
- Reads `execution_recommendation` from PRD
- Configures execution mode accordingly
- Adjusts verification level based on complexity

### Execute Skill
- Handles simple mode execution directly
- For standard/complex modes, delegates to ReleaseChain
- Provides fallback if ReleaseChain not available

## Example Assessments

### Example 1: Simple Bug Fix
```
Tasks: 1 (BUG-001: Fix login error)
Duration: 30 minutes
Dependencies: None
Capabilities: 1 (code_generation)
Risks: Low
Types: 1 (bug-fix)

Assessment: Simple Mode (score: 15)
Recommendation: Direct execution with REX-style workflow
```

### Example 2: Feature Development
```
Tasks: 5 (INFRA-001, API-001, UI-001, TEST-001, DOC-001)
Duration: 3 hours
Dependencies: Moderate (API depends on INFRA, UI depends on API)
Capabilities: 3 (code_generation, testing, review)
Risks: Medium
Types: 4 (infrastructure, api, ui, documentation)

Assessment: Standard Mode (score: 55)
Recommendation: Ralph Loop Attended with checkpoints
```

### Example 3: New Project
```
Tasks: 12 (various setup, core features, testing, deployment)
Duration: 8 hours
Dependencies: Complex (multiple dependency chains)
Capabilities: 4 (code_generation, testing, review, infrastructure)
Risks: High
Types: 6 (infrastructure, api, ui, database, testing, devops)

Assessment: Complex Mode (score: 85)
Recommendation: Ralph Loop Overnight with parallel execution
```

## Best Practices

1. **Start Simple**: Begin with REX-style for unknown complexity, escalate as needed
2. **Monitor Progress**: Track actual vs estimated time to improve future assessments
3. **Adjust Dynamically**: Allow mode switching if complexity changes during execution
4. **Learn from History**: Use completed project data to refine scoring algorithms
5. **Human Oversight**: Always include human review points for high-risk projects

## Continuous Improvement

The complexity assessment should evolve based on:
- Historical project data
- Success/failure rates by mode
- User feedback on recommendations
- Changes in agent capabilities
- New workflow patterns discovered

Update the scoring weights and thresholds periodically to maintain accuracy.