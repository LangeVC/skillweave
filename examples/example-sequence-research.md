# Prompt-Sequence Specification

## Metadata
- title: Research Sequence
- version: 0.1
- language: en
- domain: research
- intent: execute-target-sequence
- complexity: medium

## Objective
Create a structured sequence for a research task.

## Success Criteria
- current sources
- explicit assumptions
- clear synthesis

## Assumptions
- topic may be time-sensitive

## Usage Notes
- web_research: required
- citations: required
- intermediate_validation: optional
- ask_for_clarification: only_if_blocked
- execution_mode: strict_sequential
- fallback_behavior: stop_and_report
- output_style: detailed

## Inputs Required
- research topic

## Outputs Required
- cited synthesis

## Sequence Steps

### Step 1
- id: step-01
- name: Scope
- purpose: define the research scope
- depends_on: []
- instructions: |
    Define the research question and constraints.
- expected_output:
  - research scope
- validation:
  - scope is explicit
- completion_rule:
  - scope written

## Final Assembly
Produce one final synthesis with citations.

## Validation Rules
- cite factual claims

## Failure Handling
Stop and report if reliable sources are unavailable.

## Final Deliverable Format
Markdown report.
