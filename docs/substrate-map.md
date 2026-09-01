# SkillWeave Substrate Map (`.skillweave/`)

This document defines the authoritative top-level directory and file layout of the `.skillweave/` substrate. It maps each area to its primary **owner skill**, its **lifecycle phase**, its **mutability policy**, and its **operational purpose**.

Every area under `.skillweave/` is machine-checked for documentation completeness and drift prevention via `tests/unit/test_substrate_drift.py`.

---

## 1. Overview and Core Invariants

The `.skillweave/` directory is the local, version-controlled state and artifact substrate for SkillWeave projects. It houses planning artifacts, persistent architecture memory, lifecycle configurations, prompt chains, release gates, and execution journals.

### Invariants:
1. **Isolated Output Routing**: All AI planning, execution, and validation artifacts reside inside `.skillweave/`—never in arbitrary root-level directories.
2. **Single Ownership**: Every top-level area has exactly one primary owning skill or subsystem responsible for its schema, read/write semantics, and evolution.
3. **Phase Traceability**: Every area is bound to a defined lifecycle phase (Discovery, Blueprint, Design, Build, Release, Launch, Post-Release) or designated as Cross-Cutting/Global.
4. **Drift Enforcement**: Any new file or directory introduced into `.skillweave/` must be registered and documented in this specification; undocumented additions fail CI gates.

---

## 2. Top-Level Substrate Map (All 26 Canonical Areas)

