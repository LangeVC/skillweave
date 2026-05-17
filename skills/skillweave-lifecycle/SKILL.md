---
name: skillweave-lifecycle
description: Bundle-Navigator, Phasen-Status, Entry-Point-Detection, Bundle-Empfehlung, Planning-Board, Testing
argument-hint: command="[status|recommend|switch|phases|plan|test]" bundle="[id]"
---

# /skillweave-lifecycle

**Bundle-Navigator, Phasen-Status und Workflow-Empfehlung.**  
Ermittelt die aktuelle Projektphase, navigiert zwischen Phasen/Bundles und empfiehlt den optimalen nächsten Workflow basierend auf Entry Conditions und Confidence-Scoring.

## Mandatory Pre-Flight: SkillWeave Sandboxing

Before generating any output, verify and enforce the SkillWeave sandbox:

### 1. Enforce `.skillweave/` Directory Structure
If `.skillweave/` does not exist, create it:
```
.skillweave/
.skillweave/tracking-log/
.skillweave/templates/
.skillweave/sequences/
.skillweave/phases/
.skillweave/bundles/
```

### 2. Route All Outputs Into `.skillweave/`
All lifecycle reports, phase transitions, bundle recommendations, and navigation logs MUST be saved under `.skillweave/phases/` or `.skillweave/bundles/`.

### 3. Git Isolation
Ensure `.skillweave/` is listed in `.gitignore`.

### 4. Default Config
If `.skillweave/config.yaml` does not exist, create it with lifecycle defaults.

Proceed only after these four criteria are met.

## Usage

```
# Navigator & Status
/skillweave-lifecycle command="status"                    # Current phase + bundle + recommendation
/skillweave-lifecycle command="recommend"                 # Next recommended bundle/action
/skillweave-lifecycle command="phases"                    # List all 7 phases
/skillweave-lifecycle command="switch" bundle="full-lifecycle"  # Switch to bundle

# Planning Board
/skillweave-lifecycle command="plan"                      # Show planning board
/skillweave-lifecycle command="plan" action="create" title="My Task" priority="high" type="feature"
/skillweave-lifecycle command="plan" action="move" id="FEAT-001" target="doing"
/skillweave-lifecycle command="plan" action="show" id="FEAT-001"
/skillweave-lifecycle command="plan" action="seed" prd=".skillweave/prds/v1.0/prd.json"

# Testing
/skillweave-lifecycle command="test"                      # Run all test levels
/skillweave-lifecycle command="test" level="unit"         # Run specific level
/skillweave-lifecycle command="test" action="results"     # Show latest results

# Wizard & Reports
/skillweave-lifecycle command="wizard"                    # 5-question guided entry (Layer 0)
/skillweave-lifecycle command="report"                    # Show latest release report
/skillweave-lifecycle command="report" action="generate"  # Generate report from current state
/skillweave-lifecycle command="report" action="list"      # List all reports
```

## Commands

### `command="plan"`

File-based planning system using the beans-pattern (Markdown tickets with YAML frontmatter in directory-as-state). Provides Kanban-style workflow tracking without external tools.

#### Actions

| Action | Description | Parameters |
|--------|-------------|------------|
| *(none)* | Show ASCII board summary | — |
| `create` | Create new ticket | `title`, `priority`, `type`, `depends_on` |
| `move` | Transition ticket between states | `id`, `target` (backlog/doing/done) |
| `show` | Show single ticket detail | `id` |
| `seed` | Auto-create tickets from prd.json | `prd` (path to prd.json) |
| `board` | Regenerate BOARD.md | — |

#### Directory Structure

```
.skillweave/planning/
├── BOARD.md           # Auto-generated overview (regenerated on changes)
├── backlog/           # Tickets not yet started
│   ├── FEAT-001.md
│   └── ...
├── doing/             # Tickets in progress
│   └── FEAT-002.md
└── done/              # Completed tickets (with completion timestamp)
    └── INFRA-001.md
```

#### Ticket Format

Each ticket is a Markdown file with YAML frontmatter:

```yaml
---
id: FEAT-001
title: "Multi-Level Testing Flow"
status: backlog
priority: high          # high | medium | low
type: feature           # feature | bugfix | infrastructure | qa | documentation
created: 2026-05-17
completed:              # Set when moved to done/
week: 2                 # Target week
depends_on: [INFRA-001]
estimated_effort: 8     # Hours
---

Description of the task.

## Acceptance Criteria

- [ ] Criterion 1
- [ ] Criterion 2
```

#### ID Generation

New tickets receive sequential IDs based on type:
- Features: `FEAT-NNN`
- Infrastructure: `INFRA-NNN`
- Bugs: `BUG-NNN`
- QA: `QA-NNN`
- Documentation: `DOC-NNN`

