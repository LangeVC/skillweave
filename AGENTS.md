# Agent Rules

## Content Boundary

Release notes, changelogs, PR descriptions, and commit messages MUST NOT reference non-SkillWeave topics (personal tools, local setup details, private workflows). The prerelease workflow filters these automatically.

Only SkillWeave-core concepts belong in public release artifacts:
- Skill names and capabilities
- Version numbers and release types
- Feature additions, improvements, fixes
- Dependency changes relevant to users
- Documentation updates

## GitHub API Usage

**Never poll GitHub API in loops.** Use streaming/watch commands instead:

| Task | Wrong (burns rate limit) | Right (1 API call) |
|------|--------------------------|---------------------|
| Wait for CI checks | `while true; do gh pr checks ...; sleep 15; done` | `gh pr checks <PR#> --watch` |
| Wait for workflow run | `while true; do gh run view ...; sleep 10; done` | `gh run watch <run-id>` |
| Check rate limit | `while true; do gh api rate_limit; sleep 30; done` | Single check, then `gh run watch` or `--watch` |

The GitHub API rate limit is **5000 requests/hour**. Polling loops burn through this in minutes. A single `--watch` call streams results via a long-lived connection.

## Release Naming Convention

Release titles MUST be exactly `SkillWeave vX.Y.Z` — no additional text in the title. Descriptive text belongs in the release notes body only.

Regex: `^SkillWeave v[0-9]+\.[0-9]+\.[0-9]+$`

This is enforced in CI (`auto-tag-release.yml`), the launch pre-flight checklist, and the releasechain skill. Block release creation if convention is violated.
