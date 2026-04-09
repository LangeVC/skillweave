# Ralph Loop Implementation Guide

Detailed implementation guide for Ralph Loop execution within SkillWeave ReleaseChain.

## Core Loop Mechanism

### Basic Ralph Loop Structure
```bash
# Original Ralph Loop (simplified)
while true; do
  cat prompt.md | claude
  if grep -q "<promise>COMPLETE</promise>" output.txt; then
    break
  fi
done
```

### SkillWeave Enhanced Loop
```python
# Pseudocode for SkillWeave Ralph Loop
def ralph_loop_execution(prd, settings):
    """Execute tasks using Ralph Loop principles"""
    
    # Initialize memory system
    memory = initialize_memory(prd)
    task_queue = build_task_queue(prd["tasks"])
    
    iteration = 0
    while iteration < settings["max_iterations"]:
        iteration += 1
        
        # Select next task
        task = select_next_task(task_queue, memory)
        if not task:
            # All tasks completed
            break
        
        # Route to appropriate agent
        agent = route_to_agent(task, settings["available_agents"])
        
        # Execute task
        result = execute_task_with_agent(task, agent, memory)
        
        # Update memory
        update_progress_memory(memory, iteration, task, result)
        
        # Verify and update task status
        if verify_task_completion(task, result):
            task["passes"] = True
            update_agents_memory(memory, task, "success")
        else:
            task["attempts"] += 1
            update_agents_memory(memory, task, "failure")
        
        # Check completion promise
        if check_completion_promise(result):
            log_completion(memory, iteration)
            break
    
    return generate_completion_report(memory, iteration)
```

## Memory System Implementation

### progress-structured.yaml Format
```yaml
# Example progress file
project: "Todo API"
version: "1.0.0"
start_time: "2024-01-15T10:00:00Z"
settings:
  max_iterations: 30
  mode: "attended"
  verification_level: "standard"

iterations:
  - id: "iteration-001"
    timestamp: "2024-01-15T10:05:00Z"
    task: "INFRA-001"
    agent: "agent-001"
    duration_seconds: 300
    status: "success"
    changes:
      - file: "package.json"
        action: "created"
        lines: 25
      - file: "tsconfig.json"
        action: "created"
        lines: 15
    verification:
      typecheck: "passed"
      lint: "passed"
      build: "passed"
      tests: "passed"
    learnings:
      - "Use npm init -y for quick package.json setup"
      - "TypeScript strict mode catches null errors"
    next_task: "DB-001"

  - id: "iteration-002"
    timestamp: "2024-01-15T10:15:00Z"
    task: "DB-001"
    agent: "agent-001"
    duration_seconds: 600
    status: "success"
    changes:
      - file: "src/models/User.ts"
        action: "created"
        lines: 45
      - file: "src/db/migrations/001_create_users.ts"
        action: "created"
        lines: 30
    verification:
      typecheck: "passed"
      tests: "failed"  # Tests need to be written
    learnings:
      - "Database migrations should be timestamped"
      - "User model needs email validation"
    next_task: "API-001"

metrics:
  tasks_completed: 2
  tasks_total: 15
  success_rate: 100.0
  avg_iteration_time_seconds: 450
  tokens_used: 12500
  estimated_cost: 0.25
```

### agents-enhanced.md Format
```markdown
# Project Knowledge Base
## Todo API - Enhanced Agents Memory

### Architecture Patterns
#### Database Design
- Use timestamped migrations (YYYYMMDDHHMMSS_name.ts)
- Models in src/models/, migrations in src/db/migrations/
- Use UUID v4 for primary keys
- Add indexes for frequently queried columns

#### API Design
- RESTful endpoints with versioning (/api/v1/)
- Consistent error format: { error: string, code: number }
- Input validation with class-validator
- Response standardization

### Code Conventions
#### TypeScript
- Use strict mode (always)
- Prefer interfaces over type for public APIs
- Async/await over callbacks
- Proper error handling with try/catch

#### Testing
- Jest for unit tests
- Supertest for API tests
- Test database with SQLite in memory
- Coverage target: 80% minimum

### Integration Knowledge
#### Authentication
- JWT tokens with 24h expiry
- Refresh token mechanism
- Password hashing with bcrypt

#### Third-Party Services
- SendGrid for emails (template: welcome_email)
- Stripe for payments (test mode: sk_test_*)

### Common Issues & Solutions
#### Database Connection Issues
- Problem: Connection timeout under load
- Solution: Implement connection pooling
- Implementation: pg.Pool for PostgreSQL

#### TypeScript Compilation Errors
- Problem: Can't find module
- Solution: Proper tsconfig paths
- Implementation: baseUrl: "./src"

### Agent-Specific Notes
#### Opencode
- Prefers explicit file paths
- Good with structured templates
- Needs clear success criteria
- Best for: Infrastructure, database, API

#### Claude Code
- Strong with architectural decisions
- Good at explaining trade-offs
- Needs context management
- Best for: Planning, complex logic

#### Codex
- Fast iterations
- Good at code completion
- Less strong on architecture
- Best for: Small fixes, prototyping
```

