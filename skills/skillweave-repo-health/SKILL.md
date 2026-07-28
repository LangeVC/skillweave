---
name: skillweave-repo-health
description: "Assess repository health, classify files, detect duplicates, and produce safe cleanup plans."
argument-hint: 'command="[scan|report|classify|archive|duplicates|cleanup|manifest]" path="[path]"'
---

# /skillweave-repo-health

> Canonical metadata is English. User-facing artifacts follow the output language setting.

Repo Assessment & Cleanup — Inventory-Scan, 5-Class-Klassifikation, Duplikatserkennung, Archivierung, Hygiene-Report.

## 5-Class-Klassifikation

| Klasse | Bedeutung |
|---|---|
| **Active Core** | Aktiv genutzte Kern-Dateien (src/, tests/, config) |
| **Consolidation** | .gitkeep, readme, Doku — kann zusammengelegt werden |
| **Legacy** | Alte Build-Artefakte, Backup-Dateien, migrations/ |
| **Deprecated** | __pycache__, .DS_Store, node_modules (sollte in .gitignore) |
| **Needs Review** | Nicht klassifizierbar — menschliche Prüfung nötig |

## Commands

| Command | Beschreibung |
|---|---|
| `scan` | Inventory erstellen (alle Dateien + Metadaten) |
| `classify` | 5-Category Klassifikation auf Inventory |
| `duplicates` | Duplikate via MD5/Fuzzy finden |
| `archive` | Pfade nach archive/ verschieben |
| `restore` | Aus Manifest restaurieren |
| `cleanup` | Trocken (default) oder echt ausführen |
| `report` | Hygiene-Score A–F + Empfehlungen |

## Safety

- **`dry_run=true` ist Default** — keine Änderungen ohne Genehmigung
- `cleanup` erfordert explizite `--apply` Flag
- `archive` erstellt immer ein `manifest.json` für Restore
- **3-Sekunden-Regel**: Vor Cleanup wird gewartet + Zusammenfassung angezeigt

## Testing

1. `scan` + `classify` — Inventory korrekt, Klassifikation plausibel
2. `duplicates` — MD5-Exact-Treffer, Fuzzy-Ähnlichkeit
3. `archive` + `restore` — Roundtrip (Datei→archiv→zurück)
4. `report` — Score-Berechnung A–F, alle 5 Klassen repräsentiert

## Usage

```bash
# Scan
opencode skillweave-repo-health command="scan" path="./src"

# Classify + Report
opencode skillweave-repo-health command="classify" path="."
opencode skillweave-repo-health command="report" path="."

# Dry-run cleanup (default)
opencode skillweave-repo-health command="cleanup" path="."

# Archive duplicates
opencode skillweave-repo-health command="duplicates" path="."
opencode skillweave-repo-health command="archive" path="."

# Restore from manifest
opencode skillweave-repo-health command="restore" path="./archive"
```
