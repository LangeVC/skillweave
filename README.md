# SkillWeave

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.0-blue)](https://github.com/typelicious/skillweave/releases/tag/v0.3.0)
[![Python](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-passing-green)](tests/)
[![Skills](https://img.shields.io/badge/skills-4%20commands-blue)](skills/)
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

SkillWeave v0.3.0+ provides separate skill directories for each command with direct `/skillweave-*` prefixes for faster access.

### Recommended: Automated Installation (All Agents)

Use the installer script to automatically install skills to all detected AI agent directories:

```bash
# Clone the repository
git clone https://github.com/typelicious/skillweave.git
cd skillweave

# Run the multi-agent installer
./scripts/install-skills.sh
```

The installer will:
1. Detect all AI agent skill directories on your system
2. Install all SkillWeave skills as symlinks for easy updates
3. Create directories for agents that don't exist yet
4. Provide a summary of installed skills

### Manual Installation (Individual Agents)

If you prefer manual installation or want to install to specific agents:

```bash
# Clone the repository
git clone https://github.com/typelicious/skillweave.git

# Install individual skills to any agent directory
# Replace ~/.config/opencode/skills with your agent's skill directory

# Generate command
cp -r skillweave/skills/skillweave-promptchain-generate ~/.config/opencode/skills/

# Validate command  
cp -r skillweave/skills/skillweave-promptchain-validate ~/.config/opencode/skills/

# Execute command
cp -r skillweave/skills/skillweave-promptchain-execute ~/.config/opencode/skills/

# Legacy skill (optional, for compatibility)
cp -r skillweave/skills/prompt-chain ~/.config/opencode/skills/
```

### Common Agent Skill Directories

- **Opencode**: `~/.config/opencode/skills/`
- **Claude Code**: `~/.config/claude-code/skills/`
- **Codex**: `~/.config/codex/skills/`
- **Gemini CLI**: `~/.config/gemini-cli/skills/`
- **Antigravity**: `~/.config/antigravity/skills/`
- **OpenClaw**: `~/.config/openclaw/skills/`
- **Aider**: `~/.config/aider/skills/`
- **Windsurf**: `~/.config/windsurf/skills/`

### Using the Skills

Direct commands without `/load`:
- `/skillweave-promptchain-generate topic="[topic]" domain="[domain]"`
- `/skillweave-promptchain-validate sequence="[sequence]"`
- `/skillweave-promptchain-execute sequence="[sequence]" inputs="[JSON]"`

**Examples:**
```
/skillweave-promptchain-generate topic="Wellness business evaluation" domain="wellness"
/skillweave-promptchain-validate sequence="[paste your prompt sequence here]"
/skillweave-promptchain-execute sequence="[valid sequence]" inputs='{"business_idea": "Yoga studio"}'
```

### Legacy: prompt-chain (v0.1.0)

The original `prompt-chain` skill remains available for compatibility:

```bash
cp -r skillweave/skills/prompt-chain ~/.config/opencode/skills/
```

Usage with `/load`:
```
/load prompt-chain
/generate topic="Wellness business evaluation" domain="wellness"
```

---

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
