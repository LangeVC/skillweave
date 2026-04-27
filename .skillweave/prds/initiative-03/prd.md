# PRD: Initiative 03 — Release, Launch, and Workflow Rationalization

## 1. Executive Summary

**Project:** SkillWeave Release & Launch Rationalization  
**Initiative:** 03 of 06 (Master Roadmap Phase A)  
**Domain:** Developer Tooling / AI-Assisted Product Development  
**Risk Mode:** Medium  

There is meaningful overlap between `promptchain-execute` and `releasechain`. This initiative resolves the redundancy, sharpens `releasechain` into a lifecycle-scoped release tool, clarifies the separation between Release (technical shipping) and Launch (market activation), and adds intelligent workflow recommendation when users invoke release flows prematurely.

**Core Value:** Make release workflows trustworthy, focused, and stage-aware — users get guided to the right workflow at the right time.

## 2. Problem Statement

### Current Situation
- `promptchain-execute` and `releasechain` have unclear ownership boundaries
- Both can execute task sequences, creating ambiguity about which to use
- Release and Launch are loosely blended in current flows
- No mechanism to detect or redirect premature release invocations
- Users can invoke release without prerequisites being met

### Impact
- Confused user experience — "which skill do I use?"
- Redundant logic increases maintenance burden
- Release quality suffers without prerequisite checks
- Launch activities get mixed with technical release steps

## 3. Target Users & Personas

**Primary: Developer Ready to Ship**
- Has code, tests, deployment config — wants to release
- Needs: Clear release checklist, readiness validation, packaging support
- Pain: "I'm not sure if I've covered everything before releasing"

**Primary: Developer NOT Ready to Ship**
- Invokes release skill prematurely (missing tests, no deployment config)
- Needs: Gentle redirect to correct upstream workflow
- Pain: "I called release but I'm actually still building"

## 4. Solution Overview

### Role Clarification

**`releasechain` — Release Execution (Phase 5)**
- Tightly scoped to release readiness and release execution
- Testing, QA, deployment, packaging, release notes, rollout checks
- Can refuse/redirect work that belongs to earlier stages
- Checks prerequisites before proceeding

**`promptchain-execute` — General Execution Substrate**
- Reassessed as an orchestration mechanism, not a phase-specific skill
- Executes prompt sequences regardless of lifecycle phase
- Used by other skills internally (including releasechain)
- Not directly user-facing for release work

### Release vs Launch Separation

| Aspect | Release (Phase 5) | Launch (Phase 6) |
|--------|-------------------|-------------------|
| Focus | Technical shipping readiness | Market-facing activation |
| Activities | Testing, QA, deployment, packaging, release notes | Messaging, promotion, customer engagement, go-to-market |
| Owner | Engineering / DevOps | Product / Marketing |
| Artifacts | Release notes, deployment logs, test reports | Launch content, announcements, enablement materials |
| Gating | All tests pass, deployment verified | Release completed, content approved |

### Intelligent Workflow Recommendation

When release is invoked prematurely:
1. Detect missing prerequisites (no tests, no deploy config, unstable code)
2. Identify current actual stage
3. Explain the gap clearly
4. Recommend the correct upstream workflow
5. Optionally generate a release-readiness checklist

## 5. Functional Requirements

### 5.1 Core Features

**F-01: Release Readiness Assessment**
- Description: Pre-flight check that validates release prerequisites before proceeding
- Acceptance Criteria:
  - Checks for: test suite exists, tests pass, deployment config exists, release notes drafted
  - Returns readiness score with pass/fail per prerequisite
  - Blocks release execution if critical prerequisites fail
  - Provides gap analysis for failed prerequisites

**F-02: Premature Invocation Detection and Redirect**
- Description: When release is invoked before prerequisites are met, detect and guide user to correct workflow
- Acceptance Criteria:
  - Detects missing prerequisites within 2 seconds
  - Returns recommended upstream workflow (e.g., "run build phase first")
  - Explains what is missing and why it matters
  - Offers to generate a release-readiness checklist
  - Does not block with override flag

**F-03: Release Execution Workflow**
- Description: Structured release flow covering testing verification, packaging, release notes, deployment, and rollout validation
- Acceptance Criteria:
  - Sequential steps: verify tests → package → generate release notes → deploy → validate rollout
  - Each step has pass/fail gate
  - Failed steps produce actionable error guidance
  - Progress tracked in `.skillweave/tracking-log/`
  - Completion produces release summary artifact

**F-04: Launch Phase Stub**
- Description: Separate launch phase definition with distinct activities, not mixed with release
- Acceptance Criteria:
  - Launch phase defined in lifecycle registry (from Initiative 01)
  - Launch activities list documented (messaging, promotion, content, enablement)
  - Launch entry condition: release completed
  - Launch skill placeholder exists (full implementation deferred)