| # | Area Path | Kind | Owner Skill / Subsystem | Lifecycle Phase | Mutability | Purpose & Responsibilities |
|---|-----------|------|-------------------------|-----------------|------------|----------------------------|
| 1 | `archive/` | Directory | `skillweave-releasechain` / `skillweave-repo-health` | Release / Post-Release | Append-only / Immutable | Historical archive of completed runs, superseded manifests, and previous release snapshots. |
| 2 | `bundles.yaml` | YAML Config | `skillweave-lifecycle` | Global / Setup | Declarative / Config | Definitions of available lifecycle bundles (e.g. `full-lifecycle`, `design-and-build`, `release-and-launch`). |
| 3 | `checklists/` | Directory | `skillweave-promptchain-execute` / `skillweave-releasechain` | Build / Release | Versioned / Dynamic | Operational and release readiness checklists, pre-flight verification items, and gate rubrics. |
| 4 | `cleanup/` | Directory | `skillweave-repo-health` | Post-Release / Global | Generated / Writable | Repository inventory, file classification rules, duplication analysis, and lean-core optimization plans. |
| 5 | `config.yaml` | YAML Config | Core Runtime / `skillweave-lifecycle` | Global / Init | User / Engine Config | Project-level configuration: active bundle, current phase, feature flags, risk modes, lens toggles, git-flow rules. |
| 6 | `design/` | Directory | `skillweave-design` | Design (Phase 3) | Generated / Versioned | Design tokens, UI component specifications, UX principles, wireframes, and design critique reports. |
| 7 | `discovery/` | Directory | `skillweave-discovery` / `skillweave-council` | Discovery (Phase 1) | Iterative / Versioned | User research findings, empathy maps, competitive landscape analysis, problem statements, and council strategy notes. |
| 8 | `handover/` | Directory | `skillweave-lifecycle` / `skillweave-observe` | Cross-Cutting / Global | Append-only / State | Inter-session context handover records, agent shift logs, and cross-workflow continuity state. |
| 9 | `hooks/` | Directory | Core Runtime / `skillweave-promptchain-execute` | Global / Execution | Executable / Config | Lifecycle automation hooks, pre/post step triggers, validation webhooks, and execution event scripts. |
| 10 | `lenses/` | Directory | `skillweave-discovery` / `skillweave-design` | Discovery / Design | Declarative / Config | Domain and cognitive lens specifications (e.g. Design Thinking lens rules, strictness, and principles). |
| 11 | `lib/` | Directory | Core Runtime / Project Domain | Global | Code / Utilities | Local Python helper libraries, assumption scoring functions, ideation utilities, and project-specific extensions. |
| 12 | `licenses/` | Directory | `skillweave-repo-health` / `skillweave-releasechain` | Release / Global | Audit / Reference | Third-party dependency licenses, license compatibility matrices, and compliance audit reports. |
| 13 | `lifecycle/` | Directory | `skillweave-lifecycle` | Global | Engine / State | Lifecycle state machine data, custom phase transition graphs, and dynamic phase configuration. |
| 14 | `manifesto/` | Directory | `skillweave-blueprint` / Core Governance | Global / Inception | Canonical / Locked | Core project manifesto, foundational vision, non-negotiable architectural principles, and ethics guardrails. |
| 15 | `memory/` | Directory | `skillweave-observe` / `skillweave-promptchain-execute` | Global / Continuous | Managed / Versioned | Persistent project knowledge: `architecture.yaml`, `conventions.yaml`, `decisions.yaml`, `open-issues.yaml`, `rules.yaml`. |
| 16 | `onboarding-state.yaml` | YAML State | `skillweave-lifecycle` / CLI | Setup / Onboarding | Ephemeral / State | Interactive onboarding tutorial progress, completed setup milestones, and walkthrough tracking. |
| 17 | `phases.yaml` | YAML Config | `skillweave-lifecycle` | Global / Setup | Declarative / Config | Authoritative lifecycle phase hierarchy (Phases 1-7), skill mappings, phase types (core/recommended/optional). |
| 18 | `planning/` | Directory | `skillweave-blueprint` / `skillweave-lifecycle` | Blueprint / Build | Dynamic / State | File-based Kanban planning tickets (`backlog/`, `doing/`, `done/`) following the beans-pattern with YAML frontmatter. |
| 19 | `prds/` | Directory | `skillweave-blueprint` | Blueprint (Phase 2) | Versioned / Structured | Formal Product Requirements Documents containing structured `prd.json` and narrative markdown per initiative. |
| 20 | `prompts/` | Directory | `skillweave-promptchain-generate` / `skillweave-discovery` | Discovery / Blueprint / Build | Catalog / Templates | Phase-specific prompt templates, role definitions, and system prompt components organized by phase. |
| 21 | `release/` | Directory | `skillweave-releasechain` | Release (Phase 5) | Governed / Policy | Release readiness model (`readiness-model.yaml`), binary gate policies, and skill boundaries (`skill-boundaries.yaml`). |
| 22 | `reports/` | Directory | `skillweave-observe` / `skillweave-launch` | Post-Release / Observability | Generated / Audit | Execution timing analytics, gate attestation receipts, benchmark evaluations, and post-release summaries. |
| 23 | `sequences/` | Directory | `skillweave-promptchain-generate` / `skillweave-promptchain-validate` | Blueprint / Build | Structured / Executable | Machine-executable prompt sequences (`execution-sequences.yaml`), complexity analysis, and agent assignments. |
| 24 | `specs/` | Directory | `skillweave-blueprint` / `skillweave-promptchain-generate` | Blueprint (Phase 2) | Versioned / Technical | Technical specifications, feature backlogs (`backlog.yaml`), API interface definitions, and architectural schemas. |
| 25 | `templates/` | Directory | `skillweave-blueprint` / `skillweave-promptchain-generate` | Blueprint / Setup | Catalog / Scaffolds | Reusable starters for API services, CLI tools, web apps, validation templates, and discovery canvases. |
| 26 | `tracking-log/` | Directory | `skillweave-observe` / `skillweave-promptchain-execute` | Build / Release / Global | Append-only / Journal | Runtime execution logs, Ralph loop iteration records, gate attestation history, and state machine audit trails. |

*(Supplementary extensions such as `skills/` and `testing/` are supported for project-local customizations and automated verification caches).*

---

## 3. Detailed Area Specifications

### 3.1 `archive/`
- **Owner**: `skillweave-releasechain` and `skillweave-repo-health`
- **Lifecycle**: Release (Phase 5), Post-Release (Phase 7)
- **Role**: Serves as a deterministic vault for obsolete runs, retired sequences, and superseded manifests. Ensures project history is preserved without polluting active working directories.
- **Key Artifacts**: `manifest.yaml`, dated archive bundles.

### 3.2 `bundles.yaml`
- **Owner**: `skillweave-lifecycle`
- **Lifecycle**: Global / Setup
- **Role**: Defines pre-packaged lifecycle pathways combining selected phases. Allows projects to execute lean subsets (e.g. `discovery-to-blueprint` or `design-and-build`) without enforcing all 7 phases.
- **Key Schema**: List of bundle entries with `id`, `name`, `phases`, and `entry_requires`.

