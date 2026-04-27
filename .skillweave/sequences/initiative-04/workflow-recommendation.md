# Workflow Recommendation: Initiative 04

## Recommendation: **Ralph Loop Attended**

### Rationale
- **8 tasks** — exceeds REX limit (1-3), fits Ralph Loop Attended range (4-10)
- **~5.75 hours duration** — fits Attended range for multi-phase build + execution pipelines
- **Moderate dependency chain** — sequential pipeline with 2 parallel opportunities, clear phase boundaries
- **Human approval gate required** — EXEC-001 requires explicit human sign-off before archive operations execute (no-deletion-without-approval constraint)
- **Risk of breaking active functionality** — archive operations could invalidate tool paths; attended mode allows verification at each checkpoint
- **Complexity score 52** — standard complexity, no need for overnight unattended execution

### When to Use
- When the repository scanner, classifier, and archive manager are built and tested individually before pipeline execution
- When human review of the cleanup report is required before any archive operations commence
- When full test suite can be executed post-cleanup to verify backward compatibility
- When running in a development environment where immediate human feedback is available

### Checkpoint Strategy
- **Checkpoint 1** (after step 4): After TOOL-001 + TOOL-003 (tools phase) — verify scanner output is complete and archive manager works
- **Checkpoint 2** (after step 6): After TOOL-002 (classification phase) — verify classification accuracy on a sample of 50 files
- **Checkpoint 3** (after step 9): After TOOL-004 + DESIGN-001 + TOOL-005 (analysis & design phase) — review duplication report, lean core manifest, and cleanup report before execution
- **Checkpoint 4** (after step 11): After EXEC-001 + TEST-001 (execution + validation) — verify all tests pass, archive is complete, and reversible

### Gate Conditions
- **Gate 1** (pre EXEC-001): Human must review cleanup report (.skillweave/cleanup/report.md) and approve archive plan
- **Gate 2** (post EXEC-001, pre TEST-001): Quick smoke test that core tools still work before running full suite
- **Gate 3** (post TEST-001): Confirm all acceptance criteria met before marking complete

### If Complexity Increases
- If classification accuracy is unreliable > insert review iteration phase with human-in-the-loop reclassification
- If archive operations break tool paths > switch to **Ralph Loop Overnight** for automated repair iterations
- If file count exceeds 2000 > increase checkpoint frequency and add batch processing

### If Complexity Decreases
- If repository is small (< 100 files) > could merge TOOL-004 + TOOL-005 into a single analysis step
- If all classifications are high-confidence > reduce human review scope
