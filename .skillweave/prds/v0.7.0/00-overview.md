# SkillWeave v0.7.0 — Skill Suite Expansion & Bundle Integration

## Executive Summary

SkillWeave v0.6.0 implemented the **backend code** for all 6 initiatives but delivered **zero new agent-facing skills**. The lifecycle model has 7 phases but only 4 skills exist to cover them — leaving Launch, Post-Release, Discovery, and Design as empty shells or buried functionality. The bundle system in `.skillweave/lifecycle/bundles.yaml` is dead configuration: no skill reads it, no command exposes it, and no user ever sees a bundle recommendation.

**v0.7.0 closes this gap.** Every lifecycle phase gets its own agent skill (`/skillweave-*`), the bundle system becomes an active navigator, and two cross-cutting skills (repo-health, observe) complete the toolset.

## Current State (v0.6.0)

| Phase | Has Skill? | Has Code? | Sichtbar als `/skillweave-*`? |
|-------|-----------|-----------|-------------------------------|
| Discovery | Nein (in blueprint eingebaut) | `.skillweave/prompts/discovery/` | ❌ |
| Blueprint | ✅ skillweave-blueprint | `src/skillweave/` | ✅ |
| Design | Nein (frontend-design existiert extern) | `.skillweave/lenses/` | ❌ |
| Build | ✅ promptchain-execute + releasechain | `src/skillweave/execution/` | ✅ |
| Release | ✅ (in releasechain) | `src/skillweave/release/` | ✅ (teilweise) |
| Launch | Stub (54 Zeilen, keine Referenzen) | `skills/launch/SKILL.md` | ⚠️ rudimentär |
| Post-Release | ❌ | ❌ | ❌ |

## Ziel-Architektur (v0.7.0)

```
skillweave (Einstiegs-Command)
  │
  ├── /skillweave-lifecycle          # Bundle-Auswahl, Phasen-Navigation, Entry-Detection
  ├── /skillweave-discovery           # Discovery: Research, Empathy, Problemvalidierung
  ├── /skillweave-blueprint           # PRD-Erstellung (bestehend, bleibt unverändert)
  ├── /skillweave-design              # Design-Thinking Lens, UX-Prinzipien, Tokens
  ├── /skillweave-promptchain-generate# Prompt-Sequenzen (bestehend)
  ├── /skillweave-promptchain-validate# Prompt-Validierung (bestehend)
  ├── /skillweave-promptchain-execute # Ausführung (bestehend, type: orchestration)
  ├── /skillweave-releasechain        # Release Pipeline (bestehend)
  ├── /skillweave-launch              # Launch: Deployment, Communication, Go-Live
  ├── /skillweave-post-release        # Post-Release: Monitoring, Retro, Iteration
  ├── /skillweave-repo-health         # Repo Assessment, Cleanup, Hygiene
  └── /skillweave-observe             # Reports, Metriken, Execution Memory
```

## Bundle-System (aktiviert)

Die 5 Bundles aus `bundles.yaml` werden durch `/skillweave-lifecycle` aktiv vorgeschlagen:

1. **Full Lifecycle** — discovery + blueprint + design + build + release + launch + post-release
2. **Discovery to Blueprint** — discovery + blueprint (1-3 Tage)
3. **Design and Build** — design + build (2-5 Tage)
4. **Release and Launch** — release + launch (1-2 Tage)
5. **Post-Release Improvement** — post-release + blueprint + build (2-5 Tage)

**Neu**: Der lifecycle-Skill erkennt die aktuelle Phase und empfiehlt das passende Bundle inkl. Confidence-Score.

## Neue Skills im Detail

### 1. skillweave-lifecycle (NEU)
- **Typ**: Navigation / Meta
- **Phase**: Phase-agnostisch (immer verfügbar)
- **Aufgabe**: Entry-Point-Detection, Bundle-Auswahl, Phasen-Status anzeigen, Nächste-Schritte-Empfehlung
- **Commands**: `/skillweave-lifecycle status`, `/skillweave-lifecycle recommend`, `/skillweave-lifecycle switch [bundle]`
- **Backend**: Nutzt existierende `phase_detection.py`, `workflow_recommendation.py`, `lifecycle_integration.py`
- **Referenzen**: `.skillweave/lifecycle/phases.yaml`, `.skillweave/lifecycle/bundles.yaml`

### 2. skillweave-discovery (NEU — aus Blueprint extrahiert)
- **Typ**: Plan / Research
- **Phase**: Discovery (order 1)
- **Aufgabe**: Problemdefinition, User Research, Empathy Mapping, Opportunity Validation
- **Prompts**: Nutzt existierende `.skillweave/prompts/discovery/` (11 Prompts)
- **Templates**: Nutzt existierende `.skillweave/templates/discovery/` (6 Artifakte)
- **Output**: Discovery Report, Problem Statement, Decision Record

