# Workflow Recommendation: Initiative 05

## Recommendation: **Ralph Loop Overnight**

### Rationale

| Factor | Value | Criteria Met |
|--------|-------|--------------|
| Complexity Score | 72 | > 65 threshold for overnight |
| Total Tasks | 10 | Exceeds attended range (4-10 comfortably, but complexity demands autonomous) |
| Estimated Duration | ~480 min (~8 hrs) | Fits overnight window (6-12 hours) |
| Parallel Groups | 3 (max 5 simultaneous) | Complex orchestration benefits from autonomous scheduling |
| Auto-recovery patterns | 8 defined | Overnight viability confirmed |
| Critical backward compat risk | High | Needs test suite validation, but pattern matches overnight after guardrails |

### When to Use Ralph Loop Overnight

1. **Autonomous dependency resolution** — 5 tasks can run in parallel after DESIGN-001. Overnight mode schedules these optimally without human intervention.
2. **Built-in safety nets** — All 8 failure handlers have autonomous fallbacks. Human escalation only triggers on retry exhaustion or integration regressions.
3. **Checkpoint at build-critical points** — Interval of 6 steps ensures recoverability (checkpoint after PHASE 2, after PHASE 3, after PHASE 4, after INTG-001).
4. **Heartbeat viability** — 30-minute heartbeats allow stall detection without human attendance.
5. **Memory system self-heals** — Memory write failures fall back to flat file mode, compaction failures degrade gracefully.

### Checkpoint Strategy (Autonomous)

| Checkpoint | After | Trigger | Action |
|-----------|-------|---------|--------|
| CP-001 | DESIGN-001 | Format specs validated | Snapshot .skillweave/ directory structure |
| CP-002 | FEAT-001 + FEAT-002 | Checklist + memory passing gates | Verify both modules import cleanly |
| CP-003 | FEAT-003 + FEAT-004 + FEAT-006 | Compaction + observability + artifact tracking | Run compaction round-trip test |
| CP-004 | FEAT-005 + FEAT-007 | Selective loader + correction | Verify retry mechanism works |
| CP-005 | INTG-001 | Integration complete | Run backward compatibility tests |
| CP-006 | TEST-001 | All 18+ tests pass | Generate execution report |

### Autonomous Recovery Patterns

```yaml
fallback_chain:
  memory_write:
    - primary:  YAML file write
    - fallback: Raw dict dump to file
    - last:     In-memory only with warning
  compaction:
    - primary:  4-section summary
    - fallback: 2-section (current_state + next_steps)
    - last:     Minimal log line
  checklist_loop:
    - primary:  Full markdown parser
    - fallback: Flat list parser (no nesting)
    - last:     Single-item step mode
```

### If Complexity Decreases

If implementation proves simpler than estimated (e.g., reusable patterns from existing infrastructure), the system can downgrade to **Ralph Loop Attended**. Signal: all 10 tasks complete in < 5 hours with zero failure handler activations.

### If Complexity Increases

If integration exposes backward compatibility violations, or if the dependency graph requires additional coordination tasks, escalate to **Ralph Loop Extended Overnight** with 24-hour autonomous window and staggered human check-in at 12-hour mark.

### Overnight Execution Guardrails

1. **Max iterations**: 60 (from PRD settings)
2. **Hard timeout**: 900 minutes (15 hours)
3. **Human escalation triggers**:
   - Any task exceeds max_retries for its category
   - Integration test reveals broken backward compatibility
   - Heartbeat silence > 60 minutes
   - > 3 test failures persist after auto-retry
4. **Rollback procedure**: Restore from last checkpoint directory snapshot, regenerate context from last good context-summary.yaml
5. **Completion signal**: All 18+ tests pass, execution report generated, sample checklist run succeeds
