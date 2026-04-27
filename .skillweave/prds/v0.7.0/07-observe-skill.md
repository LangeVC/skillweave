# v0.7.0: skillweave-observe — Reports, Metriken & Execution Memory

**Promptchain-Typ**: `plan` — Lesezugriff, Analyse, Berichterstattung (analog zu validate)
**Promptchain-Modus**: REX (schnelle Reports, keine Schreiboperationen)

## Problem

Aus Initiative 05 existieren vollständige Observation-Module (`event_logger.py`, `timing.py`, `report_generator.py`) und `execution_memory.py` — aber kein Skill macht diese Daten zugänglich.

## SKILL.md-Struktur

```yaml
---
name: skillweave-observe
description: Execution Reports, Timing-Analyse, Event-Logs, Execution Memory und System-Health — schreibgeschützter Observability-Skill.
argument-hint: command="[report|timing|events|memory|summary|health]" session="[session-id]" level="[debug|info|warning|error]"
---
```

### Usage

```
/skillweave-observe                                               # Kurz-Status (Default)
/skillweave-observe command="report" session="2026-04-27"        # Execution-Report für Session
/skillweave-observe command="timing"                              # Timing-Analyse anzeigen
/skillweave-observe command="events" level="warning"              # Events filtern
/skillweave-observe command="memory"                              # Execution-Memory anzeigen
/skillweave-observe command="memory" query="gate policy"          # Memory durchsuchen
/skillweave-observe command="summary"                             # 5-Zeilen-Status
/skillweave-observe command="health"                              # System-Health
```

### Parameters

- `command` (optional): `report`, `timing`, `events`, `memory`, `summary`, `health` (Default: summary)
- `session` (optional): Session-ID oder Datum für gezielte Reports
- `level` (optional, für events): `debug`, `info`, `warning`, `error` (Default: info)
- `query` (optional, für memory): Suchbegriff für Memory-Durchsuchung

### Funktionsweise

1. **Report**: Generiert menschenlesbaren Report aus Event-Logs + Timing-Records einer Session
2. **Timing**: Zeigt Dauer pro Phase/Schritt, identifiziert Flaschenhälse, zeigt Trends über Sessions
3. **Events**: Filtert Log-Level, zeigt Kontext, erlaubt Drill-Down
4. **Memory**: Zeigt 5 Memory-Kategorien (rules, decisions, patterns, gotchas, metrics) + Volltext-Suche
5. **Summary**: 5-Zeilen-Status für schnellen Überblick (letzte Session, Dauer, Ergebnis, offene Punkte)
6. **Health**: Aggregierte System-Health aus Events + Memory (Fehlerrate, Retry-Rate, Session-Trends)

### Output (summary)

```
# SkillWeave Observe — Summary

Letzte Session: 2026-04-27T14:30 (v0.7.0-release)
Dauer: 45min | Ergebnis: ✅ passed
Schritte: 12 | Fehler: 1 (recovered) | Retries: 3
Offene Memory-Einträge: 2 decisions, 1 pattern

Empfehlung: Nächste Phase "launch" bereit. /skillweave-lifecycle command="recommend"
```

### Output (memory)

```
# Execution Memory

## Rules (3)
- rule-001: Always run tests before commit
- rule-002: Gate policy: binary only

## Decisions (5)
- dec-001: promptchain-execute → type: orchestration
- dec-002: releasechain → release-scoped only

## Patterns (2)
- pattern-001: Batch plan → verify → gate → next batch

## Gotchas (4)
- gotcha-001: GitHub release erfordert --follow-tags

## Metrics (7)
- metric-001: avg_session_duration=32min
```

### capability.yaml

```yaml
kind: skill
name: skillweave-observe
version: 0.7.0
description: Execution Reports, Timing-Analyse, Event-Logs, Execution Memory und System-Health
author: SkillWeave Team
license: MIT
owner: typelicious
frameworks:
  - opencode-command
  - claude-code
  - gemini-cli
keywords:
  - observe
  - reports
  - metrics
  - execution-memory
  - observability
```

### Referenzen

- `src/skillweave/observation/event_logger.py` — Structured Event Logging
- `src/skillweave/observation/timing.py` — Performance Timing Records
- `src/skillweave/observation/report_generator.py` — Session Report Generation
- `src/skillweave/execution_memory.py` — 5-Category YAML Execution Memory
- **Kein neuer Python-Code nötig** — reine SKILL.md-Exposition bestehender Module

## Tasks

| ID | Title | Deps | Typ | Sequence-Type |
|----|-------|------|-----|---------------|
| OBS-001 | SKILL.md für observe erstellen | — | content | plan |
| OBS-002 | capability.yaml erstellen | OBS-001 | config | plan |
| OBS-003 | Report- + Memory-Formate in Referenzdokument definieren | OBS-001 | doc | plan |
| OBS-004 | Tests: Report-Generierung, Memory-Zugriff, Event-Filter (6 Tests) | OBS-003 | test | test |
