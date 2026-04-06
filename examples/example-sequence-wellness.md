# Prompt-Sequence Specification

## Metadata
- title: Wellness Business Evaluation
- version: 0.1
- language: de
- domain: wellness
- intent: generate
- complexity: medium

## Objective
Erstelle eine strukturierte Prompt-Abfolge zur Bewertung einer Wellness-Geschäftsidee.

## Success Criteria
- klares Konzeptbild
- priorisierte Zielgruppen
- Risiken und Chancen
- klare nächste Schritte

## Assumptions
- Idee ist in frühem Stadium
- Standort ist Berlin

## Usage Notes
- web_research: required
- citations: required
- intermediate_validation: required
- ask_for_clarification: only_if_blocked
- execution_mode: strict_sequential
- fallback_behavior: stop_and_report
- output_style: standard

## Inputs Required
- Geschäftsidee
- Zielregion
- Preisniveau

## Outputs Required
- strukturierte Prompt-Abfolge
- priorisierte Empfehlungen

## Sequence Steps

### Step 1
- id: step-01
- name: Konzeptkern schärfen
- purpose: Klarheit über Konzeptvarianten schaffen
- depends_on: []
- instructions: |
    Analysiere die Geschäftsidee und leite drei klar unterscheidbare Konzeptvarianten ab.
- expected_output:
  - 3 Konzeptvarianten
  - erste Empfehlung
- validation:
  - Varianten unterscheiden sich klar
- completion_rule:
  - bevorzugte Richtung benannt

### Step 2
- id: step-02
- name: Zielgruppen definieren
- purpose: Zielgruppen und Personas bestimmen
- depends_on: [step-01]
- instructions: |
    Definiere Kernzielgruppen für die bevorzugte Variante.
- expected_output:
  - Zielgruppen
  - Personas
- validation:
  - passen zum Preisniveau
- completion_rule:
  - Kernzielgruppe benannt

## Final Assembly
Fasse die Ergebnisse in einer priorisierten Empfehlung zusammen.

## Validation Rules
- Quellenpflicht bei Marktfragen
- Risiken klar benennen

## Failure Handling
Bei fehlenden Daten Annahmen kennzeichnen und Grenzen offenlegen.

## Final Deliverable Format
Markdown mit H2/H3-Struktur.
