# Changelog

## 1.0.0 — Forever Free
- **RELEASE**: SkillWeave v1.0.0 "Forever Free" — production-stable AI skill orchestration
- **FEATURE**: 5-level test pyramid (Lint → Unit → E2E Smoke → Acceptance → Evidence/Groundedness) with 3-state gate (PROMOTE/HOLD/ROLLBACK)
- **FEATURE**: File-based planning system (beans-pattern) — directory-as-state Kanban with YAML frontmatter tickets in `.skillweave/planning/{backlog,doing,done}/`
- **FEATURE**: Lifecycle Navigator with automatic phase detection from `.skillweave/` artifacts and intelligent next-step recommendations
- **FEATURE**: Progressive Disclosure architecture — Layer 0 (Wizard, 5 questions), Layer 1 (7 Meta-Commands), Layer 2 (13 Direct Skills)
- **FEATURE**: Handover signal validation with JSON schemas for skill-to-skill phase transitions
- **FEATURE**: Release report generation with date-stamped markdown templates
- **FEATURE**: Free/Studio tier boundary enforcement via `.skillweave/config.yaml`
- **IMPROVEMENT**: Council stability — structured JSON peer review, CouncilDegradedError, 60s/180s timeouts, graceful degradation with partial results
- **FIX**: Council Faigate port mismatch (8092 → 8090) causing OpenCode instability
- **FIX**: `normalize_manifest` always uses `pyproject.toml` version for skill manifests
- **IMPROVEMENT**: SerpApi and Perplexity MCP search provider support
- **IMPROVEMENT**: Google CSE provider removed (API deprecated by Google)
- **DOCS**: Unified getting-started guide for 3 personas (Power User, Indie Hacker, Non-Technical)
- **DOCS**: Complete reference docs for plan commands, testing flow, navigator detection, meta-commands, wizard flow
- **LICENSE**: Copyright updated to LangeVC.com, Apache 2.0 confirmed

## 0.7.0
- **FEATURE**: 6 new agent-facing skills after promptchain pattern (SKILL.md + capability.yaml + sequence_type)
  - `skillweave-lifecycle` (plan): Bundle-Navigator, Phasen-Status, Entry-Point-Detection
  - `skillweave-discovery` (plan): Problemdefinition, User Research, Empathy Mapping, 11 Prompts
  - `skillweave-design` (mixed): Design-Thinking-Lens, Briefanalyse, Token-Extraktion, Evaluation
  - `skillweave-launch` (build): Pre-Launch-Check, Deployment-Koordination, Announce, Metrics-Vergleich
  - `skillweave-post-release` (mixed): Retrospektive, Feedback-Sammlung, Iterationsplanung
  - `skillweave-repo-health` (plan): Inventory-Scan, 5-Class-Klassifikation, Archive, Dedup, Hygiene-Report
  - `skillweave-observe` (plan): Execution Reports, Timing, Events, Memory — Read-Only Observability
- **FEATURE**: Launch infrastructure (src/skillweave/launch/)
  - `deployment.py`: GitHub Actions workflow_dispatch-Trigger, Health-Check, Rollback-Plan
  - `announce.py`: Release Notes Generator aus CHANGELOG.md, Multi-Channel-Formatting
  - `metrics.py`: Pre/Post-Launch-Metriken, Snapshot-Vergleich mit Delta-Report
- **FEATURE**: Post-Release infrastructure (src/skillweave/post_release/)
  - `retrospective.py`: Strukturierte Retro-Vorlage (Went Well / To Improve / Action Items P1-P3)
  - `feedback.py`: GitHub Issues-Feedback-Sammlung, Kategorisierung (bug/feature/improvement/question)
  - `iteration.py`: Backlog-Generator aus Retro + Feedback, Prioritäts-Scoring
- **FEATURE**: Repo-Health infrastructure (src/skillweave/repo_health/)
  - `scanner.py`: Inventory-Scan mit Typ, Größe, last_modified
  - `classifier.py`: 5-category rules-based classification (Active Core / Consolidation / Legacy / Deprecated / Needs Review)
  - `dedup.py`: MD5-Exact + Fuzzy-Content-Duplikatserkennung
  - `archive.py`: Move + Restore mit JSON-Manifest, dry_run-Pflicht
  - `report.py`: Hygiene-Score (A-F) mit konkreten Empfehlungen
