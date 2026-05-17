# Progressive Disclosure Wizard (Layer 0)

5-question guided entry for non-technical users. Maps intent to the correct skill without requiring lifecycle knowledge.

## Design Principles

- **Simple language**: No jargon, no technical terms
- **5 questions max**: Never more, often fewer (early exit on clear intent)
- **Bilingual**: German and English (detect from first response)
- **Forgiving**: Accepts fuzzy answers, maps to closest intent
- **Persona-optimized**: Works for 79yo grandmother (P2) through Power User (P0)

## Flow Diagram

```
┌─────────────────────────────────────────┐
│ Q1: Was möchtest du tun?                │
│     What would you like to do?          │
├─────────────────────────────────────────┤
│ A) Neue Idee entwickeln (New idea)      │ → Discovery
│ B) Projekt weiterarbeiten (Continue)    │ → Build
│ C) Etwas testen/prüfen (Test/check)    │ → Test
│ D) Meinung einholen (Get opinion)      │ → Council
│ E) Veröffentlichen (Publish/Release)   │ → Release
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Q2: Context (varies by Q1 answer)       │
├─────────────────────────────────────────┤
│ If A: "Worum geht es?" (What's it      │
│        about?) → free text              │
│ If B: "Welches Projekt?" (Which         │
│        project?) → detect from .skillweave │
│ If C: "Was soll getestet werden?"       │
│        (What to test?) → code/council   │
│ If D: "Welche Frage?" (What question?)  │
│        → topic for council              │
│ If E: "Ist alles fertig?" (All done?)   │
│        → yes/no                         │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Q3: Komplexität (Complexity)            │
├─────────────────────────────────────────┤
│ A) Schnelle Sache (Quick thing) → rex   │
│ B) Mittleres Projekt (Medium) → attend  │
│ C) Großes Vorhaben (Large) → overnight  │
│ [Skip if obvious from context]          │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Q4: Sprache (Language)                  │
│ [Auto-detected, only ask if unclear]    │
├─────────────────────────────────────────┤
│ A) Deutsch                              │
│ B) English                              │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Q5: Bestätigung (Confirmation)          │
├─────────────────────────────────────────┤
│ "Ich starte [skill] für [topic].        │
│  Einverstanden?" (I'll start [skill]    │
│  for [topic]. Agreed?)                  │
│                                         │
│ → Ja (Yes) → Launch skill              │
│ → Nein (No) → Back to Q1               │
└─────────────────────────────────────────┘
```

## Intent → Skill Routing

| Intent (Q1) | Complexity (Q3) | Routed Skill | Parameters |
|-------------|----------------|--------------|------------|
| New idea + Quick | rex | `/skillweave-blueprint` | idea=Q2, complexity="simple" |
| New idea + Medium | attended | `/skillweave-discovery` → `/skillweave-blueprint` | topic=Q2 |
| New idea + Large | overnight | `/skillweave-discovery` | topic=Q2, mode="full" |
| Continue + Quick | rex | `/skillweave-releasechain` | mode="simple" |
| Continue + Medium | attended | `/skillweave-promptchain-execute` | auto-detect sequence |
| Continue + Large | overnight | `/skillweave-promptchain-execute` | mode="overnight" |
| Test | any | `/skillweave test` | level=auto |
| Get opinion | any | `/skillweave-council` | topic=Q2 |
| Release | any | `/skillweave-releasechain` → `/skillweave-launch` | auto |

## Early Exit Rules

- If user types a full sentence describing intent clearly → skip to Q5 (confirmation)
- If `.skillweave/` state unambiguously indicates phase → skip Q2
- If language detected from Q1 response → skip Q4
- If complexity obvious from PRD task count → skip Q3

## Error Recovery

- Unrecognized answer → "Ich habe nicht verstanden. Kannst du es anders formulieren?"
- No .skillweave/ directory → Offer to create one (new project setup)
- Multiple possible intents → Ask clarifying sub-question before Q2

## Example Dialogues

### Grandmother Persona (P2, German)

```
Wizard: Was möchtest du tun?
User:   Ich habe eine Idee für einen Kochblog
Wizard: Schöne Idee! Wie groß soll das werden — 
        schnelle Sache oder größeres Projekt?
User:   Eher klein, zum Ausprobieren
Wizard: Gut! Ich starte den Blueprint für deinen 
        Kochblog. Einverstanden?
User:   Ja
→ Launches: /skillweave-blueprint idea="Kochblog" complexity="simple"
```

### Indie Hacker Persona (P1, English)

```
Wizard: What would you like to do?
User:   Continue working on my SaaS project
Wizard: Found your project "SkillWeave v1.0" with 
        4 tasks in progress. Continue building?
User:   Yes
→ Launches: /skillweave-promptchain-execute (resumes)
```

### Power User (P0) — Early Exit

```
User:   /skillweave start
Wizard: Was möchtest du tun?
User:   Council fragen ob meine API-Architektur sinnvoll ist
→ Detects: intent=council, topic="API-Architektur", language=DE
Wizard: Ich starte den Council zu "API-Architektur". OK?
User:   Ja
→ Launches: /skillweave-council topic="API-Architektur Bewertung"
```
