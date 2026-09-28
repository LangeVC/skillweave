# SW-159-BP-TICKET-001 — Conditional planning handshake

Role: Ops. Repository: skillweave. Expected model: byteplus-deepseek-flash.

## Outcome

Add an authority-aware planning ticket handshake before final PRD emission.

## Required result

- Terminal states are exactly linked, created, not_applicable, and needs_authority, each with evidence.
- Link or create only when an authoritative writable planning board exists.
- Continue with not_applicable when no planning repository exists.
- Stop before mutation with needs_authority when a board exists but write authority does not.
- Prevent duplicate-title and concurrent-create duplication.

## S0 — Pin

Fetch, use the integrated grounded candidate, verify clean assigned worktree, and record full SHAs plus model identity evidence.

## S1 — Bounded fan-out

Run three read-only subagents in parallel: planning-repo detection; mutation/authority boundary; duplicate/concurrency fixture design. At most 40 lines each. Recheck all load-bearing claims.

## S2 — Build

Implement the handshake module and integration tests only. Never mutate a real backlog/doing/done board during tests.

## S3 — Verify

Run all four terminal states plus duplicate-title and concurrent-create fixtures under bash -eo pipefail. Persist producer command, exit, key output, and evidence digest.

## S4 — Publish

Commit and push only the assigned branch. No merge, tag, release, cleanup, or self-review. Emit:

OPS_READY_FOR_REVIEW SW-159-BP-TICKET-001 <full-sha> PLANNING_HANDSHAKE_PASS
