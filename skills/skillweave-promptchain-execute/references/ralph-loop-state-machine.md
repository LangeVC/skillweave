# Ralph Loop State Machine

## States

### 1. Preflight
- Validate sequence structure and inputs
- Detect sequence type (`plan`, `build`, `mixed`)
- Resolve execution mode (`rex`, `ralph_attended`, `ralph_overnight`)
- Identify critical path and safe parallel lanes
- Assess repository baseline alignment

### 2. Batch Selection
- Convert sequence into executable batches
- Define batch boundaries based on:
  - Dependency clusters
  - Write scope cohesion
  - Verification boundaries
  - Integration gates
- Prioritize batches by critical path

### 3. Lane Plan
- For each batch:
  - Identify critical path step(s)
  - Identify safe sidecar lanes
  - Assign write ownership per lane
  - Define subagent assignments (if applicable)
  - Set parallelization constraints

### 4. Implement
- Execute implementation according to lane plan
- Critical path runs locally (main agent)
- Sidecar lanes may run in parallel subagents
- Monitor progress and resource usage
- Collect intermediate outputs

### 5. Verify
- Run verification commands defined in batch
- Apply binary gate criteria
- Check:
  - Tests pass
  - Build succeeds
  - Verification scripts exit cleanly
  - Required artifacts exist and match contract
- Mark as `pass`, `fail`, or `inconclusive`

### 6. Review Gate
- Present implementation results
- Request explicit `continue` or `revise` decision
- For `ralph_attended`: human review required
- For `ralph_overnight`: automated review based on predefined criteria
- Do not advance without explicit `continue`

### 7. Fix / Retry
- If gate fails or returns `revise`:
  - Apply retry budget (if defined)
  - Implement narrow fixes
  - Re-run verification
  - Return to Review Gate
- If retry budget exhausted, mark batch `blocked`

### 8. Integrate
- Merge successful implementation into working baseline
- Update progress tracking
- Commit intermediate state (if configured)
- Prepare for next batch

### 9. Advance or Stop
- If batch passed: advance to next batch
- If batch failed or blocked: stop execution
- Emit completion summary with:
  - Completed batches
  - Next executable batch
  - Blockers (if any)
  - Known limitations

## Transition Rules

### Auto-escalation to Ralph Loop
- Start in `rex` mode for simple sequences
- Escalate to `ralph_attended` when:
  - 4+ steps
  - Repository mutations
  - Binary gates required
  - Parallel lanes beneficial
  - Product-tier boundaries involved

### Batch Completion
- A batch completes only when all gates pass
- Partial completion is not allowed
- Inconclusive results require explicit resolution
- Failed batches stop the loop (do not continue)

### Parallel Lane Management
- Sidecar lanes can run in parallel
- Critical path must remain sequential
- Lanes with overlapping write scopes must be serialized
- Subagents may be used for independent lanes

## Memory & Progress Tracking

### Per Batch Memory
- `batch_id`
- `goal`
- `critical_path_step`
- `parallel_lanes`
- `write_surfaces`
- `verification_results`
- `review_decision`
- `completion_status`
- `blockers`
- `next_batch`

### Loop Persistence
- Progress should be trackable across sessions
- State should be serializable (JSON/YAML)
- Resume capability from last completed batch
- Carry-forward of decisions and constraints