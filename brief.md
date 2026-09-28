# SW-159-WORK-001 — Generic work contracts

Role: Ops. Repository: skillweave. Expected model: byteplus-deepseek-flash-41.

## Outcome

Define generic subject, evidence, capability, authority, and exact-brief contracts for Git and non-Git work.

## Required result

- Add discriminated SubjectRef variants for repository, CMS/content, configuration, deployment, and incident subjects.
- Bind EvidenceReceipt to SubjectRef without forcing Git fields on non-Git subjects.
- Define WorkContract authority, write scope, irreversible actions, verification, rollback, budget, methodology, and policy.
- Resolve capabilities through catalogue/profile with declared, detected, and runtime-attested states; keep harness/router/provider/model IDs out of skills and generic packs.
- Pass exact submitted brief bytes or immutable content-addressed reference to every worker.
- Fail before mutation when worker/adherence brief digests differ.
- Preserve existing Git dispatch and evidence consumers.

## S0 — Pin

Fetch and verify the clean assigned worktree at the frozen product controller base. Record full SHAs and model identity evidence. Stop on mismatch.

## S1 — Bounded fan-out

Run three read-only subagents in parallel: existing contracts/consumers; exact-byte dispatch path; adversarial authority/backward-compatibility tests. Maximum 40 lines each. Main worker reproduces findings.

## S2 — Build

Implement versioned contracts and minimum compatibility adapters. Keep scope within dispatch/application, runtime contracts, schemas needed by this task, and focused tests.

## S3 — Verify

Run Git compatibility, non-Git subject, capability-attestation, exact-byte, digest-mismatch, and authority fixtures under bash -eo pipefail. Persist commands, exits, key output, and hashes.

## S4 — Publish

Commit and push only the assigned branch. No merge, tag, release, cleanup, or self-review. Emit:

OPS_READY_FOR_REVIEW SW-159-WORK-001 <full-sha> GENERIC_WORK_CONTRACT_PASS
