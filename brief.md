# SW-159-ASSAY-001 — Assay runtime and policies

Role: Ops. Repository: skillweave. Expected model: byteplus-deepseek-flash.

## Outcome

Implement Assay as a methodology with Conservative, Moderate, and Unicorn autonomy policies.

## Required result

- Append-only states: PIN, HYPOTHESIS, PROBE, MEASURE, CLASSIFY, REMEDIATE, ESCALATE_OR_SPLIT, PASS, HOLD.
- Conservative approves every mutating batch and external/irreversible action; read-only probes run automatically.
- Moderate approves plan/new waves, then self-heals within an approved reversible wave.
- Unicorn retries, remediates, reschedules, and resolves capabilities inside declared reversible scopes.
- Unicorn still holds for irreversible action, scope/authority expansion, missing authority, target drift, or budget exhaustion.
- Persist heartbeats, turn-limit changes, splits, and terminal evidence; reject narrative/compaction as evidence.
- Harness-native bypass or YOLO never weakens the effective policy.

## S0 — Pin

Fetch, use the integrated methodology baseline, verify clean assigned worktree, and record SHAs plus model identity evidence.

## S1 — Bounded fan-out

Run three read-only subagents in parallel: lifecycle/strategy integration; persistence and evidence; adversarial policy-bypass cases. At most 40 lines each. Reproduce findings.

## S2 — Build

Implement the Assay state machine, three policy definitions, persistence, and focused tests. Keep model/router identities out of methodology code.

## S3 — Verify

Exercise every state, each policy checkpoint, autonomous reversible remediation, every Unicorn hold, dynamic turns, split, compaction rejection, and bypass non-weakening under bash -eo pipefail.

## S4 — Publish

Commit and push the assigned branch only. No merge, tag, release, cleanup, or self-review. Emit:

OPS_READY_FOR_REVIEW SW-159-ASSAY-001 <full-sha> ASSAY_POLICIES_PASS
