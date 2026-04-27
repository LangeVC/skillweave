# v0.7.0: skillweave-repo-health — Repo Assessment & Cleanup

**Promptchain-Typ**: `plan` — Scanning, Klassifikation, Analyse, Empfehlung (analog zu validate)
**Promptchain-Modus**: REX für schnellen Health-Check, Ralph Loop für tiefgehendes Cleanup

## Problem

Initiative 04 (Repo Cleanup) wurde als einmalige Aktion ausgeführt — aber Repo-Hygiene ist ein kontinuierlicher Prozess. Es gibt keinen Skill, um regelmäßig Dead Code zu erkennen, Dateien zu archivieren, Duplikate zu prüfen oder einen Hygiene-Report zu erstellen.

## SKILL.md-Struktur

```yaml
---
name: skillweave-repo-health
description: Repo Assessment, Cleanup und Hygiene — Inventory-Scan, Dead-Code-Erkennung, Archive-Management, Duplikat-Prüfung und Hygiene-Report.
argument-hint: command="[scan|report|classify|archive|duplicates|cleanup|manifest]" path="[path]"
---
```

### Usage

```
/skillweave-repo-health                                          # Interaktiver Health-Check
/skillweave-repo-health command="scan"                           # Vollständigen Inventory-Scan
/skillweave-repo-health command="report"                         # Hygiene-Report generieren
/skillweave-repo-health command="classify" path="src/old/"       # Dateien klassifizieren
/skillweave-repo-health command="archive" path="src/legacy/"     # Nach .skillweave/archive/
/skillweave-repo-health command="duplicates"                     # Duplikate erkennen
/skillweave-repo-health command="cleanup"                        # Cleanup-Vorschläge
/skillweave-repo-health command="manifest"                       # Archive-Manifest anzeigen
```

### Parameters

- `command` (required): `scan`, `report`, `classify`, `archive`, `duplicates`, `cleanup`, `manifest`
- `path` (optional, für classify/archive): Pfad zur Datei oder zum Verzeichnis
- `dry_run` (optional): `true` (Default) — keine tatsächlichen Änderungen, nur Vorschau

### Funktionsweise

1. **Inventory-Scan**: Katalogisiert alle Dateien (Typ, Größe, letzte Änderung, Kategorie)
2. **Klassifikation**: 5 Kategorien (Active Core, Consolidation Candidate, Legacy Valuable, Deprecated, Needs Review)
3. **Duplikat-Erkennung**: Findet identische/similar Dateien (MD5 + Fuzzy-Match für Inhalt)
4. **Archive**: Verschiebt in `.skillweave/archive/` mit Restore-Manifest (JSON)
5. **Cleanup-Vorschläge**: Generiert Vorschläge mit Risikobewertung, erfordert Genehmigung
6. **Hygiene-Report**: Zusammenfassung mit Score (A-F), Trends, konkreten Empfehlungen

### Output (report)

```
# Repo Health Report

Score: B (75/100)

## Inventory
- Total files: 312
- Active Core: 210 (67%)
- Consolidation: 45 (14%)
- Legacy: 30 (10%)
- Deprecated: 27 (9%)

## Duplicates
- 3 Paare gefunden (~2MB Einsparpotential)

## Empfehlungen
1. [P1] src/old/ → archivieren (27 Dateien, seit >6 Monaten unverändert)
2. [P2] Duplikate in src/lib/ → zusammenführen
3. [P3] .skillweave/archive/ → Restore-Manifest prüfen (letztes Cleanup: 2026-01-15)
```

### capability.yaml

```yaml
kind: skill
name: skillweave-repo-health
version: 0.7.0
description: Repo Assessment, Cleanup und Hygiene — Inventory, Dead-Code, Archive, Duplikate, Report
author: SkillWeave Team
license: MIT
owner: typelicious
frameworks:
  - opencode-command
  - claude-code
  - gemini-cli
keywords:
  - repo-health
  - cleanup
  - archive
  - hygiene
  - inventory
```

### Referenzen

- Neues Backend: `src/skillweave/repo_health/scanner.py`, `classifier.py`, `dedup.py`, `archive.py`, `report.py`
- Bestehend: `.skillweave/archive/`, `.skillweave/cleanup/`
- Init-04-Code als Basis (Inventory-Scanner, Klassifikationslogik)

## Tasks

| ID | Title | Deps | Typ | Sequence-Type |
|----|-------|------|-----|---------------|
| REPO-001 | SKILL.md für repo-health erstellen | — | content | plan |
| REPO-002 | capability.yaml erstellen | REPO-001 | config | plan |
| REPO-003 | src/skillweave/repo_health/ Modul (scanner, classifier, dedup, archive, report) | REPO-001 | code | build |
| REPO-004 | Cleanup-Safety (dry_run-Pflicht, Genehmigungs-Logik) | REPO-003 | code | build |
| REPO-005 | Tests: Scan, Klassifikation, Duplikate, Archive roundtrip, Report (12 Tests) | REPO-003..004 | test | test |
