---
id: prompt-empathy-pain-points
type: discovery
phase: empathy
name: "Pain Point Articulation"
version: 1.0.0
tags: [empathy, pain-points, problem-discovery]
lens_rules: [empathy_first, show_dont_tell, bias_toward_action]
---

# Pain Point Articulation

## Input Requirements
- **Persona(s)**: Target user descriptions
- **Current workflow**: Step-by-step description of how the user currently accomplishes their goal
- **Known frustrations**: Any existing user feedback or complaints
- **Project scope**: Boundaries of what the project can address

## Instructions

### Step 1: Journey Breakdown
Break the current workflow into 5-10 discrete steps. For each step, identify:

| Step # | Action | Tool/Method | Time Spent | Friction Level (1-5) |
|--------|--------|-------------|------------|----------------------|

### Step 2: Pain Point Extraction
For each step with friction level ≥ 3, extract a structured pain point:

- **Pain Point**: One-line description of the frustration
- **Who feels it**: Specific persona or stakeholder
- **When it occurs**: Step, frequency, context
- **Why it matters**: Impact on outcome, time, quality
- **Current workaround**: How the user copes today
- **Emotional impact**: Frustration, anxiety, resignation, etc.

Include at least one concrete example per pain point:
> *When [persona] tries to [action], [specific bad outcome happens]. They currently cope by [workaround]. This costs them [time/money/quality].*

### Step 3: Prioritization
Rate each pain point by:
- **Severity** (1-5): How bad is the impact?
- **Frequency** (1-5): How often does it occur?
- **Audience** (1-5): How many users experience it?

Priority Score = Severity × Frequency × Audience

### Step 4: Next Action
- **Target artifact**: Assumption Log (`.skillweave/templates/discovery/assumption-log.yaml`)
- **Suggested next step**: Validate top-3 pain points with user interviews

## Output Format
Markdown document with workflow breakdown table, detailed pain point cards (one per section), prioritization matrix, and recommended design focus areas.
