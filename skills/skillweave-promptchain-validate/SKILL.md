---
name: skillweave-promptchain-validate
description: Validate an existing SkillWeave prompt sequence against the standard and improve it if needed. Accepts sequence as parameter or .md/.txt attachment.
argument-hint: sequence="[prompt sequence]" (or attach .md/.txt file)
---

# /skillweave-promptchain-validate

Review an existing prompt sequence against the SkillWeave standard and improve it if needed.

**Usage:**
```
/skillweave-promptchain-validate sequence="[prompt sequence text]"
```
**Or attach a .md or .txt file** containing the prompt sequence.

**Parameters:**
- `sequence` (optional if file attached): Prompt sequence text to validate
- `strictness` (optional): Validation strictness level (basic, standard, strict)

**Attachment detection:** If no `sequence` parameter is provided, check for attached .md/.txt files. If multiple options exist, ask for clarification.

**Examples:**

**With inline sequence:**
```
/skillweave-promptchain-validate sequence="[paste sequence here]"
```

**With attached file:**
Attach `sequence.md` or `sequence.txt` and use:
```
/skillweave-promptchain-validate
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