The next available number is determined by scanning existing tickets across all states.

#### BOARD.md Auto-Generation

After any `create`, `move`, or `seed` action, BOARD.md is regenerated with:
- Summary counts (Backlog / Doing / Done)
- Tables for each state sorted by priority then ID
- Critical path visualization
- Week plan showing scheduled work

#### Seeding from prd.json

`action="seed"` reads a prd.json file and creates one ticket per task entry:
- Maps `id`, `title`, `description`, `acceptanceCriteria`, `priority`, `type`, `dependsOn`, `estimatedEffort`, `week`
- Skips tickets that already exist (by ID)
- Regenerates BOARD.md after seeding

#### Integration with ReleaseChain

When ReleaseChain starts a task, the corresponding ticket is moved to `doing/`.
When ReleaseChain completes a task (gate = PROMOTE), the ticket moves to `done/` with `completed` timestamp set.

---

### `command="test"`

Multi-level testing engine with 5-level pyramid and 3-state gate decisions. Runs automatically during ReleaseChain verify steps or manually via `/skillweave test`.

#### Parameters

| Parameter | Values | Default | Description |
|-----------|--------|---------|-------------|
| `level` | lint, unit, e2e_smoke, acceptance, evidence | *(all)* | Run specific level only |
| `action` | run, results | run | Show results instead of running |
| `run` | run-id | *(latest)* | Specific run to display |

#### Test Levels (Pyramid)

| Level | Trigger | Gate Weight |
|-------|---------|-------------|
| 1. Lint/TypeCheck | After code generation | 15% |
| 2. Unit Tests | After code generation | 30% |
| 3. E2E Smoke | Before release gate | 25% |
| 4. Acceptance | Before release gate | 20% |
| 5. Evidence/Groundedness | After Council output | 10% |

#### Gate Decision (3-State)

| Gate | Condition | Action |
|------|-----------|--------|
| **PROMOTE** | All levels pass, coverage ≥ minimum | Proceed to next phase |
| **HOLD** | Minor regression, coverage below minimum, 1 evidence gap | Suggest fix, allow manual override |
| **ROLLBACK** | Unit tests fail, lint critical errors, E2E smoke fails, >50% criteria unmet | Block progression, require fix |

#### ReleaseChain Integration

Testing integrates at two Ralph Loop points:
1. **Verify step** (after Implement): Runs Lint + Unit → gate decides Fix/Retry vs Integrate
2. **Review Gate** (before Advance): Runs E2E Smoke + Acceptance → gate decides release readiness

#### Results Storage

Results stored as JSON at `.skillweave/testing/results/yyyy-mm-dd-run-N.json` with full per-level details, gate decision, and reasoning.

#### Configuration

See `.skillweave/testing/test-config.yaml` for level enable/disable, gate weights, thresholds, and language-specific commands.

See `references/testing-flow.md` for complete documentation.

---

### `command="status"`
Reports current project phase, active bundle (if any), entry/exit conditions status, and next recommended action. Reads `.skillweave/phases/current.yaml` and `.skillweave/bundles/active.yaml`.

### `command="phases"`
Lists all 7 lifecycle phases with their entry/exit conditions, skills used, and capabilities. Validates current phase against its entry conditions.

### `command="recommend"`
Analyzes project state and recommends a bundle based on:
- Current phase and completed milestones
- Entry requirements met vs. missing
- Estimated effort vs. remaining work
- Sequence types available

Returns: Bundle ID, Confidence Score (0.0–1.0), Begründung (reasoning), und nächster Schritt (next action).

### `command="switch" bundle="[id]"`
Transitions the project into the specified bundle. Validates that entry requirements for the bundle's first phase are met. Creates an active bundle record at `.skillweave/bundles/active.yaml` and a phase tracking file at `.skillweave/phases/current.yaml`.

### `command="wizard"`

5-question guided entry for non-technical users (Layer 0 / Progressive Disclosure).

Questions:
1. What do you want to do? (new idea / continue project / test / get feedback / release)
2. Context question based on answer (project name, domain, etc.)
3. Complexity hint (quick task / medium project / large project)
4. Preferred language (DE/EN)
5. Confirmation: "Soll ich [skill] starten?" (Shall I start [skill]?)

Routes to the correct Layer 2 skill with pre-filled parameters.

### `command="report"`

Generate or view structured release reports.

| Action | Description |
|--------|-------------|
| *(none)* | Show latest report |
| `generate` | Generate report from current build state |
| `list` | List all reports in `.skillweave/reports/` |

#### Report Naming Convention

All reports follow: `yyyy-mm-dd-topic.md`

