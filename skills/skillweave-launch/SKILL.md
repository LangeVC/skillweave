---
name: skillweave-launch
description: Pre-Launch-Check, Deployment, Announce, Verify, Metrics
argument-hint: 'release_summary="[JSON]" command="[deploy|announce|verify|metrics]" environment="[production|staging]"'
---

# skillweave-launch

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
