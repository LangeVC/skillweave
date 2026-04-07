# SkillWeave

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.5-blue)](https://github.com/typelicious/skillweave/releases/tag/v0.3.5)
[![Python](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-passing-green)](tests/)
[![Skills](https://img.shields.io/badge/skills-5%20commands-blue)](skills/)
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

SkillWeave v0.3.5+ provides separate skill directories for each command with direct `/skillweave-*` prefixes for faster access.

### Recommended: Automated Installation (All Agents)

Use the installer script to automatically install skills to all detected AI agent directories with correct formats for each agent type:

```bash
# Clone the repository
git clone https://github.com/typelicious/skillweave.git
cd skillweave

# Run the multi-agent installer
./scripts/install-skills.sh
```

The installer will:
1. Detect AI agents on your system with correct paths for each agent type
2. Install skills in appropriate format for each agent (single files for Opencode, directories for others)
3. Create symlinks for easy updates
4. Create directories for agents that don't exist yet
5. Provide a summary of installed skills

### Manual Installation (Individual Agents)

If you prefer manual installation or need to install to specific agents:

#### For Opencode (single .md files in commands directory)
```bash
# Clone the repository
git clone https://github.com/typelicious/skillweave.git

# Create commands directory if it doesn't exist
mkdir -p ~/.config/opencode/commands

# Install as single .md files (symlinks recommended for updates)
ln -sf $PWD/skillweave/skills/skillweave-promptchain-generate/SKILL.md ~/.config/opencode/commands/skillweave-promptchain-generate.md
ln -sf $PWD/skillweave/skills/skillweave-promptchain-validate/SKILL.md ~/.config/opencode/commands/skillweave-promptchain-validate.md
ln -sf $PWD/skillweave/skills/skillweave-promptchain-execute/SKILL.md ~/.config/opencode/commands/skillweave-promptchain-execute.md
ln -sf $PWD/skillweave/skills/skillweave-releasechain/SKILL.md ~/.config/opencode/commands/skillweave-releasechain.md

# Legacy skill (optional, requires /load)
ln -sf $PWD/skillweave/skills/prompt-chain/SKILL.md ~/.config/opencode/commands/prompt-chain.md
```

#### For Claude Code, Codex, Antigravity (directory structure)
```bash
# Clone the repository
git clone https://github.com/typelicious/skillweave.git

# Create skills directories
mkdir -p ~/.claude/skills ~/.codex/skills ~/.antigravity/skills

# Install as directory symlinks
ln -sf $PWD/skillweave/skills/skillweave-promptchain-generate ~/.claude/skills/
ln -sf $PWD/skillweave/skills/skillweave-promptchain-validate ~/.claude/skills/
ln -sf $PWD/skillweave/skills/skillweave-promptchain-execute ~/.claude/skills/
ln -sf $PWD/skillweave/skills/prompt-chain ~/.claude/skills/

# Repeat for other agents with their respective paths
```

### Correct Agent Directories

The installer supports these agent paths with correct formats:

| Agent | Type | Path | Format |
|-------|------|------|--------|
| **Opencode** | Single file | `~/.config/opencode/commands/` | `.md` files |
| **Claude Code** | Directory | `~/.claude/skills/` | Directory structure |
| **Codex** | Directory | `~/.codex/skills/` | Directory structure |
| **Gemini CLI** | Directory | `~/.config/gemini-cli/skills/` | Directory structure |
| **Antigravity** | Directory | `~/.antigravity/skills/` | Directory structure |
| **OpenClaw** | Directory | `~/.config/openclaw/skills/` | Directory structure |
| **Aider** | Directory | `~/.config/aider/skills/` | Directory structure |
| **Windsurf** | Directory | `~/.config/windsurf/skills/` | Directory structure |

### Using the Skills

Direct commands without `/load` (for separate skill installations):
- `/skillweave-promptchain-generate topic="[topic]" domain="[domain]"`
- `/skillweave-promptchain-validate sequence="[sequence]"`
- `/skillweave-promptchain-execute sequence="[sequence]" inputs="[JSON]"`
- `/skillweave-releasechain inputs="[JSON]" target="[humanize/machinize/mixed]"`

**Examples:**
```
/skillweave-promptchain-generate topic="Wellness business evaluation" domain="wellness"
/skillweave-promptchain-validate sequence="[paste your prompt sequence here]"
/skillweave-promptchain-execute sequence="[valid sequence]" inputs='{"business_idea": "Yoga studio"}'
/skillweave-releasechain inputs='{"files": ["src/app.js"], "context": "webapp update"}' target="mixed"
```

### Legacy: prompt-chain (v0.1.0)

The original `prompt-chain` skill remains available for compatibility (requires `/load`):

```bash
# Install as directory for directory-based agents
ln -sf $PWD/skillweave/skills/prompt-chain ~/.claude/skills/

# Or as single file for Opencode
ln -sf $PWD/skillweave/skills/prompt-chain/SKILL.md ~/.config/opencode/commands/prompt-chain.md
```

Usage with `/load`:
```
/load prompt-chain
/generate topic="Wellness business evaluation" domain="wellness"
```

---

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