### 3.3 `checklists/`
- **Owner**: `skillweave-promptchain-execute` and `skillweave-releasechain`
- **Lifecycle**: Build (Phase 4), Release (Phase 5)
- **Role**: Maintains machine-checkable and human-verifiable rubrics. Used before triggering binary release gates.
- **Key Artifacts**: `release-readiness.md`, `sample-execution.md`.

### 3.4 `cleanup/`
- **Owner**: `skillweave-repo-health`
- **Lifecycle**: Post-Release (Phase 7) & Global
- **Role**: Houses codebase classification outputs, duplication detection matrices, dead code inventories, and lean-core reduction recommendations.
- **Key Artifacts**: `inventory.yaml`, `classifications.yaml`, `duplications.yaml`, `lean-core.yaml`, `report.md`.

### 3.5 `config.yaml`
- **Owner**: Core Runtime and `skillweave-lifecycle`
- **Lifecycle**: Global / Project Initialization
- **Role**: Central declarative configuration controlling execution behavior, active bundles, lens strictness, risk mode (`conservative`, `medium`, `unicorn`), feature flags, and git flow rules.
- **Key Schema**: `features`, `lifecycle`, `lens`, `mode`, `git_flow`, `release`.

### 3.6 `design/`
- **Owner**: `skillweave-design`
- **Lifecycle**: Design (Phase 3)
- **Role**: Holds UX guidelines, design tokens, interaction flows, accessibility evaluations, and frontend architecture critiques.
- **Key Artifacts**: `tokens.json`, `design-critique.md`, `wireframes.yaml`.

### 3.7 `discovery/`
- **Owner**: `skillweave-discovery` and `skillweave-council`
- **Lifecycle**: Discovery (Phase 1)
- **Role**: Stores problem validation evidence, stakeholder interviews, competitor matrices, opportunity canvases, and multi-model council strategy syntheses.
- **Key Artifacts**: `*-council-strategy.md`, `opportunity-canvas.md`, `user-interviews.md`.

### 3.8 `handover/`
- **Owner**: `skillweave-lifecycle` and `skillweave-observe`
- **Lifecycle**: Cross-Cutting / Global
- **Role**: Manages continuity between autonomous agent sessions, developer shifts, and cross-lane handoffs.
- **Key Artifacts**: `README.md`, `session-handover-*.md`.

### 3.9 `hooks/`
- **Owner**: Core Runtime and `skillweave-promptchain-execute`
- **Lifecycle**: Global / Execution
- **Role**: Houses lifecycle event hooks (e.g. `pre-execute`, `post-execute`, `on-gate-failure`) for custom automation and integration.
- **Key Artifacts**: Executable scripts and YAML hook declarations.

### 3.10 `lenses/`
- **Owner**: `skillweave-discovery` and `skillweave-design`
- **Lifecycle**: Discovery (Phase 1), Design (Phase 3)
- **Role**: Configures cognitive and domain lenses applied during planning and ideation.
- **Key Artifacts**: `design-thinking.yaml`, custom lens profiles.

### 3.11 `lib/`
- **Owner**: Core Runtime / Project Domain
- **Lifecycle**: Global
- **Role**: Contains project-local Python helper libraries and domain modules (e.g. assumption prioritization models, ideation ranking logic) consumed by prompt chains.
- **Key Artifacts**: `assumptions.py`, `ideation.py`.

### 3.12 `licenses/`
- **Owner**: `skillweave-repo-health` and `skillweave-releasechain`
- **Lifecycle**: Release (Phase 5) & Global
- **Role**: Maintains dependency license inventories, third-party attribution notices, and legal compliance audits.
- **Key Artifacts**: `license-audit.json`, `attribution.md`.

### 3.13 `lifecycle/`
- **Owner**: `skillweave-lifecycle`
- **Lifecycle**: Global
- **Role**: Holds dynamic lifecycle state machine definitions, custom phase transitions, and lifecycle hook configurations.
- **Key Artifacts**: `state-machine.yaml`, `custom-phases.yaml`.

### 3.14 `manifesto/`
- **Owner**: `skillweave-blueprint` / Core Governance
- **Lifecycle**: Global / Inception
- **Role**: Defines the fundamental mission, core architectural values, non-functional requirements, and ethical guardrails of the project.
- **Key Artifacts**: `README.md`, `principles.yaml`.

