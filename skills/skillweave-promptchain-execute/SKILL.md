---
name: skillweave-promptchain-execute
description: Execute a valid SkillWeave prompt sequence step by step using its own rules and inputs. Accepts sequence as parameter or .md/.txt attachment.
argument-hint: sequence="[prompt sequence]" inputs="[JSON]" (or attach .md/.txt file)
---

# /skillweave-promptchain-execute

Run a prompt sequence step by step using its own rules.

**Usage:**
```
/skillweave-promptchain-execute sequence="[prompt sequence text]" inputs="[JSON inputs]"
```
**Or attach a .md or .txt file** containing the prompt sequence.

**Parameters:**
- `sequence` (optional if file attached): Prompt sequence text to execute
- `inputs` (required): JSON string containing required inputs

**Attachment detection:** If no `sequence` parameter is provided, check for attached .md/.txt files. If multiple options exist, ask for clarification.

**Examples:**

**With inline sequence:**
```
/skillweave-promptchain-execute sequence="[sequence]" inputs='{"business_idea": "Yoga studio", "target_region": "Berlin"}'
```

**With attached file:**
Attach `sequence.md` or `sequence.txt` and use:
```
/skillweave-promptchain-execute inputs='{"business_idea": "Yoga studio"}'
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