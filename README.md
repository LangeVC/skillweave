# SkillWeave

Standardized prompt sequences for **generate**, **validate**, and **execute**.

SkillWeave is a modular framework for building, validating, and running structured prompt sequences instead of relying on large monolithic prompts.

## Why SkillWeave exists

Large mega-prompts are expensive, hard to maintain, and often unreliable in real execution.
SkillWeave takes a different approach:

- small modular skills
- explicit prompt-sequence specifications
- validation before execution
- structured orchestration
- clear usage notes such as web research, citations, and fallback behavior

## Core modes

- **generate** — create a standardized prompt sequence from a concrete need
- **validate** — review and improve an existing prompt sequence
- **execute** — run a valid prompt sequence step by step

## Repository structure

- `skills/prompt-chain/` — the first SkillWeave skill
- `docs/` — format, execution model, architecture, roadmap
- `examples/` — example prompt sequences
- `templates/` — reusable templates
- `schemas/` — JSON schemas for validation
- `src/skillweave/` — runtime code
- `tests/` — initial tests

## Quick start

1. Read `skills/prompt-chain/SKILL.md`
2. Read `docs/prompt-sequence-spec.md`
3. Open an example from `examples/`
4. Validate a sequence
5. Execute a sequence step by step

## MVP focus

The current MVP focuses on:

- one strong core skill
- one standardized prompt-sequence format
- one lightweight validator
- one strict sequential orchestrator

## Roadmap

Planned expansions include:

- richer validation
- branching and loops
- hosted execution
- subscription-grade service layer
- private sequence libraries
- analytics and evaluation

## License

MIT
