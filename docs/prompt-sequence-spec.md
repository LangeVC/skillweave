# Prompt Sequence Specification

## Required sections

1. **Metadata**: Title, author, version, sequence_type (plan/build/mixed), execution_mode (rex/ralph_attended/ralph_overnight)
2. **Objective**: Clear statement of what the sequence accomplishes
3. **Success Criteria**: Measurable criteria for sequence completion
4. **Assumptions**: Prerequisites and assumptions about execution context
5. **Usage Notes**: Execution requirements (web_research, citations, intermediate_validation, etc.)
6. **Inputs Required**: Data and context needed for execution
7. **Outputs Required**: Expected deliverables and their formats
8. **Sequence Steps**: Individual steps with v2 fields (see below)
9. **Final Assembly**: How outputs are combined into final deliverable
10. **Validation Rules**: How to validate sequence completion
11. **Failure Handling**: Retry strategies and fallback approaches
12. **Final Deliverable Format**: Format of the final output

## V2 Build Step Normalization (Required for Ralph Loop execution)

Each build step should define these 9 fields for safe parallelization:

1. **`id`**: Unique identifier (string)
2. **`name`**: Human-readable name
3. **`purpose`**: What this step accomplishes
4. **`depends_on`**: List of step IDs that must complete first
5. **`instructions`**: Detailed execution instructions
6. **`write_scope`**: Files/directories this step modifies (critical for parallelization)
7. **`verification`**: How to verify step completion (tests, linting, type checking)
8. **`integration_gate`**: Gate criteria before integration (tests_passed, verifier_passed, continue)
9. **`retry_budget`**: Maximum retry attempts before escalation
10. **`handoff_contract`**: Requirements for handing off to dependent steps

## Optional but Recommended Fields

- **`expected_output`**: Description of expected step output
- **`completion_rule`**: Rule for determining step completion
- **`web_research`**: Whether web research is required
- **`citations`**: Whether citations are required
- **`intermediate_validation`**: Validation required before proceeding
- **`fallback_behavior`**: What to do if primary approach fails
- **`output_style`**: Style guidelines for output

## Ralph Loop Configuration

For Ralph Loop execution, include these fields in metadata:
- **`ralph_loop_config`**: Configuration for Ralph Loop state machine
- **`batch_size`**: Maximum steps per batch
- **`parallel_lanes`**: Maximum parallel lanes per batch
- **`verification_strictness`**: How strict verification should be (strict/balanced/lenient)
