# Meta-Command Layer (Layer 1)

7 simplified commands that provide the primary UX over 13 direct skills.

## Progressive Disclosure Architecture

```
┌─────────────────────────────────────────────────┐
│ Layer 0: Wizard (/skillweave start)             │  ← Non-technical users
│   5 questions → routes to correct skill         │
├─────────────────────────────────────────────────┤
│ Layer 1: Meta-Commands (7 commands)             │  ← Indie hackers, power users
│   /skillweave, plan, build, test, council,      │
│   report, start                                 │
├─────────────────────────────────────────────────┤
│ Layer 2: Direct Skills (13 skills)              │  ← Advanced users
│   /skillweave-blueprint, -releasechain, etc.    │
└─────────────────────────────────────────────────┘
```

## Command Reference

### 1. `/skillweave` (bare — navigator home)

**Purpose**: Status overview + intelligent recommendation.

**Behavior**:
1. Run phase detection (see `navigator-detection.md`)
2. Show current phase + confidence
3. Show planning board summary (tickets in each state)
4. Recommend next action with invocable command

**Maps to**: `skillweave-lifecycle command="status"` + `command="recommend"`

**Example output**:
```
📍 SkillWeave — Build (in-progress)
   4/11 tasks complete | 3 doing | 4 backlog
   
🎯 Next: Continue with FEAT-004 (Lifecycle Navigator)
   Run: /skillweave build
```

---

### 2. `/skillweave start` (wizard entry)

**Purpose**: Guided entry for users who don't know which skill to use.

**Behavior**: 5-question flow:
1. "Was möchtest du tun?" (What do you want to do?)
   - Neue Idee entwickeln → Discovery
   - Bestehendes Projekt weiterarbeiten → Build
   - Etwas überprüfen/testen → Test
   - Meinung/Feedback einholen → Council
   - Release/Veröffentlichung → Release
2. Context questions based on answer
3. Route to correct skill with pre-filled parameters

**Maps to**: `skillweave-lifecycle command="wizard"`

---

### 3. `/skillweave plan` (planning board)

**Purpose**: View and manage the Kanban planning board.

**Behavior**:
- No args: Show ASCII board summary
- `create`: Create new ticket
- `move`: Transition ticket
- `show`: Show ticket detail
- `seed`: Create tickets from PRD

**Maps to**: `skillweave-lifecycle command="plan" [action=...]`

---

### 4. `/skillweave build` (execute work)

**Purpose**: Start or continue building from the current PRD/sequences.

**Behavior**:
1. Detect if sequences exist → route to promptchain-execute
2. Detect if PRD exists but no sequences → route to promptchain-generate first
3. Detect if no PRD → suggest blueprint first
4. If build in progress → resume from last checkpoint

**Maps to**: 
- `skillweave-promptchain-execute` (if sequences ready)
- `skillweave-promptchain-generate` → `skillweave-promptchain-execute` (if PRD only)
- `skillweave-blueprint` (if no PRD)

---

### 5. `/skillweave test` (testing flow)

**Purpose**: Run the multi-level test pyramid.

**Behavior**:
- No args: Run all enabled test levels
- `level=X`: Run specific level
- `results`: Show latest test results

**Maps to**: `skillweave-lifecycle command="test" [level=...] [action=...]`

---

### 6. `/skillweave council` (multi-model deliberation)

**Purpose**: Convene a Council for decisions, reviews, or research.

**Behavior**:
- Requires `topic` parameter
- Optional: `mode`, `time_range`, `profile`, `phase`
- Runs full 3-stage deliberation (or quick/standard based on mode)

**Maps to**: `skillweave-council topic="..." [mode=...] [phase=...]`

---

### 7. `/skillweave report` (release reports)

**Purpose**: Generate or view release reports.

**Behavior**:
- No args: Show latest report
- `generate`: Generate report from current state
- `list`: List all reports
- Reports follow `yyyy-mm-dd-topic.md` naming

**Maps to**: `skillweave-lifecycle command="report" [action=...]`

---

## Routing Logic

```python
def route_meta_command(command: str, args: dict) -> SkillInvocation:
    match command:
        case "" | "status":
            return lifecycle(command="status") + lifecycle(command="recommend")
        case "start":
            return lifecycle(command="wizard")
        case "plan":
            return lifecycle(command="plan", **args)
        case "build":
            if sequences_exist():
                return promptchain_execute(sequence=latest_sequence())
            elif prd_exists():
                return promptchain_generate(prd=latest_prd())
            else:
                return blueprint()
        case "test":
            return lifecycle(command="test", **args)
        case "council":
            return council(**args)
        case "report":
            return lifecycle(command="report", **args)
```

## Error Handling

If a meta-command can't determine what to do:
1. Show what was detected (or not detected)
2. Suggest the wizard: "Try `/skillweave start` for guided help"
3. Never fail silently — always explain and suggest
