# Ralph Loop Adaptation for Multi-Agent AI Development

Adapting Ralph Loop principles from Claude Code to work across all AI agents (Opencode, Codex, Gemini, Antigravity, etc.) with SkillWeave.

## Core Ralph Loop Concepts

### Original Ralph Loop (Claude Code)
- **Mechanism**: Bash while loop with stop hook
- **Completion Promise**: `<promise>COMPLETE</promise>` 
- **Memory**: `progress.txt` (short-term), `agents.md` (long-term)
- **Task List**: `prd.json` with `passes: true/false`
- **Verification**: Automated tests, builds, type checking

### SkillWeave Adaptation
- **Agent Agnostic**: Works with any AI agent tool
- **Standardized Format**: Consistent across all tools
- **Integration Ready**: Fits SkillWeave workflow
- **Scalable**: From single tasks to overnight builds

## Key Adaptations

### 1. Completion Promise Standardization
**Original**: `<promise>COMPLETE</promise>` (Claude-specific)
**Adapted**: Multi-agent compatible signaling

```markdown
## Completion Signal
<skillweave-complete>
status: success
task: TASK-ID
timestamp: 2024-01-15T14:32:00Z
verification: [test-results, build-status, etc.]
</skillweave-complete>
```

**Benefits:**
- Standard format across all agents
- Includes verification metadata
- Machine parseable
- Extensible for different completion types

### 2. Memory System Enhancement
**Original**: `progress.txt`, `agents.md` (flat files)
**Adapted**: Structured memory with versioning

```yaml
# progress-structured.yaml
iterations:
  - id: iteration-001
    task: TASK-ID
    agent: any
    capability: code_generation
    start: 2024-01-15T14:30:00Z
    end: 2024-01-15T14:32:00Z
    status: success
    changes:
      - file: src/api/users.ts
        action: created
        lines: 45
    learnings:
      - "Use async/await for database operations"
      - "Validate email format with regex"
    next_task: TASK-NEXT-ID
```

**Benefits:**
- Structured data for analysis
- Agent-specific context
- Time tracking
- Change tracking

### 3. Task List Enhancement
**Original**: `prd.json` with basic tasks
**Adapted**: Enhanced task specification

```json
{
  "project": {
    "name": "Project Name",
    "version": "1.0.0",
    "repository": "https://github.com/owner/repo"
  },
  "settings": {
    "max_iterations": 50,
    "timeout_minutes": 480,
    "required_capabilities": ["code_generation", "testing"],
    "verification_level": "strict"
  },
  "tasks": [
    {
      "id": "TASK-ID",
      "title": "Task Title",
      "description": "Task description",
      "agent_type": "build", // or "plan", "mixed"
      "target_agent": "any", // recommended: let the runtime map capabilities; omit to defer entirely
      "required_capabilities": ["code_generation"], // optional capability requirements
      "estimated_tokens": 2000,
      "priority": "critical",
      "dependencies": ["OTHER-TASK"],
      "acceptance_criteria": [],
      "verification_steps": [],
      "resources": {
        "files": ["path/to/file"],
        "docs": ["url/to/docs"],
        "examples": ["url/to/examples"]
      },
      "passes": false,
      "attempts": 0,
      "last_attempt": null,
      "best_practice": "Reference pattern from agents.md"
    }
  ]
}
```

## Multi-Agent Execution Strategy

### Agent Capability Mapping
Task assignment follows declared capabilities, not concrete hosts. The runtime
picks whatever available agent best matches the required capability:

| Capability | Typical Use |
|------------|-------------|
| `planning` | Architecture, design decisions |
| `code_generation` | Build tasks, infrastructure |
| `testing` | Test creation and execution |
| `review` | Code review, quality assessment |
| `research` | Planning, market research |
| `automation` | DevOps, deployment, scripting |

A concrete host is only selected through an explicit, user-supplied adapter —
never as a built-in default. See `references/adapters/`.

### Task Routing Logic
```python
def route_task(task, available_agents):
    # Route by required capability, defaulting to neutral ("any").
    required = task.get("required_capabilities") or ["any"]
    if len(required) == 1:
        capability = required[0]
    else:
        capability = "any"

    if capability == "any":
        # Any capable agent; the runtime maps based on availability.
        return available_agents[0] if available_agents else None

    # Return any available agent that declares the required capability.
    for agent in available_agents:
        if capability in (agent.get("capabilities") or []):
            return agent

    # Fallback to any available.
    return available_agents[0] if available_agents else None
```

