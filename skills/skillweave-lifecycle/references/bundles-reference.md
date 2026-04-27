# SkillWeave Lifecycle Bundles Reference

## Overview

A Bundle is a named grouping of lifecycle phases that represents a complete workflow slice. Bundles define entry requirements, sequence types used, and recommendation criteria. The lifecycle skill uses bundles to recommend the optimal path based on the current project state.

## Bundle Summary

| ID | Name | Phases | Entry Requires | Seq Types | Est. Effort |
|----|------|--------|---------------|-----------|-------------|
| full-lifecycle | Full Lifecycle | discovery, blueprint, design, build, release, launch, post-release | Project idea or problem statement | plan, mixed, build | High (weeks) |
| discovery-to-blueprint | Discovery → Blueprint | discovery, blueprint | Problem or opportunity to explore | plan | Low (days) |
| design-and-build | Design & Build | design, build | Valid PRD or clear requirements | mixed, build | Medium (days–weeks) |
| release-and-launch | Release & Launch | release, launch | Working code in releasable state | build | Low (hours–days) |
| post-release-improvement | Post-Release Improvement | post-release, blueprint, build | System is live in production | mixed, plan, build | Medium (days) |

---

## Bundle: full-lifecycle

| Field | Value |
|-------|-------|
| **ID** | `full-lifecycle` |
| **Name** | Full Lifecycle |
| **Phases** | discovery, blueprint, design, build, release, launch, post-release |
| **Entry Requires** | Project idea or problem statement |
| **Sequence Types Used** | plan, mixed, build |
| **Estimated Effort** | High (weeks to months) |
| **Recommendation Criteria** | New project with undefined scope; no existing artifacts; greenfield development; needs end-to-end lifecycle coverage |
| **When to Recommend** | Project is in early ideation, no PRD exists, no code exists, full oversight desired |

## Bundle: discovery-to-blueprint

| Field | Value |
|-------|-------|
| **ID** | `discovery-to-blueprint` |
| **Name** | Discovery → Blueprint |
| **Phases** | discovery, blueprint |
| **Entry Requires** | Problem or opportunity to explore |
| **Sequence Types Used** | plan |
| **Estimated Effort** | Low (days) |
| **Recommendation Criteria** | Problem is defined but not validated; stakeholder buy-in needed; go/no-go decision required before committing to build |
| **When to Recommend** | early exploration phase, before any build commitment, feasibility assessment needed |

## Bundle: design-and-build

| Field | Value |
|-------|-------|
| **ID** | `design-and-build` |
| **Name** | Design & Build |
| **Phases** | design, build |
| **Entry Requires** | Valid PRD or clear requirements |
| **Sequence Types Used** | mixed, build |
| **Estimated Effort** | Medium (days to weeks) |
| **Recommendation Criteria** | PRD exists and validated; requirements are stable; team is ready to implement; discovery/blueprint already complete |
| **When to Recommend** | PRD is ready, design and implementation are the next logical steps |

## Bundle: release-and-launch

| Field | Value |
|-------|-------|
| **ID** | `release-and-launch` |
| **Name** | Release & Launch |
| **Phases** | release, launch |
| **Entry Requires** | Working code in releasable state |
| **Sequence Types Used** | build |
| **Estimated Effort** | Low (hours to days) |
| **Recommendation Criteria** | Code is complete and tested; release candidate exists; deployment target is identified; no further feature work planned before release |
| **When to Recommend** | Build phase is complete, code is ready to ship |

## Bundle: post-release-improvement

| Field | Value |
|-------|-------|
| **ID** | `post-release-improvement` |
| **Name** | Post-Release Improvement |
| **Phases** | post-release, blueprint, build |
| **Entry Requires** | System is live in production |
| **Sequence Types Used** | mixed, plan, build |
| **Estimated Effort** | Medium (days) |
| **Recommendation Criteria** | System is live and collecting feedback; iteration cycle has started; improvement opportunities identified; may loop back through blueprint for new features |
| **When to Recommend** | Post-launch, feedback available, next iteration planning needed |

## Recommendation Logic

When evaluating which bundle to recommend, the skill considers:

1. **Current Phase**: Which phase the project is currently in (or `none` if unstarted).
2. **Artifact Existence**: Presence of PRD, code, release packages, etc.
3. **Entry Requirements**: Which entry conditions are met for each bundle's first phase.
4. **Phase Completion**: Which phases have exit conditions satisfied.
5. **Historical Patterns**: Past bundle usage from `.skillweave/tracking-log/`.

### Matching Matrix

| Current State | Recommended Bundle | Rationale |
|--------------|-------------------|-----------|
| No artifacts, idea only | full-lifecycle | End-to-end coverage |
| Problem defined, no PRD | discovery-to-blueprint | Validate before committing |
| PRD exists, no code | design-and-build | Requirements ready for implementation |
| Code complete, unreleased | release-and-launch | Ship it |
| Live in production | post-release-improvement | Iterate based on feedback |