## Completion Promise System

### Standard Completion Format
```xml
<skillweave-complete>
status: success
task: INFRA-001
timestamp: 2024-01-15T10:05:00Z
verification:
  typecheck: passed
  lint: passed  
  tests: passed
  build: passed
metrics:
  tokens_used: 1250
  duration_seconds: 300
  files_changed: 2
next_task: DB-001
</skillweave-complete>
```

### Verification Before Promise
```python
def verify_before_promise(task, changes):
    """Verify task completion before issuing completion promise"""
    
    verification_results = {}
    
    # 1. Code quality checks
    verification_results["typecheck"] = run_type_check()
    verification_results["lint"] = run_lint_check()
    
    # 2. Functional verification
    if task["type"] in ["api", "ui", "integration"]:
        verification_results["tests"] = run_tests(task)
    
    # 3. Build verification
    verification_results["build"] = run_build()
    
    # 4. Acceptance criteria verification
    verification_results["acceptance"] = verify_acceptance_criteria(task)
    
    # All must pass for completion
    return all(verification_results.values()), verification_results
```

## Task Execution Engine

### Task Selection Algorithm
```python
def select_next_task(task_queue, memory):
    """Select next task based on dependencies and priority"""
    
    # Filter to ready tasks (dependencies satisfied)
    ready_tasks = [
        task for task in task_queue 
        if not task["passes"] and
        all(dep in get_completed_tasks(memory) for dep in task.get("dependencies", []))
    ]
    
    if not ready_tasks:
        return None
    
    # Prioritize by: critical > high > medium > low
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ready_tasks.sort(key=lambda t: priority_order.get(t["priority"], 4))
    
    # Consider recent failures for retry
    for task in ready_tasks:
        if task.get("attempts", 0) > 0:
            # Failed task, maybe retry with different approach
            return task
    
    return ready_tasks[0]
```

### Agent Routing Logic (Capability-Based)
```python
def route_to_agent(task, available_agents):
    """Route task to appropriate agent based on capabilities"""
    
    # available_agents format: {"agent_name": ["capability1", "capability2", ...]}
    # Example: {"agent1": ["code_generation", "testing"], "agent2": ["planning", "review"]}
    
    # Check for specific agent requirement
    if task.get("target_agent") and task["target_agent"] in available_agents:
        return task["target_agent"]
    
    # Determine required capabilities based on task type
    task_type_to_capabilities = {
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
    
    required_caps = task_type_to_capabilities.get(task["type"], ["code_generation"])
    
    # Find best matching agent
    best_agent = None
    best_score = 0
    
    for agent_name, agent_capabilities in available_agents.items():
        # Calculate match score
        match_count = sum(1 for cap in required_caps if cap in agent_capabilities)
        score = match_count / len(required_caps) if required_caps else 0
        
        if score > best_score:
            best_score = score
            best_agent = agent_name
    
    # Return best match or first available
    return best_agent if best_agent else (list(available_agents.keys())[0] if available_agents else None)
```

## Verification Feedback Loops