- **FEATURE**: phases.yaml — alle 7 Phasen mit Skills + promptchain_types + global_skills-Sektion
- **FEATURE**: bundles.yaml — 5 Bundles mit sequence_types_used + entry_requires + estimated_effort
- **FEATURE**: Installer auf 13 Skills aktualisiert (12 SkillWeave + frontend-design)
- **FEATURE**: Design-Skill references: 5 UX-Prinzipien, 6 Workshop-Regeln, Token-Format, Elementify-Integration
- **FEATURE**: Lifecycle-Skill references: 7 Phasen mit Entry/Exit-Conditions, 5 Bundles mit Recommendation-Matrix
- **IMPROVEMENT**: Alle neuen Skills haben sequence_type (plan/mixed/build) für promptchain-generate-Kompatibilität
- **IMPROVEMENT**: Discovery-Skill mit 11 Prompts in 4 Gruppen (Empathy, Research, Framing, Output)
- **IMPROVEMENT**: Legacy prompt-chain aus Installer-Tabelle entfernt (nie existiert, kein Effekt)
- **IMPROVEMENT**: Release-Naming-Convention in auto-tag-release.yml enforced (SkillWeave vX.Y.Z)

## 0.6.0
- **FEATURE**: 7-phase lifecycle model with entry/exit conditions and bundle system (Initiative 01)
- **FEATURE**: Discovery prompt library (11 prompts) and Design Thinking Lens (Initiative 02)
- **FEATURE**: Release readiness assessment, premature invocation detection, Launch skill separation (Initiative 03)
- **FEATURE**: Repo cleanup, dead code removal, archive with restore manifest (Initiative 04)
- **FEATURE**: Execution system with Ralph Loop state machine, batch planner, retry, gate policy, observation layer, execution memory, sidecar manager (Initiative 05)
- **FEATURE**: GitHub Action workflows (11 workflows), GitHub integration layer, auto-tag, auto-changelog, auto-issue, auto-PR, auto-docs-sync, release readiness gate (Initiative 06)
- **FEATURE**: Phase-aware onboarding flow with state persistence
- **FEATURE**: Phase boundary enforcement (soft) with violation logging
- **FEATURE**: Ideation module (quantity-first, wild ideas, separate evaluation)
- **FEATURE**: Assumption tracking with risk scoring and validation status
- **FEATURE**: Iteration quality framework with evidence-driven revision
- **FEATURE**: Release workflow with 5 gated sequential steps
- **FEATURE**: Launch skill placeholder with separate lifecycle phase
- **FEATURE**: Capability-based GitHub Actions (workflow-inventory, auto-tag, auto-release, auto-changelog, auto-issue, auto-PR, auto-docs-sync, release-readiness-gate, integration-test, auto-release-notes)
- **IMPROVEMENT**: promptchain-execute redefined as orchestration substrate (release logic moved to releasechain)
- **IMPROVEMENT**: All 510 tests passing across full system

## 0.5.6
- **FEATURE**: Capacium badge and install section in README
- **FEATURE**: Content boundary enforcement for release artifacts (AGENTS.md + prerelease.yml)
- **IMPROVEMENT**: Version bump to 0.5.6 with updated documentation

## 0.5.0
- **RELEASE**: SkillWeave Next Level Features v0.5.0
- **FEATURE**: Three risk modes (conservative, medium, unicorn) across all skills
- **FEATURE**: .skillweave folder structure with config, tracking, manifesto
- **FEATURE**: Persistent state manager with session recovery
- **FEATURE**: Configuration manager with mode interpretation
- **FEATURE**: GitHub Issues integration with Planning Poker estimation
- **FEATURE**: Backlog synchronization with .skillweave tracking
- **FEATURE**: Optional checklist execution with markdown checkbox tracking
- **FEATURE**: Optional Design-Thinking Lens for UI/UX decisions
- **FEATURE**: Enhanced capability-based routing with dynamic agent detection
- **FEATURE**: Modular templates foundation with example templates
- **FEATURE**: Community know-how prototype for pattern extraction
- **FEATURE**: Comprehensive testing suite with 100+ tests
- **FEATURE**: Updated documentation with configuration guide and examples
- **FEATURE**: Capacium packaging for all skills - each skill ships as a self-contained capability.yaml for cap install
- **IMPROVEMENT**: All Next Level features fully tested and integrated

## 0.4.4
- **FEATURE**: Execute Skill v2 – Ralph Loop state machine with binary gates, batch planning, and safe parallelization
- **FEATURE**: Two-axis model for generate – separates `sequence_type` (plan/build/mixed) from `execution_mode` (rex/ralph_attended/ralph_overnight)
- **FEATURE**: Enhanced validate – checks parallelization readiness and separation of critical path vs sidecar lanes
- **NEW**: Three reference files for execute – `ralph-loop-state-machine.md`, `build-step-normalization.md`, `gate-policy.md`
- **IMPROVEMENT**: Execute now enforces write-scope ownership, safe parallel lanes, and binary completion signals
- **IMPROVEMENT**: Generate includes mode mapping table with 9 combinations (plan/build/mixed × rex/ralph_attended/ralph_overnight)
- **IMPROVEMENT**: Validate now identifies single-owner surfaces and integration gate requirements