### Parallel Execution with Multiple Capabilities
```yaml
execution_plan:
  phase_1:
    tasks: ["INFRA-001", "INFRA-002"]
    required_capabilities: ["code_generation"]  # Run in parallel
    strategy: parallel_independent
    
  phase_2:
    tasks: ["API-001", "UI-001"]
    required_capabilities: ["code_generation"]
    strategy: parallel_after_phase_1
    
  phase_3:
    tasks: ["TEST-001", "TEST-002"]
    required_capabilities: ["testing"]
    strategy: parallel_after_respective_tasks
```

## Verification & Feedback Loops

### Multi-Level Verification
**Level 1: Code Quality**
- Static analysis (type checking, linting)
- Code style compliance
- Security scanning

**Level 2: Functional Correctness**
- Unit tests
- Integration tests
- API contract tests

**Level 3: System Behavior**
- End-to-end tests
- Performance testing
- Load testing

**Level 4: Business Value**
- Feature acceptance testing
- User journey validation
- Success metric verification

### Automated Feedback Integration
```bash
# Verification pipeline
task_completion_flow:
  1. Run type checking: `npm run typecheck` or `tsc --noEmit`
  2. Run linting: `npm run lint` or specific linter
  3. Run tests: `npm test` or test command
  4. Run build: `npm run build` or build command
  5. Run security scan: `npm audit` or security tool
  6. If all pass → mark task complete
  7. If any fail → debug and retry
```

## Memory System Design

### Short-Term Memory (progress-structured.yaml)
**Purpose:** Track current sprint/iteration
**Content:**
- Iteration history with timestamps
- Task completion details
- Learnings and patterns
- Blockers and solutions
- Agent performance metrics

### Long-Term Memory (agents-enhanced.md)
**Purpose:** Persistent knowledge base
**Content:**

```markdown
# Project Knowledge Base

## Architecture Patterns
### API Design
- Use RESTful conventions for CRUD
- Version APIs in URL path (/api/v1/)
- Use consistent error response format
- Document with OpenAPI/Swagger

### Database Patterns
- Use migrations for schema changes
- Index frequently queried columns
- Use connection pooling
- Implement soft deletes where appropriate

## Code Conventions
### TypeScript/JavaScript
- Use strict mode
- Prefer async/await over callbacks
- Use interfaces over type aliases for public APIs
- Document complex functions with JSDoc

### Python
- Use type hints
- Follow PEP 8
- Use virtual environments
- Write docstrings for public functions

## Integration Knowledge
### Third-Party Services
- Stripe: Use test mode, handle webhooks
- SendGrid: Template management, bounce handling
- AWS S3: Bucket policies, signed URLs

### Common Issues & Solutions
- CORS errors: Configure proper headers
- Timeout issues: Implement retry logic
- Memory leaks: Monitor with profiling tools

## Agent-Specific Notes
### Opencode
- Prefers explicit file paths
- Good with structured templates
- Needs clear success criteria

### Claude Code
- Strong with architectural decisions
- Good at explaining trade-offs
- Needs context management

### Codex
- Fast iterations
- Good at code completion
- Less strong on architecture
```

### Cross-Project Memory (organization-wide)
**Purpose:** Share knowledge across projects
**Location:** Central repository or knowledge base
**Content:**
- Organizational standards
- Shared component libraries
- Deployment procedures
- Security policies
- Performance benchmarks

## Execution Levels Adaptation

### Level 1: Manual Single Runs (Learning)
**Purpose:** Understand agent behavior
**Setup:**
- One task at a time
- Watch execution closely
- Manual verification
- Note agent-specific patterns

**Outcome:**
- Agent capability mapping
- Task sizing validation
- Verification process tuning

### Level 2: Attended Loops (Confidence)
**Purpose:** Build trust in automation
**Setup:**
- Multiple tasks in sequence
- Periodic check-ins
- Semi-automated verification
- Error recovery testing

**Outcome:**
- Reliable task completion
- Understand failure modes
- Optimize task definitions

### Level 3: Unattended Overnight (Production)
**Purpose:** Autonomous development
**Setup:**
- Full task list
- Complete automation
- Comprehensive verification
- Notification system

