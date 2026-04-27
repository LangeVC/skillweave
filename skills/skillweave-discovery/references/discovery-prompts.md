# Discovery Prompts

Reference prompts grouped by phase. Each prompt is designed for structured multi-agent execution.

## Empathy Phase

### DSC-P1: Problem Exploration

| Field | Value |
|-------|-------|
| **ID** | `problem-exploration` |
| **Purpose** | Surface the core problem, its context, and why it matters |
| **Input needed** | Topic, domain, known symptoms, affected users |
| **Output format** | `.skillweave/discovery/problem-exploration.md` — sections: Context, Symptoms, Current Workarounds, Desired Outcome, Success Criteria |

### DSC-P2: User Persona

| Field | Value |
|-------|-------|
| **ID** | `user-persona` |
| **Purpose** | Create 1-3 evidence-based user personas representing key stakeholder groups |
| **Input needed** | Problem exploration output, domain knowledge |
| **Output format** | `.skillweave/discovery/user-persona.md` — sections: Name, Role, Goals, Pains, Behaviors, Context per persona |

### DSC-P3: Empathy Map

| Field | Value |
|-------|-------|
| **ID** | `empathy-map` |
| **Purpose** | Map what users say, think, do, and feel around the problem |
| **Input needed** | User persona(s) |
| **Output format** | `.skillweave/discovery/empathy-map.md` — SAY/THINK/DO/FEEL quadrants per persona, with verbatim quotes and observed behaviors |

### DSC-P4: Stakeholder Mapping

| Field | Value |
|-------|-------|
| **ID** | `stakeholder-mapping` |
| **Purpose** | Identify all stakeholders, their influence, interests, and relationships |
| **Input needed** | Problem exploration, known project context |
| **Output format** | `.skillweave/discovery/stakeholder-map.md` — sections: Power-Interest Grid, Stakeholder Profiles, Influence Map, Engagement Strategy |

## Research Phase

### DSC-P5: Competitive Landscape

| Field | Value |
|-------|-------|
| **ID** | `competitive-landscape` |
| **Purpose** | Analyze direct and indirect competitors to identify gaps and differentiation |
| **Input needed** | Domain, market segment |
| **Output format** | `.skillweave/discovery/competitive-landscape.md` — sections: Competitor Matrix, Feature Comparison, Positioning Map, Competitive Threats |

### DSC-P6: Market Analysis

| Field | Value |
|-------|-------|
| **ID** | `market-analysis` |
| **Purpose** | Assess market size, trends, and timing for the opportunity |
| **Input needed** | Domain, competitive landscape |
| **Output format** | `.skillweave/discovery/market-analysis.md` — sections: Market Sizing, Growth Trends, Segment Analysis, Timing Assessment, Risk Factors |

### DSC-P7: User Interview Synthesis

| Field | Value |
|-------|-------|
| **ID** | `user-interview` |
| **Purpose** | Synthesize findings from user interviews into actionable insights |
| **Input needed** | Interview notes or transcript snippets, persona context |
| **Output format** | `.skillweave/discovery/user-interview.md` — sections: Methodology, Key Themes, Verbatim Quotes, Pain Points, Surprising Insights, Recommendations |

### DSC-P8: Assumption Mapping

| Field | Value |
|-------|-------|
| **ID** | `assumption-mapping` |
| **Purpose** | Explicitly catalogue assumptions, classify by risk, and identify which must be validated |
| **Input needed** | All prior discovery artifacts |
| **Output format** | `.skillweave/discovery/assumption-map.md` — sections: Assumption Catalogue (per assumption: statement, category, confidence, risk level, validation method) |

## Framing Phase

### DSC-P9: Problem Statement

| Field | Value |
|-------|-------|
| **ID** | `problem-statement` |
| **Purpose** | Distill research into a crisp, actionable problem statement |
| **Input needed** | All empathy and research artifacts |
| **Output format** | `.skillweave/discovery/problem-statement.md` — sections: User, Need, Insight (framed as "We have discovered that [USER] needs [NEED] because [INSIGHT]"), Constraints, Success Metrics |

### DSC-P10: Opportunity Assessment

| Field | Value |
|-------|-------|
| **ID** | `opportunity-assessment` |
| **Purpose** | Evaluate the opportunity: impact, effort, timing, and go/no-go recommendation |
| **Input needed** | Problem statement, market analysis, competitive landscape |
| **Output format** | `.skillweave/discovery/opportunity-assessment.md` — sections: Opportunity Score (ICE or RICE), Impact Analysis, Effort Estimate, Risk Assessment, Go/No-Go Recommendation |

## Output Phase

### DSC-P11: Discovery Report

| Field | Value |
|-------|-------|
| **ID** | `discovery-report` |
| **Purpose** | Consolidated report that seeds the blueprint PRD process |
| **Input needed** | All prior phase artifacts |
| **Output format** | `.skillweave/discovery/discovery-report.md` — sections: Executive Summary, Problem Statement, Key Findings, Personas, Opportunities, Decision Record, Artifact Index, Handoff Notes for Blueprint |