### 3.15 `memory/`
- **Owner**: `skillweave-observe` and `skillweave-promptchain-execute`
- **Lifecycle**: Global / Continuous
- **Role**: Central repository of persistent architectural knowledge, conventions, active decisions, and unsolved issues.
- **Key Artifacts**: `architecture.yaml`, `conventions.yaml`, `decisions.yaml`, `open-issues.yaml`, `rules.yaml`.

### 3.16 `onboarding-state.yaml`
- **Owner**: `skillweave-lifecycle` / CLI
- **Lifecycle**: Setup / Onboarding
- **Role**: Tracks user progress through interactive CLI onboarding, completed tutorials, and active learning paths.
- **Key Schema**: `current_step`, `completed_tutorials`, `last_updated`.

### 3.17 `phases.yaml`
- **Owner**: `skillweave-lifecycle`
- **Lifecycle**: Global / Setup
- **Role**: The authoritative single source of truth for the 7 canonical lifecycle phases, their numeric order, associated skills, required capabilities, and phase strictness (`core`, `recommended`, `optional`).
- **Key Schema**: `phases` list with `id`, `order`, `skills`, `capabilities`, `phase_type`, and `global_skills`.

### 3.18 `planning/`
- **Owner**: `skillweave-blueprint` and `skillweave-lifecycle`
- **Lifecycle**: Blueprint (Phase 2), Build (Phase 4)
- **Role**: File-based Kanban planning board using the beans-pattern. Contains ticket files in `backlog/`, `doing/`, and `done/` with YAML frontmatter.
- **Key Artifacts**: `backlog/*.md`, `doing/*.md`, `done/*.md`.

### 3.19 `prds/`
- **Owner**: `skillweave-blueprint`
- **Lifecycle**: Blueprint (Phase 2)
- **Role**: Stores formal Product Requirements Documents. Each initiative directory contains structured `prd.json` and narrative `prd.md`.
- **Key Artifacts**: `initiative-*/prd.json`, `initiative-*/prd.md`, `v*/*-prd.md`.

### 3.20 `prompts/`
- **Owner**: `skillweave-promptchain-generate` and `skillweave-discovery`
- **Lifecycle**: Discovery (Phase 1), Blueprint (Phase 2), Build (Phase 4)
- **Role**: Catalog of phase-tailored prompt templates, persona cards, and structured extraction instructions.
- **Key Artifacts**: `discovery/*.md`, `design/*.md`, `build/*.md`.

### 3.21 `release/`
- **Owner**: `skillweave-releasechain`
- **Lifecycle**: Release (Phase 5)
- **Role**: Governs release verification criteria, gate policies, and skill boundary constraints.
- **Key Artifacts**: `readiness-model.yaml`, `skill-boundaries.yaml`.

### 3.22 `reports/`
- **Owner**: `skillweave-observe` and `skillweave-launch`
- **Lifecycle**: Post-Release (Phase 7), Launch (Phase 6), Observability
- **Role**: Stores generated execution summaries, timing benchmarks, gate receipts, and retrospective syntheses.
- **Key Artifacts**: `execution-report-*.json`, `benchmark-summary.md`.

### 3.23 `sequences/`
- **Owner**: `skillweave-promptchain-generate` and `skillweave-promptchain-validate`
- **Lifecycle**: Blueprint (Phase 2), Build (Phase 4)
- **Role**: Houses machine-executable prompt sequences, complexity assessments, and role assignment matrices.
- **Key Artifacts**: `initiative-*/execution-sequences.yaml`, `initiative-*/complexity-analysis.md`, `initiative-*/agent-assignments.json`.

### 3.24 `specs/`
- **Owner**: `skillweave-blueprint` and `skillweave-promptchain-generate`
- **Lifecycle**: Blueprint (Phase 2)
- **Role**: Stores technical interface specifications, task backlogs, and subsystem contract definitions.
- **Key Artifacts**: `backlog.yaml`, `README.md`, `api-spec.yaml`.