Examples:
- `2026-05-17-v1.0-release.md`
- `2026-05-17-council-opencode-diagnosis.md`
- `2026-05-20-sprint-retrospective.md`

#### Report Generation

When `action="generate"`, reads:
- Latest test results from `.skillweave/testing/results/`
- Planning board state from `.skillweave/planning/`
- Handover signals from `.skillweave/handover/`
- Git log since last report

Produces a report using the template at `.skillweave/templates/release-report.md` with sections: Executive Summary, Changes, Metrics, Key Decisions, Known Issues, Next Steps.

## Bundle-Vorschlag (Recommendation Engine)

When `command="recommend"` is used, the skill evaluates all 5 bundles against the current project state:

### Confidence-Score (0.0–1.0)
Calculated from weighted criteria:
- **Entry Requirements Met** (weight: 0.4) — percentage of satisfied entry conditions
- **Sequence Type Compatibility** (weight: 0.3) — match between available sequence types and bundle requirements
- **Phase Continuity** (weight: 0.2) — how naturally the bundle follows from the current phase
- **Historical Fit** (weight: 0.1) — pattern match from past `.skillweave/tracking-log/` entries

### Begründung
Each recommendation includes a plain-text explanation:
- Warum dieses Bundle zum aktuellen Status passt
- Welche Entry Conditions erfüllt/nicht erfüllt sind
- Welcher Sequence Type empfohlen wird
- Nächster konkreter Schritt

### Example Output
```
Bundle: full-lifecycle
Confidence: 0.87
Begründung: Projekt befindet sich in Discovery (Phase 1/7) ohne aktives Bundle.
             Entry Conditions "Problem statement" erfüllt. Full-Lifecycle deckt
             alle verbleibenden Phasen ab. Empfohlener Sequence Type: mixed.
Nächster Schritt: Switch zu full-lifecycle, dann PromptChain aus PRD generieren.
```

## Integration mit phases.yaml + bundles.yaml

The skill reads and writes structured data in YAML format:

### `.skillweave/phases/current.yaml`
```yaml
phase: discovery
started: 2026-04-01
entry_conditions:
  problem_statement: true
  stakeholder_identified: true
exit_conditions:
  validated_problem: false
  opportunity_assessment: false
```

### `.skillweave/bundles/active.yaml`
```yaml
bundle: full-lifecycle
phases: [discovery, blueprint, design, build, release, launch, post-release]
current_phase_index: 0
started: 2026-04-01
```

## Sandbox-Preflight

Upon invocation, the skill MUST:
1. Check `.skillweave/` structure exists (create if missing)
2. Check `.gitignore` for `.skillweave/` exclusion
3. Check `.skillweave/config.yaml` for lifecycle defaults
4. Check `.skillweave/phases/` and `.skillweave/bundles/` exist
5. Load `phases/current.yaml` and `bundles/active.yaml` if present
6. Determine invocation mode based on `command` parameter

If any preflight step fails, abort and report the issue before proceeding.

## Testing

The following scenarios should be verified:

- **Bundle-Empfehlung für Discovery-Phase**: Recommend a bundle when the project is in Discovery with no active bundle. Expected: full-lifecycle or discovery-to-blueprint with Confidence > 0.7.
- **Bundle-Empfehlung für Build-Phase**: Recommend a bundle when working code exists and phases indicate Build is active. Expected: release-and-launch or design-and-build.
- **Alle 7 Phasen werden angezeigt**: `command="phases"` lists all seven phases with entry/exit conditions.
- **Confidence-Score wird berechnet**: Every recommendation includes a numeric Confidence-Score (0.0–1.0) with Begründung.
- **Plan: Board anzeigbar**: `command="plan"` produces readable board summary with counts per state.
- **Plan: Ticket erstellen**: `command="plan" action="create" title="Test"` creates ticket with next available ID.
- **Plan: Ticket verschieben**: `command="plan" action="move" id="FEAT-001" target="doing"` moves file between directories and updates frontmatter status.
- **Plan: Seed from PRD**: `command="plan" action="seed" prd="path/to/prd.json"` creates all tickets and generates BOARD.md.
- **Plan: BOARD.md regeneriert**: After any mutation, BOARD.md reflects current state.

## Companion Files

- `references/phases-reference.md` — Full documentation of all 7 lifecycle phases
- `references/bundles-reference.md` — Full documentation of all 5 bundles
- `references/plan-commands.md` — File-based planning system (beans-pattern) commands and integration
- `references/testing-flow.md` — Multi-level testing pyramid, gate logic, and ReleaseChain integration
- `references/navigator-detection.md` — Phase auto-detection algorithm and recommendation engine
- `references/meta-commands.md` — 7 meta-commands (Layer 1) with routing logic
