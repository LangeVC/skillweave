# Report Format Specification

Execution reports follow a structured markdown format. Each report is generated from session event logs and memory state.

## Report Structure

```
# Execution Report: [Session ID]

## Metadata
- **Session:** <id>
- **Status:** completed | failed | running
- **Started:** <timestamp>
- **Ended:** <timestamp>
- **Duration:** <seconds>
- **Steps:** <count>
- **Errors:** <count>

## Step Timeline

| # | Step | Duration | Status | Gates Passed |
|---|------|----------|--------|--------------|
| 1 | `validate-input` | 1.2s | ✅ PASS | validation, schema |
| 2 | `build-api` | 34.5s | ✅ PASS | lint, test |
| 3 | `build-ui` | 28.1s | ✅ PASS | lint |
| 4 | `integration-test` | 12.0s | ❌ FAIL | test (failed) |

## Memory Annex

### Rules
- All Python files must pass `ruff check` before merge
- API responses must include `request_id` header

### Decisions
- Chose FastAPI over Flask for async support (2026-04-20)
- SQLite for dev, PostgreSQL for production

### Patterns
- Use Pydantic v2 models for all request/response schemas
- Repository pattern for database access layer

### Gotchas
- Ruff rule `ANN002` conflicts with Google-style docstrings — disabled
- SQLite does not enforce FK constraints by default — enabled via PRAGMA

### Metrics
- Avg step duration: 18.9s
- Total duration: 75.8s
- Total gates passed: 5
- Total gates failed: 1

## Event Log (last 10)

```
[INFO]  2026-04-27T10:00:01Z — Session started
[INFO]  2026-04-27T10:00:02Z — Step 1: validate-input
[DEBUG] 2026-04-27T10:00:02Z — Schema check: 0 errors
[INFO]  2026-04-27T10:00:03Z — Gate validation: PASS
[METRIC] 2026-04-27T10:00:03Z — step.validate-input=1.2s
[ERROR] 2026-04-27T10:01:15Z — Step 4: integration-test — AssertionError at line 142
[WARNING] 2026-04-27T10:01:16Z — Retry attempt 1/3
[ERROR] 2026-04-27T10:01:30Z — Step 4: Gate test: FAIL
```

## Memory Categories

| Category | Purpose | Retention |
|----------|---------|-----------|
| **rules** | Constraints, policies, conventions enforced during execution | Session + project |
| **decisions** | Architectural and tactical choices with timestamp and rationale | Session + project |
| **patterns** | Reusable approaches, code idioms, workflow templates | Session + project |
| **gotchas** | Pitfalls, edge cases, anti-patterns, and their resolutions | Session + project |
| **metrics** | Numerical observations — durations, counts, rates, frequencies | Session |

## Event Levels

| Level | Label | Description |
|-------|-------|-------------|
| DEBUG | `[DEBUG]` | Detailed diagnostic information for troubleshooting |
| INFO | `[INFO]` | Normal operational milestones and state transitions |
| WARNING | `[WARNING]` | Unexpected conditions that did not prevent completion |
| ERROR | `[ERROR]` | Failures, exceptions, and conditions requiring attention |
| METRIC | `[METRIC]` | Numerical data points — key=value pairs for analysis |

## Example Summary Output

```
Session: abc123 — COMPLETED
Duration: 75.8s | Steps: 4 | Errors: 1 | Gates: 5/6 passed
```

## Example Timing Output

```
Step Timeline:
  1. validate-input    — 1.2s
  2. build-api         — 34.5s  ⚠ bottleneck
  3. build-ui          — 28.1s
  4. integration-test  — 12.0s  ❌ failed
Total: 75.8s
```
