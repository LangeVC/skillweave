#!/usr/bin/env python3
"""Update releasechain skill with Next Level features section."""

import sys

# Read the entire file
with open('skills/skillweave-releasechain/SKILL.md', 'r') as f:
    lines = f.readlines()

# Find line index of "**Ralph Loop Pipeline Architecture:**"
target_line = -1
for i, line in enumerate(lines):
    if line.strip() == '**Ralph Loop Pipeline Architecture:**':
        target_line = i
        break

if target_line == -1:
    print('Could not find Ralph Loop Pipeline Architecture heading')
    sys.exit(1)

# Insert new section after this line (target_line + 1)
insert_line = target_line + 1

new_section = '''## Next Level Features

SkillWeave Next Level provides advanced capabilities that can enhance the release chain pipeline. These features are controlled by `.skillweave/config.yaml` and can be accessed via the `SkillWeaveNextLevel` class.

### Risk Mode Integration
Check `.skillweave/config.yaml` for `mode` setting (`conservative`, `medium`, `unicorn`). Adjust pipeline behavior accordingly:
- **Conservative**: Extra validation, explicit approvals, strict safety checks, detailed memory logs
- **Medium**: Balanced approach with standard validation
- **Unicorn**: Optimistic assumptions, minimal confirmations, maximum speed, concise outputs

### Checklist-Based Execution
If `checklist: true` is set in the config, the skill will:
- Parse markdown checklists (`- [ ]` and `- [x]`) from PRD inputs
- Track checklist item completion across pipeline iterations using `.skillweave/tracking-log/`
- Loop until all checklist items are marked complete
- Provide progress reports and remaining items

### Design-Thinking Lens  
If `design_thinking: true` is set in the config, apply these cognitive ergonomics principles to pipeline outputs:
1. **Value ≥ Noise**: Ensure every pipeline output provides clear user value
2. **Scan Before Read**: Structure progress reports for quick scanning with clear headings
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
- Load and combine templates from `.skillweave/templates/` for pipeline stages
- Use template inheritance for consistent pipeline structures
- Generate custom pipeline sections from reusable components

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

Adjust your pipeline execution based on enabled features to provide enhanced results while maintaining backward compatibility.

'''

# Insert new section after target_line
new_lines = lines[:insert_line] + [new_section + '\n'] + lines[insert_line:]

# Write back
with open('skills/skillweave-releasechain/SKILL.md', 'w') as f:
    f.writelines(new_lines)

print('Updated releasechain skill with Next Level features section.')