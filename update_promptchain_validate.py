#!/usr/bin/env python3
"""Update promptchain-validate skill with Next Level features section."""

import sys

# Read the entire file
with open('skills/skillweave-promptchain-validate/SKILL.md', 'r') as f:
    lines = f.readlines()

# Find line index of "## Recommended companion files"
target_line = -1
for i, line in enumerate(lines):
    if line.strip() == '## Recommended companion files':
        target_line = i
        break

if target_line == -1:
    print('Could not find ## Recommended companion files heading')
    sys.exit(1)

# Insert new section before this heading
new_section = '''## Next Level Features

SkillWeave Next Level provides advanced capabilities that can enhance prompt chain validation. These features are controlled by `.skillweave/config.yaml` and can be accessed via the `SkillWeaveNextLevel` class.

### Risk Mode Integration
Check `.skillweave/config.yaml` for `mode` setting (`conservative`, `medium`, `unicorn`). Adjust validation behavior accordingly:
- **Conservative**: Extra validation, explicit approvals, strict safety checks, detailed validation reports
- **Medium**: Balanced approach with standard validation
- **Unicorn**: Optimistic assumptions, minimal confirmations, maximum speed, concise validation feedback

### Checklist-Based Execution
If `checklist: true` is set in the config, the skill will:
- Parse markdown checklists (`- [ ]` and `- [x]`) from sequence inputs
- Track checklist item completion across validation steps using `.skillweave/tracking-log/`
- Loop until all checklist items are marked complete
- Provide progress reports and remaining items

### Design-Thinking Lens  
If `design_thinking: true` is set in the config, apply these cognitive ergonomics principles to validation outputs:
1. **Value ≥ Noise**: Ensure every validation finding provides clear user value
2. **Scan Before Read**: Structure validation reports for quick scanning with clear headings
3. **Hierarchy of Needs**: Address functional needs before advanced features
4. **Progressive Disclosure**: Reveal complexity gradually as needed
5. **Recognition Over Recall**: Use consistent patterns and familiar formats
6. **Error Tolerance**: Design for mistakes with clear recovery paths

### Community Know-How
If `community_knowhow: true` is set, the skill will:
- Extract patterns from `.skillweave/tracking-log/` across projects
- Provide repository cleanup recommendations based on common issues
- Suggest optimizations and best practices from community patterns

### Modular Templates
If `modular_templates: true` is set, the skill can:
- Load and combine templates from `.skillweave/templates/` for validation reports
- Use template inheritance for consistent validation structures
- Generate custom validation sections from reusable components

### Using Next Level Features
```python
from skillweave.next_level import SkillWeaveNextLevel

# Initialize with project root
next_level = SkillWeaveNextLevel("/path/to/project")

# Check feature availability
if next_level.is_checklist_enabled():
    checklist = next_level.parse_checklist(markdown_content)
    # Track progress, loop until completion

if next_level.is_design_thinking_enabled():
    lens = next_level.get_design_thinking_lens()
    lens.apply_to_output(your_content)

# Access other features similarly
```

Adjust your validation based on enabled features to provide enhanced results while maintaining backward compatibility.

'''

# Insert new section before target_line
new_lines = lines[:target_line] + [new_section + '\n'] + lines[target_line:]

# Write back
with open('skills/skillweave-promptchain-validate/SKILL.md', 'w') as f:
    f.writelines(new_lines)

print('Updated promptchain-validate skill with Next Level features section.')