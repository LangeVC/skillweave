# Execution Model

## Ralph Loop State Machine

### 9-State Execution Flow
1. **Preflight**: Validate sequence, check prerequisites, normalize build steps
2. **Batch Selection**: Group steps into executable batches based on dependencies and write scopes
3. **Lane Plan**: Identify critical path (single-owner surfaces) vs sidecar lanes (parallelizable work)
4. **Implement**: Execute steps with safe parallelization (only for disjoint write scopes)
5. **Verify**: Run verification (tests, linting, type checking, static analysis)
6. **Review Gate**: Binary gate decision - only `tests passed`, `verifier passed`, or explicit `continue`
7. **Fix/Retry**: Address issues with retry budget, fallback strategies
8. **Integrate**: Merge parallel lanes, resolve conflicts, update shared contracts
9. **Advance/Stop**: Move to next batch or complete execution

## Write-Scope Based Parallelization

### Key Principles
- **Explicit Write Scopes**: Each build step must define which files/directories it modifies
- **Disjoint Scopes Required**: Parallel execution only allowed for steps with disjoint write scopes
- **Critical Path Ownership**: Single-owner surfaces (package.json, config files) owned by critical path
- **Sidecar Lane Isolation**: Tests, docs, research run in parallel with independent write scopes

### Batch Planning
- **Batch ID**: Unique identifier for each execution batch
- **Critical Path Step**: Primary implementation step in batch
- **Parallel Lanes**: Sidecar steps that can run concurrently
- **Write Surfaces**: Files modified by each lane
- **Completion Contract**: Verification criteria for batch completion

## Binary Gate Policy

### Acceptable Completion Signals
1. **`tests passed`**: All automated tests pass
2. **`verifier passed`**: Linting, type checking, static analysis pass
3. **`continue`**: Explicit human approval to proceed

### Rejected Signals
- "looks good"
- "seems correct"
- "appears to work"
- Any subjective approval without verification

### Failure Handling
- **Retry Budget**: Maximum retry attempts per step
- **Fallback Strategies**: Alternative approaches if primary fails
- **Escalation Path**: Human intervention if automated recovery fails
