# PRD: Initiative 05 — Execution System, Checklists, Memory, and Observability

## 1. Executive Summary

**Project:** SkillWeave Execution Operating Model  
**Initiative:** 05 of 06 (Master Roadmap Phase C)  
**Domain:** Developer Tooling / AI-Assisted Product Development  
**Risk Mode:** Medium  

SkillWeave execution needs to become a disciplined system built around checklist-driven loops, persistent project memory, artifact-first progress, context compaction, and measurable execution patterns. This initiative transforms execution from ad-hoc skill invocation into a repeatable, efficient, agent-agnostic operating model.

**Core Value:** Execution becomes more disciplined; long-running work uses compact artifacts rather than bloated threads; project memory persists; checklists drive progress; execution cost and drift become measurable.

## 2. Problem Statement

### Current Situation
- Long-running skill work drifts into bloated context windows
- Decisions and progress live in chat threads, not persistent artifacts
- No structured memory across sessions or agent frameworks
- Execution cost and efficiency are not tracked
- Context loading is all-or-nothing, not selective

### Impact
- Increasing token cost as context grows
- Lost context between sessions
- Inconsistent results across different agent frameworks
- No way to measure execution efficiency
- Knowledge locked in individual chat sessions

## 3. Solution Overview

### Core Execution Loop
```
Read Checklist → Execute Next Item → Update Artifacts → Compact Context → Persist Memory → Continue
```

### 12 Agent-Agnostic Execution Principles

| # | Principle | Implementation |
|---|-----------|---------------|
| 1 | Context Compaction | After each step, carry only compacted result |
| 2 | Fresh-Stage Execution | Start new phases with clean context + summary |
| 3 | Batching Over Chatter | Bundle related work into structured steps |
| 4 | Artifact-First | Write to PRDs, specs, logs — not chat |
| 5 | Persistent Project Memory | Store rules, decisions, conventions centrally |
| 6 | Selective Context Loading | Load only needed files/sections per step |
| 7 | Capability-Based Routing | Lighter models for simple steps, stronger for complex |
| 8 | Feature Gating | Only activate tools when needed |
| 9 | Execution Observability | Track tokens, runtime, errors, retries |
| 10 | Correction by Regeneration | Fix by rerunning clean steps, not patching threads |
| 11 | Shared Project Assets | Frequently used inputs as stable reusable assets |
| 12 | Phase-Aware Workload | Expensive reasoning only where it adds value |

## 4. Functional Requirements

### 4.1 Core Features

**F-01: Checklist Loop Engine**
- Description: Markdown checklist-driven execution loop that reads, executes, and updates checklist items
- Acceptance Criteria:
  - Reads markdown checklists (`- [ ]` / `- [x]`) from file
  - Identifies next unchecked item
  - Executes item (delegates to appropriate skill/prompt)
  - Updates checklist file with completion status
  - Loops until all items checked or blocker encountered
  - Supports nested checklists

**F-02: Project Memory Layer**
- Description: Persistent key-value store for project rules, decisions, conventions, and architecture choices
- Acceptance Criteria:
  - Memory stored in `.skillweave/memory/` as YAML files
  - Supports categories: rules, decisions, conventions, architecture, open-issues
  - Memory loadable at skill startup
  - Memory writable during execution
  - Memory portable across agent frameworks (plain files)
  - Memory searchable by key or category

**F-03: Context Compaction Engine**
- Description: After each major step, produce a compact summary carrying only essential state forward
- Acceptance Criteria:
  - Compaction runs after each checklist item completion
  - Produces structured summary: completed_items, key_decisions, current_state, next_steps
  - Summary saved to `.skillweave/tracking-log/context-summary.yaml`
  - Summary loadable by next execution step as starting context
  - Original detailed output preserved in tracking log

**F-04: Execution Observability Dashboard**
- Description: Track and report execution metrics: token usage, runtime, errors, retries, step count
- Acceptance Criteria:
  - Metrics recorded per execution step in `.skillweave/tracking-log/metrics.yaml`
  - Tracks: step_id, tokens_used, runtime_seconds, success/failure, retries
  - Summary report generated after execution completes
  - Cumulative metrics across sessions
  - Report saved to `.skillweave/tracking-log/execution-report.md`

