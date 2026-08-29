# Architecture

SkillWeave 1.3.7 — self-hosting, multi-lane runtime.

This document describes the canonical run path and the skill layer as they are
in this release. It is a pointer, not evidence: every claim here is backed by a
machine check (see `tests/unit/test_doc_arch.py`), which scans this file for
stale statements and verifies the diagram matches the call graph.

## Canonical run path

A run flows through one authoritative integration path, never a hand-rolled
sequence of primitive calls:

```
  Run → Journal → Raw Artifact → Receipt → Verification → Gate
```

Each stage is a distinct, addressable record kind, and none is synthesized:

1. **Run** — a persisted `RunRecord` in the CAS-backed run store, with a
   compare-and-set version so two writers on the same version cannot both win.
2. **Journal** — ordered, gap-free journal events bound to the run.
3. **Raw Artifact** — content-addressed worker bytes, resolvable back to exact
   bytes.
4. **Receipt** — the `ArtifactReceipt` bound to the run and the raw digest.
5. **Verification** — a separate verifier's verdict, provenance-bound to the
   subject receipt (never the producer's self-claim).
6. **Gate** — the completion-contract state derived from the verified outcome;
   exit 0 with empty output is `inconclusive`, never a gate pass.

The Run Application Service (`skillweave/runsvc`) is the single seam a caller
drives end to end. It does not import or invoke any simulated executor: the
canonical path runs real subprocesses, and any `simulate_*` placeholder is
quarantined behind `skillweave/legacy`.

## Council model namespace

The Council's model ids are **provider-native** — unprefixed ids in the
provider's own namespace, never gateway-qualified. The `faigate/` gateway
prefix belongs to the dispatch layer only and is translated exactly once at the
adapter boundary (`translate_model_id`); a prefix in Council profile data is
refused before any provider call. Each seat records requested / resolved /
answering model, status, provider and profile revision — the answering model is
read from the response envelope, never inferred from the request. Fewer than
`min_models_required` distinct answering models is a degraded run, never
consensus.

## Multi-lane control plane

The control plane is a set of cooperating written surfaces, each with a single
owner:

* **Coordinator** (`skillweave/coordinator`) — the sole writer of the root DAG
  cursor. Workers and reviewers may read it but cannot mutate it; a fresh
  coordinator resumes the persisted cursor.
* **Workspace** (`skillweave/workspace`) — exclusive worktrees/branches
  materialised from a full base SHA, with attestation and deterministic cleanup.
* **Fan-out** (`skillweave/fanout`) — dependency-ready fan-out: independent
  workers start before any is reaped, so overlap is a measured fact.
* **Review** (`skillweave/review`) — a review child-run starts only after
  push/fetch against a pinned full remote SHA; a SHA mismatch or a write attempt
  blocks it before it starts.
* **Self-hosting** (`skillweave/selfhost`) — SkillWeave drives its own small
  sequence (two ops lanes, two reviews, one dependent lane) with no manual
  worktree or session control.

## Execution flow

```
 Blueprint → Generate → Validate → Execute → ReleaseChain
     ↓          ↓          ↓          ↓          ↓
   PRD      Sequence   Validated   Executed    Production
            with type   sequence    results    ready code
            & mode
```

## Skill layer

Thirteen skills ship as `skillweave-*` packages:

1. `skillweave-blueprint`
2. `skillweave-council`
3. `skillweave-design`
4. `skillweave-discovery`
5. `skillweave-launch`
6. `skillweave-lifecycle`
7. `skillweave-observe`
8. `skillweave-post-release`
9. `skillweave-promptchain-execute`
10. `skillweave-promptchain-generate`
11. `skillweave-promptchain-validate`
12. `skillweave-releasechain`
13. `skillweave-repo-health`

## Agent-agnostic design

* **Capability-based routing**: tasks are assigned by declared capability, never
  by a hard-coded harness name or a name-prefix rule.
* **Read-only review**: the reviewer role is technically read-only; mutation
  attempts are blocked before execution.
* **Model independence is not claimed**: Ops and Review run under one routed
  model; the split is a cost/routing choice, not an independence statement.
