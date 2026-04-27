# v0.7.0: skillweave-discovery — Eigenständiger Discovery-Skill

**Promptchain-Typ**: `plan` — Research, Analyse, Framing (analog zu generate, aber auf Erkenntnisse statt Sequenzen fokussiert)
**Promptchain-Modus**: Ralph Loop für tiefgehende Discovery, REX für schnelle Problemvalidierung

## Problem

Discovery-Funktionalität (Research, Empathy, Problemvalidierung) ist in `skillweave-blueprint` eingebaut — aber die Discovery-Phase ist optional und sollte auch alleinstehend nutzbar sein. Die 11 Prompts in `.skillweave/prompts/discovery/` und 6 Templates in `.skillweave/templates/discovery/` sind vorhanden, aber ohne Skill unsichtbar.

## SKILL.md-Struktur

```yaml
---
name: skillweave-discovery
description: Discovery-Phase — Problemdefinition, User Research, Empathy Mapping und Opportunity Validation als eigenständiger Skill.
argument-hint: topic="[topic]" domain="[domain]" mode="[quick|deep]"
---
```

### Usage

```
/skillweave-discovery                                            # Interaktive Discovery-Session
/skillweave-discovery topic="User retention" domain="saas"       # Gezielte Discovery
/skillweave-discovery mode="quick" topic="Bug prioritization"    # Schnelle Problemvalidierung
/skillweave-discovery mode="deep" domain="enterprise"            # Tiefgehende Research-Phase
```

### Parameters

- `topic` (optional): Problem oder Opportunity, die untersucht werden soll
- `domain` (optional): Domänenkontext (saas, enterprise, mobile, etc.)
- `mode` (optional): `quick` (1-2 Prompts, 30min) oder `deep` (alle 11 Prompts, 2-4h). Default: `deep`

### Phases

1. **Empathy** — User Research, Stakeholder-Mapping, Problem-Kontext (Prompts: empathy-map, user-persona, stakeholder-map)
2. **Research** — Marktanalyse, Wettbewerbs-Recherche, Opportunity-Sizing (Prompts: market-analysis, competitive-landscape)
3. **Framing** — Problem Statement, Hypothesis-Framework, Decision Record (Prompts: problem-statement, hypothesis-framework)
4. **Output** — Discovery Report mit Go/No-Go-Entscheidung

### Output

```
# Discovery Report
## Problem Statement
[validiertes Problem]

## Research Findings
- Marktgröße: X
- Wettbewerber: Y
- Opportunity: Z

## Assumptions (bewertet)
| Annahme | Risiko | Validierungs-Status |
|---------|--------|---------------------|

## Decision
[Go / No-Go / Needs more research]
```

### capability.yaml

```yaml
kind: skill
name: skillweave-discovery
version: 0.7.0
description: Discovery-Phase — Problemdefinition, User Research, Empathy Mapping und Opportunity Validation
author: SkillWeave Team
license: MIT
owner: typelicious
frameworks:
  - opencode-command
  - claude-code
  - gemini-cli
keywords:
  - discovery
  - research
  - empathy
  - problem-validation
```

### Referenzen

- `.skillweave/prompts/discovery/` — 11 Prompts (empathy, research, framing, iteration)
- `.skillweave/templates/discovery/` — 6 Artifact-Templates
- `.skillweave/lib/ideation.py` — Ideation-Modul
- `.skillweave/lib/assumptions.py` — Assumption-Tracking

### Integration mit Blueprint

- Blueprint erkennt ob Discovery bereits durchgeführt (`.skillweave/prds/` oder Discovery Report vorhanden)
- Wenn ja: Überspringe Discovery, starte bei Blueprint
- Discovery-Output (Problem Statement, Research) wird automatisch in Blueprint-Kontext übernommen

## Tasks

| ID | Title | Deps | Typ | Sequence-Type |
|----|-------|------|-----|---------------|
| DSC-001 | SKILL.md für discovery erstellen | — | content | plan |
| DSC-002 | capability.yaml erstellen | DSC-001 | config | plan |
| DSC-003 | Discovery-Prompts als Skill-Commands dokumentieren | DSC-001 | content | plan |
| DSC-004 | Blueprint-Integration (Discovery-Erkennung) dokumentieren | DSC-001 | content | plan |
| DSC-005 | Tests: Prompt-Zugriff, Output-Format, Blueprint-Bridge (8 Tests) | DSC-003 | test | plan |
