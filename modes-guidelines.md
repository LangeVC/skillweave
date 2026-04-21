# SkillWeave Mode Guidelines

## Overview
Three risk modes influence how SkillWeave skills behave. The mode is set in `.skillweave/config.yaml` under `mode: conservative|medium|unicorn`.

## Conservative Mode
**Goal**: Maximum safety, security, and reliability. Suitable for production-critical projects.

### Behavior Changes
#### Blueprint Skill
- Requires explicit approval for all assumptions
- Validates all inputs with strict rules
- Generates detailed documentation
- Suggests conservative technology choices

#### PromptChain Skills
- Adds extra validation steps
- Requires human confirmation before execution of each batch
- Limits parallel execution to reduce risk
- Enforces comprehensive testing requirements

#### ReleaseChain Skill
- Requires manual approval for each task
- Runs extensive security checks
- Limits autonomous execution (more human checkpoints)
- Prevents destructive operations without explicit consent

#### General
- All operations are logged in detail
- Error handling is cautious (fail early)
- Performance is secondary to safety

## Medium Mode
**Goal**: Balanced approach between safety and productivity. Default for most projects.

### Behavior Changes
#### Blueprint Skill
- Validates inputs with standard rules
- Seeks approval only for high-risk assumptions
- Generates standard documentation

#### PromptChain Skills
- Standard validation
- Human confirmation at major gates (batch boundaries)
- Moderate parallel execution
- Standard testing requirements

#### ReleaseChain Skill
- Automatic execution with periodic checkpoints
- Standard security checks
- Balanced autonomy with oversight
- Destructive operations require confirmation

#### General
- Standard logging
- Balanced error handling
- Good performance with acceptable risk

## Unicorn Mode
**Goal**: Maximum creativity, speed, and innovation. Suitable for prototyping, research, and experimental projects.

### Behavior Changes
#### Blueprint Skill
- Minimal validation
- Makes optimistic assumptions
- Generates lightweight documentation
- Suggests cutting-edge technology choices

#### PromptChain Skills
- Minimal validation steps
- Autonomous execution with few interruptions
- Maximizes parallel execution
- Lightweight testing requirements

#### ReleaseChain Skill
- Fully autonomous execution
- Minimal security checks (assumes trusted environment)
- High autonomy with few checkpoints
- Allows destructive operations with warning

#### General
- Minimal logging (only errors)
- Optimistic error handling (retry, continue)
- Performance prioritized over safety

## Configuration Examples
```yaml
# .skillweave/config.yaml
mode: medium  # conservative, medium, unicorn

# Optional feature toggles
features:
  checklist_execution: true
  design_thinking_lens: false
  community_patterns: false

# Mode-specific overrides (optional)
overrides:
  conservative:
    max_parallel_tasks: 1
    require_approval: true
  unicorn:
    max_parallel_tasks: 10
    require_approval: false
```

## Implementation Notes
- Skills should read mode from configuration manager
- Default behavior is Medium if not specified
- Mode can be changed mid-project (with warning)
- Each skill must document mode-specific behavior