### 3.25 `templates/`
- **Owner**: `skillweave-blueprint` and `skillweave-promptchain-generate`
- **Lifecycle**: Blueprint (Phase 2) / Setup
- **Role**: Reusable starter templates for project scaffolding (APIs, CLI tools, web apps, validation sheets, discovery tools).
- **Key Artifacts**: `api_service_starter.yaml`, `cli_tool_starter.yaml`, `web_app_starter.yaml`, `prompt-sequence-template.md`.

### 3.26 `tracking-log/`
- **Owner**: `skillweave-observe` and `skillweave-promptchain-execute`
- **Lifecycle**: Build (Phase 4), Release (Phase 5), Global
- **Role**: Authoritative chronological execution log and state store. Records Ralph Loop iterations, prompt inventory, gate validation records, and run receipts.
- **Key Artifacts**: `iterations.yaml`, `execution-state.json`, `status.yaml`.

---

## 4. Lifecycle Flow and Substrate Progression

The 7 lifecycle phases interact with `.skillweave/` areas in strict sequential order while cross-cutting areas maintain continuous governance:

```
Phase 1: Discovery  ──► .skillweave/discovery/, lenses/, prompts/discovery/
      │
Phase 2: Blueprint  ──► .skillweave/prds/, specs/, sequences/, planning/, templates/
      │
Phase 3: Design     ──► .skillweave/design/, lenses/
      │
Phase 4: Build      ──► .skillweave/sequences/, checklists/, tracking-log/
      │
Phase 5: Release    ──► .skillweave/release/, checklists/, archive/, licenses/
      │
Phase 6: Launch     ──► .skillweave/reports/
      │
Phase 7: Post-Rel   ──► .skillweave/cleanup/, archive/, reports/
```

### Cross-Cutting Substrates (Active in All Phases):
- **Configuration & Phasing**: `.skillweave/config.yaml`, `phases.yaml`, `bundles.yaml`, `onboarding-state.yaml`
- **Knowledge & Memory**: `.skillweave/memory/`, `manifesto/`, `handover/`, `hooks/`, `lib/`

---

## 5. Supplementary & Workspace Substrate Areas

The following areas under `.skillweave/` represent supplementary runtime artifacts, project-local extensions, and caching structures:

### 5.1 `bundles/`
- **Owner**: `skillweave-lifecycle`
- **Lifecycle**: Global / Setup
- **Role**: Directory containing unpacked or project-specific lifecycle bundle definition overrides and custom bundle manifests.
- **Key Artifacts**: Custom bundle configuration files and descriptors.

### 5.2 `docs/`
- **Owner**: `skillweave-lifecycle` / Documentation Subsystem
- **Lifecycle**: Global / Setup
- **Role**: Project-level substrate documentation, onboarding guidelines, and reference materials.
- **Key Artifacts**: `getting-started.md`, architecture summaries.

### 5.3 `observation/`
- **Owner**: `skillweave-observe`
- **Lifecycle**: Build (Phase 4) / Observability
- **Role**: Active telemetry collection, structured event streaming logs, and execution metric traces.
- **Key Artifacts**: `events/*.jsonl`, streaming traces.

### 5.4 `phases/`
- **Owner**: `skillweave-lifecycle`
- **Lifecycle**: Global / Setup
- **Role**: Directory containing custom, domain-specific phase definition schemas and extension manifests.
- **Key Artifacts**: Extended phase descriptors and lifecycle transitions.

### 5.5 `schemas/`
- **Owner**: Core Runtime / `skillweave-promptchain-execute`
- **Lifecycle**: Build (Phase 4), Release (Phase 5), Global
- **Role**: JSON schema specifications and validation contracts ensuring phase gate conformance and artifact structural integrity.
- **Key Artifacts**: `blueprint-ready.schema.json`, `build-complete.schema.json`, `deployed.schema.json`, `handover.schema.json`, `launch-ready.schema.json`.

### 5.6 `testing/`
- **Owner**: `skillweave-promptchain-execute` / Verification Subsystem
- **Lifecycle**: Build (Phase 4) / Verification
- **Role**: Automated verification configurations, temporary test execution workspaces, and gate validation results cache.
- **Key Artifacts**: `test-config.yaml`, `results/`.

### 5.7 `wizard/`
- **Owner**: `skillweave-lifecycle` / CLI
- **Lifecycle**: Setup / Inception
- **Role**: Interactive onboarding wizard scaffolds, project initialization state, and guided setup workflows.
- **Key Artifacts**: Wizard step state and scaffolding templates.

