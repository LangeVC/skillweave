# Workflow Context

The workflow context stores the runtime state of a Ralph Loop execution.

## Ralph Loop State Fields

### Execution State
- **sequence_id**: Unique identifier for the sequence
- **sequence_type**: plan/build/mixed
- **execution_mode**: rex/ralph_attended/ralph_overnight
- **ralph_loop_state**: Current state (preflight, batch_selection, lane_plan, implement, verify, review_gate, fix_retry, integrate, advance_stop)
- **batch_id**: Current execution batch identifier
- **current_step_id**: Currently executing step (if any)
- **critical_path_step**: Primary step in current batch
- **parallel_lanes**: Sidecar steps running concurrently

### Progress Tracking
- **completed_steps**: List of completed step IDs
- **step_outputs**: Map of step ID to output
- **write_surfaces**: Files modified by each step/lane
- **verification_results**: Results of verification steps
- **gate_decisions**: Binary gate decisions (tests_passed, verifier_passed, continue)

### Configuration & Inputs
- **inputs**: Initial inputs to the sequence
- **ralph_loop_config**: Ralph Loop configuration (batch_size, parallel_lanes, verification_strictness)
- **usage_notes**: Execution requirements from sequence
- **retry_budgets**: Remaining retry attempts per step
- **handoff_contracts**: Requirements for step handoffs

### Error Handling
- **validation_findings**: Findings from validation steps
- **errors**: Errors encountered during execution
- **fallback_strategies**: Active fallback strategies
- **escalation_path**: Path for human intervention if needed

### Final Output
- **final_output**: Final assembled deliverable
- **completion_certificate**: Verification that all success criteria met
- **integration_report**: Report of parallel lane integration

The context supports execution, debugging, resumability, and audit logging across the complete Ralph Loop workflow.
