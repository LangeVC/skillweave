---
id: prompt-research-opportunity-assessment
type: discovery
phase: research
name: "Market Opportunity Assessment"
version: 1.0.0
tags: [research, opportunity, market]
lens_rules: [value_over_noise, hierarchy_of_needs, bias_toward_action]
---

# Market Opportunity Assessment

## Input Requirements
- **Problem statement**: The problem being solved
- **Target market**: Market size indication or target segment
- **Competitive landscape**: Summary from competitor analysis (optional)
- **Technical feasibility**: Current technology readiness level

## Instructions

### Step 1: Opportunity Scoring
Score the opportunity across these dimensions (1-10):

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Market Size | | TAM/SAM/SOM context or qualitative estimate |
| Growth Rate | | Market growth trajectory |
| Problem Severity | | How painful is the problem? |
| Solution Gap | | How well do current solutions address it? |
| Technical Feasibility | | Can we build it? |
| Competitive Moat | | Defensibility of the solution |
| User Willingness to Pay | | Evidence of monetization |
| Strategic Fit | | Alignment with organizational strengths |

### Step 2: Opportunity Details
For the scored opportunity, describe:
1. **Core opportunity**: What exactly is the opportunity (1-2 sentences)
2. **Why now**: What has changed to make this viable
3. **Success scenario**: What success looks like in 6, 12, 24 months
4. **Failure modes**: What could go wrong and how likely each is

Include examples of similar opportunities that succeeded or failed:

> *Similar to how [company] entered [market] by [approach], this opportunity targets [gap] that [current solutions] miss.*

### Step 3: Opportunity vs. Risk Balance

| Factor | Opportunity | Risk | Net |
|--------|-------------|------|-----|
| Market timing | | | |
| Technical complexity | | | |
| User adoption | | | |
| Competition response | | | |
| Resource requirements | | | |

### Step 4: Recommendation
- **Go / No-Go / Pivot**: Clear recommendation
- **Confidence level**: High / Medium / Low
- **Minimum next step**: Smallest action to improve confidence

### Step 5: Next Action
- **Target artifact**: Opportunity Canvas (`.skillweave/templates/discovery/opportunity-canvas.md`)
- **Suggested next step**: Present assessment to decision-makers

## Output Format
Markdown document with opportunity scoring table, detailed narrative sections, risk balance table, and clear go/no-go recommendation.