**F-05: `promptchain-execute` Role Redefinition**
- Description: Clarify `promptchain-execute` as internal orchestration substrate, not a user-facing release tool
- Acceptance Criteria:
  - Documentation updated to clarify execute's role
  - Execute skill metadata marks it as "orchestration" type
  - Release-specific logic removed from execute (lives in releasechain)
  - Execute remains usable for general prompt sequence execution
  - No user-facing behavior changes for non-release usage

**F-06: Release Readiness Checklist Generator**
- Description: Generate a markdown checklist of release prerequisites based on project state
- Acceptance Criteria:
  - Checklist generated from readiness assessment results
  - Items are actionable and specific (not generic)
  - Checklist saved to `.skillweave/checklists/release-readiness.md`
  - Items can be tracked (checkbox format)
  - Integrates with Initiative 05 checklist execution system

### 5.2 User Stories

- As a developer ready to release, I want readiness validation so that I don't ship with missing prerequisites
- As a developer who invoked release too early, I want clear guidance on what to do first so that I can prepare properly
- As an AI agent, I want clear skill boundaries so that I invoke the right skill for the right phase
- As a product owner, I want release and launch separated so that technical shipping doesn't mix with market activation

## 6. Non-Functional Requirements

### Compatibility
- Existing `promptchain-execute` invocations must continue to work
- `releasechain` API changes must be backward-compatible or clearly versioned
- Must integrate with Initiative 01 lifecycle phase system

### Performance
- Release readiness assessment completes in < 5 seconds
- Premature invocation detection completes in < 2 seconds

## 7. Technical Architecture

### Release Readiness Model
```yaml
release_prerequisites:
  critical:
    - id: tests_exist
      check: "Test files exist in project"
      remediation: "Create test suite using build phase"
    - id: tests_pass
      check: "Test suite runs without failures"
      remediation: "Fix failing tests before release"
    - id: deploy_config
      check: "Deployment configuration exists"
      remediation: "Set up deployment in infrastructure task"
  recommended:
    - id: release_notes
      check: "Release notes drafted"
      remediation: "Generate release notes from changelog"
    - id: version_bumped
      check: "Version number updated"
      remediation: "Bump version in package manifest"
  optional:
    - id: monitoring
      check: "Post-release monitoring configured"
      remediation: "Set up health checks and alerts"
```

### Skill Boundary Definitions
```yaml
# releasechain metadata
skill: releasechain
phase: release
type: phase-specific
prerequisites: [tests_exist, tests_pass, deploy_config]

# promptchain-execute metadata  
skill: promptchain-execute
phase: any
type: orchestration-substrate
prerequisites: []
```

## 8. Success Metrics (Binary & Testable)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Readiness assessment works | Correctly identifies 3+ prerequisite states | Automated test |
| Premature detection works | Redirects user when prerequisites missing | Automated test |
| Release flow completes | End-to-end release on prepared project succeeds | Integration test |
| Role separation clear | Documentation distinguishes execute vs releasechain | Review |
| Backward compatible | All existing tests pass | Test suite |

## 9. Scope & Constraints

### In Scope
- Release readiness assessment
- Premature invocation detection and redirect
- Release execution workflow
- promptchain-execute role clarification
- Release vs Launch separation
- Release readiness checklist generator

### Out of Scope
- Full Launch skill implementation (placeholder only)
- Deployment automation for specific platforms
- CI/CD pipeline creation
- Post-release monitoring implementation

## 10. Timeline & Milestones

| Phase | Deliverable | Estimated Effort |
|-------|-------------|-----------------|
| Design | Release readiness model + skill boundary definitions | 1 hour |
| Build | Release readiness assessment | 1.5 hours |
| Build | Premature invocation detection + redirect | 1.5 hours |
| Build | Release execution workflow | 2 hours |
| Build | Checklist generator + launch phase stub | 1 hour |
| Refactor | promptchain-execute role clarification | 1.5 hours |
| Testing | Integration and backward compatibility tests | 1.5 hours |

**Total Estimated Effort:** ~10 hours

## 11. Assumptions & Dependencies

### Assumptions
- Overlap between execute and releasechain can be resolved without breaking changes
- Users accept release prerequisite checks as helpful, not obstructive
- Release and Launch are conceptually separable for all project types

### Dependencies
- Initiative 01 (Process Architecture) for lifecycle phase registry
- Initiative 05 (Execution System) for checklist integration
- Existing promptchain-execute codebase for refactoring

## 12. Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Refactoring execute breaks existing workflows | Medium | Critical | Backward compatibility tests, gradual migration |
| Release prerequisites too strict for small projects | Medium | Medium | Configurable strictness levels, override flag |
| Launch phase unclear without full implementation | Low | Low | Clear stub with documented future scope |
