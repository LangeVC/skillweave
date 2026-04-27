# Workflow Recommendation — Initiative 06

**Recommended: Ralph Loop Attended**

## Rationale

Ralph Loop Attended is the correct choice for Initiative 06 because:

### 1. Multi-repo orchestration requires human oversight

Two separate GitHub repositories must be created, and the design must be consistent across both. The Attended mode allows the agent to create the repos, push code, and validate — with human intervention when GitHub API permissions, naming conflicts, or repository visibility decisions arise.

### 2. False-positive verification demands human review

Validation Actions are trust-critical. A false positive in bundle validation would undermine the entire SkillWeave quality system. Attended mode ensures a human can review test outputs and confirm the Action correctly rejects intentionally broken bundles before accepting known-good ones.

### 3. Markets and distribution decisions

Marketplace listing preparation (DIST-001) involves publishing decisions that should be reviewed by a human. The agent can prepare the listing, version tags, and documentation, but the final publish step benefits from human sign-off.

### 4. GitHub App assessment is inherently strategic

DOC-001 evaluates whether to build a GitHub App — a significant architectural decision. The agent should gather evidence and draft the assessment, but the proceed/defer/skip recommendation must be reviewed by a project maintainer.

## Why Not Unattended

Unattended execution would be appropriate if:
- The Actions were being added to a single existing repo (no creation permissions needed)
- Trust signals were a later concern
- The GitHub App assessment had already been decided

Since none of these conditions hold, Attended mode provides the right balance of autonomy and safety.

## Why Not Manual

Manual execution would be too slow. The agent can generate Action code, set up CI workflows, and run tests far faster than a human. The 9-task sequence with parallel tracks benefits significantly from agent automation.

## Loop Configuration

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Max iterations | 14 | 9 tasks + up to 5 rework cycles |
| Checkpoint interval | 3 | Checkpoint after every 3 steps for mid-sequence review |
| Gate enforcement | strict | All gates must pass before proceeding to next phase |
| Parallel batch size | 2 | Two tracks (A and B) can run simultaneously |
| Human review points | After DESIGN-001, after TEST-001, before DIST-001 | Strategic checkpoints for spec sign-off, test validation, and publish approval |
