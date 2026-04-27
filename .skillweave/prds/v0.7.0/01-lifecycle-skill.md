# v0.7.0: skillweave-lifecycle — Bundle-Navigator & Phasen-Steuerung

**Promptchain-Typ**: `plan` — Validierung, Zustandsanalyse, Empfehlung (analog zu validate)
**Promptchain-Modus**: passt zu REX (einfache Abfragen) oder Ralph Loop (komplexe Bundle-Analyse)

## Problem

Der Nutzer hat keine Möglichkeit, den Lifecycle-Status zu sehen, ein Bundle auszuwählen oder die nächste Phase zu erfahren. Die Bundles in `bundles.yaml` und die Phasen in `phases.yaml` sind reine Datendeklarationen — kein Skill macht sie zugänglich.

## SKILL.md-Struktur (nach promptchain-Muster)

```yaml
---
name: skillweave-lifecycle
description: Lifecycle-Navigation, Bundle-Auswahl, Phasen-Status und Entry-Point-Detection — der zentrale Einstiegsskill für jede SkillWeave-Session.
argument-hint: command="[status|recommend|switch|phases]" bundle="[id]"
---
```

### Usage

```
/skillweave-lifecycle                                  # Status + Bundle-Empfehlung (Default)
/skillweave-lifecycle command="status"                 # Aktuelle Phase, Bundles, Fortschritt
/skillweave-lifecycle command="recommend"              # Bundle-Empfehlung mit Confidence-Score
/skillweave-lifecycle command="switch" bundle="design-and-build"  # Bundle wechseln
/skillweave-lifecycle command="phases"                 # Alle 7 Phasen mit Status
```

### Mandatory Pre-Flight

Wie alle Skills: `.skillweave/` prüfen, Outputs in `.skillweave/` routen, Git-Isolation sicherstellen.

### Parameters

- `command` (optional): `status`, `recommend`, `switch`, `phases` (Default: kombinierte Ansicht)
- `bundle` (optional, nur mit command="switch"): Bundle-ID aus bundles.yaml

### Output

```
╔══════════════════════════════════════════════════╗
║  SkillWeave Lifecycle Status                     ║
╠══════════════════════════════════════════════════╣
║  Aktuelle Phase: build (confidence: 0.92)        ║
║  Aktives Bundle: design-and-build                ║
║                                                  ║
║  Phasen:                                         ║
║    [1] discovery.. ✅ übersprungen               ║
║    [2] blueprint... ✅ completed                 ║
║    [3] design....... ✅ completed                ║
║    [4] build........ ▶ active                    ║
║    [5] release...... ◻ pending                   ║
║    [6] launch........ ◻ pending                   ║
║    [7] post-release.. ◻ pending                   ║
║                                                  ║
║  Empfohlen: Bundle "Release and Launch"          ║
║  (nach build-Abschluss)                          ║
╚══════════════════════════════════════════════════╝
```

### capability.yaml

```yaml
kind: skill
name: skillweave-lifecycle
version: 0.7.0
description: Lifecycle-Navigation, Bundle-Auswahl, Phasen-Status und Entry-Point-Detection
author: SkillWeave Team
license: MIT
owner: typelicious
frameworks:
  - opencode-command
  - claude-code
  - gemini-cli
keywords:
  - lifecycle
  - navigation
  - bundle
  - phase
  - detection
```

### Referenzen

- `references/phases-reference.md` — Auflistung aller 7 Phasen mit Entry/Exit-Conditions
- `references/bundles-reference.md` — Auflistung aller 5 Bundles mit Empfehlungskriterien
- Backend: `src/skillweave/phase_detection.py`, `src/skillweave/workflow_recommendation.py`, `src/skillweave/lifecycle_integration.py`

### Funktionsweise

1. **Entry-Point-Detection**: Scannt Projekt nach Artefakten (PRD → blueprint, Code → build, Tag → release)
2. **Bundle-Empfehlung**: Zeigt 1-3 passende Bundles mit Confidence-Score und Begründung
3. **Phasen-Status**: Markiert abgeschlossene, aktive und ausstehende Phasen
4. **Bundle-Switch**: Setzt `active_bundle` in `.skillweave/config.yaml`

### Integration

- Wird von Installer als erster Skill installiert (Einstiegspunkt)
- Von jedem anderen Skill als "zurück zum Lifecycle" referenzierbar
- Nutzt Config, die von `lifecycle_integration.py` geschrieben wurde

## Tasks (prd.json)

| ID | Title | Deps | Typ | Sequence-Type |
|----|-------|------|-----|---------------|
| LIF-001 | SKILL.md für lifecycle erstellen | — | content | plan |
| LIF-002 | capability.yaml erstellen | LIF-001 | config | plan |
| LIF-003 | references/phases-reference.md | LIF-001 | doc | plan |
| LIF-004 | references/bundles-reference.md | LIF-001 | doc | plan |
| LIF-005 | Tests: lifecycle-Befehle, Bundle-Vorschlag, Phasen-Status (10 Tests) | LIF-001..003 | test | plan |