### 5.8 `catalogue.yaml`
- **Owner**: Core Runtime / Model & Harness Catalogue Subsystem
- **Lifecycle**: Global / Setup
- **Role**: Declares the model-and-harness catalogue (runtime CLI, harness statuses, model capabilities, role defaults, contract index), the single source of truth for role-to-model resolution and the `!= ops` separation-of-duties guard.
- **Key Artifacts**: `catalogue.yaml`.

---

## 6. Core Subsystem & Runtime Architecture Layout (SW-140)

SkillWeave core runtime and execution components are structured under `src/skillweave/`:

### 6.1 `src/skillweave/api/`
- **Owner**: Core Runtime / API Subsystem
- **Lifecycle**: Execution / Runtime
- **Role**: Programmatic entry points and service interfaces exposing execution capabilities, pipeline triggers, and lifecycle operations.
- **Key Artifacts**: `api/run.py`, `api/__init__.py`.

### 6.2 `src/skillweave/cli/`
- **Owner**: Core Runtime / CLI Subsystem
- **Lifecycle**: Cross-Cutting / Tooling
- **Role**: Command-line interface orchestration, argument parsing, interactive terminal commands, and command routing.
- **Key Artifacts**: `cli/main.py`, `cli/run.py`, `cli/__init__.py`.

### 6.3 `src/skillweave/core/proc/`
- **Owner**: Core Runtime / Process Subsystem
- **Lifecycle**: Build (Phase 4) / Execution
- **Role**: Low-level process execution management, async subprocess runners, isolation boundaries, and streaming process output capture.
- **Key Artifacts**: `core/proc/runner.py`, `core/proc/__init__.py`.

### 6.4 `src/skillweave/core/observer/`
- **Owner**: Core Runtime / Observer Subsystem
- **Lifecycle**: Execution / Runtime
- **Role**: Read-only tracking of execution events, maintaining persistent lease and journal offset, preventing unauthorized state mutation.
- **Key Artifacts**: `observer.py`, `__init__.py`.

### 6.5 `src/skillweave/core/context/`
- **Owner**: Core Runtime / Context Subsystem
- **Lifecycle**: Execution / Runtime
- **Role**: Context check-pointing, block-level provenance, and token threshold limits (`no_new_task`, `checkpoint`, `stop`).
- **Key Artifacts**: `checkpoint.py`, `config.py`, `limits.py`, `manager.py`.
### 6.6 `src/skillweave/core/recovery/`
- **Owner**: Core Runtime / Recovery Subsystem
- **Lifecycle**: Execution / Runtime
- **Role**: Reconstructs execution state (DAG, Claims, Gate) from the ReadOnlyObserver after crashes (Orphan, Worker, Coordinator).
- **Key Artifacts**: `manager.py`, `__init__.py`.
### 6.7 `src/skillweave/core/policy/`
- **Owner**: Core Runtime / Policy Subsystem
- **Lifecycle**: Execution / Runtime
- **Role**: Maintains persistent policy for execution retries, backoff schedules, budget tracking, and idempotent compensation.
- **Key Artifacts**: `policy.py`, `__init__.py`.
### 6.8 `src/skillweave/core/workspace/remote/`
- **Owner**: Core Runtime / Workspace Subsystem
- **Lifecycle**: Execution / Runtime
- **Role**: Provides Sandbox/Remote Workspace environments honoring the core Workspace contract, without introducing external orchestration truth.
- **Key Artifacts**: `provider.py`, `__init__.py`.

### 6.9 `src/skillweave/core/operator/`
- **Owner**: Core Runtime / Operator Subsystem
- **Lifecycle**: Execution / Runtime
- **Role**: Delegated autonomous operator agent capable of running reversible, in-scope decisions while strictly escalating irreversible actions.
- **Key Artifacts**: `operator_agent.py`, `__init__.py`.

### 6.10 `src/skillweave/core/catalogue/`
- **Owner**: Core Runtime / Model & Harness Catalogue Subsystem
- **Lifecycle**: Execution / Runtime
- **Role**: Parses the model & harness catalogue (`config/catalogue.yaml`) and resolves roles to models, honouring the `!= ops` separation-of-duties constraint and `cost_index` preference.
- **Key Artifacts**: `__init__.py`.