### Multi-Level Verification Pipeline
```bash
# Verification script template
#!/bin/bash
# verify_task.sh

TASK_ID=$1
TASK_TYPE=$2

echo "Starting verification for task: $TASK_ID"

# Level 1: Code Quality
echo "=== Level 1: Code Quality ==="
npm run typecheck
TYPE_CHECK_RESULT=$?

npm run lint
LINT_RESULT=$?

# Level 2: Functional Correctness
echo "=== Level 2: Functional Correctness ==="
if [[ "$TASK_TYPE" == "api" || "$TASK_TYPE" == "ui" ]]; then
    npm test -- --testPathPattern="$TASK_ID"
    TEST_RESULT=$?
else
    TEST_RESULT=0  # Skip tests for infrastructure tasks
fi

# Level 3: Build Verification
echo "=== Level 3: Build Verification ==="
npm run build
BUILD_RESULT=$?

# Level 4: Acceptance Criteria
echo "=== Level 4: Acceptance Criteria ==="
# Custom verification based on task
verify_acceptance_criteria "$TASK_ID"
ACCEPTANCE_RESULT=$?

# Overall result
if [[ $TYPE_CHECK_RESULT -eq 0 && $LINT_RESULT -eq 0 && $TEST_RESULT -eq 0 && $BUILD_RESULT -eq 0 && $ACCEPTANCE_RESULT -eq 0 ]]; then
    echo "Verification PASSED"
    exit 0
else
    echo "Verification FAILED"
    echo "Details:"
    echo "  Type check: $TYPE_CHECK_RESULT"
    echo "  Lint: $LINT_RESULT"
    echo "  Tests: $TEST_RESULT"
    echo "  Build: $BUILD_RESULT"
    echo "  Acceptance: $ACCEPTANCE_RESULT"
    exit 1
fi
```

## Execution Levels Implementation

### Level 1: Manual Execution
```python
def execute_level_manual(prd, settings):
    """Level 1: Manual execution with observation"""
    
    print("=== Ralph Loop Level 1: Manual Execution ===")
    print("Execute one task at a time with manual verification")
    
    task_queue = build_task_queue(prd["tasks"])
    
    for task in task_queue:
        print(f"\nTask: {task['id']} - {task['title']}")
        print(f"Description: {task['description']}")
        
        # Show acceptance criteria
        print("\nAcceptance Criteria:")
        for i, criterion in enumerate(task['acceptance_criteria'], 1):
            print(f"  {i}. {criterion}")
        
        # Ask for confirmation
        response = input("\nExecute this task? (y/n): ")
        if response.lower() != 'y':
            continue
        
        # Execute
        result = execute_task(task)
        
        # Manual verification
        print("\nVerification required:")
        print("1. Review the code changes")
        print("2. Run tests if applicable")
        print("3. Check acceptance criteria")
        
        verified = input("\nDid the task pass verification? (y/n): ")
        if verified.lower() == 'y':
            task['passes'] = True
            print(f"Task {task['id']} marked as complete")
        else:
            print(f"Task {task['id']} needs rework")
    
    return generate_report(task_queue)
```

### Level 2: Attended Execution
```python
def execute_level_attended(prd, settings):
    """Level 2: Attended execution with checkpoints"""
    
    print("=== Ralph Loop Level 2: Attended Execution ===")
    print("Multiple tasks with periodic check-ins")
    
    checkpoint_interval = settings.get("checkpoint_interval", 5)
    memory = initialize_memory(prd)
    
    iteration = 0
    while iteration < settings["max_iterations"]:
        iteration += 1
        
        task = select_next_task(prd["tasks"], memory)
        if not task:
            break
        
        # Execute task
        result = execute_task_with_agent(task, "auto", memory)
        
        # Checkpoint every N iterations
        if iteration % checkpoint_interval == 0:
            print(f"\n=== Checkpoint at iteration {iteration} ===")
            print(f"Tasks completed: {count_completed_tasks(memory)}/{len(prd['tasks'])}")
            print(f"Success rate: {calculate_success_rate(memory)}%")
            
            response = input("Continue? (y/n/pause): ")
            if response.lower() == 'n':
                break
            elif response.lower() == 'pause':
                print("Paused. Current state saved.")
                save_checkpoint(memory)
                input("Press Enter to continue...")
    
    return generate_completion_report(memory)
```

