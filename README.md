# SkillWeave

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.8.0-blue)](https://github.com/typelicious/SkillWeave/releases/tag/v0.8.0)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Skills](https://img.shields.io/badge/skills-13%20skills-blue)](skills/)
[![Status](https://img.shields.io/badge/status-production%20ready-green)](https://github.com/typelicious/SkillWeave)
[![Capacium](https://img.shields.io/badge/Capacium-Install%20via%20cap-0B1020?style=flat-square&logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjIwMCA1MCAyNTAgNTAwIj48cGF0aCBmaWxsPSIjRjdGQUZDIiBkPSJNMzA4LjgzLDU5MC40N2wtMzYuMDItMzYuMjQtMjExLjMyLS4wNC0uMDItMjExLjczLTMzLjExLTMzLjk3LDMzLjEtMzIuODMuMDYtMjE1Ljc0LDIxMy43NC0uMDQsMzMuNDQtMzIuOTcsMzIuNzIsMzIuOTUsMjE0LjAxLjA2LjA5LDIxNS42MiwzMi44NSwzMi43Ni0zMi45OCwzMy4xMS4wNywyMTIuNzQtMjEwLjQuMTItMzYuMjMsMzYuMjJaTTMwOS4wNiw1NTQuMzhsNzUuNTktNzYuODQsMTM5LjgzLTE0MS4zMSwyNy43MS0yOC4xNi05MC42NS05MC43Mi0xNTMuMjItMTUzLjE0LTEyMS41MiwxMjAuNTQtOTQuOTMsOTUuNDYtMjguMTIsMjguNDQsMTA0Ljc1LDEwNS41LDc0LjA4LDczLjY2LDY2LjQ3LDY2LjU3Wk0yMTcuMjYsMTE4LjQ0bDMyLjE0LTMyLjAyLTE2Mi41MS0uMDMuMDQsMTYyLjQ4TDIxNy4yNiwxMTguNDRaTTUyOS44OSw4Ni4zNmwtMTYyLjY1LjA2LDE2Mi42MSwxNjIuNDguMDQtMTYyLjUzWk0yMTIuNTksNDk0LjQ4bC04MC41NS04MS44Ny00NS4wMi00NS43Mi0uMTEsMTYyLjA2LDE1OS40Ny0uMDUtMzMuNzktMzQuNDJaTTM2OC4zNSw1MjguOTRoMTYxLjUzcy0uMDUtMTYyLjA0LS4wNS0xYy4wNGwtNTUuMSw1NC45OS0xMDYuMzgsMTA3LjA1WiIvPjxwYXRoIGZpbGw9IiNGOEZBRkMiIGQ9Ik0zMDguODIsNDgwLjA3bC03OS43Ny00Ny43My02Ny4xMi00MC4wNy0uMDItMTcwLjczLDE0Ni43Mi04NC4yNSw2NC44MywzNi44NSw4Mi45Miw0Ny4xNS4wMiwxNzEuNDgtMTQ3LjU5LDg3LjNaTTMyNi41OSwyMzEuNTRjMTYuMDgsNC4zNiwyOS43MywxMy4zOCw0MC40NywyNi4xNmw0OS41OS0yOC40OS0xMDcuNzgtNjIuODEtMTA3LjE3LDYyLjQzLDQ5Ljc1LDI4LjU1YzE4LjI2LTIyLjY2LDQ2Ljk5LTMyLjg0LDc1LjE1LTI1Ljg0Wk0yOTUuODIsMzg2LjQ2Yy00Ny41OS0xMC4yMS03NC45Ni02MC44My01Ny4xOC0xMDYuMzlsLTUwLjktMjkuNjEtLjA4LDEyOC40LDEwOC4wNiw2Mi4zMi4xLTU0LjdWTTMyMS45NSwzODYuNmwuMjgsNTQuNjQsMTA3LjktNjIuMjktLjA1LTEyOC4yNC00OS43NCwyOS4yN2MxMy43MSwzNS41OS41OSw3NS40My0zMS4zOSw5NS43My04LjMyLDUuNzEtMTcuMTgsOC44Ni0yNi45OSwxMC44OFoiLz48L3N2Zz4%3D&labelColor=0B1020&logoColor=F7FAFC)](https://github.com/Capacium/capacium)

**A complete 7-phase AI-assisted development lifecycle ecosystem.**

SkillWeave provides **13 agent-facing skills** organized into seven phases — from Discovery to Post-Release — with bundle system, prompt chain orchestration, a Ralph Loop-powered execution engine, and an LLM Council for multi-model deliberation.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         SKILLWEAVE LIFECYCLE                             │
│  ┌─────────┐  ┌──────────┐  ┌────────┐  ┌───────┐  ┌─────────┐  ┌──────┐  ┌────────────┐
│  │DISCOVERY│→│BLUEPRINT │→│ DESIGN │→│ BUILD │→│ RELEASE │→│LAUNCH│→│POST-RELEASE│
│  │         │  │          │  │        │  │       │  │         │  │      │  │            │
│  │discovery│  │blueprint │  │ design │  │execute│  │release- │  │launch│  │post-release│
│  │blueprint│  │generate  │  │frontend│  │observe│  │chain    │  │      │  │repo-health │
│  │council  │  │validate  │  │-design │  │       │  │observe  │  │      │  │council     │
│  └────┬────┘  └────┬─────┘  └───┬────┘  └──┬────┘  └────┬────┘  └──┬───┘  └─────┬──────┘
│       │             │            │          │            │           │             │
│       └─────────────┴────────────┴──────────┴────────────┴───────────┴─────────────┘
│                                                                                  │
│  ┌─────────────── GLOBAL SKILLS (always available) ───────────────────────────────┤
│  │ lifecycle (nav + bundle)  │  repo-health (scan/archive/cleanup)  │  observe    │
│  └────────────────────────────────────────────────────────────────────────────────┘
│                                                                                  │
│  ┌─────────────── LLM COUNCIL (available any phase) ──────────────────────────────┤
│  │ council (3-stage deliberation + web search + multi-model peer review)          │
│  └────────────────────────────────────────────────────────────────────────────────┘
└──────────────────────────────────────────────────────────────────────────┘

   5 BUNDLES: full-lifecycle  │  discovery-to-blueprint  │  design-and-build
              release-and-launch  │  post-release-improvement
```

### 7-Phase Lifecycle

| Phase | Type | Skills | Description |
|-------|------|--------|-------------|
| **Discovery** | optional | discovery, blueprint, council | Problem definition, user research, empathy mapping, multi-model research |
| **Blueprint** | recommended | blueprint, generate, validate | Structured PRD creation, complexity assessment |
| **Design** | optional | design, frontend-design, council | Design-Thinking Lens, token extraction, design evaluation |
| **Build** | core | execute, releasechain, observe | Ralph Loop execution with parallel lanes |
| **Release** | core | releasechain, observe, council | Release readiness gate, versioning, code review |
| **Launch** | optional | launch | Pre-launch checklist, deployment, metrics |
| **Post-Release** | optional | post-release, repo-health, observe, council | Retrospective, feedback, backlog iteration |

### 13 Skills

#### Phase Skills
| # | Skill | Type | Description |
|---|-------|------|-------------|
| 1 | `skillweave-discovery` | plan | Problem definition, user research, 11 prompts |
| 2 | `skillweave-blueprint` | plan | Structured PRD creation, complexity assessment |
| 3 | `skillweave-design` | mixed | Design-Thinking Lens, token extraction |
| 4 | `skillweave-promptchain-generate` | plan | Sequence generation from PRD |
| 5 | `skillweave-promptchain-validate` | plan | Validate sequences for completeness |
| 6 | `skillweave-promptchain-execute` | build | Ralph Loop state machine, batch execution |
| 7 | `skillweave-releasechain` | build | Release pipeline, gates, reviews |
| 8 | `skillweave-launch` | build | Deployment, announce, metrics comparison |
| 9 | `skillweave-post-release` | mixed | Retrospective, feedback, iteration planning |

#### Phase-Agnostic Skills (always available)
| # | Skill | Type | Description |
|---|-------|------|-------------|
| 10 | `skillweave-lifecycle` | plan | Phase navigation, bundle recommendations |
| 11 | `skillweave-repo-health` | plan | Inventory scan, dedup, archive, hygiene report |
| 12 | `skillweave-observe` | plan | Execution reports, events, memory (read-only) |
| 13 | `skillweave-council` | mixed | Multi-Model LLM Council — deliberation, peer review, chairman synthesis with web search and multi-provider routing |

### LLM Council

Cross-phase skill for research, analysis, code review, and design evaluation:

| Feature | Detail |
|---------|--------|
| **Architecture** | 3-stage deliberation: opinion → peer review → synthesis |
| **Modes** | quick (opinions only), standard (+ peer review), full (+ chairman) |
| **Router Support** | Faigate, OpenRouter, KiloRouter, ClawRouter, LlmAI — auto-detect + SingleModel fallback |
| **Web Search** | DuckDuckGo (free), Serper, Tavily, Brave — time ranges 30d/quarter/6mo/1yr/any |
| **Profiles** | default (4 models), quick (2), deep (6), expert (4 top-tier) |
| **Output** | Markdown or JSON with consensus_score, key_insights, dissent |

### Execution Engine

- **Ralph Loop State Machine**: Preflight → Batch Select → Lane Plan → Implement → Verify → Review Gate → Fix/Retry → Integrate → Advance/Stop
- **Safe Parallelization**: Only disjoint write scopes, no shared ownership of contract surfaces
- **Binary Gates**: Only hard completion signals (tests passed, verifier passed, explicit `continue`)
- **Agent-Agnostic**: Capability-based routing (, , ) — works with any AI coding agent

### Bundle System

Choose your entry point:

| Bundle | Phases | Effort |
|--------|--------|--------|
| `full-lifecycle` | all 7 | Full project duration |
| `discovery-to-blueprint` | discovery → blueprint | 1-3 days |
| `design-and-build` | design → build | 2-5 days |
| `release-and-launch` | release → launch | 1-2 days |
| `post-release-improvement` | post-release → blueprint → build | 2-5 days |

---

## Quickstart

### Via Capacium

```bash
brew install capacium/tap/capacium
cap install skillweave
```

### Via curl

```bash
curl -s https://raw.githubusercontent.com/typelicious/SkillWeave/main/install.sh | bash
```

### Via Python installer

```bash
git clone https://github.com/typelicious/SkillWeave.git
cd SkillWeave
python3 -m skillweave.installer --interactive
```

---

## Configuration

### .skillweave Folder

```
.skillweave/
├── config.yaml          # Risk mode and settings
├── bundles.yaml         # 5 entry-point bundles
├── phases.yaml          # 7 lifecycle phases
├── prds/                # Product Requirements Documents
├── prompts/             # Phase prompts (discovery, etc.)
├── lenses/              # Design-thinking lenses
├── templates/           # Reusable templates
├── sequences/           # Generated prompt sequences
├── tracking-log/        # Execution tracking
└── release/             # Release artifacts
```

### Risk Modes

| Mode | Behavior |
|------|----------|
| **conservative** | Extra validation, explicit approvals, strict checks |
| **medium** | Balanced automation with safety checks (default) |
| **unicorn** | Maximum automation, optimistic assumptions |

Override via CLI (`--risk-mode=conservative`), env (`SKILLWEAVE_RISK_MODE`), or `config.yaml` (`mode: medium`).

---

## Repository

```
SkillWeave/
├── skills/                       # 13 SkillWeave skills
│   ├── skillweave-blueprint/     # SKILL.md + capability.yaml + references
│   ├── skillweave-council/       # Multi-Model LLM Council
│   ├── skillweave-design/
│   ├── skillweave-discovery/
│   ├── skillweave-launch/
│   ├── skillweave-lifecycle/
│   ├── skillweave-observe/
│   ├── skillweave-post-release/
│   ├── skillweave-promptchain-execute/
│   ├── skillweave-promptchain-generate/
│   ├── skillweave-promptchain-validate/
│   ├── skillweave-releasechain/
│   └── skillweave-repo-health/
├── src/skillweave/               # Core Python library
│   ├── installer.py              # Multi-agent installer (13 skills)
│   ├── council/                  # LLM Council engine, providers, search, synthesis
│   ├── execution/                # Ralph Loop state machine + batch planner
│   ├── release/                  # Release workflow, readiness, notes
│   ├── launch/                   # Deployment, announce, metrics
│   ├── post_release/             # Retrospective, feedback, iteration
│   ├── repo_health/              # Scanner, classifier, dedup, archive, report
│   ├── observation/              # Event logging, report generation
│   ├── github_integration/       # Auto-tag, changelog, release gate, issue sync, capacium
│   ├── intelligent_detection/    # Onboarding, skill routing
│   ├── design_thinking.py        # Design-Thinking Lens
│   ├── execution_memory.py       # Memory across execution sessions
│   ├── lifecycle_integration.py  # Phase detection + bundle navigation
│   ├── workflow_recommendation.py # Bundle suggestion engine
│   ├── phase_detection.py        # Current phase detection
│   └── ...
├── .github/workflows/            # 13 GitHub Actions
│   ├── auto-tag-release.yml      # Version bump → tag → release → Capacium publish
│   ├── auto-changelog.yml        # Changelog generation
│   ├── capacium-validate.yml     # Capacium manifest validation
│   ├── release-readiness-gate.yml # Pre-release validation
│   └── ...
└── tests/                        # 577 tests
```

---

## Usage

```
/skillweave-lifecycle command="recommend"     # Get bundle suggestion
/skillweave-discovery topic="e-commerce"      # Problem exploration
/skillweave-blueprint                          # Interactive PRD creation
/skillweave-design command="lens" input="..."  # Apply design lens
/skillweave-council query="..."               # Multi-model deliberation
/skillweave-promptchain-generate topic="..."   # Generate execution plan
/skillweave-promptchain-execute sequence="..." # Execute with Ralph Loop
/skillweave-releasechain inputs='{...}'        # Manage release
/skillweave-launch command="deploy" env="staging"
/skillweave-post-release command="retrospective" version="1.0"
/skillweave-repo-health command="scan"          # Inventory check
/skillweave-observe command="report"            # Execution report
```

---

## Current Release (v0.8.0)

- **13 skills** (9 phase + 4 global) — skillweave-council added, replacing last30days
- **LLM Council**: 3-stage deliberation engine with multi-provider routing (Faigate, OpenRouter, Kilo, Claw, LlmAI, SingleModel)
- **Multi-Provider**: Auto-detection of available routers, credit validation, /models availability check
- **Web Search**: DuckDuckGo (free), Serper, Tavily, Brave — time ranges 30d/quarter/6mo/1yr/any
- **Capacium**: Validate + Publish actions integrated into CI/CD pipeline
- **Capacium Root Manifest**: capability.yaml with 13 sub-capabilities for Exchange indexing
- **577 tests** — engine, synthesis, prompts, providers, search, integration

---

## License

Apache 2.0 — See [LICENSE](LICENSE)
