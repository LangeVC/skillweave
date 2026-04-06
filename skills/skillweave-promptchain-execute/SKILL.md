---
name: skillweave-promptchain-execute
description: Execute a valid SkillWeave prompt sequence step by step using its own rules and inputs
argument-hint: sequence="[valid prompt sequence]" inputs='{"key": "value"}'
---

# /skillweave-promptchain-execute

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

**Execution rules:**
- execute in sequence unless the sequence explicitly allows otherwise
- respect usage notes before marking a step complete
- if `web_research: required`, do not complete the step without research
- if `citations: required`, do not complete the step without citations
- if `intermediate_validation: required`, validate before moving on
- if the sequence is blocked, follow failure handling rules
- do not freestyle beyond the defined scope of the sequence

## Recommended companion files

Use these files if present:
- `references/execution-rules.md`
- `references/format-spec.md`
- `assets/workflow-context.schema.json`