### Level 3: Overnight Execution
```python
def execute_level_overnight(prd, settings):
    """Level 3: Overnight autonomous execution"""
    
    print("=== Ralph Loop Level 3: Overnight Execution ===")
    print(f"Starting autonomous execution for up to {settings['max_iterations']} iterations")
    print(f"Expected completion: Overnight (8 hours)")
    
    # Setup notifications
    if settings.get("notifications"):
        setup_notifications(settings["notifications"])
    
    # Start timer
    start_time = datetime.now()
    timeout = timedelta(minutes=settings.get("timeout_minutes", 480))
    
    memory = initialize_memory(prd)
    
    try:
        iteration = 0
        while iteration < settings["max_iterations"]:
            iteration += 1
            
            # Check timeout
            if datetime.now() - start_time > timeout:
                print("Timeout reached")
                send_notification("Ralph Loop timeout reached")
                break
            
            task = select_next_task(prd["tasks"], memory)
            if not task:
                # All tasks completed
                send_notification("Ralph Loop completed successfully")
                break
            
            # Execute task
            result = execute_task_with_agent(task, "auto", memory)
            
            # Log progress
            if iteration % 10 == 0:
                log_progress(memory, iteration)
        
        # Generate morning report
        report = generate_morning_report(memory, iteration)
        send_notification(f"Ralph Loop finished: {report['summary']}")
        
        return report
        
    except Exception as e:
        error_msg = f"Ralph Loop error: {str(e)}"
        send_notification(error_msg)
        log_error(memory, e)
        raise
```

## Pattern Implementations

### Feature Builder Pattern
```python
def execute_feature_builder(prd, settings, available_agents, memory):
    """Execute Feature Builder pattern"""
    
    print("=== Feature Builder Pattern ===")
    
    # Filter to feature tasks
    feature_tasks = [t for t in prd["tasks"] if t["type"] in ["api", "ui", "feature"]]
    
    # Group by feature
    features = group_tasks_by_feature(feature_tasks)
    
    for feature_name, tasks in features.items():
        print(f"\nBuilding feature: {feature_name}")
        
        # Execute feature tasks with capability-based routing
        for task in tasks:
            print(f"  Task: {task['id']} - {task['title']}")
            agent = route_to_agent(task, available_agents)
            execute_task_with_agent(task, agent, memory)
        
        # Feature verification
        print(f"Verifying feature: {feature_name}")
        verify_feature(feature_name, tasks)
    
    return generate_feature_report(features)
```

### Test-Until-Green Pattern
```python
def execute_test_until_green(prd, settings, available_agents, memory):
    """Execute Test-Until-Green pattern"""
    
    print("=== Test-Until-Green Pattern ===")
    
    target_coverage = settings.get("coverage_target", 80)
    current_coverage = get_current_coverage()
    
    print(f"Current coverage: {current_coverage}%")
    print(f"Target coverage: {target_coverage}%")
    
    iteration = 0
    while current_coverage < target_coverage and iteration < settings["max_iterations"]:
        iteration += 1
        
        # Find untested code
        untested_files = find_untested_files()
        
        if not untested_files:
            print("No more untested files found")
            break
        
        # Select file to test
        file_to_test = select_file_for_testing(untested_files)
        
        # Create test task
        task = create_test_task(file_to_test)
        
        # Execute with capability-based routing
        agent = route_to_agent(task, available_agents)
        execute_task_with_agent(task, agent, memory)
        
        # Update coverage
        current_coverage = get_current_coverage()
        print(f"Iteration {iteration}: Coverage now {current_coverage}%")
    
    print(f"Final coverage: {current_coverage}%")
    return generate_coverage_report(current_coverage, target_coverage, iteration)
```

