---
id: prompt-framing-assumption-surfacing
type: discovery
phase: framing
name: "Assumption Surfacing"
version: 1.0.0
tags: [framing, assumptions, risk]
lens_rules: [value_over_noise, hierarchy_of_needs, bias_toward_action]
---

# Assumption Surfacing

## Input Requirements
- **Project description**: Detailed description of the project, its goals, and approach
- **Problem statement**: Validated problem statement
- **Target users**: Who will use the solution

## Instructions

### Step 1: Assumption Extraction
Read the project description and extract assumptions across these categories:

| Category | What to Look For | Example |
|----------|------------------|---------|
| User | Beliefs about who users are, what they want, how they behave | *"Users will complete onboarding in under 2 minutes"* |
| Market | Beliefs about market size, growth, competition | *"The market will grow 20% YoY"* |
| Technical | Beliefs about technology feasibility, scalability | *"The database will handle 10K concurrent users"* |
| Value | Beliefs about perceived value and willingness to pay | *"Users will pay $10/mo for this feature"* |
| Business | Beliefs about cost, timeline, resources | *"The team can deliver in 3 months"* |
| Adoption | Beliefs about how users adopt and engage | *"Viral growth will reduce customer acquisition cost"* |

### Step 2: Assumption Cards
For each assumption, create a structured card:

```
## Assumption: [Title]

**Category**: [User/Market/Technical/Value/Business/Adoption]
**Source**: Where this assumption appears (project description, stakeholder claim, etc.)
**Stated as fact?**: Yes/No — Is it presented as certain?
**Rationale**: Why we believe this (evidence, experience, intuition)
**Impact if wrong**: What happens if this assumption is false
```

Extract minimum 5 assumptions. Target 8+ for complex projects.

### Step 3: Assumption Rating
For each assumption, provide a preliminary rating:
- **Evidence level**: None / Anecdotal / Correlational / Causal
- **Certainty**: High / Medium / Low
- **Risk level if wrong**: Critical / Significant / Manageable / Minor

### Step 4: Next Action
- **Target artifact**: Assumption Log (`.skillweave/templates/discovery/assumption-log.yaml`)
- **Target module**: Assumption prioritization for risk matrix scoring
- **Suggested next step**: Run assumption prioritization to determine which to validate first

## Output Format
Markdown document with category table of extracted assumptions, per-assumption detail cards (minimum 5), evidence and certainty ratings, and recommended validation order.
