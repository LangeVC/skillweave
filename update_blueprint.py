#!/usr/bin/env python3
"""Update blueprint skill with Next Level features section."""

import sys

# Read the entire file
with open('skills/skillweave-blueprint/SKILL.md', 'r') as f:
    lines = f.readlines()

# Lines are 0-indexed, we want to replace lines 56-58 (inclusive) which correspond to lines 57-59 in 1-indexed
# lines[56] = line 57, lines[57] = line 58 (blank), lines[58] = line 59 (heading)
# We'll replace lines[56:59] with our new content

new_section = '''Adjust your interview questions, validation rigor, documentation depth, and technology suggestions accordingly.

## Next Level Features

SkillWeave Next Level provides advanced capabilities that can enhance the blueprint process. These features are controlled by `.skillweave/config.yaml` and can be accessed via the `SkillWeaveNextLevel` class.

### Checklist-Based Execution
If `checklist: true` is set in the config, the skill will:
- Parse markdown checklists (`- [ ]` and `- [x]`) from input or attached files
- Track checklist item completion across sessions using `.skillweave/tracking-log/`
- Loop until all checklist items are marked complete
- Provide progress reports and remaining items

### Design-Thinking Lens  
If `design_thinking: true` is set in the config, apply these cognitive ergonomics principles:
1. **Value ≥ Noise**: Ensure every output provides clear user value
2. **Scan Before Read**: Structure content for quick scanning with clear headings
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
- Load and combine templates from `.skillweave/templates/`
- Use template inheritance for consistent documentation
- Generate custom PRD sections from reusable components

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

Adjust your execution based on enabled features to provide enhanced results while maintaining backward compatibility.

## Interactive PRD Creation Process'''

# Replace lines 56:59 (exclusive of 59) with new_section split into lines
new_lines = lines[:56] + [new_section + '\n'] + lines[59:]

# Write back
with open('skills/skillweave-blueprint/SKILL.md', 'w') as f:
    f.writelines(new_lines)

print('Updated blueprint skill with Next Level features section.')