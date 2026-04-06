---
name: skillweave-promptchain-validate
description: Validate an existing SkillWeave prompt sequence against the standard and improve it if needed
argument-hint: sequence="[prompt sequence]"
---

# /skillweave-promptchain-validate

Review an existing prompt sequence against the SkillWeave standard and improve it if needed.

**Usage:**
```
/skillweave-promptchain-validate sequence="[prompt sequence text]"
```

**Parameters:**
- `sequence` (required): Existing prompt sequence to validate
- `strictness` (optional): Validation strictness level (basic, standard, strict)

**Example:**
```
/skillweave-promptchain-validate sequence="[paste sequence here]"
```

**Output:**
- Validation findings
- Missing parts
- Inconsistencies
- Weak steps
- Improved version of the sequence

**Validation focus:**
- structural completeness
- logical step order
- consistency of inputs and outputs
- usefulness of usage notes
- usefulness of validation rules
- usefulness of failure handling

**Rules:**
- do not only critique; improve
- preserve original intent when possible
- call out weak assumptions explicitly
- identify when steps are too broad, too vague, or out of order

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
- `references/validation-rules.md`
- `assets/prompt-sequence.schema.json`
- `assets/workflow-context.schema.json`