## 0.4.3
- **FIX**: Installed `skillweave-blueprint` for supported agents so Codex and related tools see the full five-skill SkillWeave set
- **FIX**: Cleaned up legacy SkillWeave duplicates under `~/.agents/skills` to prevent duplicate promptchain entries with stale descriptions
- **FIX**: Source/Target directory separation – installer now copies skills from development repo to `~/.skillweave` installation directory
- **FIX**: Removed duplicate git repository from `~/.skillweave` (target directory should be plain folder, not a git repo)
- **FIX**: Added warning when target directory is a git repository with cleanup instructions
- **NEW**: `update-local-skills.sh` script for developers to sync changes from development repo to installation
- **IMPROVEMENT**: Installer automatically copies skills from source to target when run from development repository
- **IMPROVEMENT**: Better logging and dry-run output for copying operations

## 0.4.2
- **FEATURE**: Interactive installer with agent selection modes (`--interactive`, `--uninstall`, `--update`, `--troubleshoot`)
- **FIX**: Correct agent paths for Gemini CLI (`~/.gemini/skills`) and Qwen Code (`~/.qwen/skills`)
- **FIX**: Prevent creating directories for non-existent agents (no "file-leichen")
- **IMPROVEMENT**: Smart agent detection with numeric selection, `all`, or `none` options
- **DOCS**: Updated README with interactive installation section and corrected agent paths

## 0.4.1
- **DOCS**: Complete README overhaul with "Product development flow on steroids" branding
- **DOCS**: Added DEVELOPMENT_WORKFLOW.md with standardized release process
- **DOCS**: Release conventions and "SkillWeave vX.Y.Z" naming standardization
- **IMPROVEMENT**: ASCII workflow diagram and enhanced architecture documentation
- **IMPROVEMENT**: Repository structure updates and clearer onboarding guidance

## 0.4.0
- **FEATURE**: Blueprint Skill (`/skillweave-blueprint`) for structured PRD creation
- **FEATURE**: Enhanced Execute Skill with parallel execution and dependency analysis
- **FEATURE**: Enhanced ReleaseChain Skill with dual-mode (REX/Ralph Loop) execution
- **ARCHITECTURE**: Parallel execution core with dependency graph analysis
- **ARCHITECTURE**: Capability-based agent-agnostic design for any AI coding agent
- **DOCS**: Full workflow example and comprehensive testing suite
- **PERFORMANCE**: Optimizations for large projects (50+ tasks)

## 0.3.5
- **FEATURE**: Intelligent `skillweave-promptchain-execute` with plan/build/mixed mode detection
- **NEW**: `skillweave-releasechain` development pipeline skill
- Execute skill now detects sequence type and adapts outputs accordingly
- Post-execution options: target audience (humanize/machinize/mixed)
- Build components can trigger automated development pipeline
- Releasechain handles: review, testing, iteration, commit, push, PR, release, changelog
- Better integration between execute and releasechain skills

## 0.3.4
- **IMPROVEMENT**: Enhanced `skillweave-promptchain-validate` with better output handling
- Added user prompts for output format: Validation Report, Improved sequence only, Both separate files
- Added sequence type detection: plan mode, build mode, mixed
- Improved sequence must be complete (no placeholder references)
- Output format adaptation based on sequence type
- Better documentation of validation interaction process

## 0.3.3
- **FEATURE**: Attachment detection for `skillweave-promptchain-execute` and `skillweave-promptchain-validate`
- Skills now accept prompt sequences as .md/.txt file attachments
- Updated descriptions, usage examples, and parameters
- Added attachment detection logic description
- Clarified that generate uses parameters only (no attachments)

## 0.3.2
- **FIX**: YAML parsing in `skillweave-promptchain-execute` argument-hint
- Changed `inputs='{\"key\": \"value\"}'` to `inputs=\"[JSON]\"` to avoid YAML parser errors
- Fixes Codex and other agent compatibility issues

## 0.3.1
- **FIX**: Multi-agent installer with correct paths and formats for all agents
- **FIX**: Opencode installation as single `.md` files to `~/.config/opencode/commands/`
- **FIX**: Claude Code/Codex/Antigravity paths to correct locations (`~/.claude/skills/`, `~/.codex/skills/`, `~/.antigravity/skills/`)
- **FIX**: Different installation formats per agent type (single files vs directories)
- **FIX**: Updated README with correct manual installation instructions
- **IMPROVEMENT**: Better error handling and logging in installer script

## 0.3.0
- separate skill directories for each command: `skillweave-promptchain-generate`, `-validate`, `-execute`
- initial multi-agent installer script (had incorrect paths for some agents)
- license changed from MIT to Apache 2.0
- initial README updates for multi-agent installation

## 0.2.0
- new `skillweave-promptchain` skill with direct `/skillweave-*` commands
- `/skillweave-promptchain-generate`, `-validate`, `-execute` commands
- improved README with new installation instructions
- updated multi-agent quickstart section

## 0.1.0
- initial repository structure
- first `prompt-chain` skill
- initial docs
- initial schemas
- initial parser, validator, orchestrator, executor
- first examples and templates
