---
name: skillweave-design
description: "Analyze design briefs, derive UX principles and design tokens, and evaluate implementation quality."
argument-hint: command="[brief|lens|tokens|evaluate]" input="[design-brief-or-path]"
---

# /skillweave-design

> Canonical metadata is English. User-facing artifacts follow the output language setting.

**Design-Thinking-Lens für Frontend-Projekte.** Analysiert Design-Briefs, wendet UX-Prinzipien an, extrahiert Design-Tokens und evaluiert Designs. Mixed-Type Skill — Analyse und Generierung.

## Workshop-Regeln (Skill Logic)

1. **Value ≥ Noise** — Jede Beobachtung muss klaren Nutzen liefern. Rauschen streichen.
2. **Scan Before Read** — Ergebnisse strukturieren für schnelles Erfassen: Hierarchie, Bullets, Tabellen.
3. **Hierarchy of Needs** — Funktionale Anforderungen (Inhalt, Navigation) vor ästhetischen verhandeln.
4. **Progressive Disclosure** — Komplexität schrittweise enthüllen. Basislayer zuerst, Details auf Anfrage.
5. **Recognition Over Recall** — Konsistente Patterns und vertraute UI-Konventionen. Nutzer merken sich nichts.
6. **Error Tolerance** — Fehler als Lernchance. Nie wertend, immer konstruktiv mit konkreten Fixes.

## UX-Prinzipien

1. **Klarheit > Kreativität** — Eindeutige Kommunikation schlägt originelle Gestaltung.
2. **Konsistenz > Konsistenzbruch** — Einheitliche Patterns aufbauen und nur bewusst brechen.
3. **Feedback > Stille** — Jede Aktion braucht sichtbare Reaktion innerhalb von 100ms.
4. **Nähe + Ausrichtung** — Zusammengehöriges gruppieren, alles an definierten Achsen ausrichten.
5. **Weniger ist mehr** — Jedes Element muss Existenz rechtfertigen. Entfernen zuerst.

## Integration mit frontend-design

Dieser Skill ist die Analyse-Ebene für `frontend-design`. Empfohlenes Sequenz-Muster:

1. `skillweave-design command="brief" input="..."` — Brief analysieren
2. `skillweave-design command="tokens" input="..."` — Design-Tokens extrahieren
3. `frontend-design` — Komponenten generieren
4. `skillweave-design command="evaluate" input="..."` — Ergebnis evaluieren

## Commands

| Command | Description |
|---------|-------------|
| `brief` | Design-Brief auf Vollständigkeit, Klarheit, Konsistenz analysieren. Output: Stärken, Lücken, Risiken, Prinzipien-Check |
| `lens` | Skill-Logik (6 Regeln + 5 Prinzipien) auf Design-Input anwenden. Output: bewertete Analyse pro Regel/Prinzip |
| `tokens` | Farben, Typografie und Spacing extrahieren. Output: strukturiertes Token-Set (siehe `references/design-tokens.md`) |
| `evaluate` | Design gegen 5 UX-Prinzipien evaluieren. Output: Scorecard (0–10 pro Prinzip), Gesamtscore, Verbesserungen |

## Usage

Invoke the skill by its name with arguments. The skill is
host-neutral; no executable prefix is required — route it through any host on
any supported transport (Markdown or MCP).

```
skillweave-design command="brief" input="[text-or-path]"
skillweave-design command="tokens" input="[spec-or-path]"
skillweave-design command="evaluate" input="[design-or-path]"
```

`input` akzeptiert Inline-Text oder Pfad zu `.md`/`.txt`/`.yaml`.

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `command` | yes | `brief`, `lens`, `tokens`, `evaluate` |
| `input` | yes | Design-Input als Text oder Dateipfad |
| `detail` | no | `compact` (default) oder `full` |
| `format` | no | Output-Format: `markdown`, `yaml`, `json` |

## Testing

| Test Case | What to Validate |
|-----------|------------------|
| Lens auf Design-Input anwendbar | `command="lens"` produziert Analyse aller 6 Regeln + 5 Prinzipien |
| Evaluation gibt validen Report | `command="evaluate"` gibt Scorecard mit 5 Werten (0–10) und priorisierten Items |
| Token-Extraktion valide | `command="tokens"` gibt Primary, Secondary, Text, Accent + Font-Stack |
| Brief-Analyse vollständig | `command="brief"` deckt Stärken, Lücken, Risiken, Prinzipien-Check ab |
| Detailstufen unterscheidbar | `detail="compact"` vs `detail="full"` liefern unterschiedliche Tiefe |
| Output-Formate wechselbar | `format="yaml"` und `format="json"` produzieren valides YAML/JSON |

## Companion Files

- `references/design-commands.md` — Full function signatures and examples
- `references/design-tokens.md` — Token format specification with elementify integration
