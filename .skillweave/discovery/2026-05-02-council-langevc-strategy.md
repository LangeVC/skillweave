# skillweave-council · Round 2 · deep profile · phase: design

**Date:** 2026-05-02
**Topic:** LangeVC Git & Documentation Strategy — Full Ecosystem Architecture
**Council:** deep profile (6 models)
**Chairman:** claude-opus-4
**Consensus Score:** 1.0 (unanimous on risk-first approach)

---

## I. Executive Summary

The council evaluated 3 dimensions of the LangeVC ecosystem strategy across 6 independent perspectives, followed by anonymous peer review. The result is a unanimous consensus on the risk-first, bootstrap-first approach (Model F), with strong agreement on Capacium-first prioritization (Model A), precise stub triage (Model C), and CI/CD mirror architecture (Model D).

**The council identified 3 critical gaps in the current strategy:**
1. No backup plan for the 51-repo migration
2. The typelicious personal account is a single point of failure for SkillWeave
3. docs.langevc.com is sequenced too late in all naive plans

---

## II. Ecosystem Architecture

### Adopted Hierarchy

```
LangeVC (holding identity)
│
├── Capacium (standards layer · open source)
│   SkillWeave lives here — it consumes cap, produces capabilities
│
├── FusionAIze (infrastructure layer · open core)
│   faigate + faigrid = active
│   3-4 stubs retained with clarified roles
│
├── Vamerli (application layer · commercial)
│   Elementify MCP + WordPress ecosystem
│
├── LangeVC (cross-cutting)
│   Docs hub, website, governance, roadmap, unified Homebrew tap
│
└── typelicious (personal archive · GitHub only)
    Dormant repos stay; SkillWeave migrated out
```

### SkillWeave Decision

Create a `skillweave` org in Forgejo under LangeVC immediately. Do not merge into Capacium now (wait for product direction). This eliminates the #1 risk in the ecosystem and takes 10 minutes.

Council vote: 6/6 unanimous.

### FusionAIze Stubs Decision

| Repo | Verdict | Rationale |
|------|---------|-----------|
| faisignal | keep | Monitoring needed for production |
| failens | keep | Observability needed |
| faifabric | keep | Core infra concept, strategic |
| fusionaize-sdk | keep | SDK needed before external devs |
| faios | archive | Too vague, no code |
| faistudio | archive | Overlaps with Vamerli Studio |
| faiops-cli | archive | Faisignal + failens will handle ops |
| faiops-browser | archive | Low priority |
| fusionaize-docs | merge | Into docs.langevc.com |
| fusionaize-project-template | keep | Useful for onboarding |

**Result:** 10 → 6-repo footprint (4 kept, 4 archived, 1 merged, 1 kept).

---

## III. Mirror Architecture Decision

```
Forgejo (source of truth)
    ↓ push mirror (post-receive hook)
GitHub (read-only mirror + Actions)
```

- Cap private repos → Forgejo only (no mirror)
- Cap public repos → Forgejo SOURCE, GitHub mirror
- GitHub Actions repos → GitHub native (must stay for Actions marketplace)
- Homebrew taps → UNIFIED tap at `LangeVC/homebrew-tap`, GitHub Actions for formula updates
- CI: Forgejo Actions for private, GitHub Actions for public (community visibility)

**Unified Homebrew Tap:** Consolidate `Capacium/homebrew-tap` + `fusionAIze/homebrew-tap` → `LangeVC/homebrew-tap`.

---

## IV. 90-Day Implementation Plan

### Phase 0: Bootstrap (Week 1)

| Day | Action |
|-----|--------|
| 1 | Write `forgejo-bootstrap.sh`: Docker check, Forgejo API, Caddy config, DNS verify, org create, test push |
| 1 | Full GitHub backup: `gh clone-all` all 51 repos to local disk |
| 2 | Configure Caddy on CPX22 for git.langevc.com → Forgejo container |
| 2 | Create Forgejo orgs: Capacium, FusionAIze, Vamerli, Elementify, skillweave, LangeVC |
| 2 | **Rescue SkillWeave**: Create skillweave org, push SkillWeave to Forgejo |
| 3 | Configure Forgejo daily backups (SQLite dump + repo tarball) to external storage |
| 3 | Set up Forgejo Actions runner on CPX22 (for private repo CI) |

**Checkpoint:** git.langevc.com reachable, SkillWeave migrated, backups running, CI runner ready.

### Phase 1: Docs Foundation + Capacium Private (Weeks 2-3)

