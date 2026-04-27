# PRD: Initiative 06 — GitHub Action, GitHub App, and Integration Layer

## 1. Executive Summary

**Project:** SkillWeave GitHub-Native Integration Layer  
**Initiative:** 06 of 06 (Master Roadmap Phase D)  
**Domain:** Developer Tooling / AI-Assisted Product Development  
**Risk Mode:** Medium  

SkillWeave should not remain only a repository-based skill bundle. This initiative defines GitHub-native surfaces — Actions for validation and release readiness, optional future App logic for deeper integration — that improve trust, automation, and discoverability while keeping the core repo focused.

**Core Value:** Bundle and release validation improve; trust and automation strengthen; GitHub integration supports the product rather than distracting from it.

## 2. Problem Statement

### Current Situation
- SkillWeave bundles have no automated validation in CI/CD
- Release readiness is manual and inconsistent
- No trust signals beyond repository stars and README claims
- No standard way to validate bundle structure or metadata
- Distribution relies on manual git clone or copy

### Impact
- Bundle quality varies without automated checks
- Users cannot trust bundle integrity without manual review
- Release discipline is ad-hoc
- Adoption limited by lack of GitHub-native integration points

## 3. Solution Overview

### Three-Layer Approach

**Layer 1: Validation Action (Immediate)**
GitHub Action that validates bundle structure, skill metadata, manifest consistency, and documentation completeness.

**Layer 2: Release Readiness Action (Immediate)**
GitHub Action that checks release prerequisites: version consistency, changelog updated, tests passing, required files present.

**Layer 3: GitHub App (Future, Assessed)**
Optional deeper integration for repository sync, release signal capture, trust enrichment, and discovery support. This PRD assesses feasibility but does not require immediate implementation.

### Architecture Decision: Separate Integration Repos

GitHub Actions should live in **dedicated repos** (e.g., `skillweave-action-validate`, `skillweave-action-release-check`) rather than bloating the core SkillWeave repo. This keeps the core focused and follows GitHub Actions distribution conventions.

## 4. Functional Requirements

### 4.1 Core Features

**F-01: Bundle Validation Action**
- Description: GitHub Action that validates SkillWeave bundle structure and metadata
- Acceptance Criteria:
  - Action validates: skill directory structure, SKILL.md presence, capability.yaml schema, required fields
  - Action validates: manifest consistency (if manifest exists)
  - Action validates: no broken internal references
  - Action produces structured output (pass/fail per check, summary)
  - Action configurable via `action.yml` inputs (strictness level, paths)
  - Action usable in any GitHub repository

**F-02: Release Readiness Action**
- Description: GitHub Action that checks if a release meets defined prerequisites
- Acceptance Criteria:
  - Checks: version bumped, CHANGELOG updated, tests passing, required files present
  - Checks: no draft/WIP markers in release candidate
  - Produces readiness report (pass/fail per prerequisite)
  - Configurable prerequisite list via input or config file
  - Can block PR merge if readiness fails (as status check)
  - Produces release summary artifact

**F-03: Validation Output Format**
- Description: Standardized output format for validation and readiness results
- Acceptance Criteria:
  - JSON output with: checks[], summary, pass_count, fail_count, warnings
  - GitHub Actions annotations (error/warning) for failed checks
  - Markdown summary for PR comments
  - Machine-readable for downstream automation

**F-04: Trust Signal Generation**
- Description: Generate provenance and trust signals from validation results
- Acceptance Criteria:
  - Validation badge (pass/fail) generatable for README
  - Release validation results stored as GitHub release asset
  - Validation history trackable across releases
  - Attestation-ready output format (for future supply chain signing)

**F-05: GitHub App Feasibility Assessment**
- Description: Assessment of whether a GitHub App adds value beyond Actions
- Acceptance Criteria:
  - Assessment covers: repository sync use case, release signal capture, trust enrichment, discovery support
  - Assessment evaluates: build cost, maintenance burden, user value
  - Recommendation: proceed / defer / skip with rationale
  - If proceed: scope definition for MVP App features

**F-06: Action Distribution and Versioning**
- Description: Proper versioning and distribution of Actions via GitHub Marketplace
- Acceptance Criteria:
  - Each Action has semantic versioning
  - Actions published to GitHub Marketplace (or usable via direct reference)
  - README with usage examples for each Action
  - Version pinning supported (major version tags)

### 4.2 User Stories

- As a SkillWeave bundle author, I want automated validation in my CI so that I catch structure issues before release
- As a consumer of SkillWeave bundles, I want to see validation badges so that I can trust bundle quality
- As a release manager, I want pre-merge readiness checks so that no incomplete release gets published
- As the SkillWeave maintainer, I want GitHub-native integration in separate repos so that the core stays focused

## 5. Non-Functional Requirements

### Portability
- Actions must work on `ubuntu-latest` GitHub runners
- No proprietary dependencies — standard GitHub Actions ecosystem only

### Performance
- Validation Action completes in < 30 seconds for typical bundle
- Release Readiness Action completes in < 60 seconds

### Maintainability
- Actions in separate repos with independent release cycles
- Core SkillWeave repo has no Action-related code

## 6. Technical Architecture

### Repository Structure
```
github.com/anomalyco/
  ├── SkillWeave/                      # Core product repo (unchanged)
  ├── skillweave-action-validate/      # Bundle validation Action
  │   ├── action.yml
  │   ├── src/
  │   ├── dist/
  │   └── README.md
  └── skillweave-action-release-check/ # Release readiness Action
      ├── action.yml
      ├── src/
      ├── dist/
      └── README.md
```

### Validation Action Usage
```yaml
# .github/workflows/validate.yml
name: Validate SkillWeave Bundle
on: [push, pull_request]
jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: anomalyco/skillweave-action-validate@v1
        with:
          path: '.'
          strictness: 'standard'
```

### Release Readiness Usage
```yaml
# .github/workflows/release-check.yml
name: Release Readiness Check
on:
  pull_request:
    branches: [main]
jobs:
  readiness:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: anomalyco/skillweave-action-release-check@v1
        with:
          require_changelog: true
          require_version_bump: true
          require_tests: true
```

## 7. Success Metrics (Binary & Testable)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Validation Action works | Validates SkillWeave repo structure correctly | Action runs on SkillWeave repo without false positives |
| Release Readiness works | Correctly identifies ready/not-ready states | Test with prepared and unprepared releases |
| Separate repos created | Actions not in core repo | Repo exists with action.yml |
| Output format valid | JSON + markdown outputs correct | Schema validation |
| App assessment complete | Recommendation documented | Assessment document exists |

## 8. Timeline & Milestones

| Phase | Deliverable | Estimated Effort |
|-------|-------------|-----------------|
| Design | Action specifications + output format | 1.5 hours |
| Build | Bundle Validation Action (separate repo) | 3 hours |
| Build | Release Readiness Action (separate repo) | 3 hours |
| Build | Trust signal generation | 1.5 hours |
| Assessment | GitHub App feasibility document | 2 hours |
| Testing | Actions tested on SkillWeave repo | 1.5 hours |
| Distribution | Marketplace listing + versioning | 1 hour |

**Total Estimated Effort:** ~13.5 hours

## 9. Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Actions too rigid for diverse bundle structures | Medium | Medium | Configurable strictness levels, extensible check system |
| Maintenance burden of separate repos | Medium | Medium | Minimal scope, automated testing, shared CI patterns |
| GitHub App over-scoped | Medium | High | Assessment-first approach, defer until clear value demonstrated |
| False positives in validation | Medium | High | Conservative defaults, whitelist mechanism for known patterns |
