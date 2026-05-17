# Lifecycle Navigator — Phase Detection & Recommendation

## Phase Detection Algorithm

The navigator auto-detects the current lifecycle phase by scanning `.skillweave/` for phase-indicative artifacts. Detection runs on every `/skillweave` or `/skillweave-lifecycle command="status"` invocation.

### Artifact → Phase Mapping

| Artifact Present | Phase Detected | Confidence |
|-----------------|---------------|------------|
| `.skillweave/discovery/discovery-report.md` | discovery (completed) | 0.95 |
| `.skillweave/discovery/problem-exploration.md` only | discovery (in-progress) | 0.80 |
| `.skillweave/prds/*/prd.json` | blueprint (completed) | 0.95 |
| `.skillweave/prds/*/prd.md` without prd.json | blueprint (in-progress) | 0.70 |
| `.skillweave/sequences/*/execution-sequences.yaml` | blueprint → build transition | 0.90 |
| `.skillweave/design/` with token files | design (completed) | 0.85 |
| `.skillweave/planning/doing/*.md` (non-empty) | build (in-progress) | 0.90 |
| `.skillweave/planning/done/*.md` count > 50% of total | build (near-complete) | 0.85 |
| `.skillweave/testing/results/*.json` with PROMOTE | release-ready | 0.90 |
| `.skillweave/handover/build-complete-*.json` | release | 0.95 |
| `.skillweave/handover/launch-ready-*.json` | launch | 0.95 |
| `.skillweave/handover/deployed-*.json` | post-release | 0.95 |
| No `.skillweave/` or empty | pre-discovery | 1.0 |

### Detection Priority (highest wins)

1. Handover signals (most authoritative — explicit phase transitions)
2. Planning board state (doing/done ratios)
3. PRD existence
4. Discovery artifacts
5. Empty state (pre-discovery)

### Compound Detection Rules

```
IF handover/deployed-*.json EXISTS:
  phase = post-release (0.95)
ELIF handover/launch-ready-*.json EXISTS:
  phase = launch (0.95)
ELIF handover/build-complete-*.json EXISTS:
  phase = release (0.95)
ELIF planning/doing/ HAS tickets AND testing/results/ HAS recent PROMOTE:
  phase = build (near-complete, ready for release) (0.90)
ELIF planning/doing/ HAS tickets:
  phase = build (in-progress) (0.85)
ELIF sequences/*/execution-sequences.yaml EXISTS:
  phase = build (ready-to-start) (0.80)
ELIF prds/*/prd.json EXISTS:
  phase = blueprint (completed) (0.90)
ELIF discovery/discovery-report.md EXISTS:
  phase = discovery (completed, ready for blueprint) (0.90)
ELIF discovery/ HAS any file:
  phase = discovery (in-progress) (0.75)
ELSE:
  phase = pre-discovery (1.0)
```

## Recommendation Engine

After detecting the current phase, recommend the next action:

### Phase → Recommendation Matrix

| Current Phase | Recommended Next | Skill to Invoke | Confidence Boost |
|--------------|-----------------|-----------------|------------------|
| pre-discovery | Start discovery | `/skillweave-discovery` | +0.1 if README.md exists |
| discovery (in-progress) | Continue discovery | `/skillweave-discovery` | — |
| discovery (completed) | Create blueprint | `/skillweave-blueprint` | +0.1 if personas defined |
| blueprint (completed) | Generate sequences | `/skillweave-promptchain-generate` | — |
| build (ready-to-start) | Execute sequences | `/skillweave-promptchain-execute` | — |
| build (in-progress) | Continue build | `/skillweave-releasechain` | — |
| build (near-complete) | Run final tests | `/skillweave test` | +0.1 if all tickets done |
| release | Prepare launch | `/skillweave-launch` | — |
| launch | Deploy | `/skillweave-launch` | — |
| post-release | Start retro | `/skillweave-post-release` | — |

### Output Format

```
📍 Current Phase: Build (in-progress)
   Confidence: 0.90
   Detected via: planning/doing/ has 3 active tickets

🎯 Recommended Next: Continue build execution
   Skill: /skillweave-releasechain
   Reason: 3 tasks in-progress, 5 remaining in backlog
   
📊 Progress: 4/11 tasks complete (36%)
   Critical path: FEAT-004 → FEAT-008 → FEAT-007
```

## Integration with `/skillweave` (bare command)

When the user types just `/skillweave` with no arguments, the lifecycle navigator:

1. Runs phase detection
2. Shows current phase + confidence
3. Shows progress summary (from planning board)
4. Recommends next action with one-click command suggestion
5. If wizard mode requested, switches to Layer 0 (5-question flow)

This is the "home screen" of SkillWeave — the single entry point that orients the user regardless of where they are in the lifecycle.
