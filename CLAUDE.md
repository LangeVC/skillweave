# CLAUDE.md

Read and follow AGENTS.md — it contains rules that apply to all agents including Claude.

## GitHub CLI

Use `gh pr checks <PR#> --watch` and `gh run watch <run-id>` instead of polling loops. Never poll `gh api` in a loop — one `--watch` call replaces 60+ API requests.

## Release Process

1. Version in `pyproject.toml`, CHANGELOG.md entry, README badge updated
2. Release title: exactly `SkillWeave vX.Y.Z` (no extra text)
3. Tag format: `vX.Y.Z`
4. Use `auto-tag-release.yml` workflow when possible; manual `gh release create` must follow same naming convention
