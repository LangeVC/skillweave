# Prompt-Sequence Specification

## Metadata
- title: Strategy Sequence
- version: 0.1
- language: de
- domain: strategy
- intent: validate
- complexity: medium
- mode: plan

## Objective
Prüfe eine Strategie-Idee in einer klaren Schrittlogik.

## Success Criteria
- klare Hypothesen
- Risiken
- Handlungsempfehlung

## Assumptions
- frühe Produktphase

## Usage Notes
- web_research: optional
- citations: optional
- intermediate_validation: required
- ask_for_clarification: allowed
- execution_mode: strict_sequential
- fallback_behavior: retry_once
- output_style: standard

## Inputs Required
- Strategie-Briefing

## Outputs Required
- validierte Strategie-Abfolge

## Sequence Steps

### Step 1
- id: step-01
- name: Hypothesen
- purpose: Hypothesen extrahieren
- depends_on: []
- instructions: |
    Extrahiere die Kernhypothesen.
- expected_output:
  - Hypothesenliste
- validation:
  - nicht redundant
- completion_rule:
  - mindestens 3 Hypothesen

## Final Assembly
Fasse Befunde und Empfehlung zusammen.

## Validation Rules
- Lücken markieren

## Failure Handling
Bei fehlenden Inputs offene Punkte benennen.

## Final Deliverable Format
Markdown.
