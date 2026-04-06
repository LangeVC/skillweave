# SkillWeave

**Standardized prompt sequences for generate, validate, and execute.**

SkillWeave helps you turn complex AI work into structured, reusable prompt sequences instead of fragile mega-prompts.

It is designed for builders who want:
- clearer multi-step AI workflows
- reusable sequence formats
- explicit usage rules
- validation before execution
- a path from prompt craft to durable agent skills

---

## What SkillWeave is

SkillWeave is a modular framework and product direction for working with **standardized prompt sequences**.

Instead of stuffing everything into one giant prompt, SkillWeave breaks work into:
- a clear sequence specification
- explicit usage notes
- validation rules
- step-by-step execution logic
- final assembly of results

The MVP currently focuses on three core modes:

- **generate**  
  Create a prompt sequence from a concrete need

- **validate**  
  Review and improve an existing sequence

- **execute**  
  Run a valid sequence step by step

---

## Why SkillWeave exists

Most prompt workflows break for predictable reasons:
- they become too large
- they mix planning and execution
- they hide assumptions
- they are hard to validate
- they are difficult to reuse across teams and runtimes

SkillWeave exists to make prompt workflows:
- more modular
- more explicit
- easier to maintain
- easier to evaluate
- easier to productize

---

## Core idea

A SkillWeave workflow is not a mega-prompt.

It is a **prompt sequence** with a defined structure:

1. Metadata
2. Objective
3. Success Criteria
4. Assumptions
5. Usage Notes
6. Inputs Required
7. Outputs Required
8. Sequence Steps
9. Final Assembly
10. Validation Rules
11. Failure Handling
12. Final Deliverable Format

This makes the workflow:
- readable by humans
- structured enough for orchestration
- easier to validate
- easier to execute consistently

---

## Who SkillWeave is for

SkillWeave is for:
- AI builders
- agent designers
- prompt engineers
- product teams
- consultants and operators
- teams creating reusable workflows across domains

Typical use cases:
- research workflows
- strategy workflows
- content systems
- analysis pipelines
- domain-specific business planning
- verticalized agent skills

---

## Repository structure

```text
skillweave/
├── docs/
├── examples/
├── schemas/
├── skills/
│   └── prompt-chain/
├── src/
├── templates/
└── tests/
```

Start here:
- `skills/prompt-chain/SKILL.md`
- `docs/prompt-sequence-spec.md`
- `examples/`

---

## Current MVP

The current MVP includes:
- one core skill: `prompt-chain`
- a standardized prompt-sequence format
- lightweight schemas
- initial parser / validator / orchestrator structure
- first examples and templates

MVP focus:
- keep the model small
- keep the format explicit
- keep execution strict
- avoid unnecessary complexity

---

## What comes next

Planned next steps:
- richer validation logic
- stronger execution model
- branching and loops
- hosted execution
- team libraries
- subscription-grade online service
- private and public sequence directories

---

## Vision

SkillWeave aims to become a durable layer between:
- prompt engineering
- skill design
- agent orchestration
- reusable organizational knowledge

The long-term goal is simple:

**turn prompt sequences into a portable, validated, execution-ready asset.**

---

## Status

Early MVP / architecture phase.

If this direction is relevant to your work, the best starting point is:
1. inspect the `prompt-chain` skill
2. review the sequence format
3. test examples
4. adapt the pattern to your own workflow domain

---

## License

MIT
