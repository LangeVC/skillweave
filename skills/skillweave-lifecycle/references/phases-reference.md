# SkillWeave Lifecycle Phases Reference

## Overview

The SkillWeave lifecycle defines 7 sequential phases that guide a project from initial idea through post-release iteration. Each phase has clear entry/exit conditions, associated skills, and supported sequence types.

## Phase Summary

| ID | Name | Entry → Exit | Skills Used | Sequence Types |
|----|------|-------------|-------------|----------------|
| 1 | Discovery | Problem statement → Validated problem + opportunity assessment | skillweave-lifecycle | plan |
| 2 | Blueprint | Validated problem → PRD + prompt sequence | skillweave-blueprint, skillweave-promptchain-generate | plan, mixed |
| 3 | Design | PRD → Design spec + tokens | skillweave-promptchain-generate | plan, mixed |
| 4 | Build | Design/PRD → Working code + tests | skillweave-promptchain-execute, skillweave-releasechain | mixed, build |
| 5 | Release | Working code → Release package + notes | skillweave-releasechain | build |
| 6 | Launch | Release package → Deployed + verified | skillweave-releasechain | build |
| 7 | Post-Release | Live system → Retro + next iteration plan | skillweave-lifecycle, skillweave-blueprint | mixed, plan, build |

---

## Phase 1: Discovery

| Field | Value |
|-------|-------|
| **ID** | `discovery` |
| **Name** | Discovery |
| **Entry Conditions** | Problem statement, stakeholder identification |
| **Exit Conditions** | Validated problem, opportunity assessment, go/no-go decision |
| **Skills Used** | skillweave-lifecycle |
| **Capabilities** | lifecycle_management, phase_detection |
| **Sequence Types** | plan |
| **Typical Artifacts** | Problem statement, opportunity assessment, stakeholder map |

## Phase 2: Blueprint

| Field | Value |
|-------|-------|
| **ID** | `blueprint` |
| **Name** | Blueprint |
| **Entry Conditions** | Validated problem, opportunity assessment |
| **Exit Conditions** | PRD document, prompt sequence for execution |
| **Skills Used** | skillweave-blueprint, skillweave-promptchain-generate |
| **Capabilities** | planning, prd_generation, promptchain_generation |
| **Sequence Types** | plan, mixed |
| **Typical Artifacts** | prd.json, prd.md, prompt sequence |

## Phase 3: Design

| Field | Value |
|-------|-------|
| **ID** | `design` |
| **Name** | Design |
| **Entry Conditions** | PRD, clear requirements |
| **Exit Conditions** | Design specification, design tokens, component architecture |
| **Skills Used** | skillweave-promptchain-generate |
| **Capabilities** | design_spec, token_generation, architecture_planning |
| **Sequence Types** | plan, mixed |
| **Typical Artifacts** | Design spec, token definitions, component tree |

## Phase 4: Build

| Field | Value |
|-------|-------|
| **ID** | `build` |
| **Name** | Build |
| **Entry Conditions** | Design spec or PRD, validated requirements |
| **Exit Conditions** | Working code, passing tests, code review completed |
| **Skills Used** | skillweave-promptchain-execute, skillweave-releasechain |
| **Capabilities** | code_generation, testing, code_review |
| **Sequence Types** | mixed, build |
| **Typical Artifacts** | Source code, test suite, build artifacts |

## Phase 5: Release

| Field | Value |
|-------|-------|
| **ID** | `release` |
| **Name** | Release |
| **Entry Conditions** | Working code in releasable state |
| **Exit Conditions** | Release package, release notes, version bump |
| **Skills Used** | skillweave-releasechain |
| **Capabilities** | release_management, versioning, changelog_generation |
| **Sequence Types** | build |
| **Typical Artifacts** | Release package, changelog, version tag |

## Phase 6: Launch

| Field | Value |
|-------|-------|
| **ID** | `launch` |
| **Name** | Launch |
| **Entry Conditions** | Release package, deployment plan |
| **Exit Conditions** | Deployed system, verified functionality, monitoring active |
| **Skills Used** | skillweave-releasechain |
| **Capabilities** | deployment, verification, monitoring_setup |
| **Sequence Types** | build |
| **Typical Artifacts** | Deployment log, health check report, monitoring config |

## Phase 7: Post-Release

| Field | Value |
|-------|-------|
| **ID** | `post-release` |
| **Name** | Post-Release |
| **Entry Conditions** | Live system in production |
| **Exit Conditions** | Retrospective, next iteration plan |
| **Skills Used** | skillweave-lifecycle, skillweave-blueprint |
| **Capabilities** | retrospective, iteration_planning, feedback_analysis |
| **Sequence Types** | mixed, plan, build |
| **Typical Artifacts** | Retro report, next iteration PRD, improvement backlog |
