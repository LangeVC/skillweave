---
name: skillweave-promptchain-execute
description: Execute SkillWeave prompt sequences with plan/build/mixed mode detection, adaptive outputs, and post-execution options. Accepts sequence as parameter or .md/.txt attachment.
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

**Example Execution Interaction:**

1. **Skill analyzes sequence**: "Detected mixed sequence: 5 plan steps (business concept), 3 build steps (website prototype)"
2. **Skill executes steps** with type-appropriate outputs:
   - Plan steps → Business plan .md sections
   - Build steps → Code files + technical report .md
3. **Skill asks post-execution questions**:
   - "Target audience for plan outputs? [Humanize/Machinize/Mixed]"
   - "Target audience for build outputs? [Humanize/Machinize/Mixed]"
   - "Initiate development pipeline for build components? [Yes/No]"
4. **If development pipeline requested**:
   - "Initiating `/skillweave-releasechain` with: review, testing, commit, push, PR, release, changelog"
   - Transfers build outputs to releasechain skill for processing
5. **Final deliverables presented** organized by type and audience

**Execution Process:**

1. **Sequence Analysis:**
   - Detect sequence type: **plan mode** (conceptual, strategy, business planning), **build mode** (development, coding, implementation), or **mixed**
   - Analyze step purposes and expected outputs
   - Identify which steps produce human-readable vs. machine-readable outputs

2. **Adaptive Execution:**
   - For **plan mode steps**: Create well-structured .md documents (business plans, strategies, reports)
   - For **build mode steps**: Generate code/files with accompanying technical documentation
   - For **mixed sequences**: Separate plan and build outputs appropriately

3. **Post-Execution Options:**
   - Ask about **target audience** for outputs:
     - **Humanize**: Optimize for human readability (explanations, summaries, formatting)
     - **Machinize**: Optimize for machine processing (structured data, APIs, code)
     - **Mixed**: Separate human and machine outputs appropriately
   - For **build components**: Offer to initiate development pipeline via `/skillweave-releasechain` (review, testing, commit, push, PR, release, changelog)
   - For **plan components**: Offer document consolidation and formatting options

4. **Output Structure:**
   - Step-by-step execution with progress tracking
   - Validation status per step with improvement suggestions
   - Error or fallback handling with recovery options
   - Final assembled deliverables organized by purpose and audience

**Execution Rules:**
- Execute in sequence unless the sequence explicitly allows otherwise
- Respect usage notes before marking a step complete
- If `web_research: required`, do not complete the step without research
- If `citations: required`, do not complete the step without citations
- If `intermediate_validation: required`, validate before moving on
- If the sequence is blocked, follow failure handling rules
- Do not freestyle beyond the defined scope of the sequence
- Adapt output format based on detected sequence type and step purpose

## Recommended companion files

Use these files if present:
- `references/execution-rules.md`
- `references/format-spec.md`
- `assets/workflow-context.schema.json`