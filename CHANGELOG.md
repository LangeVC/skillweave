# SkillWeave Changelog
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
