# PRD: Initiative 02 — Discovery, Research, and Design Thinking Lens

## 1. Executive Summary

**Project:** SkillWeave Discovery & Design Thinking Enhancement  
**Initiative:** 02 of 06 (Master Roadmap Phase A)  
**Domain:** Developer Tooling / AI-Assisted Product Development  
**Risk Mode:** Medium  

SkillWeave needs stronger discovery, research, and design-thinking capabilities. Currently, design thinking principles are referenced but not operationalized. Discovery and research deserve first-class treatment as distinct process steps rather than being absorbed into broader blueprint work. This initiative creates a dedicated Discovery & Research skill focus and embeds an operational Design Thinking Lens across adjacent skills.

**Core Value:** Improve the quality of thinking inside SkillWeave phases, not just the sequence of steps.

## 2. Problem Statement

### Current Situation
- Discovery and research are implicit, not explicitly guided
- Design thinking principles exist as configuration flags but lack operational depth
- Early-stage problem framing quality directly impacts later execution quality
- Workshop rules (quantity over quality, defer judgment, fail fast) are not embedded in prompt behavior
- Novice users lack guidance on how to think, not just what step comes next

### Impact
- Weak problem framing leads to poorly scoped PRDs
- Users skip research and jump to building
- Design decisions lack user-centered evidence
- Iteration quality suffers without structured feedback synthesis

## 3. Target Users & Personas

**Primary: Product-Minded Developer**
- Wants to validate ideas before building
- Needs: Structured research prompts, competitor analysis templates, user empathy frameworks
- Pain: "I built the wrong thing because I skipped research"

**Primary: Novice SkillWeave User**
- New to structured product development
- Needs: Guided discovery process, design thinking principles made practical
- Pain: "I know I should do research but don't know how"

**Secondary: Design-Oriented Team Lead**
- Uses SkillWeave to guide team through ideation and design
- Needs: Workshop-ready prompts, divergent thinking support, artifact-first outputs
- Pain: "SkillWeave is great for execution but weak on early-stage thinking"

## 4. Solution Overview

### Two Deliverables

**A. Discovery & Research Skill Focus**
A new skill or skill extension that explicitly covers:
- Problem and opportunity articulation
- User empathy and context gathering
- Competitor and landscape mapping
- Assumption surfacing and validation
- Research artifact generation

**B. Operational Design Thinking Lens**
A cross-cutting lens embedded in multiple skills that operationalizes:
- Workshop rules as prompt behaviors
- UX/product principles as review criteria
- Cognitive ergonomics as output formatting rules
- Iteration quality as feedback synthesis patterns

### Design Thinking Workshop Rules → Prompt Behaviors

| Workshop Rule | Prompt Behavior |
|--------------|----------------|
| Quantity Over Quality | Ideation prompts generate 5+ options before evaluating |
| Defer Judgment | Separate ideation steps from evaluation steps |
| Embrace Wild Ideas | Include "unconventional" option in every ideation output |
| Fail Fast, Cheap, Often | Prototype prompts favor speed and low-cost validation |
| Show, Don't Tell | Outputs include diagrams, flows, mockups, structured artifacts |
| Build on Ideas of Others | Expansion prompts reference and extend prior ideas |

### UX/Product Principles → Output Rules

| Principle | Output Rule |
|-----------|------------|
| Scan Before Read | All outputs use headers, bullets, summaries |
| Value Over Noise | Every section justifies its inclusion |
| Use Known Patterns | Prefer conventional formats users already understand |
| Visual Hierarchy | Emphasize key information, de-emphasize details |
| Human-Centricity | User impact stated for every decision |

## 5. Functional Requirements

### 5.1 Core Features

**F-01: Discovery Prompt Library**
- Description: Structured prompts for each discovery sub-phase (empathy, research, framing, assumptions)
- Acceptance Criteria:
  - 10+ discovery prompts exist as reusable templates
  - Prompts cover: user empathy, problem articulation, competitor analysis, assumption surfacing
  - Each prompt has clear input requirements and expected output format
  - Prompts produce artifacts (documents), not just chat responses

**F-02: Research Artifact Templates**
- Description: Templates for common research outputs (persona cards, competitor matrix, assumption log, opportunity canvas)
- Acceptance Criteria:
  - 5+ artifact templates exist in `.skillweave/templates/discovery/`
  - Templates are fillable by AI from research prompts
  - Templates follow Scan Before Read principle
  - Output format supports markdown and structured YAML

**F-03: Design Thinking Lens Configuration**
- Description: Configurable lens that can be activated per-skill to apply design thinking principles to outputs
- Acceptance Criteria:
  - Lens is activatable via `.skillweave/config.yaml` (design_thinking_lens: true)
  - Lens defines behavioral rules for ideation, evaluation, and iteration
  - Rules are loadable by any skill at runtime
  - Lens applies to both prompts (input shaping) and outputs (formatting/review)

**F-04: Ideation Mode with Divergent Thinking**
- Description: Dedicated ideation mode that enforces quantity-first, judgment-deferred idea generation
- Acceptance Criteria:
  - Ideation mode generates minimum 5 options per prompt
  - At least 1 option is explicitly unconventional/wild
  - Evaluation is deferred to a separate step
  - Prior ideas can be expanded (Build on Others rule)
  - Output includes brief rationale per option

