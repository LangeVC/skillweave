# Parallel Execution & Safe Parallelization

Execute SkillWeave sequences with write-scope awareness, safe parallel lanes, and binary gate synchronization. Parallelism is allowed only when it is safe.

## Core Concepts

### 1. **Write Scope & Ownership**
- Each step defines its `write_scope`: files, directories, or system surfaces it will modify
- Steps with overlapping write scopes **cannot** run in parallel
- Write scope determines ownership and conflict prevention

### 2. **Critical Path vs Sidecar Lanes**
- **Critical Path**: Steps that modify single-owner integration surfaces (database schemas, core APIs, config files)
- **Sidecar Lanes**: Independent computations, research, documentation, isolated tests
- Critical path steps run sequentially, sidecar lanes can run in parallel

### 3. **Safe Parallel Lanes**
Parallelize steps only when they have:
- **Disjoint write scopes**: No overlapping files or surfaces
- **No unresolved dependencies**: Independent or properly synchronized
- **No shared ownership**: Each lane owns its write surfaces exclusively

### 4. **Integration Gates**
- Points where parallel lanes must synchronize and validate integration
- Defined by `integration_gate` field: `"pre"`, `"post"`, `"both"`, or `"none"`
- Ensure system consistency before advancing

## Parallelization Rules

### Safe to Parallelize
- Read-only research and analysis
- Documentation drafting
- Isolated unit tests
- Release notes and changelogs
- Audit and verification passes
- Independent module implementations (disjoint write scopes)

### Keep Sequential (Critical Path)
- Product-tier registries and configurations
- Tool index / tool registration
- Shared contracts used across many modules
- Release and export manifests
- Database schema migrations
- Core API interfaces
- Configuration files with wide impact

### Subagent Policy
Use subagents only for:
- Independent sidecar lanes with disjoint write scope
- Isolated implementation that doesn't block local context-building
- Verification or review that can run asynchronously

Do **not** delegate:
- Critical path steps
- Steps that modify shared integration surfaces
- Immediate blocking tasks the next local action depends on

## Execution Flow with Safe Parallelization

### Phase 1: Preflight & Write Scope Analysis
```
1. Parse sequence and extract all steps
2. Analyze `write_scope` for each step (infer if missing)
3. Identify write scope overlaps and conflicts
4. Map dependency graph with write scope awareness
5. Classify steps: critical path vs sidecar lanes
```

### Phase 2: Batch Planning with Lane Assignment
```
1. Group steps into batches based on integration gates
2. For each batch:
   - Identify critical path step(s)
   - Identify safe sidecar lanes
   - Assign write ownership per lane
   - Define parallelization constraints
   - Set integration gate requirements
3. Create lane plan with subagent assignments
```

### Phase 3: Safe Parallel Execution
```
1. Execute critical path steps locally (main agent)
2. Launch sidecar lanes in parallel subagents (if safe)
3. Monitor lane progress and resource usage
4. Synchronize at integration gates
5. Validate integration before advancing
```

### Phase 4: Integration & Result Assembly
```
1. Merge results from parallel lanes
2. Validate overall system consistency
3. Apply final assembly instructions
4. Format outputs with execution timeline
```

## Examples with Write Scope Awareness

### Example 1: Safe Parallel Implementation
```
Step 1: 
  title: "Implement user authentication module"
  write_scope: ["src/auth/", "tests/auth/"]
  depends_on: []

Step 2:
  title: "Implement payment processing module"  
  write_scope: ["src/payments/", "tests/payments/"]
  depends_on: []

Step 3:
  title: "Update shared configuration"
  write_scope: ["config/app.yaml"]
  depends_on: ["step-1", "step-2"]

→ Execution: [1,2] (parallel, disjoint write scopes) → 3 (sequential, shared config)
```

