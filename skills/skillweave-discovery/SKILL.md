---
name: skillweave-discovery
description: Problemdefinition, User Research, Empathy Mapping, Opportunity Validation
argument-hint: topic="[topic]" domain="[domain]" mode="[quick|deep]"
---

# /skillweave-discovery

**Define the right problem before building the wrong solution.** Empathy-driven research, problem framing, and opportunity validation for multi-agent AI development.

## Mandatory Pre-Flight: SkillWeave Sandboxing

Before generating output, verify and enforce:

1. **Directory**: Create `.skillweave/` with `discovery/`, `prds/`, `tracking-log/` subdirs if missing.
2. **Routing**: ALL artifacts go under `.skillweave/discovery/` — never the repo root.
3. **Git**: Append `.skillweave/` to `.gitignore` if not present.
4. **Pre-Scan**: Scan `.skillweave/prds/` for existing PRDs. If found, flag and ask whether to update or skip discovery.

## Phases

### Phase 1: Empathy
Understand stakeholders, users, and their unmet needs.

| Step | Description | Artifact |
|------|-------------|----------|
| 1.1 | Problem exploration | `.skillweave/discovery/problem-exploration.md` |
| 1.2 | User persona creation | `.skillweave/discovery/user-persona.md` |
| 1.3 | Empathy map | `.skillweave/discovery/empathy-map.md` |
| 1.4 | Stakeholder mapping | `.skillweave/discovery/stakeholder-map.md` |

### Phase 2: Research
Gather evidence, validate assumptions, analyze the landscape.

| Step | Description | Artifact |
|------|-------------|----------|
| 2.1 | Competitive landscape | `.skillweave/discovery/competitive-landscape.md` |
| 2.2 | Market analysis | `.skillweave/discovery/market-analysis.md` |
| 2.3 | User interview synthesis | `.skillweave/discovery/user-interview.md` |
| 2.4 | Assumption mapping | `.skillweave/discovery/assumption-map.md` |

### Phase 3: Framing
Synthesize findings into a crisp problem statement and assess opportunity.

| Step | Description | Artifact |
|------|-------------|----------|
| 3.1 | Problem statement | `.skillweave/discovery/problem-statement.md` |
| 3.2 | Opportunity assessment | `.skillweave/discovery/opportunity-assessment.md` |

### Phase 4: Output
Deliver a consolidated discovery report consumable by skillweave-blueprint.

| Step | Description | Artifact |
|------|-------------|----------|
| 4.1 | Discovery report | `.skillweave/discovery/discovery-report.md` |

## Blueprint Integration

`skillweave-blueprint` reads discovery output to seed the PRD interview:

- **Problem Statement** → `problem` section in blueprint PRD
- **Decision Record** → `constraints` / `assumptions` in blueprint PRD
- **Persona + Stakeholder Map** → `target_audience` in blueprint PRD

Blueprint scans `.skillweave/discovery/` for the discovery report. If present, it skips exploration preamble and jumps to solution-oriented questions.

## Testing

| Check | Criteria |
|-------|----------|
| Prompts accessible | All 11 reference prompts load from `references/discovery-prompts.md` |
| Output valid | Each phase artifact is valid markdown with required sections |
| Blueprint detects status | Blueprint pre-scan correctly identifies `.skillweave/discovery/` contents |
| Sandbox enforced | All artifacts land under `.skillweave/discovery/` |
