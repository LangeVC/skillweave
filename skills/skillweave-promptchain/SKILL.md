---
name: skillweave-promptchain
description: Generate, validate, and execute standardized prompt sequences with explicit usage notes, validation rules, and step-by-step orchestration.
---

# Skill: SkillWeave PromptChain

## Commands

### /skillweave-promptchain-generate
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

---

### /skillweave-promptchain-validate
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

---

### /skillweave-promptchain-execute
Run a prompt sequence step by step using its own rules.

**Usage:**
```
/skillweave-promptchain-execute sequence="[valid prompt sequence]" inputs="[JSON inputs]"
```

**Parameters:**
- `sequence` (required): Valid prompt sequence to execute
- `inputs` (required): JSON string containing required inputs

**Example:**
```
/skillweave-promptchain-execute sequence="[sequence]" inputs='{"business_idea": "Yoga studio", "target_region": "Berlin"}'
```

**Output:**
- Step outputs
- Validation status per step
- Error or fallback notes when relevant
- Final assembled deliverable

---

## When to use these commands

Use these commands when the task involves:
- multi-step prompt workflows
- standardized prompt sequence creation
- prompt sequence quality review
- step-by-step execution logic
- explicit usage notes such as web research, citations, and fallback behavior

Do not use when a simple single-shot prompt is clearly sufficient.

---

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

---

## Recommended companion files

Use these files if present:
- `references/format-spec.md`
- `references/execution-rules.md`
- `references/validation-rules.md`
- `assets/prompt-sequence.schema.json`
- `assets/workflow-context.schema.json`