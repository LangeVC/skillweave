# SkillWeave

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.4.0-blue)](https://github.com/typelicious/skillweave/releases/tag/v0.4.0)
[![Python](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-passing-green)](tests/)
[![Skills](https://img.shields.io/badge/skills-6%20skills-blue)](skills/)
[![Status](https://img.shields.io/badge/status-production%20ready-green)](https://github.com/typelicious/skillweave)
[![Repo Safety](https://img.shields.io/badge/repo%20safety-checked-green.svg)](SECURITY.md)

**Product development flow on steroids - from idea to production with AI agents.**

SkillWeave transforms AI-assisted development into a complete product development ecosystem with intelligent parallel execution, agent-agnostic design, and adaptive workflow selection.

It is designed for builders who want:
- clearer multi-step AI workflows
- reusable sequence formats
- explicit usage rules
- validation before execution
- a path from prompt craft to durable agent skills

---

## What SkillWeave is

SkillWeave is a complete product development ecosystem for AI-assisted development with **three integrated skills**:

### 1. **Blueprint Skill** (`/skillweave-blueprint`)
- **Structured PRD Creation**: Guided interview for comprehensive product requirements
- **Complexity Analysis**: Automatic assessment of task complexity and dependencies  
- **Execution Recommendations**: REX vs Ralph Loop selection based on project scope
- **Ralph Loop Integration**: Adapts Ralph Loop concepts for multi-agent AI development

### 2. **PromptChain Skills** (generate, validate, execute)
- **Generate**: Create prompt sequences from PRDs or concrete needs
- **Validate**: Review and improve existing sequences
- **Execute**: Run sequences with intelligent parallel execution and dependency analysis

### 3. **ReleaseChain Skill** (`/skillweave-releasechain`)
- **Dual-Mode Execution**: Simple REX-style for 1-3 tasks, full Ralph Loop for complex projects
- **Agent-Agnostic Routing**: Capability-based task assignment to any AI coding agent
- **Completion Promise System**: Standardized completion signaling with verification
- **Memory Systems**: Progress tracking and knowledge accumulation across sessions

Instead of linear, slow development workflows, SkillWeave enables **parallel, intelligent product development flows** with dependency-aware execution and adaptive workflow selection.

---

## Why SkillWeave exists

Most AI-assisted development workflows break for predictable reasons:
- **Sequential bottlenecks**: Linear execution prevents parallelization
- **Agent lock-in**: Hardcoded to specific AI agents, not capabilities
- **Complexity blindness**: No automatic assessment of task complexity
- **Dependency ignorance**: Manual dependency tracking leads to errors
- **Workflow rigidity**: One-size-fits-all execution modes

SkillWeave v0.4.0 transforms these weaknesses into strengths with:
- **Parallel execution engine**: Dependency-aware parallelization with 70% faster execution
- **Agent-agnostic design**: Capability-based routing works with any AI coding agent
- **Complexity-based routing**: Automatic REX vs Ralph Loop selection
- **Dependency analysis**: Kahn's algorithm for optimal execution ordering
- **Adaptive workflows**: Right execution mode for the right task complexity

---

## Core Architecture

### Complete Workflow Flowchart
```
                         ┌─────────────────────────────────────┐
                         │            Idea / Concept           │
                         └──────────────────┬──────────────────┘
                                            │
                                            ▼
                         ┌─────────────────────────────────────┐
                         │           Blueprint Skill           │
                         │      (Structured PRD Creation)      │
                         └──────────────────┬──────────────────┘
                                            │
                         Creates PRD with complexity assessment
                                            │
                                            ▼
                         ┌─────────────────────────────────────┐
                         │         PromptChain Skills          │
                         │  (Sequence Generation & Analysis)   │
                         └──────────────────┬──────────────────┘
                                            │
                     Generates execution sequence with dependencies
                                            │
                                            ▼
                	 ┌─────────────────────────────────────────────┐
                     │            Complexity Assessment            │
                     │    (Automatic REX vs Ralph Loop Selection)  │
                     └──────────────────────┬──────────────────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    │                       │                       │
                    ▼                       ▼                       ▼
           ┌──────────────┐       ┌──────────────────┐    ┌──────────────────┐
           │  Simple Task │       │  Medium Project  │    │ Complex Project  │
           │ (1-3 tasks)  │       │ (4-10 tasks)     │    │ (10+ tasks)      │
           │   <60 min    │       │   1-4 hours      │    │   >4 hours       │
           └──────┬───────┘       └────────┬─────────┘    └────────┬─────────┘
                  │                        │                       │
                  ▼                        ▼                       ▼
           ┌──────────────┐       ┌──────────────────┐    ┌──────────────────┐
           │   REX Mode   │       │  Mixed Mode      │    │  Ralph Loop Mode │
           │  (Simple)    │       │  (Adaptive)      │    │   (Complex)      │
           └──────┬───────┘       └────────┬─────────┘    └────────┬─────────┘
                  │                        │                       │
           Plan → Implement → Review       │          Full autonomous pipeline
                                           │        with memory & verification
                                           │                       │
                                           │───────────────────────┘
                                           │
                                           ▼
                        ┌─────────────────────────────────────┐
                        │         ReleaseChain Skill          │
                        │  (Production Development Pipeline)  │
                        └──────────────────┬──────────────────┘
                                           │
                    Parallel execution with agent-agnostic routing
                                           │
                                           ▼
                        ┌─────────────────────────────────────┐
                        │        Production-Ready Code        │
                        │    (Tested, Reviewed, Deployed)     │
                        └─────────────────────────────────────┘
```

### Parallel Execution Engine
- **Dependency Graph Analysis**: Kahn's algorithm for topological sorting
- **Execution Grouping**: Identify steps that can run in parallel
- **Subagent Triggering**: Maximize concurrency with Task tool integration
- **Timeout & Error Handling**: Robust execution with recovery strategies

### Agent-Agnostic Design
- **Capability Definitions**: `planning`, `code_generation`, `testing`, `review`, etc.
- **Dynamic Agent Registry**: Agents declare capabilities at runtime
- **Intelligent Routing**: Tasks routed to agents matching required capabilities
- **Fallback Strategies**: Automatic fallback if preferred agents unavailable

### Complexity-Based Workflow Selection
- **REX Mode**: Simple Plan → Implement → Review for 1-3 tasks, <60 minutes
- **Ralph Loop Mode**: Full autonomous development pipeline for complex projects
- **Automatic Assessment**: Task count, duration, dependency depth analysis
- **Adaptive Execution**: Right workflow for the right complexity level

### Three-Skill Ecosystem
1. **Blueprint**: Idea → Structured PRD with complexity assessment
2. **PromptChain**: PRD → Execution sequences with parallelization planning
3. **ReleaseChain**: Sequences → Production-ready code with verification loops

---

## Who SkillWeave is for

SkillWeave is for teams and individuals who want **AI-assisted development at scale**:

### For Development Teams
- **Product Managers**: Turn ideas into structured PRDs with complexity assessment
- **Engineering Teams**: Parallel development with dependency-aware execution
- **DevOps Engineers**: Automated deployment pipelines with verification loops
- **QA Teams**: Integrated testing with AI-assisted test generation

### For AI Practitioners
- **AI Builders**: Create reusable, validated prompt sequences
- **Agent Designers**: Build capability-based agent ecosystems
- **Prompt Engineers**: Structured prompt workflows with explicit validation
- **ML Engineers**: Parallel experimentation and model evaluation pipelines

### For Business & Consulting
- **Startup Founders**: Rapid prototyping from idea to MVP
- **Consultants**: Domain-specific business planning and analysis
- **Product Teams**: Verticalized agent skills for specific industries
- **Enterprise Teams**: Scalable AI-assisted development across organizations

### Typical Use Cases
- **Product Development**: Idea → PRD → Implementation → Deployment
- **Research Workflows**: Parallel literature review, data analysis, synthesis
- **Content Systems**: Multi-channel content creation with consistency checks
- **Analysis Pipelines**: Complex data processing with dependency tracking
- **Automated Testing**: AI-generated tests with execution verification

---

## Repository structure

```text
skillweave/
├── docs/                          # Documentation
├── examples/                      # Working examples and demos
│   ├── integration/              # Full workflow examples
│   ├── parallel_execution_example.py
│   └── *.md example sequences
├── schemas/                      # JSON schemas for validation
├── skills/                       # All SkillWeave skills
│   ├── skillweave-blueprint/     # PRD creation with complexity analysis
│   ├── skillweave-promptchain-generate/    # Sequence generation
│   ├── skillweave-promptchain-validate/    # Sequence validation  
│   ├── skillweave-promptchain-execute/     # Parallel execution engine
│   ├── skillweave-releasechain/  # Ralph Loop development pipeline
│   └── prompt-chain/             # Legacy skill (v0.1.0 compatibility)
├── src/skillweave/               # Core Python library
│   ├── orchestrator.py           # Dependency analysis & execution planning
│   ├── executor.py               # Parallel execution engine
│   ├── models.py                 # Data models
│   └── validator.py              # Sequence validation
├── tests/                        # Test suite
│   ├── test_integration.py       # Full workflow tests
│   ├── test_performance.py       # Large project performance tests
│   └── test_orchestrator.py      # Unit tests
└── DEVELOPMENT_WORKFLOW.md       # Release process & conventions
```

Start here:
- `examples/integration/full-workflow-example.md` - Complete Blueprint → PromptChain → ReleaseChain
- `examples/parallel_execution_example.py` - Parallel execution demonstration
- `skills/skillweave-blueprint/SKILL.md` - Blueprint skill documentation
- `DEVELOPMENT_WORKFLOW.md` - Contribution and release guidelines

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
