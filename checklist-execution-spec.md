# Checklist Execution Specification

## Overview
SkillWeave can process markdown checklists and execute tasks in a loop until all checkboxes are checked. This feature is optional and can be enabled/disabled in config.

## Input Format
Checklists are provided as part of the skill input (embedded in markdown). Example:

```markdown
# Project Setup Checklist

- [ ] Initialize repository
- [ ] Configure build tools
- [ ] Set up CI/CD pipeline
- [ ] Write initial documentation
```

## Processing Logic
1. **Detection**: Skill scans input for markdown checkboxes (`- [ ]`).
2. **Parsing**: Each unchecked checkbox becomes a task.
3. **Execution**: Skills process tasks sequentially (or in parallel if dependencies allow).
4. **Progress Tracking**: Checked state is persisted in tracking-log.
5. **Loop**: After each iteration, skill checks if any checkboxes remain unchecked. If yes, continues.

## Persistence
- Checkbox state is stored in `.skillweave/tracking-log/checklist-<hash>.yaml`
- Format:
  ```yaml
  checklist_hash: abc123
  items:
    - id: 0
      text: "Initialize repository"
      checked: true
      completed_at: "2025-04-20T10:30:00"
    - id: 1
      text: "Configure build tools"
      checked: false
  ```
- On session restart, skill loads previous state and continues.

## Integration with Skills
### Blueprint Skill
- Can accept checklist as part of PRD creation.
- Each checkbox may correspond to a section of the PRD.

### PromptChain Skills
- Checklist can define steps in a sequence.
- Each checkbox may map to a batch or step.

### ReleaseChain Skill
- Checklist can represent task list from PRD.
- Each checkbox is a development task.

## Configuration
```yaml
# .skillweave/config.yaml
features:
  checklist_execution: true  # or false

checklist:
  auto_continue: true        # automatically continue loop
  max_iterations: 50         # safety limit
  require_confirmation: false # ask before each iteration (conservative mode)
```

## Error Handling
- If a task fails, checkbox remains unchecked.
- Skill may retry based on mode (conservative: stop, unicorn: continue).
- Failures logged in tracking-log.

## Examples
### Simple Checklist
```
/skillweave-blueprint idea="Setup new project" checklist="
- [ ] Choose tech stack
- [ ] Design architecture
- [ ] Create repository
"
```

### Combined with Other Inputs
```
/skillweave-promptchain-execute inputs='{"checklist": "- [ ] Build API\n- [ ] Write tests", "business_idea": "E-commerce"}'
```

## Implementation Notes
- Feature should be backward compatible (ignore checkboxes if disabled).
- Checkbox detection should be robust (handle nested lists, different markdown flavors).
- State management must be thread-safe if parallel execution.