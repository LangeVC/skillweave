# v0.7.0: skillweave-post-release — Post-Release & Iteration

**Promptchain-Typ**: `mixed` — Analyse (validate) + Planung (generate) für Retrospektiven und Iterationen
**Promptchain-Modus**: Ralph Loop für strukturierte Post-Release-Zyklen

## Problem

Nach dem Launch gibt es keinen Skill für Post-Release-Aktivitäten: Monitoring, Feedback-Sammlung, Retrospektive, Iterationsplanung. Die Post-Release-Phase in `phases.yaml` hat `skills: []`.

## SKILL.md-Struktur

```yaml
---
name: skillweave-post-release
description: Post-Release-Phase — Retrospektive, Feedback-Sammlung, Monitoring und Iterationsplanung.
argument-hint: command="[retrospective|feedback|monitor|plan|health]" version="[version]"
---
```

### Usage

```
/skillweave-post-release                                              # Interaktive Post-Release-Session
/skillweave-post-release command="retrospective"                      # Retrospektive durchführen
/skillweave-post-release command="feedback"                           # Feedback sammeln + kategorisieren
/skillweave-post-release command="monitor" version="0.7.0"            # Monitoring-Report erstellen
/skillweave-post-release command="plan"                               # Nächste Iteration planen
/skillweave-post-release command="health"                             # System-Health-Report
```

### Parameters

- `command` (optional): `retrospective`, `feedback`, `monitor`, `plan`, `health` (Default: interaktiv)
- `version` (optional): Zielversion für Monitoring/Health
- `mode` (optional): `guided` (schrittweise) oder `assisted` (automatisch). Default: guided

### Funktionsweise

1. **Retrospektive**: Strukturierte Retro (What went well? What to improve? Action Items)
2. **Feedback-Kategorisierung**: Sammelt und kategorisiert User-Feedback aus Issues, Comments, Metrics
3. **Monitoring-Report**: Fasst Metriken, Errors, Performance-Daten zusammen (ruft observe auf)
4. **Iterationsplanung**: Erstellt nächsten Iteration-Backlog basierend auf Feedback + Retro
5. **Health-Report**: System-Health (Uptime, Error-Rate, Response-Time)

### Output (retrospective)

```
# Post-Release Retrospective — v0.7.0

## What went well
- [item 1]
- [item 2]

## What to improve
- [item 1] → Action: [konkreter Schritt]

## Action Items
| Prio | Action | Owner | Due |
|------|--------|-------|-----|
| P1 | ... | ... | ... |

## Nächste Iteration: Backlog
- [Item 1] (aus Feedback)
- [Item 2] (aus Retro)
```

### capability.yaml

```yaml
kind: skill
name: skillweave-post-release
version: 0.7.0
description: Post-Release-Phase — Retrospektive, Feedback, Monitoring und Iterationsplanung
author: SkillWeave Team
license: MIT
owner: typelicious
frameworks:
  - opencode-command
  - claude-code
  - gemini-cli
keywords:
  - post-release
  - retrospective
  - feedback
  - iteration
  - monitoring
```

### Referenzen

- Neues Backend: `src/skillweave/post_release/retrospective.py`, `feedback.py`, `iteration.py`
- `skillweave-observe` für Rohdaten (Events, Timings, Memory)
- `.github/workflows/` für Issue-Tracking

### Integration mit observe

- **post-release** = menschlicher Part (Retro, Entscheidungen, Planung)
- **observe** = maschineller Part (Rohdaten, Events, Metriken)
- post-release ruft observe auf für Daten, ergänzt eigene Analyse

## Tasks

| ID | Title | Deps | Typ | Sequence-Type |
|----|-------|------|-----|---------------|
| POST-001 | SKILL.md für post-release erstellen | — | content | mixed |
| POST-002 | capability.yaml erstellen | POST-001 | config | plan |
| POST-003 | src/skillweave/post_release/retrospective.py | POST-001 | code | build |
| POST-004 | src/skillweave/post_release/feedback.py | POST-001 | code | build |
| POST-005 | src/skillweave/post_release/iteration.py | POST-003 | code | build |
| POST-006 | Integration mit observe dokumentieren | POST-001 | content | plan |
| POST-007 | Tests: Retro, Feedback, Iteration, observe-Integration (10 Tests) | POST-003..006 | test | test |
