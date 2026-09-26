---
id: prompt-framing-assumption-prioritization
type: discovery
phase: framing
name: "Assumption Prioritization (Risk Matrix)"
version: 1.0.0
tags: [framing, assumptions, risk-matrix, prioritization]
lens_rules: [value_over_noise, scan_before_read, bias_toward_action]
---

# Assumption Prioritization (Risk Matrix)

## Input Requirements
- **Assumptions list**: Assumptions extracted from assumption surfacing (minimum 5)
- **Project context**: The project or feature being evaluated

## Instructions

### Step 1: Risk Matrix Scoring
For each assumption, score on two axes:

**Impact (1-5)** — How damaging if this assumption is wrong:
1. Negligible — Minor inconvenience, easily corrected
2. Minor — Noticeable setback but recoverable
3. Significant — Major rework or scope change needed
4. Critical — Project failure or fundamental redesign needed
5. Catastrophic — Irreversible damage, market failure

**Probability (1-5)** — How likely the assumption is wrong:
1. Improbable — Strong evidence supports it
2. Unlikely — Some evidence, but gap exists
3. Possible — Plausible but unvalidated
4. Likely — Weak evidence, high uncertainty
5. Almost Certain — No evidence, pure belief

### Step 2: Priority Calculation

| Assumption | Impact (1-5) | Probability (1-5) | Risk Score (I×P) | Zone |
|------------|-------------|-------------------|-----------------|------|
| [Name] | I | P | I×P | High/Med/Low |

**Zones**:
- **High** (score 15-25): Validate immediately before proceeding
- **Medium** (score 6-14): Validate before key decisions
- **Low** (score 1-5): Monitor, validate if time permits

### Step 3: Validation Plan
For the top 5 assumptions (highest risk scores), define:

| Assumption | Validation Method | Success Criterion | Effort (hrs) | Cost |
|------------|------------------|-------------------|-------------|------|
| [Name] | [Interview/Survey/Prototype/Data Analysis] | [What proves this true] | [Hours] | [$] |

### Step 4: Risk Register
Create a risk register from the high-zone assumptions:

```
## Risk: [Assumption title]
- **Score**: [Impact] × [Probability] = [Total] (High)
- **Contingency**: What we do if it proves false
- **Trigger**: What signals we should watch for
- **Owner**: Who monitors this assumption
```

### Step 5: Next Action
- **Target artifact**: Assumption Log (`.skillweave/templates/discovery/assumption-log.yaml`)
- **Target module**: `.skillweave/lib/assumptions.py` for tracking
- **Suggested next step**: Execute the top-2 validation experiments

## Output Format
Markdown document with risk matrix scoring table (all assumptions), zone-based sorting, detailed validation plan for top-5 assumptions, risk register for high-zone items, and recommended execution order.
