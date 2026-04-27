# v0.7.0: skillweave-design — Design-Thinking als eigenständiger Skill

**Promptchain-Typ**: `mixed` — Analyse (validate) + Generierung (generate) von Design-Tokens und Evaluation
**Promptchain-Modus**: Ralph Loop für Design-Evaluation, REX für Token-Extraktion

## Problem

Die Design-Thinking-Lens existiert als `.skillweave/lenses/design-thinking.yaml` und `design_thinking.py` — aber nur als passiver Filter, nicht als aktiver Skill. Die Design-Phase ist in `phases.yaml` definiert aber ohne zugehörigen Skill.

## SKILL.md-Struktur

```yaml
---
name: skillweave-design
description: Design-Phase — Design-Thinking-Lens anwenden, UX-Prinzipien durchsetzen, Design-Tokens extrahieren und Designs evaluieren.
argument-hint: command="[brief|lens|tokens|evaluate]" input="[design-brief-or-path]"
---
```

### Usage

```
/skillweave-design                                               # Interaktive Design-Session
/skillweave-design command="brief" input="..."                   # Design-Brief analysieren
/skillweave-design command="lens"                                # Design-Thinking-Lens anzeigen
/skillweave-design command="tokens"                              # Design-Tokens extrahieren
/skillweave-design command="evaluate" input="..."                # Bestehendes Design evaluieren
```

### Parameters

- `command` (optional): `brief`, `lens`, `tokens`, `evaluate` (Default: interaktiv)
- `input` (optional): Design-Brief, Pfad zu Design-Artefakten oder zu evaluierendes Element

### Funktionsweise

1. **Lens-Anwendung**: Wendet 6 Workshop-Regeln (Quantity over Quality, Defer Judgment, Embrace Wild Ideas, Fail Fast, Show Don't Tell, Build on Ideas) auf Design-Inputs an
2. **UX-Prinzipien**: 5 Prinzipien (Value>=Noise, Scan Before Read, Hierarchy of Needs, Progressive Disclosure, Recognition over Recall) als Check-Format
3. **Token-Extraktion**: Liest Global Colors + Typography (über design_thinking.py + optional Elementify)
4. **Design-Evaluation**: Prüft bestehende Designs gegen Lens + Prinzipien, gibt strukturierten Report

### Output (evaluate)

```
# Design Evaluation Report

## Lens-Check
| Regel | Status | Hinweis |
|-------|--------|---------|

## UX-Prinzipien
| Prinzip | Status | Hinweis |
|---------|--------|---------|

## Design-Tokens
- Primary: #...
- Secondary: #...
- Font: Inter 400/700
```

### capability.yaml

```yaml
kind: skill
name: skillweave-design
version: 0.7.0
description: Design-Phase — Design-Thinking-Lens, UX-Evaluation, Design-Token-Extraktion
author: SkillWeave Team
license: MIT
owner: typelicious
frameworks:
  - opencode-command
  - claude-code
  - gemini-cli
keywords:
  - design
  - design-thinking
  - ux
  - design-tokens
```

### Referenzen

- `src/skillweave/design_thinking.py` — Lens-Logik
- `.skillweave/lenses/design-thinking.yaml` — Regeldefinitionen
- `frontend-design` (externer Skill, optional)

## Tasks

| ID | Title | Deps | Typ | Sequence-Type |
|----|-------|------|-----|---------------|
| DES-001 | SKILL.md für design erstellen | — | content | mixed |
| DES-002 | capability.yaml erstellen | DES-001 | config | plan |
| DES-003 | Design-Thinking-Lens als Skill-Commands dokumentieren | DES-001 | content | plan |
| DES-004 | Design-Token-Extraktion als Command dokumentieren | DES-001 | content | plan |
| DES-005 | Tests: Lens-Anwendung, Evaluation, Token-Extraktion (8 Tests) | DES-003 | test | plan |
