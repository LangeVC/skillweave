# Workflow Context

The workflow context stores the runtime state of a prompt sequence.

## Minimal fields

- sequence_id
- mode
- status
- current_step_id
- completed_steps
- step_outputs
- inputs
- usage_notes
- validation_findings
- errors
- final_output

The context is intended to support execution, debugging, and later resumability.
