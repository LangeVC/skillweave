# Testing Flow Reference

Multi-level testing integrated into the SkillWeave lifecycle via `/skillweave test`.

## 5-Level Test Pyramid

```
         ╱╲
        ╱  ╲  Level 5: Evidence/Groundedness
       ╱────╲        (Council outputs sourced?)
      ╱      ╲
     ╱  L4    ╲  Level 4: Acceptance
    ╱──────────╲        (PRD criteria met?)
   ╱            ╲
  ╱   Level 3    ╲  E2E Smoke
 ╱────────────────╲        (Critical paths work?)
╱                  ╲
╱    Level 2: Unit   ╲  (Functions correct?)
╱══════════════════════╲
╱  Level 1: Lint/Type   ╲  (Code valid?)
╱══════════════════════════╲
```

## Auto-Trigger Points

| Level | Trigger | Phase |
|-------|---------|-------|
| Lint/TypeCheck | After any code generation step | Build |
| Unit Tests | After code generation + lint passes | Build |
| E2E Smoke | Before release gate | Release |
| Acceptance | Before release gate | Release |
| Evidence | After Council deliberation | Any |

## Gate Decision Matrix

```
┌─────────────────────────────────────────────────────────┐
│                  3-STATE GATE                            │
├──────────┬──────────────────────┬───────────────────────┤
│ Decision │ Condition            │ Action                │
├──────────┼──────────────────────┼───────────────────────┤
│ PROMOTE  │ All levels pass      │ Proceed to next phase │
│          │ Coverage ≥ minimum   │                       │
│          │ No critical failures │                       │
├──────────┼──────────────────────┼───────────────────────┤
│ HOLD     │ Minor regression     │ Suggest fix           │
│          │ Coverage < minimum   │ Allow manual override │
│          │ 1 evidence gap       │ Log as known issue    │
│          │ Warning threshold    │                       │
├──────────┼──────────────────────┼───────────────────────┤
│ ROLLBACK │ Unit tests fail      │ Block progression     │
│          │ Lint critical errors │ Require fix           │
│          │ E2E smoke fails      │ Retry budget applies  │
│          │ >50% criteria unmet  │                       │
└──────────┴──────────────────────┴───────────────────────┘
```

## Command: `/skillweave test`

### Default (run all enabled levels)

```
/skillweave-lifecycle command="test"
```

Runs all enabled levels in order (1→5), stops on ROLLBACK-triggering failure.

### Run specific level

```
/skillweave-lifecycle command="test" level="unit"
/skillweave-lifecycle command="test" level="lint"
/skillweave-lifecycle command="test" level="acceptance"
```

### Show last results

```
/skillweave-lifecycle command="test" action="results"
/skillweave-lifecycle command="test" action="results" run="2026-05-17-run-1"
```

## Output Format

### Terminal Summary

```
🧪 SkillWeave Test Run — 2026-05-17-run-2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✅ Lint/TypeCheck    0 errors, 2 warnings           (2.3s)
  ✅ Unit Tests        47 passed, 0 failed, 3 skipped (8.1s)
  ⏭️  E2E Smoke        skipped (not configured)
  ✅ Acceptance        15/15 criteria met              (0.0s)
  ⏭️  Evidence         skipped (no Council output)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Gate Decision: PROMOTE ✅
  Coverage: 72.4% (minimum: 60%)
  Duration: 10.5s
```

### JSON Results File

Stored at `.skillweave/testing/results/yyyy-mm-dd-run-N.json`:

```json
{
  "run_id": "yyyy-mm-dd-run-N",
  "timestamp": "ISO 8601",
  "trigger": "manual | phase_gate | code_generation",
  "levels": {
    "lint": { "status": "pass|fail|skip", "duration_ms": 0, "details": {} },
    "unit": { "status": "...", "details": { "passed": 0, "failed": 0, "coverage_percent": 0 } },
    "e2e_smoke": { "status": "...", "details": {} },
    "acceptance": { "status": "...", "details": { "criteria_total": 0, "criteria_met": 0 } },
    "evidence": { "status": "...", "details": {} }
  },
  "gate_decision": "PROMOTE | HOLD | ROLLBACK",
  "gate_reasoning": "Human-readable explanation",
  "summary": { "levels_run": 0, "total_passed": 0, "total_failed": 0, "duration_ms": 0 }
}
```

## ReleaseChain Integration

The testing flow integrates with ReleaseChain at two points:

### 1. After Code Generation (Ralph Loop: Verify step)

```
Ralph Loop: Implement → [code generated] → Verify
                                              ↓
                                        Run Lint (L1)
                                        Run Unit (L2)
                                              ↓
                                    Gate: PROMOTE → Integrate
                                    Gate: HOLD → Fix/Retry (with suggestion)
                                    Gate: ROLLBACK → Fix/Retry (mandatory)
```

### 2. Before Release Gate

```
Ralph Loop: Integrate → [all tasks done] → Review Gate
                                              ↓
                                        Run E2E Smoke (L3)
                                        Run Acceptance (L4)
                                              ↓
                                    Gate: PROMOTE → Advance to Release
                                    Gate: HOLD → Manual review required
                                    Gate: ROLLBACK → Back to Implement
```

## Evidence/Groundedness Check (Level 5)

Validates Council outputs against sources:

1. Extract all factual claims from Council synthesis
2. For each claim, check if it traces back to:
   - A cited source from web search
   - A model's direct output with reasoning
   - A verifiable fact (numbers, dates, names)
3. Score: claims_sourced / total_claims
4. Threshold: >90% = pass, 80-90% = HOLD, <80% = ROLLBACK

## Configuration

See `.skillweave/testing/test-config.yaml` for:
- Level enable/disable
- Gate weight per level
- Failure thresholds
- Command mappings per language
- Coverage minimums
