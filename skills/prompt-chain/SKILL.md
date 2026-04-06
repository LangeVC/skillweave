---
name: prompt-chain
description: Generate, validate, and execute standardized prompt sequences with explicit usage notes, validation rules, and step-by-step orchestration.
---

# Skill: Prompt Chain for SkillWeave

## Purpose

Use this skill when the user needs one of the following:

1. **generate**
   Create a standardized prompt sequence from a concrete need or problem statement.

2. **validate**
   Review an existing prompt sequence against the SkillWeave standard and improve it if needed.

3. **execute**
   Run a prompt sequence step by step, following its usage notes and execution rules.

This skill is designed for structured prompt chaining, not for monolithic mega-prompts.

## When to use this skill

Use this skill if the task involves:
- multi-step prompt workflows
- standardized prompt sequence creation
- prompt sequence quality review
- step-by-step execution logic
- explicit usage notes such as web research, citations, and fallback behavior

Do not use this skill when a simple single-shot prompt is clearly sufficient.

## Core modes

### Mode 1 – generate

Goal:
Create a prompt sequence in the SkillWeave standard format.

Expected input:
- topic or problem statement
- goal
- optional context
- optional quality level
- optional domain
- optional output expectations

Expected output:
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

Rules:
- make the sequence logically ordered
- keep steps distinct
- include explicit usage notes
- mark web research or citations when required
- avoid vague or redundant steps
- do not collapse the whole workflow into one large prompt

### Mode 2 – validate

Goal:
Check whether an existing prompt sequence conforms to the SkillWeave standard and improve it where necessary.

Expected input:
- existing prompt sequence
- optional target use case
- optional preferred strictness level

Expected output:
- validation findings
- missing parts
- inconsistencies
- weak steps
- improved version of the sequence

Validation focus:
- structural completeness
- logical step order
- consistency of inputs and outputs
- usefulness of usage notes
- usefulness of validation rules
- usefulness of failure handling

Rules:
- do not only critique; improve
- preserve original intent when possible
- call out weak assumptions explicitly
- identify when steps are too broad, too vague, or out of order

### Mode 3 – execute

Goal:
Execute a prompt sequence step by step using its own rules.

Expected input:
- a valid prompt sequence
- the required task inputs

Expected output:
- step outputs
- validation status per step
- error or fallback notes when relevant
- final assembled deliverable

Execution rules:
- execute in sequence unless the sequence explicitly allows otherwise
- respect usage notes before marking a step complete
- if `web_research: required`, do not complete the step without research
- if `citations: required`, do not complete the step without citations
- if `intermediate_validation: required`, validate before moving on
- if the sequence is blocked, follow failure handling rules
- do not freestyle beyond the defined scope of the sequence

## Standard format to enforce

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

If any critical section is missing, flag it during validation or execution setup.

## Usage notes model

Treat usage notes as operational rules, not decorative text.

Expected core fields:
- `web_research`
- `citations`
- `intermediate_validation`
- `ask_for_clarification`
- `execution_mode`
- `fallback_behavior`
- `output_style`

When usage notes and a step instruction conflict, treat the usage notes as higher priority.

## Recommended companion files

Use these files if present:
- `references/format-spec.md`
- `references/execution-rules.md`
- `references/validation-rules.md`
- `assets/prompt-sequence.schema.json`
- `assets/workflow-context.schema.json`

Load them only when needed.
