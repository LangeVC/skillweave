# Architecture

## Core Concepts

### Ralph Loop State Machine
SkillWeave v0.4.4+ implements a 9-state execution flow:
1. **Preflight**: Validate sequence, check prerequisites
2. **Batch Selection**: Group steps into executable batches
3. **Lane Plan**: Identify critical path vs sidecar lanes
4. **Implement**: Execute steps with parallelization where safe
5. **Verify**: Run verification (tests, linting, type checking)
6. **Review Gate**: Binary gate decision (continue/fix/retry)
7. **Fix/Retry**: Address issues with retry budget
8. **Integrate**: Merge parallel lanes, resolve conflicts
9. **Advance/Stop**: Move to next batch or complete execution

### Write-Scope Based Parallelization
- **Write Scope**: Explicit definition of which files/directories a step modifies
- **Disjoint Scopes**: Parallel execution only allowed for steps with disjoint write scopes
- **Single-Owner Surfaces**: Critical files (package.json, config files) owned by critical path
- **Sidecar Lanes**: Parallelizable work (tests, docs, research) with independent write scopes

### Two-Axis Model
- **Sequence Type**: `plan` (analysis only), `build` (implementation), `mixed` (both)
- **Execution Mode**: `rex` (simple Plan→Implement→Review), `ralph_attended` (standard with human checkpoints), `ralph_overnight` (autonomous batch execution)

### Binary Gate Policy
Only accepts hard completion signals:
- `tests passed`: All tests pass
- `verifier passed`: Linting, type checking, static analysis pass
- `continue`: Explicit human approval to proceed
Soft signals like "looks good" are rejected.

## Skill Layer Architecture

### Five Integrated Skills
1. **Blueprint Skill**: PRD creation with complexity analysis
2. **PromptChain Generate**: Two-axis sequence generation
3. **PromptChain Validate**: Parallelization readiness validation
4. **PromptChain Execute**: Ralph Loop state machine execution
5. **ReleaseChain Skill**: Ralph Loop-powered development pipeline

### Execution Flow
```
Blueprint → Generate → Validate → Execute → ReleaseChain
    ↓           ↓          ↓          ↓           ↓
  PRD      Sequence   Validated   Executed    Production
           with type   sequence    results    ready code
           & mode
```

### Agent-Agnostic Design
- **Capability-based routing**: Tasks assigned to agents based on declared capabilities
- **Multi-agent installation**: Single installer supports 9+ AI coding agents
- **Format adaptation**: Correct file/directory formats for each agent type
