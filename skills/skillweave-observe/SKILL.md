---
name: skillweave-observe
description: Execution Reports, Timing, Events, Memory, Summary, Health — Read-Only Observability
argument-hint: command="[report|timing|events|memory|summary|health]" session="[id]" level="[level]"
---

# /skillweave-observe

**Read-only observability for SkillWeave execution sessions.**  
Inspect reports, timing data, event streams, memory drawers, health status, and session summaries from past or active runs. No side effects — observation never modifies state.

## Usage

```
/skillweave-observe command="report" session="<id>"
/skillweave-observe command="events" session="<id>" level="WARNING"
/skillweave-observe command="memory" session="<id>"
/skillweave-observe command="health"
```

## Commands

| Command | Description |
|---------|-------------|
| `report` | Generate a full execution report for a session (see `references/report-format.md`) |
| `timing` | Show step-level timing breakdown — duration, sequence, bottlenecks |
| `events` | Stream or filter events by level (DEBUG, INFO, WARNING, ERROR, METRIC) |
| `memory` | Read execution memory drawers for a session — rules, decisions, patterns, gotchas, metrics |
| `summary` | Compact session overview — status, duration, step count, errors |
| `health` | Runtime health check — system load, queue depth, error rate, uptime |

## Report Format

Reports follow a structured markdown format with session metadata, per-step tables, and memory annex. See `references/report-format.md` for the full specification with example output.

## Memory Categories

Each session stores execution knowledge in five memory drawers:

- **rules** — Constraints and policies discovered during execution
- **decisions** — Architectural or tactical choices with rationale
- **patterns** — Reusable approaches and idioms that worked
- **gotchas** — Pitfalls, edge cases, anti-patterns encountered
- **metrics** — Numerical observations (durations, counts, rates)

## Event Levels

| Level | Meaning |
|-------|---------|
| DEBUG | Detailed diagnostic information |
| INFO | Normal operational milestones |
| WARNING | Unexpected but non-fatal conditions |
| ERROR | Failures requiring attention |
| METRIC | Numerical data points (timings, counts) |

## Backend

This skill reads from:
- `observation/` — Event logs, timing snapshots, health signals
- `execution_memory.py` — Session-level memory drawer API

No new Python code is required; this is a pure SKILL.md exposition of existing observation modules.

## Testing

| Test Case | What to Validate |
|-----------|------------------|
| Report from event_logs | `command="report" session="<id>"` produces valid structured markdown with session metadata and per-step rows |
| Memory categories readable | `command="memory" session="<id>"` returns content for all five drawers (rules, decisions, patterns, gotchas, metrics) |
| Event filter by level | `command="events" session="<id>" level="WARNING"` returns only events at WARNING level or above |
| Summary output valid | `command="summary" session="<id>"` returns compact output with status, duration, step count, and error count |
| Health endpoint | `command="health"` returns valid JSON with system load, queue depth, error rate, and uptime |
| Timing breakdown | `command="timing" session="<id>"` returns per-step durations with identified bottlenecks |