### Multi-Persona Review Pattern
```python
def execute_multi_persona_review(prd, settings):
    """Execute Multi-Persona Review pattern"""
    
    print("=== Multi-Persona Review Pattern ===")
    
    # Define personas by required capabilities instead of specific agents
    personas = settings.get("personas", [
        {"role": "security", "required_capabilities": ["security", "review"]},
        {"role": "performance", "required_capabilities": ["performance", "review"]},
        {"role": "accessibility", "required_capabilities": ["ui_design", "review"]},
        {"role": "code-quality", "required_capabilities": ["code_generation", "review"]}
    ])
    
    cycles = settings.get("cycles", 2)
    available_agents = settings.get("available_agents", {})  # {"agent": ["cap1", "cap2"]}
    
    issues_found = []
    
    for cycle in range(cycles):
        print(f"\nCycle {cycle + 1}/{cycles}")
        
        for persona in personas:
            # Route to best agent for this persona's capabilities
            agent = route_to_agent_by_capabilities(
                persona["required_capabilities"], 
                available_agents
            )
            print(f"  Persona: {persona['role']} (assigned agent: {agent})")
            
            # Review from persona perspective
            issues = review_from_persona(persona, prd)
            issues_found.extend(issues)
            
            # Fix issues found with assigned agent
            if issues:
                print(f"    Found {len(issues)} issues, fixing...")
                fix_issues(issues, agent)
    
    print(f"\nTotal issues found and fixed: {len(issues_found)}")
    return generate_review_report(issues_found, cycles)


def route_to_agent_by_capabilities(required_capabilities, available_agents):
    """Route to best agent based on required capabilities"""
    best_agent = None
    best_score = 0
    
    for agent_name, agent_capabilities in available_agents.items():
        match_count = sum(1 for cap in required_capabilities if cap in agent_capabilities)
        score = match_count / len(required_capabilities) if required_capabilities else 0
        
        if score > best_score:
            best_score = score
            best_agent = agent_name
    
    return best_agent if best_agent else (list(available_agents.keys())[0] if available_agents else None)
```

## Integration with SkillWeave

### Complete Workflow Integration
```python
def complete_skillweave_workflow(idea, domain):
    """Complete SkillWeave workflow from idea to production"""
    
    print("=== SkillWeave Complete Workflow ===")
    
    # Step 1: Create blueprint
    print("1. Creating blueprint...")
    prd = skillweave_blueprint(idea=idea, domain=domain)
    
    # Step 2: Generate execution sequences
    print("2. Generating execution sequences...")
    sequences = skillweave_promptchain_generate(prd=prd)
    
    # Step 3: Execute with Ralph Loop
    print("3. Executing with Ralph Loop...")
    result = skillweave_releasechain(
        inputs={"prd": prd, "sequences": sequences},
        mode="overnight",
        max_iterations=50
    )
    
    # Step 4: Generate final report
    print("4. Generating final report...")
    report = generate_final_workflow_report(prd, sequences, result)
    
    return report
```

## Best Practices & Troubleshooting

### Common Issues and Solutions

#### Issue: Loop Doesn't Terminate
**Symptoms**: Infinite iterations, no completion promise
**Solutions**:
1. Check acceptance criteria - ensure they're binary and testable
2. Verify verification steps actually run and pass
3. Add iteration limit with progress reporting
4. Implement timeout mechanism

#### Issue: Poor Quality Output
**Symptoms**: Code works but is messy or inefficient
**Solutions**:
1. Strengthen verification (add linting, type checking)
2. Implement multi-persona review pattern
3. Add code quality gates
4. Use more appropriate agent for task type

#### Issue: Agent Resource Exhaustion
**Symptoms**: Rate limiting, timeouts, context window exceeded
**Solutions**:
1. Implement token budgeting per task
2. Add rate limiting with exponential backoff
3. Split large tasks into smaller ones
4. Use agent rotation for different task types

#### Issue: Dependency Deadlock
**Symptoms**: Tasks stuck waiting for each other
**Solutions**:
1. Analyze dependency graph for cycles
2. Implement deadlock detection
3. Allow manual override for stuck tasks
4. Redesign tasks to minimize dependencies

### Performance Optimization

1. **Parallel Execution**: Run independent tasks simultaneously
2. **Agent Specialization**: Route tasks to best-suited agents
3. **Caching**: Cache verification results and agent outputs
4. **Incremental Verification**: Only verify changed components
5. **Resource Pooling**: Share resources across iterations

### Monitoring and Metrics

**Key Metrics to Track**:
- Tasks completed per iteration
- Success rate per agent type
- Average iteration time
- Token usage and cost
- Verification pass/fail rates
- Dependency resolution efficiency

**Alerting**:
- Iteration timeout alerts
- Low success rate alerts
- High token usage alerts
- Verification failure alerts
- Dependency deadlock alerts

## Conclusion

This implementation guide provides the foundation for Ralph Loop execution within SkillWeave ReleaseChain. By following these patterns and best practices, teams can achieve reliable autonomous AI development with predictable outcomes and continuous improvement through the memory system.