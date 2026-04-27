---
name: skillweave-launch
description: Launch coordination for the Launch lifecycle phase — deployment, user communication, go-live coordination, and metrics baseline capture.
argument-hint: release_summary="[JSON]" mode="[guided/assisted]"
---

# /skillweave-launch

**Launch coordination — take a published release live.**

This skill handles the Launch phase of the SkillWeave lifecycle (phase order: 6).
It runs after Release is complete and the artifact is published.

## Phase Context

- **Order**: 6 (follows Release at order 5)
- **Type**: optional
- **Entry condition**: Release is published and available
- **Exit conditions**:
  - Deployment complete and verified
  - User-facing communication sent
  - Launch metrics baseline captured

## Responsibilities

| Activity | Description |
|----------|-------------|
| Production deployment | Coordinate deployment to production environment(s) |
| User communication | Prepare and distribute release notes, changelogs, announcements |
| Go-live coordination | Manage rollout timing, verify deployment health |
| Metrics baseline | Capture pre/post launch metrics for comparison |

## Relationship to Release

Release and Launch are **separate phases**:

| Dimension | Release | Launch |
|-----------|---------|--------|
| Focus | Artifact creation, versioning, publishing | Production deployment, communication |
| Output | Published package + git tag | Live system + user notifications |
| Precedes | Launch | Post-release |
| Rollback | Re-publish previous version | Re-deploy previous version |

## Usage

```
/skillweave-launch release_summary='{"version":"0.6.0","artifact_locations":["dist/"],"changelog":"..."}'
```

## Parameters

- `release_summary` (required): JSON from releasechain containing version, artifact locations, changelog
- `mode` (optional): `guided` (step-by-step) or `assisted` (automatic with human confirmation at gates)
- `environments` (optional): List of target environments (default: `["production"]`)