**Outcome:**
- Overnight progress
- Consistent quality
- Scalable development

## Pattern Adaptations

### Feature Builder Pattern
**Original:** Single-agent feature development
**Adapted:** Multi-agent collaborative building

```yaml
pattern: collaborative_feature_build
agents:
  planner: planning     # Architecture and design
  builder: code_generation  # Implementation
  tester: testing       # Test creation
  reviewer: review      # Quality assurance
flow:
  - planner: Create design specification
  - builder: Implement based on specification
  - tester: Create tests for implementation
  - reviewer: Verify against acceptance criteria
  - loop: Until all criteria met
```

### Multi-Persona Review Pattern
**Original:** Single agent rotating personas
**Adapted:** Multiple agents as different personas

```yaml
pattern: multi_agent_review
personas:
  - role: security_reviewer
    capability: review
    focus: vulnerabilities, input validation
  
  - role: performance_reviewer  
    capability: review
    focus: optimization, bottlenecks
  
  - role: accessibility_reviewer
    capability: review
    focus: WCAG compliance, screen readers
  
  - role: code_quality_reviewer
    capability: code_generation
    focus: standards, maintainability
process: Parallel review with consolidated feedback
```

### Test-Until-Green Pattern
**Original:** Single agent improving test coverage
**Adapted:** Specialized agents for different test types

```yaml
pattern: specialized_testing
agents:
  unit_tester: testing          # Fast, many small tests
  integration_tester: testing   # API, database tests
  e2e_tester: testing           # User flow tests
  coverage_analyst: research    # Analysis, reporting
strategy: Parallel test development with coverage tracking
```

## Integration with SkillWeave Workflow

### Complete Development Flow
```
Blueprint → PromptChain → Execute → ReleaseChain
      ↓          ↓          ↓          ↓
   PRD      Sequences   Parallel   Ralph Loop
   Creation  Generation  Execution  Execution
```

### Blueprint Skill Integration
- Creates Ralph Loop compatible PRD
- Sets up memory system structure
- Defines agent routing preferences
- Configures verification levels

### PromptChain Skill Integration  
- Generates agent-specific prompts
- Creates verification scripts
- Sets up completion promise format
- Configures memory logging

### Execute Skill Integration
- Manages parallel agent execution
- Routes tasks to appropriate agents
- Monitors progress and resource usage
- Implements fallback strategies

### ReleaseChain Skill Integration
- Runs Ralph Loop execution
- Manages iteration cycles
- Handles completion promises
- Updates memory systems

## Best Practices

### 1. Start Simple
- Begin with single-agent tasks
- Master Level 1 execution
- Gradually increase complexity

### 2. Document Everything
- Use structured memory format
- Capture both successes and failures
- Share learnings across team

### 3. Verify Rigorously
- Implement multiple verification levels
- Automated checks for everything possible
- Manual checks for critical paths

### 4. Monitor Resources
- Track token usage per agent
- Monitor execution time
- Watch for rate limiting
- Manage context window usage

### 5. Iterate and Improve
- Review completed tasks for improvements
- Update task templates based on learnings
- Refine agent routing logic
- Enhance verification processes

## Success Metrics

### Development Metrics
- **Task completion rate**: % of tasks completed successfully
- **Iteration efficiency**: Tasks per iteration
- **Verification pass rate**: % passing on first attempt
- **Agent utilization**: Balanced use of available agents

### Quality Metrics
- **Test coverage**: Code coverage percentage
- **Bug rate**: Defects per task
- **Code quality scores**: Static analysis results
- **Performance metrics**: Response times, load capacity

### Business Metrics
- **Development velocity**: Features per time period
- **Cost efficiency**: Cost per feature/task
- **Time to market**: Idea to production timeline
- **Stakeholder satisfaction**: Feedback scores

## Conclusion

The Ralph Loop adaptation for multi-agent AI development enables:

1. **Agent-Agnostic Execution**: Works across all AI tools
2. **Structured Automation**: From planning to production
3. **Scalable Workflows**: From simple tasks to complex projects
4. **Quality Assurance**: Built-in verification at every step
5. **Knowledge Accumulation**: Continuous learning and improvement

By adapting Ralph Loop principles to the SkillWeave framework, teams can achieve autonomous AI-assisted development with predictable outcomes and consistent quality across any AI agent ecosystem.