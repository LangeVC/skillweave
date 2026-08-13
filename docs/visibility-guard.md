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

> Status: the source `.forgejo/workflows/mirror.yml` gains a `visibility-gate` job that
> runs **before** the mirror job. The mirror job depends on it with `needs:`, so a
> failing gate prevents the push from reaching GitHub. This protection is only in effect
> once the change is merged to the branch the mirror actually runs from. Until then,
> there is no gate: do not rely on any Vorkehrung that has not yet shipped.

An absent gate is externally indistinguishable from a working gate as long as all you
observe is "nothing came through." The proof that a gate exists must be a red test
commit, not a branch that happened not to arrive.

Blocked paths on any touched file:

- `.skillweave/**`
- `strategy.md`, `**/strategy.md`
- `prd*.md`, `**/prd*.md`, `prd*.json`, `**/prd*.json`
- `*.contract*`, `**/*.contract*`

A deliberate case can be released via `workflow_dispatch` with `release_override=true`
and a mandatory `release_override_reason`. Without a reason, the override is rejected:
a gate without an escape hatch gets circumvented, which is worse than none.