**F-05: Assumption Surfacing and Validation Framework**
- Description: Systematic approach to identifying, documenting, and prioritizing assumptions for validation
- Acceptance Criteria:
  - Assumption extraction prompt identifies 5+ assumptions from any project description
  - Assumptions are categorized by risk (impact if wrong × probability)
  - Validation methods are suggested per assumption
  - Assumptions are tracked in `.skillweave/tracking-log/assumptions.yaml`

**F-06: Iteration Quality Framework**
- Description: Structured feedback synthesis and evidence-driven revision patterns for design iteration
- Acceptance Criteria:
  - Feedback synthesis template exists for collecting and organizing input
  - Revision prompts reference evidence (not opinion) for changes
  - Learning extraction happens after each iteration
  - Iteration log tracks what changed and why

### 5.2 User Stories

- As a developer with a vague idea, I want discovery prompts to help me articulate the problem so that my PRD has a strong foundation
- As a product thinker, I want ideation mode to generate many options so that I don't prematurely narrow my solution space
- As a team lead, I want research artifact templates so that discovery outputs are consistent and shareable
- As an iterating builder, I want structured feedback synthesis so that my revisions are evidence-driven
- As a SkillWeave user, I want design thinking principles applied to outputs so that they are scannable and clear

## 6. Non-Functional Requirements

### Compatibility
- Design Thinking Lens must work with existing skills (blueprint, promptchain)
- Discovery features must integrate with Initiative 01 lifecycle phases
- Must not add mandatory dependencies — lens is opt-in

### Output Quality
- All outputs follow Scan Before Read principle
- No output section without clear value justification
- Artifact-first: knowledge goes into files, not chat

## 7. Technical Architecture

### Lens Configuration
```yaml
# .skillweave/config.yaml (extended)
features:
  design_thinking_lens: true
  
design_thinking:
  workshop_rules:
    quantity_over_quality: true
    defer_judgment: true
    embrace_wild_ideas: true
    fail_fast: true
    show_dont_tell: true
    build_on_others: true
  output_rules:
    scan_before_read: true
    value_over_noise: true
    use_known_patterns: true
    visual_hierarchy: true
    human_centricity: true
  ideation:
    min_options: 5
    require_wild_option: true
    separate_evaluation: true
```

### Discovery Templates Structure
```
.skillweave/templates/discovery/
  ├── persona-card.md
  ├── competitor-matrix.md
  ├── assumption-log.yaml
  ├── opportunity-canvas.md
  └── research-summary.md
```

### Integration Points
- Lens loaded by skills at startup when `design_thinking_lens: true`
- Discovery prompts invocable from Blueprint skill or standalone
- Assumption tracking feeds into PRD risk section
- Research artifacts referenced by Blueprint phase

## 8. Success Metrics (Binary & Testable)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Discovery prompts available | 10+ prompts with clear I/O specs | File count and schema validation |
| Artifact templates available | 5+ templates in discovery/ | File count and content check |
| Lens configuration works | Config loads and rules apply | Automated test |
| Ideation mode produces 5+ options | Every ideation run has ≥5 options | Output validation |
| Assumption tracking works | Assumptions extracted and stored | File existence and content check |

## 9. Scope & Constraints

### In Scope
- Discovery prompt library
- Research artifact templates
- Design Thinking Lens configuration and rules
- Ideation mode with divergent thinking
- Assumption surfacing framework
- Iteration quality framework

### Out of Scope
- Full Discovery skill implementation as separate executable (deferred)
- Visual mockup generation (requires external tools)
- User interview automation
- Competitive intelligence API integrations
- Analytics or telemetry for design decisions

## 10. Timeline & Milestones

| Phase | Deliverable | Estimated Effort |
|-------|-------------|-----------------|
| Design | Lens configuration schema + workshop rule mapping | 1.5 hours |
| Build | Discovery prompt library (10+ prompts) | 2 hours |
| Build | Research artifact templates (5+ templates) | 1.5 hours |
| Build | Ideation mode + assumption framework | 2 hours |
| Build | Iteration quality framework | 1 hour |
| Integration | Connect lens to existing skills | 1.5 hours |
| Testing | Validate all outputs and configurations | 1 hour |

**Total Estimated Effort:** ~10.5 hours

## 11. Assumptions & Dependencies

### Assumptions
- Design thinking principles can be meaningfully operationalized as prompt rules
- Users benefit from structured research even in solo/indie contexts
- Artifact-first approach produces better outcomes than chat-first

### Dependencies
- Initiative 01 (Process Architecture) for lifecycle phase integration
- Existing `.skillweave/config.yaml` configuration system
- Existing template loading infrastructure (or new if not present)

## 12. Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Design thinking rules feel forced/artificial | Medium | Medium | Make all rules opt-in, provide clear value examples |
| Discovery prompts too generic to be useful | Medium | High | Ground prompts in real scenarios, test with actual projects |
| Lens adds overhead without clear value | Low | Medium | Measure output quality before/after lens activation |
| Template explosion / too many artifacts | Medium | Low | Start with 5 core templates, expand based on demand |
