# SkillWeave

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.5.6-blue)](https://github.com/typelicious/SkillWeave/releases/tag/v0.5.6)
[![Python](https://img.shields.io/badge/python-3.x-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-184%20passing-green)](tests/)
[![Skills](https://img.shields.io/badge/skills-5%20skills-blue)](skills/)
[![Status](https://img.shields.io/badge/status-production%20ready-green)](https://github.com/typelicious/SkillWeave)
[![Capacium](https://img.shields.io/badge/Capacium-Install%20via%20cap-0B1020?style=flat-square&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjIwMCA1MCAyNTAgNTAwIj48cGF0aCBmaWxsPSIjRjdGQUZDIiBkPSJNMzA4LjgzLDU5MC40N2wtMzYuMDItMzYuMjQtMjExLjMyLS4wNC0uMDItMjExLjczLTMzLjExLTMzLjk3LDMzLjEtMzIuODMuMDYtMjE1Ljc0LDIxMy43NC0uMDQsMzMuNDQtMzIuOTcsMzIuNzIsMzIuOTUsMjE0LjAxLjA2LjA5LDIxNS42MiwzMi44NSwzMi43Ni0zMi45OCwzMy4xMS4wNywyMTIuNzQtMjEwLjQuMTItMzYuMjMsMzYuMjJaTTMwOS4wNiw1NTQuMzhsNzUuNTktNzYuODQsMTM5LjgzLTE0MS4zMSwyNy43MS0yOC4xNi05MC42NS05MC43Mi0xNTMuMjItMTUzLjE0LTEyMS41MiwxMjAuNTQtOTQuOTMsOTUuNDYtMjguMTIsMjguNDQsMTA0Ljc1LDEwNS41LDc0LjA4LDczLjY2LDY2LjQ3LDY2LjU3Wk0yMTcuMjYsMTE4LjQ0bDMyLjE0LTMyLjAyLTE2Mi41MS0uMDMuMDQsMTYyLjQ4TDIxNy4yNiwxMTguNDRaTTUyOS44OSw4Ni4zNmwtMTYyLjY1LjA2LDE2Mi42MSwxNjIuNDguMDQtMTYyLjUzWk0yMTIuNTksNDk0LjQ4bC04MC41NS04MS44Ny00NS4wMi00NS43Mi0uMTEsMTYyLjA2LDE1OS40Ny0uMDUtMzMuNzktMzQuNDJaTTM2OC4zNSw1MjguOTRoMTYxLjUzcy0uMDUtMTYyLjA0LS4wNS0xNjIuMDRsLTU1LjEsNTQuOTktMTA2LjM4LDEwNy4wNVoiLz48cGF0aCBmaWxsPSIjRjdGQUZDIiBkPSJNMzA4LjgyLDQ4MC4wN2wtNzkuNzctNDcuNzMtNjcuMTItNDAuMDctLjAyLTE3MC43MywxNDYuNzItODQuMjUsNjQuODMsMzYuODUsODIuOTIsNDcuMTUuMDIsMTcxLjQ4LTE0Ny41OSw4Ny4zWk0zMjYuNTksMjMxLjU0YzE2LjA4LDQuMzYsMjkuNzMsMTMuMzgsNDAuNDcsMjYuMTZsNDkuNTktMjguNDktMTA3Ljc4LTYyLjgxLTEwNy4xNyw2Mi40Myw0OS43NSwyOC41NWMxOC4yNi0yMi42Niw0Ni45OS0zMi44NCw3NS4xNS0yNS44NFpNMjk1LjgyLDM4Ni40NmMtNDcuNTktMTAuMjEtNzQuOTYtNjAuODMtNTcuMTgtMTA2LjM5bC01MC45LTI5LjYxLS4wOCwxMjguNCwxMDguMDYsNjIuMzIuMS01NC43Wk0zMjEuOTUsMzg2LjZsLjI4LDU0LjY0LDEwNy45LTYyLjI5LS4wNS0xMjguMjQtNDkuNzQsMjkuMjdjMTMuNzEsMzUuNTkuNTksNzUuNDMtMzEuMzksOTUuNzMtOC4zMiw1LjcxLTE3LjE4LDguODYtMjYuOTksMTAuODhaIi8%2BPC9zdmc%2B&labelColor=0B1020&logoColor=F7FAFC)](https://github.com/Capacium/capacium)

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

SkillWeave is a complete product development ecosystem for AI-assisted development with **five integrated skills**:

### 1. **Blueprint Skill** (`/skillweave-blueprint`)
- **Structured PRD Creation**: Guided interview for comprehensive product requirements
- **Complexity Analysis**: Automatic assessment of task complexity and dependencies  
- **Execution Recommendations**: REX vs Ralph Loop selection based on project scope
- **Ralph Loop Integration**: Adapts Ralph Loop concepts for multi-agent AI development

### 2. **PromptChain Generate** (`/skillweave-promptchain-generate`)
- **Two-Axis Model**: Generates sequences with `sequence_type` (plan/build/mixed) and `execution_mode` (rex/ralph_attended/ralph_overnight)
- **Complexity-Aware**: Creates execution plans optimized for REX (simple) or Ralph Loop (standard/complex) workflows
- **Backward Compatibility**: Supports legacy `mode` parameter while encouraging explicit type/mode separation

### 3. **PromptChain Validate** (`/skillweave-promptchain-validate`)
- **Comprehensive Validation**: Reviews sequences for completeness, parallelization readiness, and integration gates
- **Parallelization Readiness**: Checks for write-scope conflicts and single-owner surfaces
- **Improvement Suggestions**: Recommends enhancements to sequences for better execution

### 4. **PromptChain Execute** (`/skillweave-promptchain-execute`)
- **Ralph Loop State Machine**: 9-state execution flow (Preflight → Batch Selection → Lane Plan → Implement → Verify → Review Gate → Fix/Retry → Integrate → Advance/Stop)
- **Write-Scope Based Parallelization**: Safe parallel execution only for disjoint write scopes
- **Binary Gate Policy**: Only accepts hard completion signals (tests passed, verifier passed, explicit `continue`)
- **Batch Planning**: Intelligent batching with `critical_path_step`, `parallel_lanes`, `write_surfaces`

### 5. **ReleaseChain Skill** (`/skillweave-releasechain`)
- **Ralph Loop Pipeline**: Ralph Loop-powered development pipeline for autonomous AI development
- **Completion Promises**: Handles review, testing, iteration with completion promises, memory systems, and multi-agent execution
- **Multi-Agent Orchestration**: Safe parallel subagent orchestration with dependency-aware batching

### 6. **Install via Capacium** (`cap install`)
SkillWeave is also available as a **Capacium** capability package. Install any skill directly:

```bash
# Install via Capacium (recommended)
cap install skillweave-blueprint
cap install skillweave-promptchain-generate
cap install skillweave-promptchain-validate
cap install skillweave-promptchain-execute
cap install skillweave-releasechain
```

Each skill ships as a self-contained `capability.yaml` with all dependencies, gates, and tools declared — ready for the Capacium runtime.

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

### Next Level Features
SkillWeave Next Level provides advanced capabilities that enhance all skills with intelligent execution modes, design thinking principles, and persistent tracking:

- **Mode-Aware Execution**: Three risk modes (Conservative, Medium, Unicorn) control parallelization limits, approval requirements, and safety checks
- **Checklist-Based Tracking**: Parse markdown checklists (`- [ ]` and `- [x]`) to track task completion across sessions using `.skillweave/tracking-log/`
- **Design-Thinking Lens**: Apply cognitive ergonomics principles (Value ≥ Noise, Scan Before Read, Hierarchy of Needs, etc.) for better outputs
- **Community Know-How**: Extract patterns from `.skillweave/tracking-log/` across projects for optimization recommendations
- **Modular Templates**: Load and combine templates from `.skillweave/templates/` for consistent documentation
- **Capability-Based Routing**: Dynamic agent detection and intelligent task routing based on declared capabilities

**Usage**: Initialize with `--init` flag or via `SkillWeaveNextLevel` Python class. Configure via `.skillweave/config.yaml` in your project root.

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

## Configuration & .skillweave

SkillWeave v0.5.0 introduces a `.skillweave` folder structure for persistent configuration, tracking, and project management:

### `.skillweave/config.yaml` – Risk Mode Configuration
```yaml
mode: medium  # conservative, medium, or unicorn
tracking:
  enabled: true
  log_dir: ".skillweave/tracking-log"
github:
  enabled: true
  owner: "your-org"
  repo: "your-repo"
```

### Folder Structure
```
.skillweave/
├── config.yaml          # Risk mode and settings
├── handover/            # Handover documents between sessions
├── specs/               # Specifications (backlog.yaml, requirements)
├── tracking-log/        # Execution tracking logs (gitignored)
└── manifesto/           # Project vision and principles
```

### Three Risk Modes
1. **Conservative**: Safe defaults, explicit confirmations, minimal automation
2. **Medium**: Balanced automation with safety checks, recommended for most projects
3. **Unicorn**: Maximum automation, experimental features, for experienced users

To get started, create `.skillweave/config.yaml` in your project root or let SkillWeave create it automatically when you first run a skill.

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
│   └── skillweave-releasechain/  # Ralph Loop development pipeline
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

## Current Release (v0.5.6)

SkillWeave v0.5.6 refines the **README documentation** with Capacium branding, content boundary enforcement, and prerelease quality gates:

### Five Integrated Skills
1. **Blueprint Skill** (`/skillweave-blueprint`): Structured PRD creation with complexity analysis
2. **PromptChain Generate** (`/skillweave-promptchain-generate`): Two-axis sequence generation with type/mode separation
3. **PromptChain Validate** (`/skillweave-promptchain-validate`): Comprehensive validation with parallelization readiness checks
4. **PromptChain Execute** (`/skillweave-promptchain-execute`): Ralph Loop state machine with write-scope based parallelization
5. **ReleaseChain Skill** (`/skillweave-releasechain`): Ralph Loop-powered development pipeline

### Core Architecture
- **Ralph Loop State Machine**: 9-state execution flow with binary gate policy
- **Write-Scope Based Parallelization**: Safe parallel execution only for disjoint write scopes
- **Two-Axis Model**: Explicit separation of `sequence_type` (plan/build/mixed) and `execution_mode` (rex/ralph_attended/ralph_overnight)
- **Batch Planning**: Intelligent batching with critical path vs sidecar lanes
- **Binary Gate Policy**: Only hard completion signals (tests passed, verifier passed, explicit `continue`)
- **Agent-Agnostic Design**: Capability-based routing for any AI coding agent

### Next Level Features (v0.5.0)
- **Three Risk Modes**: Conservative, Medium, Unicorn – configurable behavior across all skills
- **.skillweave Folder Structure**: Persistent configuration, tracking logs, specs, and manifesto
- **GitHub Issues Integration**: Automatic issue creation with Planning Poker estimation
- **Backlog Synchronization**: Sync GitHub Issues with `.skillweave/specs/backlog.yaml`
- **Persistent State Manager**: Session recovery and configuration management
- **Optional Checklist Execution**: Markdown checkbox tracking for step-by-step validation
- **Design-Thinking Lens**: UI/UX decision framework for product development
- **Enhanced Capability Routing**: Dynamic agent detection and capability matching
- **Modular Templates Foundation**: Reusable template system with examples
- **Community Know-How Prototype**: Pattern extraction and knowledge sharing
- **Comprehensive Testing**: 100+ tests covering all Next Level features

### Production-Ready Features
- Comprehensive testing suite (unit, integration, performance)
- Extensive examples and documentation
- Multi-agent installation support
- Standardized release process and conventions

---

## Roadmap: What comes next

Building on v0.5.0's "Next Level Features", the roadmap focuses on scaling and ecosystem growth:

### v0.5.0 - Next Level Features ✓ (Released)
- **Three Risk Modes**: Conservative, Medium, Unicorn – configurable behavior across all skills
- **.skillweave Folder Structure**: Persistent configuration, tracking logs, specs, and manifesto
- **GitHub Issues Integration**: Automatic issue creation with Planning Poker estimation
- **Backlog Synchronization**: Sync GitHub Issues with `.skillweave/specs/backlog.yaml`
- **Persistent State Manager**: Session recovery and configuration management
- **Optional Checklist Execution**: Markdown checkbox tracking for step-by-step validation
- **Design-Thinking Lens**: UI/UX decision framework for product development
- **Enhanced Capability Routing**: Dynamic agent detection and capability matching
- **Modular Templates Foundation**: Reusable template system with examples
- **Community Know-How Prototype**: Pattern extraction and knowledge sharing
- **Comprehensive Testing**: 100+ tests covering all Next Level features

### v0.6.0 - Ecosystem Expansion
- **Community Examples & Tutorials**: Comprehensive guides for common use cases
- **Performance Optimization**: Enhanced execution for 100+ task projects
- **Visualization Tools**: Interactive dependency graphs and progress tracking
- **Extended Agent Support**: Broader compatibility with emerging AI coding agents

### v0.7.0 - Collaboration Features
- **Team Workflows**: Multi-user collaboration with role-based access
- **Project Templates**: Industry-specific templates and best practices
- **Cloud Integration**: Optional hosted execution with API access
- **Enterprise Features**: Audit logs, compliance tracking, and governance

### Future Vision
- **Marketplace Ecosystem**: Share and discover skills across organizations
- **AI-Native CI/CD**: Full integration with development pipelines
- **Domain-Specialized Skills**: Vertical solutions for specific industries
- **Research Integration**: Academic and R&D workflow optimization

Contributions welcome! See [DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) for how to contribute.

---

## Vision

SkillWeave's vision is to create **the definitive product development ecosystem for the AI era** - transforming how teams go from idea to production with intelligent AI assistance.

### Three-Layer Architecture
1. **Blueprint Layer**: Structured requirements and complexity assessment
2. **Orchestration Layer**: Intelligent parallel execution with dependency analysis  
3. **Production Layer**: Verified, production-ready code with completion promises

### Long-Term Goals
- **Democratize AI-Assisted Development**: Make sophisticated AI workflows accessible to all skill levels
- **Accelerate Innovation**: Reduce development cycles from weeks to days through parallel execution
- **Build Organizational Intelligence**: Capture and reuse development patterns across projects
- **Create Agent-Agnostic Standards**: Establish capability-based routing as the industry standard

### The Big Picture
**Product development flow on steroids** - where AI agents work in coordinated parallel, adapt to project complexity, and produce verified results that teams can trust and deploy with confidence.

---

## Configuration and Risk Mode Override System

SkillWeave v0.5.5 introduces a hierarchical override system for risk mode configuration. The effective risk mode is determined by the following precedence order (highest to lowest):

1. **CLI parameter**: `--risk-mode=conservative|medium|unicorn` (if provided in skill invocation)
2. **Environment variable**: `SKILLWEAVE_RISK_MODE` (if set)
3. **Project configuration**: `.skillweave/config.yaml` `mode` setting
4. **Global user configuration**: `~/.skillweave/config.yaml` `mode` setting
5. **System default**: `medium`

### Command-Line Utilities

- `skillweave-risk-mode` - shows effective risk mode given current context
- `skillweave-interactive-mode` - interactive risk mode selection with project analysis and persistence options

### Adjusting Behavior

- **Conservative**: Extra validation, explicit approvals, strict safety checks
- **Medium**: Balanced approach with standard validation  
- **Unicorn**: Optimistic assumptions, minimal confirmations, maximum speed

For more details, see the "Risk Mode Integration" section in each skill's documentation.

## Status

**Production Ready** - SkillWeave v0.5.0+ is a complete, battle-tested product development ecosystem used for real projects.

### Current Status
- **Version**: v0.5.6 (latest stable release)
- **Stability**: Production-ready with comprehensive test suite
- **Performance**: Optimized for projects with 50+ parallel tasks, now with Ralph Loop state machine
- **Adoption**: Used by teams for AI-assisted product development
- **Key Features**: Ralph Loop execution, write-scope parallelization, two-axis model, binary gate policy

### Getting Started
The best starting point depends on your needs:

**For new users:**
1. Run the automated installer: `./scripts/install-skills.sh`
2. Try the Blueprint skill: `/skillweave-blueprint` 
3. Explore examples: `examples/integration/full-workflow-example.md`

**For developers:**
1. Review architecture: `src/skillweave/orchestrator.py`
2. Study parallel execution: `examples/parallel_execution_example.py`
3. Check tests: `tests/test_integration.py`

**For contributors:**
1. Read `DEVELOPMENT_WORKFLOW.md` for contribution guidelines
2. Check open issues for areas needing improvement
3. Join discussions about future roadmap items

---

## Multi-Agent Quickstart

SkillWeave v0.5.0+ provides separate skill directories for each command with direct `/skillweave-*` prefixes for faster access.

### Install via Capacium

If you have the [Capacium](https://github.com/Capacium/capacium) CLI installed:

```bash
cap install skillweave-blueprint
cap install skillweave-promptchain-generate
cap install skillweave-promptchain-validate
cap install skillweave-promptchain-execute
cap install skillweave-releasechain
```

### Online Installer (One-line)

Install SkillWeave with a single command:

```bash
curl -s https://raw.githubusercontent.com/typelicious/SkillWeave/main/install.sh | bash
```

Or with options:

```bash
# Interactive installation
curl -s https://raw.githubusercontent.com/typelicious/SkillWeave/main/install.sh | bash -s -- --interactive

# Dry-run to preview changes
curl -s https://raw.githubusercontent.com/typelicious/SkillWeave/main/install.sh | bash -s -- --dry-run

# Initialize Next Level features in current project
curl -s https://raw.githubusercontent.com/typelicious/SkillWeave/main/install.sh | bash -s -- --init
```

### Recommended: Automated Installation (All Agents)

Use the installer script to automatically install skills to all detected AI agent directories with correct formats for each agent type:

```bash
# Clone the repository
git clone https://github.com/typelicious/SkillWeave.git
cd SkillWeave

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
git clone https://github.com/typelicious/SkillWeave.git

# Create commands directory if it doesn't exist
mkdir -p ~/.config/opencode/commands

# Install as single .md files (symlinks recommended for updates)
ln -sf $PWD/SkillWeave/skills/skillweave-blueprint/SKILL.md ~/.config/opencode/commands/skillweave-blueprint.md
ln -sf $PWD/SkillWeave/skills/skillweave-promptchain-generate/SKILL.md ~/.config/opencode/commands/skillweave-promptchain-generate.md
ln -sf $PWD/SkillWeave/skills/skillweave-promptchain-validate/SKILL.md ~/.config/opencode/commands/skillweave-promptchain-validate.md
ln -sf $PWD/SkillWeave/skills/skillweave-promptchain-execute/SKILL.md ~/.config/opencode/commands/skillweave-promptchain-execute.md
ln -sf $PWD/SkillWeave/skills/skillweave-releasechain/SKILL.md ~/.config/opencode/commands/skillweave-releasechain.md
```

#### For Claude Code, Codex, Antigravity (directory structure)
```bash
# Clone the repository
git clone https://github.com/typelicious/SkillWeave.git

# Create skills directories
mkdir -p ~/.claude/skills ~/.codex/skills ~/.gemini/antigravity/skills

# Install as directory symlinks
ln -sf $PWD/SkillWeave/skills/skillweave-blueprint ~/.claude/skills/
ln -sf $PWD/SkillWeave/skills/skillweave-promptchain-generate ~/.claude/skills/
ln -sf $PWD/SkillWeave/skills/skillweave-promptchain-validate ~/.claude/skills/
ln -sf $PWD/SkillWeave/skills/skillweave-promptchain-execute ~/.claude/skills/
ln -sf $PWD/SkillWeave/skills/skillweave-releasechain ~/.claude/skills/

# Repeat for other agents with their respective paths
```

### Correct Agent Directories

The installer supports these agent paths with correct formats:

| Agent | Type | Path | Format |
|-------|------|------|--------|
| **Opencode** | Single file | `~/.config/opencode/commands/` | `.md` files |
| **Claude Code** | Directory | `~/.claude/skills/` | Directory structure |
| **Codex** | Directory | `~/.codex/skills/` | Directory structure |
| **Gemini CLI** | Directory | `~/.gemini/skills/` | Directory structure |
| **Antigravity** | Directory | `~/.gemini/antigravity/skills/` | Directory structure |
| **OpenClaw** | Directory | `~/.config/openclaw/skills/` | Directory structure |
| **Aider** | Directory | `~/.config/aider/skills/` | Directory structure |
| **Windsurf** | Directory | `~/.config/windsurf/skills/` | Directory structure |
| **Qwen Code** | Directory | `~/.qwen/skills/` | Directory structure |

### Interactive Installation

SkillWeave now includes an interactive installer with multiple modes:

```bash
./scripts/install-skills.sh --interactive
./scripts/install-skills.sh --uninstall
./scripts/install-skills.sh --update
./scripts/install-skills.sh --troubleshoot
./scripts/install-skills.sh --list
```

**Features:**
- **Interactive selection**: Choose which agents to install/update/uninstall
- **Smart detection**: Only installs to existing agent directories (no file-leichen)
- **Multiple modes**: Install, uninstall, update, troubleshoot
- **Dry-run option**: Preview changes with `--dry-run`
- **Agent status**: List detected agents with `--list`

### For Developers & Contributors

If you maintain a local fork or development repository, use the update script:

```bash
./scripts/update-local-skills.sh
```

This script:
1. **Copies skills** from your development repo to `~/.skillweave`
2. **Updates installer** and configuration files
3. **Checks repository status** (git branch, latest commit)
4. **Warns if** `~/.skillweave` is a git repository (should be plain directory)
5. **Offers to run installer** automatically after update
6. **Lets the installer clean up** legacy `~/.agents/skills` duplicates during install/update

**Typical workflow:**
```bash
# 1. Update your development repo
cd ~/Documents/repositories/github/SkillWeave
git pull

# 2. Copy to local installation directory
./scripts/update-local-skills.sh

# 3. Install to agents (interactive selection)
./scripts/install-skills.sh --interactive
```

### Using the Skills

Direct commands without `/load` (for separate skill installations):
- `/skillweave-blueprint` - Create structured PRD with complexity analysis
- `/skillweave-promptchain-generate topic="[topic]" domain="[domain]"`
- `/skillweave-promptchain-validate sequence="[sequence]"`
- `/skillweave-promptchain-execute sequence="[sequence]" inputs="[JSON]"`
- `/skillweave-releasechain inputs="[JSON]" target="[humanize/machinize/mixed]"`

**Examples:**
```
/skillweave-blueprint
/skillweave-promptchain-generate topic="Wellness business evaluation" domain="wellness"
/skillweave-promptchain-validate sequence="[paste your prompt sequence here]"
/skillweave-promptchain-execute sequence="[valid sequence]" inputs='{"business_idea": "Yoga studio"}'
/skillweave-releasechain inputs='{"files": ["src/app.js"], "context": "webapp update"}' target="mixed"
```



---

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.
