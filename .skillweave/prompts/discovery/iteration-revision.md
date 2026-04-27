---
id: prompt-iteration-revision
type: discovery
phase: iteration
name: "Evidence-Driven Revision"
version: 1.0.0
tags: [iteration, revision, feedback, quality]
lens_rules: [yes_and, show_dont_tell, bias_toward_action]
---

# Evidence-Driven Revision

## Input Requirements
- **Prior version**: The artifact or output being revised (full content or reference)
- **Feedback**: Structured feedback from feedback synthesis (`.skillweave/templates/discovery/feedback-synthesis.md`)
- **Evidence**: Data, user research, or test results that inform the revision
- **Iteration log**: Prior iteration entries from `.skillweave/tracking-log/iterations.yaml`

## Instructions

### Step 1: Learning Extraction
Before making changes, extract learnings from the feedback:

| Question | Answer |
|----------|--------|
| What did we learn? | Key insight from feedback or evidence |
| What surprised us? | Unexpected finding that challenges assumptions |
| What was confirmed? | Previous assumptions validated |
| What changed? | Shift in understanding or priority |

Base every answer on evidence, not opinion. Each claim must reference a specific data point, quote, or metric.

### Step 2: Change Planning
For each proposed change, document:

```
## Change: [Brief description]

**Evidence**: Why this change is needed (reference feedback or data)
**Prior State**: What it was before
**Proposed State**: What it will become
**Expected Impact**: What outcome this change should produce
**Revert Criterion**: What would tell us this change was wrong
```

### Step 3: Revision
Apply changes by building on prior work. Follow these rules:
1. **Extend, don't replace**: Keep what works, add what's missing
2. **Reference prior output**: Use IDs or section references from the prior version
3. **Document rationale**: Every change must cite its evidence source
4. **Version tracking**: Increment the revision counter

### Step 4: Impact Assessment
After revising, assess:

| Aspect | Prior | Revised | Delta |
|--------|-------|---------|-------|
| Clarity | [Rating] | [Rating] | +/- |
| Completeness | [%] | [%] | +/- |
| Actionability | [Rating] | [Rating] | +/- |

### Step 5: Next Action
- **Target artifact**: Updated artifact in `.skillweave/templates/discovery/` or `.skillweave/prompts/discovery/`
- **Target log**: `.skillweave/tracking-log/iterations.yaml` — append new iteration entry
- **Suggested next step**: Run validation on the revised output

## Output Format
Markdown document with learning extraction table, per-change planning sections (one per change), revised full output, impact assessment table, and recommended next validation step.
