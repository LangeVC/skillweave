---
name: skillweave-launch
description: "Coordinate pre-launch checks, environment deployment, communication, verification, and launch metrics."
argument-hint: 'release_summary="[JSON]" command="[deploy|announce|verify|metrics]" environment="[production|staging]" mode="[guided|assisted]"'
---

# /skillweave-launch

> Canonical metadata is English. User-facing artifacts follow the output language setting.

Launch coordination — take a published release live.

This skill handles the Launch phase of the SkillWeave lifecycle (phase order: 6).
It runs after Release is complete and the artifact is published.

## Phase Context

- **Order**: 6 (follows Release at order 5)
- **Type**: optional
- **Entry condition**: Release is published and available
- **Exit conditions**:
  - Deployment complete and verified
  - User-facing communication sent
  - Launch metrics baseline captured

## Responsibilities

| Activity | Description |
|----------|-------------|
| Production deployment | Coordinate deployment to production environment(s) |
| User communication | Prepare and distribute release notes, changelogs, announcements |
| Go-live coordination | Manage rollout timing, verify deployment health |
| Metrics baseline | Capture pre/post launch metrics for comparison |

## Pre-Launch-Checkliste (erzwungener Gate)

Jeder Deployment-Durchlauf MUSS vor Ausführung den Pre-Launch-Check durchlaufen.
Bei Fehlschlag wird das Deployment blockiert.

- [ ] Alle Tests grün (CI-Pipeline)
- [ ] CHANGELOG.md aktualisiert und versioniert
- [ ] README.md aktualisiert (Version-Badge, Features, Getting Started)
- [ ] Release-Naming-Convention: exakt `SkillWeave vX.Y.Z` — kein zusätzlicher Text im Titel (Beschreibungstext gehört in die Release Notes Body). Regex: `^SkillWeave v[0-9]+\.[0-9]+\.[0-9]+$`. Bei Verstoß: Release blockieren.
- [ ] Git-Flow-Check: Release-Branch wurde über `dev` → `main` gemerged (kein direkter Feature-Branch → `main` Merge). Falls `dev` nicht existiert: Warnung ausgeben und empfehlen.
- [ ] Release-Tag existiert (git tag vX.Y.Z)
- [ ] Secrets/ENVs in Ziel-Umgebung gesetzt
- [ ] Maintenance-Mode konfiguriert (Production)
- [ ] Database-Backup erstellt
- [ ] Health-Endpoint erreichbar (staging → ok)
- [ ] Rollback-Plan dokumentiert (siehe unten)
- [ ] Dependency-Updates reviewed
- [ ] Breaking Changes kommuniziert

## Rollback-Plan

Jedes Deployment erzeugt einen dokumentierten Rollback-Plan:

```json
{
  "git_revert_cmd": "git revert <deploy-hash>",
  "db_restore": "backup_<timestamp>.sql",
  "estimated_downtime_sec": 30,
  "trigger": "health_check.status != 'ok' after deploy"
}
```

Der Rollback wird NIE automatisch ausgeführt — nur als dokumentierter Plan.

## Abgrenzung zu skillweave-releasechain

| Aspekt | releasechain | launch |
|---|---|---|
| Phase | Build → Review → Iteration | Deployment → Go-Live |
| Fokus | Code-Qualität, Tests, PRs | Pre-Check, Auslieferung, Metriken |
| Ausführung | Ralph Loop (iterativ) | Linear, gate-basiert |
| Rollback | Code-Revert im Loop | Deployment-Rollback (geplant) |
| Outcome | Fertiges Release-Artifact | Live-System + Announcement |

## Usage

```
/skillweave-launch release_summary='{"version":"0.6.0","artifact_locations":["dist/"],"changelog":"..."}'
```

## Parameters

- `release_summary` (required): JSON from releasechain containing version, artifact locations, changelog
- `command` (optional): Select sub-command — `deploy`, `announce`, `verify`, or `metrics`
- `environment` (optional): Target environment (default: `production`)
- `mode` (optional): `guided` (step-by-step) or `assisted` (automatic with human confirmation at gates)

## Commands

### check — Pre-Launch-Check
- Führt Pre-Launch-Checkliste aus
- Gibt Pass/Fail mit Details zurück
- Blockiert deploy bei Fail

### deploy — Deployment ausführen
- Triggert GitHub Actions workflow_dispatch
- Führt health_check nach Deployment aus
- Dokumentiert Rollback-Plan
- Akzeptiert `environment` (staging/production)

### announce — Release Notes + Announcement
- Liest CHANGELOG.md
- Kombiniert mit release_summary (JSON)
- Output: Markdown (default) oder JSON

### verify — Health-Check nach Deployment
- Ruft Health-Endpoint auf
- Prüft response_time_ms, http_status
- Output: Status ok/degraded/down

### metrics — Pre/Post-Metriken vergleichen
- Erfasst MetricSnapshot vor/nach Deployment
- Vergleicht response_time, error_rate, requests_per_minute
- Liefert delta_pct und Verdict (improved/degraded/stable)

## Testing

- `deployment.trigger_deployment`: Korrekter workflow_dispatch-Aufruf, Environment-Weitergabe
- `deployment.health_check`: Positiv (200, <500ms) / Negativ (Timeout, 5xx)
- `deployment.rollback`: Plan-Dokumentation, kein automatischer Revert
- `announce.generate_release_notes`: CHANGELOG.md-Parsing, summary-Merge, valides Markdown/JSON
- `announce.format_announcement`: Channel-spezifische Formatierung
- `metrics.capture_metrics`: Endpoint-Abfrage, Timeout-Handling
- `metrics.compare_metrics`: Delta-Berechnung, Verdict-Logik (Schwellwerte: >5% degraded)
