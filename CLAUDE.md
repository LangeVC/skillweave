# CLAUDE.md

Read and follow AGENTS.md — it contains rules that apply to all agents including Claude.

## GitHub CLI

Use `gh pr checks <PR#> --watch` and `gh run watch <run-id>` instead of polling loops. Never poll `gh api` in a loop — one `--watch` call replaces 60+ API requests.

## Release Process

1. Version in `pyproject.toml`, CHANGELOG.md entry, README badge updated
2. Release title: exactly `SkillWeave vX.Y.Z` (no extra text)
3. Tag format: `vX.Y.Z`
4. Release model is Forgejo-first: the ops-engine `ReleaseHandler` creates the canonical tag and release object on Forgejo; GitHub is distribution-only. Local detail: `docs/release-flow.md` (authority: `lvc-ops/docs/release-flow-division.md`)
