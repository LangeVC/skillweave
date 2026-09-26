---
id: prompt-empathy-user-context
type: discovery
phase: empathy
name: "User Context Mapping"
version: 1.0.0
tags: [empathy, context, journey]
lens_rules: [empathy_first, show_dont_tell, bias_toward_action]
---

# User Context Mapping

## Input Requirements
- **Target persona(s)**: Persona names or descriptions (from persona development)
- **Task/scenario**: What the user is trying to accomplish
- **Environment**: Physical/digital environment details
- **Current workflow**: How the task is done today

## Instructions

### Step 1: Context Dimensions
Map the user context across these dimensions:

| Dimension | What to Capture |
|-----------|-----------------|
| Physical | Location, devices, connectivity, distractions |
| Social | Collaboration partners, stakeholders, audience |
| Temporal | Time pressure, frequency, duration of task |
| Emotional | Frustration, motivation, confidence level |
| Technical | Tools, platforms, skill level, constraints |

### Step 2: Context Scenario
Write a concrete scenario (3-5 paragraphs) showing the user in their context. Include specific details: time of day, environment, emotional state, and how they currently accomplish their goal.

Example framing:
> *It's [time] on a [day]. [Persona] is [location] trying to [goal]. They have [tools/resources]. They feel [emotion] because [reason].*

### Step 3: Context Analysis
For each dimension in Step 1, identify:
1. **Current friction**: What makes the current context suboptimal
2. **Opportunity**: How the context could be improved
3. **Constraint**: What cannot change about the context

### Step 4: Next Action
- **Target artifact**: Research Summary (`.skillweave/templates/discovery/research-summary.md`)
- **Suggested next step**: Share context map with project stakeholders for validation

## Output Format
Markdown document with context dimensions table, narrative scenario, friction-opportunity-constraint analysis, and recommended design responses.
