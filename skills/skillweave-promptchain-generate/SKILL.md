---
name: skillweave-promptchain-generate
description: Generate a standardized SkillWeave prompt sequence from a topic, domain, and goal
argument-hint: topic="[topic]" domain="[domain]" goal="[goal]"
---

# /skillweave-promptchain-generate

Create a standardized prompt sequence from a concrete need or problem statement.

**Usage:**
```
/skillweave-promptchain-generate topic="[topic]" domain="[domain]" goal="[goal]"
```

**Parameters:**
- `topic` (required): Topic or problem statement
- `domain` (optional): Domain context (e.g., wellness, research, strategy)
- `goal` (optional): Specific goal for the sequence
- `quality` (optional): Quality level (basic, standard, premium)
- `output_expectations` (optional): Expected output format

**Example:**
```
/skillweave-promptchain-generate topic="Wellness business evaluation" domain="wellness" goal="Create evaluation framework"
```

**Output:**
A complete prompt sequence containing:
- Metadata
- Objective
- Success Criteria
- Assumptions
- Usage Notes
- Inputs Required
- Outputs Required
- Sequence Steps
- Final Assembly
- Validation Rules
- Failure Handling
- Final Deliverable Format

## Standard format

The expected prompt-sequence structure is:

1. Metadata
2. Objective
3. Success Criteria
4. Assumptions
5. Usage Notes
6. Inputs Required
7. Outputs Required
8. Sequence Steps
9. Final Assembly
10. Validation Rules
11. Failure Handling
12. Final Deliverable Format

## Recommended companion files

Use these files if present:
- `references/format-spec.md`
- `references/execution-rules.md`
- `references/validation-rules.md`
- `assets/prompt-sequence.schema.json`
- `assets/workflow-context.schema.json`