### Example 2: Critical Path Protection
```
Step 1:
  title: "Update database schema"
  write_scope: ["migrations/001_users.sql", "models/user.py"]
  depends_on: []

Step 2:
  title: "Update API endpoints"
  write_scope: ["api/users.py", "api/auth.py"]  
  depends_on: ["step-1"]

Step 3:
  title: "Write documentation"
  write_scope: ["docs/users.md"]
  depends_on: []

→ Execution: 1 → 2 (sequential, critical path) + 3 (parallel sidecar, disjoint write scope)
```

### Example 3: Integration Gate Synchronization
```
Step 1:
  title: "Implement frontend component"
  write_scope: ["frontend/src/ComponentA/"]
  integration_gate: "post"
  depends_on: []

Step 2:
  title: "Implement backend API"
  write_scope: ["backend/src/api/"]
  integration_gate: "post"  
  depends_on: []

Step 3:
  title: "Integration test"
  write_scope: ["tests/integration/"]
  depends_on: ["step-1", "step-2"]

→ Execution: [1,2] (parallel) → [Integration Gate] → 3 (after both complete)
```

## Build-Step Normalization for Parallelization

For safe parallel execution, build steps should define:

```yaml
id: "COMP-001"
title: "Implement component X"
depends_on: []
required_capabilities: ["code_generation", "testing"]
write_scope: ["src/components/X/", "tests/components/X/"]
verification: ["unit tests pass", "compiles without errors"]
integration_gate: "post"
retry_budget: 2
handoff_contract: ["files_changed", "tests_run", "known_limitations"]
```

## Error Handling in Parallel Execution

### Failure Scenarios with Write Scope:
- **Write scope conflict**: Two parallel steps attempt to modify same file
- **Integration gate failure**: Parallel lanes produce incompatible results
- **Dependency violation**: Sidecar lane depends on incomplete critical path
- **Resource deadlock**: Parallel steps waiting for each other's write surfaces

### Recovery Strategies:
1. **Rollback conflicting writes**: Restore original state, retry with synchronization
2. **Isolate write conflicts**: Serialize steps with overlapping write scopes
3. **Partial rollback**: Undo only conflicting changes, preserve independent work
4. **Gate retry**: Re-run integration verification with adjusted parameters

## Performance Optimization with Safety

### 1. **Write Scope Minimization**
- Define precise write scopes to maximize parallel opportunities
- Avoid broad write scopes like `["src/"]` unless necessary
- Use directory-level granularity when possible

### 2. **Lane Resource Allocation**
- Allocate resources based on write scope complexity
- Monitor I/O contention for file system operations
- Balance CPU vs I/O intensive lanes

### 3. **Adaptive Parallelization**
- Start with conservative parallelization (fewer lanes)
- Increase lanes as write scope safety is confirmed
- Dynamic adjustment based on conflict history

## Integration with Ralph Loop

### Combined with Batch Planning:
- Each Ralph Loop batch defines its parallel lane structure
- Critical path steps advance the loop state
- Sidecar lanes complete within batch boundaries
- Integration gates synchronize lanes before batch completion

### Combined with Gate Policy:
- Parallel lanes have individual verification gates
- Integration gates validate cross-lane consistency
- Batch completion requires all lanes to pass their gates

## Best Practices for Safe Parallelization

1. **Define precise write scopes**: Enables accurate conflict detection
2. **Separate critical path from sidecars**: Clear ownership boundaries
3. **Use integration gates liberally**: Prevent subtle integration bugs
4. **Monitor write conflicts**: Log and learn from parallelization issues
5. **Design for retryability**: Make parallel steps idempotent when possible
6. **Document lane dependencies**: Help reviewers understand parallel structure

## Safety-First Parallelization Philosophy

SkillWeave's parallel execution prioritizes **safety over maximal parallelism**:

- **From**: "Parallelize everything possible" (risky, conflict-prone)
- **To**: "Parallelize only what's safe" (reliable, deterministic)
- **Result**: Accelerated development **without** integration nightmares

This enables teams to:
- **Develop multiple features simultaneously without stepping on each other**
- **Run tests and documentation in parallel with implementation**
- **Accelerate iteration while maintaining system integrity**
- **Scale AI-assisted development with confidence**