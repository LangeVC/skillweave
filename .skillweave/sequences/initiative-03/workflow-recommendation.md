# Workflow Recommendation: Initiative 03

## Recommendation: **Ralph Loop Attended**

### Rationale
- **8 tasks** — exceeds REX limit (1-3), fits Ralph Loop Attended range (4-10)
- **~5.75 hours duration** — fits Attended range well
- **Complexity score 58** — standard mode, warrants attended oversight
- **Refactoring risk (REFAC-001)** — modifying promptchain-execute risks breaking existing workflows; human checkpoints essential before and after
- **Backward compatibility constraint** — all existing promptchain-execute usages must continue to work; attended mode allows verification at each gate
- **2 parallel opportunities** — Ralph Loop Attended handles parallel execution cleanly with per-batch checkpoints
- **Critical prerequisites gating downstream work** — DESIGN-001 gates all features; FEAT-001 gates detection, checklist, and workflow — attended mode ensures quality before expanding scope

### When to Use

- When the release readiness model and skill boundary definitions are stable
- When running in an environment where test suite can be executed
- When backward compatibility of promptchain-execute must be verified
- When multiple feature streams (detection, checklist, workflow) depend on a shared module

### Checkpoint Strategy
- Checkpoint after DESIGN phase (1 task — DESIGN-001)
- Checkpoint after CORE phase (2 parallel tasks — FEAT-001, FEAT-005)
- Checkpoint after DETECTION+CHECKLIST phase (2 parallel tasks — FEAT-002, FEAT-004)
- Checkpoint after WORKFLOW phase (1 task — FEAT-003)
- Checkpoint before REFACTOR (1 task — REFAC-001; highest risk, review execute usage map first)
- Final checkpoint after TESTING (1 task — TEST-001)

### If Complexity Increases
- If backward compatibility issues emerge during REFAC-001 > pause, document findings, escalate to **Ralph Loop Overnight** for deeper analysis
- If release prerequisites prove ungeneralizable across project types > add project-type-specific model before continuing FEAT-001
- If dependency graph expands beyond 12 tasks > switch to **Ralph Loop Overnight**

### If Complexity Decreases
- If FEAT-005 (launch stub) is deferred to Initiative 04 > score drops to ~48, could run as **REX-style** with single-agent execution
- If REFAC-001 is scoped down to documentation-only > risk drops significantly, checkpoint interval could widen to 4