**F-05: Selective Context Loader**
- Description: Load only the files and sections needed for the current step, not the entire project
- Acceptance Criteria:
  - Each checklist item can declare required_context (file paths, sections)
  - Loader reads only declared context
  - Default context includes: memory, current checklist, last context summary
  - Overridable with explicit context specification
  - Reduces token usage compared to full-context loading

**F-06: Artifact-First Progress Tracking**
- Description: All progress, decisions, and learnings written to files instead of remaining in chat
- Acceptance Criteria:
  - Decision log exists at `.skillweave/tracking-log/decisions.yaml`
  - Learning log exists at `.skillweave/tracking-log/learnings.yaml`
  - Task log exists at `.skillweave/tracking-log/task-log.yaml`
  - Each log entry has timestamp, context, and rationale
  - Logs are append-only (no overwrites)

**F-07: Correction by Regeneration**
- Description: When a step fails, fix by rerunning a clean step definition rather than patching in-thread
- Acceptance Criteria:
  - Failed steps are marked in checklist with failure reason
  - Retry creates fresh context from last good summary
  - Retry count tracked per item
  - Max retries configurable (default: 3)
  - After max retries, item flagged for human review

## 5. Non-Functional Requirements

### Portability
- All state stored as plain files (YAML, Markdown)
- No agent-specific serialization formats
- Works across Claude, OpenCode, Gemini, and other frameworks

### Performance
- Checklist loop overhead < 1 second per iteration
- Context compaction completes in < 2 seconds
- Selective loading reduces context by 50%+ vs full loading

### Reliability
- Execution state survives agent crashes (file-based persistence)
- Resumable from last completed checklist item

## 6. Technical Architecture

### Directory Structure
```
.skillweave/
  ├── memory/
  │   ├── rules.yaml
  │   ├── decisions.yaml
  │   ├── conventions.yaml
  │   ├── architecture.yaml
  │   └── open-issues.yaml
  ├── checklists/
  │   ├── current.md
  │   └── archive/
  ├── tracking-log/
  │   ├── task-log.yaml
  │   ├── decisions.yaml
  │   ├── learnings.yaml
  │   ├── metrics.yaml
  │   ├── context-summary.yaml
  │   └── execution-report.md
  └── config.yaml
```

### Checklist Format
```markdown
# Release Preparation Checklist

## Prerequisites
- [x] Tests written and passing
- [x] Code review completed
- [ ] Release notes drafted

## Release Steps
- [ ] Version bumped
- [ ] Package built
- [ ] Deployed to staging
- [ ] Smoke tests passed
- [ ] Deployed to production
```

### Memory Format
```yaml
# .skillweave/memory/decisions.yaml
decisions:
  - id: DEC-001
    date: "2026-04-27"
    context: "Architecture decision for data layer"
    decision: "Use YAML files for all state persistence"
    rationale: "Agent-agnostic, human-readable, no database dependency"
    status: active
```

## 7. Success Metrics (Binary & Testable)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Checklist loop works | Reads, executes, updates checklist items | Automated test |
| Memory persists | Write and read back memory entries | File existence + content check |
| Context compaction works | Summary produced after step completion | File existence + structure validation |
| Metrics tracked | Token count and runtime recorded per step | Metrics file has entries |
| Selective loading works | Less context loaded than full-load | Token count comparison |
| Correction works | Failed step retried from clean state | Automated test |

## 8. Timeline & Milestones

| Phase | Deliverable | Estimated Effort |
|-------|-------------|-----------------|
| Design | Directory structure + format definitions | 1 hour |
| Build | Checklist loop engine | 2.5 hours |
| Build | Project memory layer | 2 hours |
| Build | Context compaction engine | 1.5 hours |
| Build | Execution observability | 1.5 hours |
| Build | Selective context loader | 1.5 hours |
| Build | Artifact-first tracking + correction by regeneration | 2 hours |
| Integration | Connect to existing skills | 1.5 hours |
| Testing | Full test suite | 1.5 hours |

**Total Estimated Effort:** ~15 hours

## 9. Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Checklist format too rigid for complex workflows | Medium | Medium | Support nested checklists and conditional items |
| Memory files grow large over time | Medium | Low | Retention policy, archive old entries |
| Observability overhead | Low | Low | Make metrics collection optional via config |
| Context compaction loses important details | Medium | High | Preserve full output in tracking log, compaction is summary only |
