# Blueprint Integration

How `skillweave-discovery` and `skillweave-blueprint` hand off context.

## Discovery Output Format

When discovery completes, these files exist under `.skillweave/discovery/`:

```
.skillweave/discovery/
  problem-statement.md        # Mandatory — seeds PRD problem section
  decision-record.md          # Mandatory — seeds PRD constraints/assumptions
  user-persona.md             # Mandatory — seeds PRD target_audience
  empathy-map.md              # Optional
  stakeholder-map.md          # Optional
  competitive-landscape.md    # Optional
  market-analysis.md          # Optional
  user-interview.md           # Optional
  assumption-map.md           # Optional
  opportunity-assessment.md   # Optional
  discovery-report.md         # Mandatory — consolidated handoff
```

### Decision Record Format

Each decision in `decision-record.md` follows this structure:

```markdown
## DEC-001: [Title]

- **Date**: YYYY-MM-DD
- **Status**: Decided / Deprecated / Superseded
- **Context**: Why this decision was needed
- **Options Considered**: List with pros/cons per option
- **Outcome**: What was chosen and why
```

## Blueprint Pre-Scan Logic

When `skillweave-blueprint` loads, it scans `.skillweave/prds/` for existing PRD files and `.skillweave/discovery/` for discovery artifacts:

```
IF prd.json exists in .skillweave/prds/:
  → Flag: "Blueprint already complete. Edit or regenerate?"
  → Skip discovery handoff
ELSE IF discovery-report.md exists in .skillweave/discovery/:
  → Read discovery-report.md
  → Extract: Problem Statement, Decision Record, Personas
  → Seed PRD interview with pre-filled context
  → Jump to solution-oriented questions (skip exploration preamble)
ELSE:
  → Run full PRD interview from scratch
```

## Handoff Contract

The discovery report header MUST include this metadata block for the blueprint to parse:

```yaml
---
discovery-status: complete
discovery-date: YYYY-MM-DD
blueprint-ready: true
artifacts:
  - problem-statement
  - decision-record
  - user-persona
  - discovery-report
---
```

Without this header, the blueprint treats discovery as incomplete and falls back to full interview mode.
