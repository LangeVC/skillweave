# Workflow Recommendation: Initiative 01

## Recommendation: **Ralph Loop Attended**

### Rationale
- **8 tasks** — exceeds REX limit (1-3), fits Ralph Loop Attended range (4-10)
- **~6 hours duration** — fits Attended range (1-4 hours at lower end, realistic for integration)
- **Moderate dependencies** — clear sequential path with parallel opportunities
- **Backward compatibility critical** — human checkpoints needed at integration phase
- **Risk of breaking existing functionality** — attended mode allows verification at each gate

### When to Use

- When the phase definitions and bundle configurations are stable
- When running in an environment where test suite can be executed
- When integration with existing skills needs human verification at gates

### Checkpoint Strategy
- Checkpoint after ARCH phase (2 tasks)
- Checkpoint after core-development phase (2 tasks, parallel)
- Checkpoint after onboarding phase (2 tasks)
- Checkpoint before final merge (after INTG-001)

### If Complexity Increases
- If dependencies become more complex > switch to **Ralph Loop Overnight**
- If backward compatibility issues found > add review iterations

### If Complexity Decreases
- If only core-detection needed without onboarding/enforcement > could run as **REX-style**
