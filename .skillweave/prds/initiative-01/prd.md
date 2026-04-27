# PRD: Initiative 01 — Process Architecture and Bundle System

## 1. Executive Summary

**Project:** SkillWeave Process Architecture Redesign  
**Initiative:** 01 of 06 (Master Roadmap Phase A)  
**Domain:** Developer Tooling / AI-Assisted Product Development  
**Risk Mode:** Medium  

SkillWeave needs a clearer, more explicit product-development lifecycle that covers the full journey from idea to post-release optimization. The current process model has gaps in phase separation, entry-point flexibility, and bundle composition. This initiative redesigns the process architecture and defines a modular bundle system that supports different scopes, starting points, and user maturity levels.

**Core Value:** Transform SkillWeave from a skill bundle into a lifecycle-aware process system with intelligent routing and multiple bundle variants.

## 2. Problem Statement

### Current Situation
- SkillWeave has strong practical utility but lacks explicit lifecycle coverage
- Phase boundaries are unclear — discovery blends into blueprinting, release blends into launch
- No formal support for different entry points (user might start at idea, or mid-build, or pre-release)
- Bundle composition is monolithic — one size fits all
- Onboarding does not adapt to user context or maturity

### Impact
- Users unsure which skill to invoke for their current stage
- Workflow recommendation is weak — users must self-navigate
- Bundle system cannot serve different project scopes efficiently
- New users face steep learning curve without stage-aware guidance

## 3. Target Users & Personas

**Primary: Solo Developer / Indie Maker**
- Uses SkillWeave for end-to-end product development
- Needs: Clear guidance on which phase they're in, which bundle to use
- Pain: "I have an idea but don't know where to start in SkillWeave"

**Primary: Agency / Freelance Developer**
- Uses SkillWeave for client projects at various stages
- Needs: Jump into any stage, use only what's relevant
- Pain: "My client already has a spec, I just need build+release"

**Secondary: AI Agent Operator**
- Runs SkillWeave skills programmatically across agent frameworks
- Needs: Clean API boundaries between phases, capability-based routing
- Pain: "Skill overlap makes orchestration harder"

## 4. Solution Overview

### Revised Lifecycle Model (7 Phases)

| # | Phase | Focus |
|---|-------|-------|
| 1 | **Discovery & Research** | Market/problem discovery, user understanding, landscape mapping |
| 2 | **Definition & Blueprinting** | Problem definition, strategic framing, scope, PRD creation |
| 3 | **Solution Design** | User flows, architecture, feature breakdown, prototype direction |
| 4 | **Build & Preparation** | Task planning, implementation, execution sequences, handoff |
| 5 | **Release** | Testing, QA, deployment, packaging, release notes, rollout |
| 6 | **Launch** | Go-to-market, messaging, promotion, customer engagement |
| 7 | **Post-Release & Optimization** | Feedback, monitoring, iteration, adoption insights |

### Bundle Variants

| Bundle | Phases Covered | Use Case |
|--------|---------------|----------|
| **Full Lifecycle** | 1→7 | End-to-end product work |
| **Discovery-to-Blueprint** | 1→2 | Early-stage concept and research |
| **Design-and-Build** | 3→4 | Validated concept, needs implementation |
| **Release-and-Launch** | 5→6 | Ready to ship, needs finalization |
| **Post-Release Improvement** | 7 | Feedback-driven iteration |

### Entry Point Logic
The system detects user's current stage based on:
- Available artifacts (PRD exists? Code exists? Tests pass?)
- Explicit user declaration
- Skill invocation context
- Artifact maturity signals

### Workflow Recommendation
When a user invokes any skill, the system:
1. Assesses current stage and artifact maturity
2. Identifies gaps between current state and requested action
3. Recommends the appropriate bundle or upstream step
4. Provides guided onboarding if user is new

## 5. Functional Requirements

### 5.1 Core Features

**F-01: Lifecycle Phase Registry**
- Description: Central registry defining all 7 lifecycle phases with boundaries, inputs, outputs, and transitions
- Acceptance Criteria:
  - Phase definitions exist as structured data (YAML/JSON)
  - Each phase has defined entry conditions and exit conditions
  - Phase transitions are explicit (what must be true to move forward)
  - Phase registry is loadable by all SkillWeave skills

**F-02: Bundle Composition Engine**
- Description: System for composing bundles from phases, supporting predefined and custom combinations
- Acceptance Criteria:
  - 5 predefined bundle variants exist as configurations
  - Custom bundle composition is supported (pick phases)
  - Bundle metadata includes required capabilities, estimated effort, and recommended workflow
  - Bundles are selectable via CLI parameter or interactive prompt

**F-03: Entry Point Detection**
- Description: Automatic detection of user's current lifecycle stage based on project artifacts
- Acceptance Criteria:
  - Detection checks for: PRD, code, tests, deployment config, release notes
  - Detection returns a confidence-scored stage assessment
  - Detection works without requiring user to declare stage manually
  - Fallback to interactive stage selection if confidence is low

**F-04: Workflow Recommendation Engine**
- Description: Intelligent recommendation of next steps and appropriate bundle based on current state
- Acceptance Criteria:
  - Recommends bundle variant based on detected stage and declared goal
  - Identifies gaps (e.g., "PRD missing before build can start")
  - Suggests concrete next action
  - Integrates with existing SkillWeave intelligent detection system

