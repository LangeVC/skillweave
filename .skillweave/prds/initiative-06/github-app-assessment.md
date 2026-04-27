# GitHub App Feasibility Assessment

**Initiative 06 — GitHub Action, GitHub App, and Integration Layer**
**Date:** 2026-04-27
**Status:** Complete

## Summary

| Dimension | Verdict |
|-----------|---------|
| Add value beyond Actions? | Limited — marginal for current needs |
| Build cost | Medium (3-4 weeks, $5-8k equivalent) |
| Maintenance burden | Medium (ongoing updates, hosting, security) |
| User value per use case | Low to Medium |
| **Recommendation** | **Defer** — revisit at v1.0 when ecosystem has more users |

---

## Use Case Evaluation

### 1. Repository Sync (Webhook-driven sync of SkillWeave configs)

- **Current alternative**: Manual git operations, Actions already trigger on push/PR
- **App value**: Could auto-sync `.skillweave/` configs across repos
- **User base affected**: < 5 users currently
- **Verdict**: Low value — existing Actions handle this

### 2. Release Signal Capture (Capture release metadata, badge states, trust signals)

- **Current alternative**: Actions already generate structured JSON output and release assets
- **App value**: Centralized signal aggregation across repos
- **User base affected**: 1 repo (SkillWeave)
- **Verdict**: Low value — Actions outputs + artifacts are sufficient

### 3. Trust Enrichment (Combine validation results + release history + dependency health)

- **Current alternative**: Manual cross-referencing, badges from shields.io
- **App value**: Automated trust scoring dashboard
- **User base affected**: Developers evaluating SkillWeave skills
- **Verdict**: Medium value, but premature — trust ecosystem needs organic growth first

### 4. Discovery Support (Skill directory browsing, version comparison, compatibility matrix)

- **Current alternative**: README files, manual inspection
- **App value**: Web UI for browsing/installing skills
- **User base affected**: Potential skill consumers
- **Verdict**: Medium value, but overlaps with planned skill registry feature

---

## Build Cost Estimate

| Component | Effort | Notes |
|-----------|--------|-------|
| GitHub App manifest + webhook setup | 2-3 days | Standard setup |
| Event handling (push, release, check_run) | 3-5 days | 6+ event types |
| Storage + API layer | 3-5 days | DB schema, REST endpoints |
| Dashboard UI | 5-8 days | Minimal viable dashboard |
| Security + auth | 2-3 days | JWT, secret rotation |
| Deployment + CI | 2-3 days | Hosting, monitoring |
| **Total** | **17-27 days** | |

## Risks

1. **API rate limits**: GitHub App JWT tokens have higher limits but still constrained
2. **Webhook reliability**: Missed webhooks need reconciliation logic
3. **Hosting cost**: Requires always-on server (vs serverless Actions)
4. **Permission complexity**: Granular permissions needed per use case

## Recommendation: DEFER

**Rationale:**
- All four use cases are adequately served by the current GitHub Actions + workflow_dispatch model
- User base (< 5 active users) does not justify the build/maintenance cost
- Trust and discovery needs are better addressed by a future skill registry (separate product)
- The Actions infrastructure built in this initiative already generates structured JSON output that a future App could ingest

**Condition to revisit:**
- When SkillWeave has 20+ active users OR
- When 3+ external repositories use SkillWeave Actions OR
- When a clear need for cross-repo centralized signal aggregation emerges

**If/when proceeding, MVP scope:**
- Phase 1: Webhook receiver that stores validation results from Actions
- Phase 2: Simple status dashboard showing pass/fail per repo
- Phase 3: Release signal aggregation with version history

---

*Assessment completed as part of Initiative 06 execution.*