### 3. skillweave-design (NEU — Design-Thinking als Skill)
- **Typ**: Plan / Design
- **Phase**: Design (order 3)
- **Aufgabe**: Design-Thinking Lens anwenden, UX-Prinzipien durchsetzen, Design-Tokens extrahieren
- **Backend**: Nutzt `design_thinking.py`, `.skillweave/lenses/design-thinking.yaml`
- **Integration**: Kann `frontend-design` als externen Skill referenzieren für UI-Generierung

### 4. skillweave-launch (ERWEITERT)
- **Typ**: Build / Operation
- **Phase**: Launch (order 6)
- **Aufgabe**: Deployment-Koordination, User Communication, Go-Live, Metrics-Baseline
- **Backend**: Existiert als 54-zeiliger Stub — wird vollständig implementiert
- **Referenzen**: `.github/workflows/` für Deployment-Actions

### 5. skillweave-post-release (NEU)
- **Typ**: Plan / Analysis
- **Phase**: Post-Release (order 7)
- **Aufgabe**: Monitoring, Feedback-Sammlung, Retrospektive, Iterationsplanung
- **Output**: Post-Mortem Report, Feedback-Kategorisierung, Next-Iteration-Backlog

### 6. skillweave-repo-health (NEU — aus Init 04)
- **Typ**: Utility
- **Phase**: Phase-agnostisch (jederzeit ausführbar)
- **Aufgabe**: Repo Inventory, Dead-Code-Erkennung, Archive-Manager, Duplikat-Prüfung, Hygiene-Report
- **Backend**: Nutzt bzw. erweitert Code aus Init 04 (inventory scanner, classification, archive manager)

### 7. skillweave-observe (NEU — aus Init 05 Observation Layer)
- **Typ**: Utility / Analysis
- **Phase**: Phase-agnostisch (meist Build/Release)
- **Aufgabe**: Execution Reports, Timing-Analyse, Event-Logs durchsuchen, Memory-Drawer einsehen
- **Backend**: Nutzt `src/skillweave/observation/` (event_logger, timing, report_generator) und `execution_memory.py`

## Scope & Out of Scope

### In Scope (v0.7.0)
- 7 neue/erweiterte Skills als vollständige SKILL.md + capability.yaml
- Bundle-Navigator in `/skillweave-lifecycle`
- Aktualisierung von `phases.yaml` und `bundles.yaml`
- PRD-JSONs für alle 7 neuen Skills mit task lists
- Installer-Update: 12 statt 6 Skills

### Out of Scope (v0.7.0)
- Keine Änderung an bestehenden Skills (blueprint, generate, validate, execute, releasechain)
- Keine Änderung an `src/skillweave/` Backend-Code (wiederverwendung existierender Module)
- Kein GitHub App Entwicklung (bleibt deferriert)
- Keine separaten Repos (alle Skills im SkillWeave-Hauptrepo)

## Timeline & Abhängigkeiten

| Schritt | Abhängigkeit | Geschätzt |
|---------|-------------|-----------|
| 1. lifecycle SKILL.md + capability.yaml | phases.yaml, bundles.yaml (existieren) | 2h |
| 2. discovery SKILL.md + capability.yaml | discovery prompts (existieren) | 2h |
| 3. design SKILL.md + capability.yaml | design_thinking.py, lenses (existieren) | 1.5h |
| 4. launch SKILL.md (vollständig) | release-Workflows (existieren) | 2h |
| 5. post-release SKILL.md + capability.yaml | — | 2h |
| 6. repo-health SKILL.md + capability.yaml | Init 04 Code (existiert) | 2h |
| 7. observe SKILL.md + capability.yaml | observation/, execution_memory (existieren) | 1.5h |
| 8. phases.yaml + bundles.yaml update | alle neuen Skills | 1h |
| 9. Installer-Update | alle SKILL.md | 1h |
| 10. Tests + Validierung | alle Objekte | 2h |

**Gesamt: ~17 Stunden** (ralph_attended, 6-8 Batches)

## Risiken & Annahmen

- **Risiko**: Bestehende Skills (blueprint, execute, releasechain) könnten Discovery/Launch-Funktionalität duplizieren.
  - **Mitigation**: Extraction statt Kopie — blueprint verweist auf discovery für Research-Phase.
- **Risiko**: post-release und observe könnten überlappen.
  - **Mitigation**: observe = Rohdaten + Reports, post-release = menschliche Retro + Entscheidungen.
- **Annahme**: Alle 11 discovery prompts sind qualitativ ausreichend für einen eigenständigen Skill.
- **Annahme**: Der Bundle-Navigator kann als reine SKILL.md + Verweis auf lifecycle_integration.py existieren (kein neuer Python-Code nötig).
