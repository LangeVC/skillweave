# Mirror visibility guard

`skillweave` is canonical on Forgejo and mirrored as a public, read-only repo on
GitHub (`LangeVC/skillweave`). Planning, strategy, PRD, and proposal content must never
reach that public mirror; it belongs in the separate planning repository, which is
Forgejo-only and not mirrored.

## Where content belongs

See the shared placement rule in the planning repository:
`skillweave-planning/SKILLWEAVE-SCOPE.md`. In short:

- Planning, strategy, PRDs, tickets, proposals: planning repository, `.skillweave/planning/`.
- Product repositories: only runtime state the runtime recreates per project.
- `.gitignore`: use an allowlist form, not a blanket ignore, in planning repositories.

## The gate

`.forgejo/workflows/mirror.yml` contains a `visibility-gate` job that runs **before** the
mirror job. The mirror job depends on it with `needs:`, so a failing gate prevents the
push from reaching GitHub.

A gate in `mirror.yml` protects exactly the refs that carry it — Forgejo runs the
workflow as it exists at the pushed ref, not as it exists on `main`. A feature branch
that ships the gate is protected by it; a branch where it has not yet been merged is not.

Two consequences follow:

1. Until the gate is merged to `main`, the primary path is unprotected. A push to
   `main` (or `dev`, which feeds the mirror) goes through without a check.
2. A gate protects only the paths it knows. This list covers `.skillweave/**`; it does
   not cover `docs/` — which is exactly where a prior session placed a contract carrying
   the open-core boundary. A rule that forbids a path without naming a home for that
   content relocates it to the nearest unguarded path.

Treat every push as public until the gate is deployed — not because there is no gate,
but because a gate only covers the refs and paths it knows. The end-to-end proof is a
red run **and** a ref that does not arrive (an absent gate is externally
indistinguishable from a working gate if all you observe is that nothing came through).

Blocked paths on any touched file:

- `.skillweave/**`
- `strategy.md`, `**/strategy.md`
- `prd*.md`, `**/prd*.md`, `prd*.json`, `**/prd*.json`
- `*.contract*`, `**/*.contract*`

Paths NOT yet covered (known gap, tracked in the OPS-011 ticket):

- `docs/**` — the GLE-004 contract case landed here. Decide explicitly whether a
  contract/proposal convention in `docs/` belongs to the blocked set.

A deliberate case can be released via `workflow_dispatch` with `release_override=true`
and a mandatory `release_override_reason`. Without a reason, the override is rejected:
a gate without an escape hatch gets circumvented, which is worse than none.
