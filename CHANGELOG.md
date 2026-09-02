# SkillWeave Changelog
## v1.5.2 (2026-09-02)

### Substrate
- **Three-tier model**: package defaults (shipped under `skillweave/assets/`), durable input under `skillweave.config/`, and generated output under `.skillweave/`, which is git-excluded. A team's tuned catalogue lives in `skillweave.config/` and survives upgrades; generated state never ships and never tracks.
- **Generic substrate contract**: `direction` (input/output), `durability` (authored/generated, with `ephemeral` as a first-class value), and `disclosure` (public/private) declared per area, plus a backing-store seam that resolves an area's store from its declaration rather than from a `.git` directory. Durable areas in a non-git workspace sync through the configured org planning repository and are reported at-risk (not silently accepted) when no store is reachable.

### Mirror
- **Single mirror workflow**: the visibility-gate, the release-tag version-gate, and the mirror job are one workflow ordered by `needs`, with a destination guard that proves the GitHub destination is reachable before any push instead of failing inside one.

### Version topology
- **`decoupled_member_pins`**: the bundle and the runtime carry the train version; the `capabilities[]` member pins and the 13 skill capability files are informational and may lag the bundle together. A bundle bump can be packaging alone, so a plain bump moves only the two required locations (`pyproject.toml` and `capability.yaml`) and leaves the pins and member files where they are. The pin never diverges from its own member file — that consistency is owned by `scripts/check-manifest.py`, not by the release gate.

### Testing
- **Hermetic suite**: tests that depended on untracked local state (sibling checkouts, the git-excluded `.skillweave/` tree) now skip with an explicit reason when that state is absent, so a fresh `git archive` clone reproduces a green suite.

### Onboarding
- **Substrate rule taught**: onboarding states the substrate rule, writes the anchored `/.skillweave/` gitignore exclusion, records the private planning-repository answer, and refuses to leave substrate content tracked when the origin remote is public.


## v1.5.0 (2026-09-01)

### Features (Production Agent-Native)
- **Crash Recovery**: Orphan-, Worker-, and Coordinator-Crash-Recovery that reconstructs execution DAGs from persistent context without brittle transcript parsing.
- **Context Limits & Checkpointing**: Configurable token profiles (e.g., 120k `no_new_task`, 150k `checkpoint`, 170k `stop`) to bound AI execution budgets safely.
- **Operator Agent Escalation**: `operator_agent` with strict deterministic decision scopes. Irreversible choices automatically escalate before mutating state.
- **Persistent Policy**: Idempotent compensation, backoff, and retry budgets ensuring a crash loop doesn't double-charge tokens.
- **Remote Workspace Sandbox**: Distributed execution honoring the precise `skillweave-workspace` contract without leaking orchestration state.
- **Soak & Langlauf**: Added extensive multi-hour degradation limits and `DoubleStartGuard` process protection.


## v1.4.0 (2026-08-31)

### Features
- **Public Control Plane**: Complete separation of integration tests and host-neutral API paths.
- **MCP Guard Rails**: Full enforcement of negative authority limits in the MCP server.
- **Skill Portability**: All 13 skills audited and refactored for host-neutral Command/Intent contracts (experimental).
- **Harness Provenance**: Hermetic Fakes and OpenCode-DeepSeek proofs with append-only receipts.
- **Faigate Diversity**: Expanded ops, review, and comparison routing profiles with Anti-Masking detection.
- **Dispatchability**: Explicit execution queues, topological phase batching, and metadata validation.

### Deprecations
- **SW-DEPR-001**: `skillweave.executor` is deprecated. Test doubles moved to `skillweave.legacy.test_double`.

---