| Day | Action |
|-----|--------|
| 4-5 | mkdocs-material skeleton: base config, Caddy for docs.langevc.com, Cap docs v1 |
| 6-10 | Migrate Capacium private → Forgejo: ops → models → crawler → exchange → bridge |
| 10 | CI verification: pytest + ruff on Forgejo Actions for migrated repos |
| 11-14 | Capacium docs v1 complete (install, manifest spec, trust model, adapters) |

### Phase 2: Capacium Mirrors + FusionAIze (Weeks 4-6)

| Day | Action |
|-----|--------|
| 15-18 | Set up push mirrors for public Capacium repos to GitHub |
| 18 | Test end-to-end: push to Forgejo → mirror to GH → GH Actions run |
| 19-21 | FusionAIze stub triage: archive 4, keep 4, merge fusionaize-docs into docs hub |
| 22-28 | Migrate faigate + faigrid to Forgejo, keep- stubs with updated READMEs |

### Phase 3: Vamerli + Docs Build-out (Weeks 7-9)

| Day | Action |
|-----|--------|
| 29-35 | Migrate all 5 Vamerli repos to Forgejo |
| 36-49 | Docs build-out: FusionAIze docs, Vamerli docs, cross-references, ecosystem map |

### Phase 4: Launch + Cleanup (Weeks 10-12)

| Day | Action |
|-----|--------|
| 50-56 | Unify Homebrew taps: LangeVC/homebrew-tap |
| 57-63 | GitHub cleanup: archive old repos, update READMEs with git.langevc.com URLs |
| 64-70 | Launch: blog post, community announcement, all READMEs updated |
| 71-77 | Buffer + retrospective |

### Phase 5: Next Steps (Week 13)

| Day | Action |
|-----|--------|
| 78-84 | Bi-directional sync POC (if community contributors emerge) |
| 84-90 | Retrospective doc, Phase 3 plan (sevenofnine.xyz, Enterprise capability planning) |

---

## V. Key Decisions Made

| Decision | Adopted From | Status |
|----------|-------------|--------|
| Risk-first, bootstrap-first sequencing | F (unanimous) | ADOPTED |
| Capacium-first migration priority | A | ADOPTED |
| SkillWeave → own org in Forgejo, Week 1 | F + C | ADOPTED |
| Push mirror model (not bidirectional yet) | D | ADOPTED |
| FusionAIze stubs: 4 keep, 4 archive, 1 merge, 1 keep | C (refined) | ADOPTED |
| Unified Homebrew tap under LangeVC | C | ADOPTED |
| Docs parallel to migration, not after | F | ADOPTED |
| typelicious stays on GitHub as personal archive | C + B | ADOPTED |
| Forgejo Actions for private CI, GitHub Actions for public | D | ADOPTED |
| Backup strategy before any migration | F (unanimous) | ADOPTED |

---

## VI. Immediate Next Action

**Write `forgejo-bootstrap.sh`** — a single bash script that:
1. Checks Forgejo Docker container status + port on CPX22
2. Generates Caddy reverse-proxy config for git.langevc.com
3. Verifies DNS resolution
4. Creates admin user via Forgejo API
5. Creates orgs: Capacium, FusionAIze, Vamerli, Elementify, skillweave, LangeVC
6. Verifies with test push/pull

This is the gate. Nothing else proceeds until this works.

---

## VII. Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| typelicious account compromise → SkillWeave lost | Critical | Migrate Week 1 Day 2 |
| Forgejo DB corruption during migration | High | Daily backups before first migration |
| CPX22 resource exhaustion | Medium | Monitor during migration phases |
| GitHub Actions break on mirror | Medium | Test end-to-end Phase 2 |
| Community confusion on repo home | Low | Blog post + README updates in launch phase |

---

## VIII. Dissent

No significant dissent. Council score: 1.0 (unanimous on risk-first approach).

Minor divergence:
- A prefers monorepo merge for stubs (fusionaize-platform), C and F prefer selective keep/archive. Chairman adopts C's selective approach with F's risk analysis.
- D wants CI/CD analysis upfront (incorporated into Phase 0 bootstrap).
- B wants faster pacing (14 vs 13 weeks — negligible).

---

## Appendix: Council Composition

| Model | Role | Ranking (Self) |
|-------|------|----------------|
| claude-sonnet-4-5 | Deliberator A | #2 (20 pts) |
| gpt-4o | Deliberator B | #6 (5 pts) |
| gemini-2-5-pro | Deliberator C | #3 (16 pts) |
| deepseek-v4-pro | Deliberator D | #4 (15 pts) |
| llama-4-maverick | Deliberator E | #5 (9 pts) |
| mistral-large | Deliberator F | #1 (25 pts) — UNANIMOUS |
| claude-opus-4 | Chairman | Synthesis |
