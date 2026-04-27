# Initiative 06 — GitHub Action, GitHub App & Integration Layer

## Problem

SkillWeave hat 11 GitHub Actions Workflows in `.github/workflows/` und ein `github_integration/` Python-Modul, aber:
- Keine gepflegte GitHub Action (public Marketplace-Eintrag)
- Keine Validation Action für Bundle-Struktur und Skill-Metadaten
- `src/skillweave/github_integration/` ist unvollständig (Teams, Orgas, Issues-Verknüpfung fehlen)
- Release-Validation ist lose gekoppelt (release_gate.py — kein Action-Wrapper)
- Keine GitHub App für Deep-Integration (Repository-Sync, Trust-Signale)
- Issues sind nicht an `.skillweave/tracking-log/` gebunden

## Scope

Dieses PRD definiert die GitHub-native Integration für SkillWeave in 3 Schichten:

### Layer 1: Validation Action (v0.8.0)
Eine publikumsfähige GitHub Action, die:
- Bundle-Struktur validiert
- Skill-Metadaten + capability.yaml prüft
- manifest-Konsistenz sicherstellt
- Release-Readiness checkt
- CHANGELOG + Version-Bump validiert

→ Wrapper um bestehende `src/skillweave/github_integration/` + `release/readiness.py`

### Layer 2: Issues ↔ Tracking-Log Bidirectional Sync (v0.8.0)
- GitHub Issues werden automatisch mit `.skillweave/tracking-log/` synchronisiert
- Issue-Status ↔ Backlog-Status bidirektional
- Task-Erledigung in GitHub = Checkbox in tracking-log ✓
- Neue Issues landen automatisch im Iteration-Backlog
- Tagging: `skillweave/backlog`, `skillweave/phase:build`, etc.

### Layer 3: GitHub App (v0.9.0+)
- Repository-Sync (SkillWeave-Templates in andere Repos deployen)
- Release-Signal-Capture (Telemetrie aus Releases)
- Trust-Enrichment (Provenance, Signatur)
- Usage/Discovery-Support (Bundle-Vorschlag aus Repo-Analyse)

## Out of Scope
- Kein separater MCP-Server für GitHub
- Kein Fork-Management
- Keine CI/CD-Pipeline außerhalb SkillWeave

## Dependencies
- Baut auf bestehendem `src/skillweave/github_integration/` auf
- Baut auf `src/skillweave/release/readiness.py` auf
- Erfordert `.skillweave/tracking-log/` (existiert aus Init 05)
- GitHub Action erfordert `action.yml` im Repo-Root

## Definition of Success
- GitHub Action ist im Marketplace veröffentlicht
- Issues ↔ Tracking-Log Sync funktioniert bidirektional
- Release-Validation läuft als automatisierter Check
- Bundle-Struktur wird bei PRs validiert
- GitHub App ist als Option dokumentiert (nicht implementiert)
