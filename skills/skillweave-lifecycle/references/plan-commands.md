# Plan Commands Reference

File-based planning system (beans-pattern) for SkillWeave lifecycle management.

## Architecture

```
.skillweave/planning/
├── BOARD.md           # Auto-generated, read-only view
├── backlog/           # State: not started
├── doing/             # State: in progress
└── done/              # State: completed (with timestamp)
```

State is encoded in directory position. Moving a file = changing state.

## Commands

### Show Board (default)

```
/skillweave-lifecycle command="plan"
```

Output: ASCII summary of all tickets grouped by state, with counts and critical path.

Example output:
```
📋 Planning Board (11 tickets)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Done (1)
  INFRA-001  Define Handover Schemas            [high] completed 2026-05-17

🔄 Doing (2)
  INFRA-002  Council Cross-Model Bug             [high] week 1
  FEAT-002   File-Based Planning System         [high] week 1

📥 Backlog (8)
  FEAT-001   Multi-Level Testing Flow           [high] week 2 ← INFRA-001
  FEAT-004   Lifecycle Navigator                [high] week 3 ← INFRA-001
  FEAT-005   Council Stability                  [high] week 4 ← INFRA-002
  FEAT-006   Handover Signal Validation         [med]  week 3 ← INFRA-001
  FEAT-008   Meta-Command Layer                 [med]  week 3 ← FEAT-004
  FEAT-003   Automatic Release Reports          [med]  week 4 ← FEAT-001
  FEAT-007   Progressive Disclosure Wizard      [med]  week 5 ← FEAT-004
  FEAT-009   Free/Studio Boundary               [low]  week 4 ← FEAT-008
  QA-001     Integration Testing                [high] week 5 ← FEAT-007
  DOC-001    Unified Documentation              [med]  week 5 ← QA-001
```

### Create Ticket

```
/skillweave-lifecycle command="plan" action="create" title="My Feature" priority="high" type="feature"
```

Optional parameters:
- `depends_on`: Comma-separated list of dependency IDs
- `week`: Target week number
- `estimated_effort`: Hours estimate

Process:
1. Determine next available ID for the given type
2. Create `{ID}.md` in `backlog/` with YAML frontmatter
3. Regenerate BOARD.md

### Move Ticket

```
/skillweave-lifecycle command="plan" action="move" id="FEAT-001" target="doing"
```

Valid targets: `backlog`, `doing`, `done`

Process:
1. Find ticket file across all state directories
2. Move file to target directory (equivalent to `git mv`)
3. Update `status` field in frontmatter
4. If target is `done`, set `completed: {today's date}`
5. If target is `done`, check all `- [ ]` items and mark `- [x]` where applicable
6. Regenerate BOARD.md

### Show Ticket Detail

```
/skillweave-lifecycle command="plan" action="show" id="FEAT-001"
```

Displays full ticket content including acceptance criteria with completion status.

### Seed from PRD

```
/skillweave-lifecycle command="plan" action="seed" prd=".skillweave/prds/v1.0/prd.json"
```

Process:
1. Read prd.json, extract `tasks` array
2. For each task, check if ticket with that ID already exists
3. Create missing tickets in `backlog/` with full acceptance criteria
4. Regenerate BOARD.md
5. Report: "Created N tickets, skipped M existing"

### Regenerate Board

```
/skillweave-lifecycle command="plan" action="board"
```

Force-regenerates BOARD.md from current directory state. Useful after manual edits.

## BOARD.md Generation Algorithm

1. Scan all `.md` files in `backlog/`, `doing/`, `done/`
2. Parse YAML frontmatter from each file
3. Group by state (done → doing → backlog)
4. Sort within groups: priority (high→med→low) then ID
5. Generate markdown tables with summary counts
6. Append critical path visualization
7. Append week plan table
8. Write to `.skillweave/planning/BOARD.md`

## Integration Points

### ReleaseChain Integration

When ReleaseChain begins executing a task:
- Emit: `plan move {task_id} doing`

When ReleaseChain completes a task (gate = PROMOTE):
- Emit: `plan move {task_id} done`

### PromptChain Integration

When promptchain-execute starts a batch:
- Move all tasks in the batch to `doing`

When promptchain-execute completes a batch successfully:
- Move completed tasks to `done`

### Handover Integration

When a handover signal is emitted, update any tickets that correspond to the completed phase.
