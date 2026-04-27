# v0.7.0: skillweave-launch — Vollständiger Launch-Skill

**Promptchain-Typ**: `build` — Deployment, Ausführung, Koordination (analog zu execute, aber auf Deployment fokussiert)
**Promptchain-Modus**: Ralph Loop für mehrstufige Launch-Prozesse

## Problem

Der Launch-Skill existiert als 54-zeiliger Stub (`skills/launch/SKILL.md`) ohne capability.yaml, ohne Referenzen, ohne Code-Backend. Die Launch-Phase in `phases.yaml` hat `skills: []`. Ein tatsächlicher Launch (Deployment, Communication, Go-Live) ist damit nicht durchführbar.

## SKILL.md-Struktur

```yaml
---
name: skillweave-launch
description: Launch-Phase — Deployment-Koordination, User Communication, Go-Live und Metrics-Baseline.
argument-hint: release_summary="[JSON]" command="[deploy|announce|verify|metrics]" environment="[production|staging]"
---
```

### Usage

```
/skillweave-launch release_summary='{"version":"0.7.0"}'                   # Kompletter Launch
/skillweave-launch command="deploy" environment="production"                # Nur Deployment
/skillweave-launch command="announce" version="0.7.0"                       # Release Notes + Announcement
/skillweave-launch command="verify"                                         # Deployment-Health-Check
/skillweave-launch command="metrics"                                        # Pre/Post-Launch-Metriken
```

### Parameters

- `release_summary` (optional): JSON mit version, artifact_locations, changelog (von releasechain)
- `command` (optional): `deploy`, `announce`, `verify`, `metrics` (Default: complete launch workflow)
- `environment` (optional): `production`, `staging` (Default: production)
- `mode` (optional): `guided` (schrittweise) oder `assisted` (automatisch mit Gates). Default: guided

### Pre-Launch Checklist (erzwungen)

1. Release-Tag existiert (`git tag`)
2. Changelog ist aktuell
3. Tests bestanden
4. Deployment-Pfad ist definiert
5. Rollback-Plan existiert

Fehlt ein Punkt: Skill bricht ab und empfiehlt releasechain oder manuelle Korrektur.

### Funktionsweise

1. **Pre-Launch-Check**: Release-Readiness prüfen (Tag, Changelog, Tests, Artefakte)
2. **Deployment**: Koordination mit CI/CD, Health-Check nach Deployment
3. **Communication**: Release Notes aus changelog, Announcement-Text für Nutzer
4. **Go-Live**: Rollout-Timing, Health-Monitoring, Rollback-Bereitschaft
5. **Metriken-Baseline**: Pre/Post-Launch-Metriken erfassen (+20% / -20% etc.)

### Output (deploy)

```
# Launch Report — v0.7.0

## Deployment
- Environment: production
- Status: ✅ deployed
- Health: ✅ 200 OK, p95=120ms
- Rollback: git revert v0.7.0

## Communication
- Release Notes: RELEASE_NOTES.v0.7.0.md
- Announcement: [draft]

## Metrics Baseline
| Metrik | Pre | Post | Delta |
|--------|-----|------|-------|
| Response Time | 150ms | 120ms | -20% |
| Error Rate | 0.5% | 0.3% | -40% |
```

### capability.yaml

```yaml
kind: skill
name: skillweave-launch
version: 0.7.0
description: Launch-Phase — Deployment, Communication, Go-Live und Metrics-Baseline
author: SkillWeave Team
license: MIT
owner: typelicious
frameworks:
  - opencode-command
  - claude-code
  - gemini-cli
keywords:
  - launch
  - deployment
  - release-notes
  - go-live
```

### Referenzen

- Neues Backend: `src/skillweave/launch/deployment.py`, `launch/announce.py`, `launch/metrics.py`
- Bestehend: `src/skillweave/release/readiness.py`, `.github/workflows/`
- `.skillweave/release/readiness-model.yaml`

### Trennung von releasechain

| Aspekt | releasechain (v0.6.0) | launch (v0.7.0) |
|--------|----------------------|-----------------|
| Fokus | Artefakt + Tag + Changelog | Deployment + Kommunikation |
| Output | GitHub Release | Live-System + Announcement |
| Precedes | Launch | Post-Release |
| Rollback | Re-Publish Tag | Re-Deploy + Benachrichtigung |

## Tasks

| ID | Title | Deps | Typ | Sequence-Type |
|----|-------|------|-----|---------------|
| LCH-001 | SKILL.md vollständig umschreiben | — | content | build |
| LCH-002 | capability.yaml erstellen | LCH-001 | config | plan |
| LCH-003 | src/skillweave/launch/ Modul erstellen (deployment.py, announce.py, metrics.py) | LCH-001 | code | build |
| LCH-004 | Pre-Launch-Checklist in Skill-Logik einbetten | LCH-003 | code | build |
| LCH-005 | Tests: Deployment, Announce, Metrics, Pre-Launch-Check (12 Tests) | LCH-003..004 | test | test |
