---
name: skillweave-lifecycle
description: Bundle-Navigator, Phasen-Status, Entry-Point-Detection, Bundle-Empfehlung
argument-hint: command="[status|recommend|switch|phases]" bundle="[id]"
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
/skillweave-lifecycle command="status"                    # Current phase + bundle
/skillweave-lifecycle command="recommend"                 # Next recommended bundle
/skillweave-lifecycle command="phases"                    # List all 7 phases
/skillweave-lifecycle command="switch" bundle="full-lifecycle"  # Switch to bundle
```

## Commands

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

## Companion Files

- `references/phases-reference.md` — Full documentation of all 7 lifecycle phases
- `references/bundles-reference.md` — Full documentation of all 5 bundles
