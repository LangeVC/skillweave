# SkillWeave Changelog

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
