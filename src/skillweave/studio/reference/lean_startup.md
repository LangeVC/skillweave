# Lean Startup Methodology — SkillWeave SKILL.md

> Reference capability for pre_discovery injection point (Free tier).

## Purpose

This SKILL.md is injected at the `pre_discovery` phase to guide the
discovery process with Lean Startup methodology principles.

## Trigger Specification

```json
{
  "triggers": [
    {
      "type": "dev.skillweave.hook",
      "source": "skillweave",
      "filter": {
        "phase": "discovery",
        "position": "pre"
      }
    }
  ]
}
```

## Methodology Overlay

When this SKILL.md is active, apply these principles to the discovery phase:

### 1. Build-Measure-Learn Loop
- Start with hypotheses, not assumptions
- Design the smallest experiment to validate each hypothesis
- Measure results with actionable metrics, not vanity metrics

### 2. Minimum Viable Product (MVP)
- Identify the riskiest assumption first
- Build only what's needed to test that assumption
- Ship fast, learn fast, iterate fast

### 3. Validated Learning
- Define success criteria BEFORE building
- Use binary pass/fail metrics where possible
- Document learnings, not just outcomes

### 4. Pivot or Persevere
- Set clear pivot triggers before starting
- Review data at each checkpoint
- Be willing to change direction based on evidence

## Integration with SkillWeave Phases

| Phase | Lean Startup Activity |
|-------|----------------------|
| Discovery | Customer interviews, problem validation |
| Blueprint | Hypothesis mapping, experiment design |
| Build | MVP development |
| Test | Experiment execution, data collection |
| Release | Market test, soft launch |
| Launch | Scale what works |
| Observe | Metrics review, pivot/persevere decision |
