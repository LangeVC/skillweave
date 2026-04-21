# Design-Thinking Lens Specification

## Overview
Optional lens that applies decision rules to UI/UX elements during design and development. The lens is based on principles from design thinking and cognitive ergonomics.

## Core Rules
### 1. Value ≥ Noise
- **Principle**: Every element must provide clear value; remove or reduce noise.
- **Application**: Skills should question elements that don't contribute to user goals.
- **Example**: Remove decorative graphics that don't aid understanding.

### 2. Scan Before Read
- **Principle**: Information should be scannable before requiring deep reading.
- **Application**: Structure content with headers, bullet points, visual hierarchy.
- **Example**: Use clear headings, short paragraphs, emphasis on key terms.

### 3. Active Over Available
- **Principle**: Prefer active decisions over making all options available.
- **Application**: Guide users toward decisions rather than presenting endless choices.
- **Example**: Wizard interface over complex configuration panel.

### 4. Glance First, Drill-Down on Demand
- **Principle**: Provide overview first, details on request.
- **Application**: Implement progressive disclosure.
- **Example**: Dashboard with summary, click for details.

### 5. Widget ≠ Workspace
- **Principle**: Clearly distinguish between components (widgets) and the workspace.
- **Application**: Maintain clear visual separation.
- **Example**: Toolbar vs. canvas differentiation.

### 6. Decision-Ready Data
- **Principle**: Present data in a format ready for decision-making.
- **Application**: Summarize, visualize, highlight trends.
- **Example**: Charts instead of raw tables.

## Implementation
### Configuration
```yaml
# .skillweave/config.yaml
features:
  design_thinking_lens: true  # or false

design_thinking:
  rules:
    - value_noise: true
    - scan_before_read: true
    - active_over_available: false  # optional per rule
  strictness: medium  # low, medium, high
```

### Integration Points
#### Blueprint Skill
- Applies rules to PRD structure and documentation.
- Suggests information architecture improvements.
- Questions unnecessary features.

#### PromptChain Skills
- Applies rules to generated sequences.
- Ensures step-by-step guidance (active over available).
- Structures output for scannability.

#### ReleaseChain Skill
- Applies rules to UI components during development.
- Suggests improvements to user interfaces.
- Encourages progressive disclosure.

### Behavior
- When lens is enabled, skills should output "Design-Thinking Notes" section.
- Notes suggest improvements based on rules.
- Can be ignored (advisory) or enforced (strict mode).

## Examples
### Blueprint Output
```markdown
# Design-Thinking Notes
- **Value ≥ Noise**: Consider removing "Social Media Integration" if not core to MVP.
- **Scan Before Read**: Add executive summary at top of PRD.
- **Decision-Ready Data**: Include comparison table of technology options.
```

### UI Component Review
```
Design-Thinking Feedback:
- **Widget ≠ Workspace**: Make toolbar more distinct from main content area.
- **Glance First**: Add summary card before detailed statistics.
- **Active Over Available**: Reduce configuration options to recommended defaults.
```

## Customization
Rules can be extended in `.skillweave/manifesto/design-rules.yaml`:
```yaml
custom_rules:
  - name: "Mobile First"
    description: "Design for mobile before desktop"
    apply_to: ["blueprint", "releasechain"]
  - name: "Accessibility First"
    description: "Ensure WCAG compliance"
    apply_to: ["releasechain"]
```

## Notes
- Lens is optional and can be disabled.
- Rules are advisory by default; strictness controls enforcement.
- Should not significantly slow down skill execution.