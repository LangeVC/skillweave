---
name: skillweave-post-release
description: Retrospektive, Feedback, Monitoring, Iterationsplanung
argument-hint: command="[retrospective|feedback|monitor|plan|health]" version="[version]"
---

# skillweave-post-release

Post-release lifecycle: retrospective, feedback collection, metric monitoring,
iteration planning, and system health checks. Mixed plan/build skill.

## Retro-Vorlage

Jede Retrospektive folgt dieser Struktur:

```markdown
## Retrospective v{version}

**Datum:** {date}
**Teilnehmer:** {participants}

### What went well
- {item}
### What to improve
- {item}
### Action Items
| Priority | Action | Owner |
|----------|--------|-------|
| P1       | {desc} | @user |
```

Action Items use P1 (blocker), P2 (next iteration), P3 (backlog) priority.

## Observe Integration

- `command="retrospective"` kann einen observe-report einbetten:
  `/skillweave-observe command="report" session="<id>"` liefert Rohdaten
  für die Retro-Diskussion (Timings, Fehler, Bottlenecks).
- Feedback wird mit Memory-Daten angereichert: `/skillweave-observe command="memory" session="<id>"`
  liefert decisions/gotchas aus dem Release-Session-Kontext.

## Commands

| Command         | Description |
|-----------------|-------------|
| `retrospective` | Führt eine Retro durch. Nutzt Vorlage + observe-Integration. Output: Markdown-Report |
| `feedback`      | Sammelt Feedback aus GitHub Issues seit letztem Tag. Kategorisiert in bug/feature/improvement/question |
| `monitor`       | Ruft Metriken ab (via observe health endpoint + deployment metrics) |
| `plan`          | Erstellt Iterationsplan aus Retro + Feedback. Priorisiert nach urgency × effort |
| `health`        | System-Health-Check via observe health endpoint |

## Backend Modules

- `src/skillweave/post_release/retrospective.py` — Retro-Vorlage, Report-Formatierung
- `src/skillweave/post_release/feedback.py` — GitHub Issue-Feedback, Kategorisierung
- `src/skillweave/post_release/iteration.py` — Backlog-Priorisierung, Plan-Formatierung

## Testing

| Test Case | What to Validate |
|-----------|------------------|
| Retro-Vorlage korrekt | `create_retro_template("0.7.0")` liefert dict mit version, sections (4 keys), date |
| Feedback-Kategorisierung | `categorize_feedback()` trennt bugs/features/improvements/questions korrekt |
| Iteration-Backlog valide | `plan_iteration()` produziert sortierte Liste mit priority_score |
| Observe-Integration | Retro-Report enthält Hinweis auf observe-report-Einbettung |
| Action-Item-Priorisierung | P1-Items stehen vor P2/P3 in der sortierten Ausgabe |
