# Gate Policy

## Binary Completion Principle

All meaningful completion decisions must be binary: **pass** or **fail**. No soft advancement.

## Allowed Completion Signals

### 1. Automated Verification
- **Tests passed**: All relevant tests execute and pass
- **Build succeeded**: Compilation, bundling, or build process completes without errors
- **Verifier passed**: Static analysis, linters, type checkers return clean
- **Schema validation**: Configuration, data, or schema validates against defined schema
- **Contract satisfied**: Generated artifacts match expected format and content

### 2. Human Review
- **Explicit `continue`**: Reviewer explicitly states "continue" or equivalent
- **Approval recorded**: Formal approval captured (e.g., "approved", "LGTM")
- **No blocking issues**: Reviewer identifies no blocking concerns

### 3. Artifact Verification
- **Required artifact exists**: Expected file, output, or deliverable is present
- **Artifact matches contract**: Content matches specification (format, structure, quality)
- **Integrity check passed**: Checksums, signatures, or validation passes

## Not Sufficient On Their Own

The following are **not** valid completion signals:

- "looks good"
- "seems fine"
- "mostly done"
- "probably works"
- "should be okay"
- "I think it's ready"
- "no obvious issues"

These statements indicate uncertainty and require conversion to binary signals.

## Inconclusive Results

When verification is inconclusive, mark the batch `inconclusive` and:

1. **Explain why**: Describe what couldn't be verified
2. **Identify next action**: Specify what's needed to reach binary decision
3. **Do not advance**: Never silently proceed from inconclusive state
4. **Offer resolution path**: Suggest how to resolve (more tests, manual review, etc.)

## Gate Types

### 1. Implementation Gate
- **When**: After implementation, before review
- **Checks**: Basic correctness (compiles, tests run, no crashes)
- **Criteria**: Automated verification passes
- **Failure action**: Fix and retry (uses retry budget)

### 2. Review Gate
- **When**: After implementation gate passes
- **Checks**: Quality, design, alignment with requirements
- **Criteria**: Human review returns `continue` or automated review passes
- **Failure action**: Revise based on feedback

### 3. Integration Gate
- **When**: Before/after implementation (per `integration_gate` setting)
- **Checks**: Compatibility with other components, systems
- **Criteria**: Integration tests pass, no regression
- **Failure action**: Adjust integration points

### 4. Release Gate
- **When**: Before release/deployment
- **Checks**: Release readiness, documentation, compatibility
- **Criteria**: All release checks pass
- **Failure action**: Address release blockers

## Gate Implementation

### For `ralph_attended` Mode
- Human review required for review gates
- Automated gates can be human-overridden
- Progress requires explicit human `continue`
- Suitable for substantial repo work

### For `ralph_overnight` Mode
- All gates must be automated or pre-defined
- No human intervention during execution
- Requires well-specified verification criteria
- Suitable for large, structured sequences

### For `rex` Mode
- Lightweight gates only
- May combine implementation and review
- Quick human approval sufficient
- Suitable for small, low-risk work

## Gate Sequence

### Standard Ralph Loop Gate Flow
```
Implementation → [Implementation Gate] → Review → [Review Gate] → Integration → [Integration Gate] → Advance
```

### Parallel Lane Gates
- Sidecar lanes have their own gate sequences
- Critical path gates may depend on sidecar lane completion
- Integration gates synchronize parallel lanes

## Gate Failure Handling

### 1. Implementation Gate Failure
- Apply retry budget
- Attempt narrow fix
- If retries exhausted, mark batch `blocked`
- Do not proceed to review

### 2. Review Gate Failure
- Incorporate feedback
- Revise implementation
- Return to implementation gate
- No retry budget consumption (review is not implementation)

### 3. Integration Gate Failure
- Identify integration points
- Adjust interfaces or contracts
- May require coordination with other lanes
- Potentially complex fix

### 4. Release Gate Failure
- Address release-specific issues
- May involve documentation, packaging, deployment
- Often requires cross-cutting fixes

## Gate Recording

For each gate, record:

- `gate_type`: Implementation, Review, Integration, Release
- `timestamp`: When gate was evaluated
- `criteria`: What was checked
- `result`: `pass`, `fail`, `inconclusive`
- `evidence`: Test results, review comments, verification output
- `decision_basis`: Why the result was assigned

## Best Practices

### 1. Define Gates Early
- Specify gate criteria during batch planning
- Avoid retroactive gate definition
- Ensure verifiability

### 2. Keep Gates Atomic
- One clear pass/fail criterion per gate
- Avoid compound gates (e.g., "tests pass AND review approved")
- Chain atomic gates instead

### 3. Document Gate Rationale
- Explain why each gate exists
- Link to requirements or risks
- Help reviewers understand importance

### 4. Plan for Gate Failure
- Have retry strategies
- Know escalation paths
- Understand blockers

## Examples

### Passing Gate
```
Gate: Implementation Gate
Criteria: All unit tests pass
Evidence: 42 tests passed, 0 failed
Result: pass
Decision: Tests confirm implementation works as specified
```

### Failing Gate
```
Gate: Review Gate
Criteria: Human review returns "continue"
Evidence: Reviewer: "Missing error handling in lines 45-50"
Result: fail
Decision: Implementation incomplete without error handling
```

### Inconclusive Gate
```
Gate: Integration Gate
Criteria: Integration tests with System B pass
Evidence: System B is currently unavailable
Result: inconclusive
Next Action: Wait for System B availability or mock integration
```