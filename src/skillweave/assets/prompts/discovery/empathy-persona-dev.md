---
id: prompt-empathy-persona-dev
type: discovery
phase: empathy
name: "Persona Development"
version: 1.0.0
tags: [empathy, persona, user-research]
lens_rules: [empathy_first, show_dont_tell, bias_toward_action]
---

# Persona Development

## Input Requirements
- **Project domain**: What is the product/service domain?
- **Target audience**: Known user segments or demographics
- **Existing research**: Any user interviews, surveys, or analytics available
- **Problem space**: Brief description of the problem being solved

## Instructions

### Step 1: User Context
Start by describing the user's real-world context. Think about:
- What does their daily environment look like?
- What tools and technologies do they currently use?
- What constraints (time, budget, skill) do they operate under?
- What is their relationship to the problem domain?

### Step 2: Persona Details
For each persona, define:

| Field | Description |
|-------|-------------|
| Name | Fictional name representing the persona |
| Role | Job title or relationship to the domain |
| Demographics | Age range, experience level, relevant context |
| Goals | 3-5 goals this persona wants to achieve |
| Pain Points | 3-5 frustrations or obstacles they face |
| Usage Context | When and how they would use the solution |
| Quote | A direct-quote capturing their perspective |

### Step 3: Concrete Example
For each persona, include a concrete scenario showing how they experience the current problem. Format:

> *[Persona name] needs to [goal] but [obstacle]. For example, when [specific situation], [persona] [specific behavior/outcome].*

### Step 4: Next Action
- **Target artifact**: `.skillweave/templates/discovery/persona-card.md`
- **Suggested next step**: Validate persona with stakeholder interview or survey

## Output Format
Produce a markdown document with 2-4 personas. Each persona follows the template structure above. End with a "Design Implications" section summarizing what these personas mean for the solution.
