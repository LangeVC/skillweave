# SkillWeave

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-passing-green)](tests/)
[![Skill](https://img.shields.io/badge/skill-prompt--chain-blue)](skills/prompt-chain/SKILL.md)
[![Status](https://img.shields.io/badge/status-early%20MVP-yellow)](https://github.com/typelicious/skillweave)
[![Repo Safety](https://img.shields.io/badge/repo%20safety-checked-green.svg)](SECURITY.md)

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

## Multi-Agent Quickstart

SkillWeave's `prompt-chain` skill can be installed in various AI agent tools to enable structured prompt sequence workflows. Below are installation instructions for popular multi-agent platforms:

### Opencode
```bash
# Clone the repository
git clone https://github.com/typelicious/skillweave.git

# Copy the skill to opencode skills directory
cp -r skillweave/skills/prompt-chain ~/.config/opencode/skills/
```

### Claude Code
```bash
# Copy skill to Claude Code skills directory (typical location)
cp -r skillweave/skills/prompt-chain ~/.config/claude-code/skills/
```
*Note: Check Claude Code documentation for exact skill path.*

### Codex
```bash
# Copy skill to Codex skills directory
cp -r skillweave/skills/prompt-chain ~/.config/codex/skills/
```

### Gemini CLI
```bash
# Copy skill to Gemini CLI skills directory
cp -r skillweave/skills/prompt-chain ~/.config/gemini-cli/skills/
```

### Antigravity
```bash
# Copy skill to Antigravity skills directory
cp -r skillweave/skills/prompt-chain ~/.config/antigravity/skills/
```

### OpenClaw
```bash
# Copy skill to OpenClaw skills directory
cp -r skillweave/skills/prompt-chain ~/.config/openclaw/skills/
```

### General Installation
For any agent tool that supports skills, copy the `prompt-chain` folder to the tool's skills directory. The skill will be automatically detected on next launch.

### Using the Skill
Once installed, you can invoke the skill with:
- `generate`: Create a new prompt sequence
- `validate`: Review and improve an existing sequence  
- `execute`: Run a validated sequence step by step

Example usage in Opencode:
```
/load prompt-chain
/generate topic="Wellness business evaluation" domain="wellness"
```

---

## License

MIT
