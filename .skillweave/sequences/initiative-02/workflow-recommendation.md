# Workflow Recommendation — Initiative 02

## Recommended: Ralph Loop Attended (ralph-loop-attended)

### Rationale

**1. Mixed sequence type with plan-before-build pattern**

The sequence contains 4 planning/design tasks (DESIGN-001, DISC-001, DISC-002, DISC-003) that must complete before 5 build tasks can execute reliably. Ralph Loop's iterative structure naturally handles this plan→build→verify cadence. The attended variant is chosen because the schema design (DESIGN-001) defines rules that propagate through all subsequent work — human sign-off at this gate prevents compounding errors.

**2. Moderate parallel complexity with cross-task dependencies**

Phase 2 offers 5-way parallelism, but DISC-003 outputs feed directly into FEAT-002 which feeds INTG-001. Ralph Loop's dependency-aware batching ensures agents start the right tasks at the right time without manual intervention, while the attendant reviews integration boundaries.

**3. Integration risk requires human judgment**

INTG-001 connects the Design Thinking Lens to existing Blueprint and PromptChain skills. Backward compatibility is a stated requirement. Ralph Loop's checkpoint mechanism (every 4 steps) catches regressions early, and the attendant can inspect integration test results before signing off on the final phase.

**4. Documentation artifacts benefit from iterative review**

Prompt library quality (DISC-001/002/003) and template utility (TMPL-001) improve with revision. Ralph Loop's completion promise pattern — "deliver by this checkpoint, revise by that checkpoint" — prevents endless polish while ensuring quality. The attendant chooses when to accept or request another loop.

### Why Not Other Workflows

| Workflow | Reason Against |
|---|---|
| REX | Simple single-pass execution. Cannot handle 5-phase dependency chain or cross-skill integration. No support for plan-then-build handoff. |
| Ralph Loop Unattended | The schema design phase and integration phase both benefit from human review. Too much risk of silent backward compatibility breakage with unattended execution. |
| Ralph Loop Delegation | Not appropriate — this is a single-initiative execution with 10 tasks, not a multi-initiative orchestration problem. Delegation overhead would exceed benefit. |

### Checkpoint Plan

| Checkpoint | Step | Attendant Action |
|---|---|---|
| 1 | STEP-01 (DESIGN-001) | Approve lens schema before prompts/features branch out |
| 2 | STEP-04 (DISC-003) | Review all 10+ prompts for quality and I/O completeness |
| 3 | STEP-07 (TMPL-001) | Validate 5 templates and their compatibility with prompts |
| 4 | STEP-09 (INTG-001) | Verify backward compatibility and cross-skill integration |
| Final | STEP-10 (TEST-001) | Review test results, approve initiative completion |

### Estimated Iterations: 14

Based on:
- 10 tasks × 1.0 base passes (documentation-heavy, lower revision probability)
- +2 iterations for integration debugging (INTG-001 cross-skill risk)
- +2 iterations for prompt refinement based on attendant feedback (typical for creative/documentation work)