**F-05: Phase-Aware Onboarding Flow**
- Description: Guided onboarding that adapts to user's stage and experience level
- Acceptance Criteria:
  - Onboarding asks about current stage, available artifacts, and goal
  - Onboarding recommends a bundle and starting skill
  - Onboarding can be skipped by experienced users
  - Onboarding state persists in `.skillweave/` for session continuity

**F-06: Phase Boundary Enforcement**
- Description: Skills respect phase boundaries and refuse or redirect work outside their scope
- Acceptance Criteria:
  - Each skill declares which phase(s) it belongs to
  - Invoking a skill outside its phase triggers a recommendation (not a hard block)
  - Phase boundary violations are logged for observability
  - Override is possible with explicit user consent

### 5.2 User Stories

- As a developer with only an idea, I want SkillWeave to guide me to Discovery first so that I don't skip important research
- As an agency developer with an existing spec, I want to start at Design-and-Build so that I don't repeat completed work
- As an AI agent operator, I want phase boundaries clearly defined so that I can orchestrate skills correctly
- As a new SkillWeave user, I want onboarding to tell me where to start so that I don't get overwhelmed
- As a returning user, I want SkillWeave to remember my project stage so that I can resume efficiently

## 6. Non-Functional Requirements

### Compatibility
- Must work with existing SkillWeave v0.5.x skill interfaces
- Must not break current skill invocation patterns
- Phase system must be opt-in (existing users can ignore it)

### Performance
- Entry point detection must complete in < 2 seconds
- Bundle composition must not add startup overhead > 500ms

### Extensibility
- New phases can be added without modifying core logic
- New bundle variants can be defined via configuration
- Third-party skills can declare phase membership

## 7. Technical Architecture

### Phase Registry Format
```yaml
# .skillweave/lifecycle/phases.yaml
phases:
  - id: discovery
    name: "Discovery & Research"
    order: 1
    entry_conditions:
      - "Project idea or problem statement exists"
    exit_conditions:
      - "Research artifacts produced"
      - "Problem space documented"
    skills: ["skillweave-discovery"]
    capabilities: ["research", "planning"]
    
  - id: blueprint
    name: "Definition & Blueprinting"
    order: 2
    entry_conditions:
      - "Problem statement validated"
    exit_conditions:
      - "PRD exists and is approved"
      - "Task breakdown complete"
    skills: ["skillweave-blueprint"]
    capabilities: ["planning"]
```

### Bundle Definition Format
```yaml
# .skillweave/lifecycle/bundles.yaml
bundles:
  full-lifecycle:
    phases: [discovery, blueprint, design, build, release, launch, post-release]
    recommended_for: "New projects from scratch"
    
  design-and-build:
    phases: [design, build]
    entry_requires: ["prd.json exists", "scope defined"]
    recommended_for: "Projects with existing validated concept"
```

### Integration Points
- Existing `integrate_with_skill()` function extended with phase awareness
- `.skillweave/config.yaml` extended with `active_bundle` and `current_phase`
- Progress tracking in `.skillweave/tracking-log/` extended with phase transitions

## 8. Success Metrics (Binary & Testable)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Phase definitions complete | 7 phases defined with entry/exit conditions | File exists and validates |
| Bundle variants defined | 5 bundles with metadata | Configuration validates against schema |
| Entry detection works | Correctly identifies stage for 3+ test scenarios | Automated test passes |
| Workflow recommendation works | Returns valid recommendation for all entry points | Automated test passes |
| Backward compatible | Existing skill invocations work unchanged | Existing test suite passes |

## 9. Scope & Constraints

### In Scope (This Initiative)
- Lifecycle phase model definition
- Bundle variant definitions
- Entry point detection logic
- Workflow recommendation logic
- Onboarding flow design
- Phase boundary enforcement design
- Integration with existing intelligent detection

### Out of Scope
- Individual skill rewrites (handled by other initiatives)
- Release vs Launch separation details (Initiative 03)
- Execution system changes (Initiative 05)
- GitHub integration (Initiative 06)
- Discovery skill implementation (Initiative 02)

## 10. Timeline & Milestones

| Phase | Deliverable | Estimated Effort |
|-------|-------------|-----------------|
| Design | Phase registry schema + bundle definitions | 2 hours |
| Build | Entry point detection + recommendation engine | 3 hours |
| Build | Onboarding flow + phase boundary logic | 2 hours |
| Integration | Connect to existing skill system | 2 hours |
| Testing | Validation across scenarios | 1 hour |

**Total Estimated Effort:** ~10 hours

## 11. Assumptions & Dependencies

### Assumptions
- Current skill interfaces remain stable during redesign
- Phase model covers all practical SkillWeave use cases
- Users will accept guided workflow over free-form skill invocation

### Dependencies
- Initiative 02 (Discovery skill) for Discovery phase implementation
- Initiative 03 (Release rationalization) for Release/Launch phase clarity
- Initiative 05 (Execution system) for phase-aware execution

## 12. Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Over-engineering phase system | Medium | High | Start minimal, 7 phases max, iterate |
| Breaking existing workflows | Low | Critical | Backward compatibility as hard requirement |
| User resistance to guided flow | Medium | Medium | Make phases opt-in, not mandatory |
| Phase boundaries too rigid | Medium | Medium | Soft enforcement with override option |
