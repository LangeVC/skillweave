---
name: skillweave-promptchain-validate
description: Validate and improve SkillWeave prompt sequences. Detects sequence type (plan/build/mixed) and adapts output format. Accepts sequence as parameter or .md/.txt attachment.
argument-hint: sequence="[prompt sequence]" (or attach .md/.txt file)
---

# /skillweave-promptchain-validate

Review an existing prompt sequence against the SkillWeave standard and improve it if needed.

**Usage:**
```
/skillweave-promptchain-validate sequence="[prompt sequence text]"
```
**Or attach a .md or .txt file** containing the prompt sequence.

**Parameters:**
- `sequence` (optional if file attached): Prompt sequence text to validate
- `strictness` (optional): Validation strictness level (basic, standard, strict)

**Attachment detection:** If no `sequence` parameter is provided, check for attached .md/.txt files. If multiple options exist, ask for clarification.

**Examples:**

**With inline sequence:**
```
/skillweave-promptchain-validate sequence="[paste sequence here]"
```

**With attached file:**
Attach `sequence.md` or `sequence.txt` and use:
```
/skillweave-promptchain-validate
```

**Example Validation Interaction:**

1. **Skill analyzes sequence** and detects type (e.g., "plan mode - business concept development")
2. **Skill presents validation findings** with specific improvements needed
3. **Skill asks:** "What should be saved as .md?
   - Validation Report (complete)
   - Improved sequence only  
   - Both in separate files
   - Custom answer"
4. **Skill asks about output structure:** "Based on the plan mode detection, should outputs be structured as:
   - Single consolidated business plan document
   - Multiple separate documents (executive summary, business plan, appendices)
   - Custom structure"
5. **Skill provides complete improved sequence** with all placeholder content replaced
6. **Skill offers to split consolidated outputs** into appropriate separate documents if requested

**Output Options (ask user before finalizing):**

What should be saved as .md?
1. **Validation Report (complete)** - Full validation report including improved version
2. **Improved sequence only** - Only the improved sequence block
3. **Both in separate files** - Report and improved sequence as two separate .md files
4. **Custom answer** - User specifies custom format

**Validation Process:**

1. **Sequence Type Detection:**
   - Analyze if sequence is **plan mode** (conceptual, business planning, strategy)
   - Analyze if sequence is **build mode** (development, coding, implementation)  
   - Analyze if sequence is **mixed** (combination of plan and build)
   - Use detailed heuristics from `references/sequence-type-detection.md` for accurate detection
   - Adapt output structure based on detected type

2. **Complete Improved Sequence:**
   - Provide FULL improved sequence, NOT just references to original
   - Replace placeholder comments like `[Unverändert aus Original – hier einfügen]` with actual content
   - Ensure improved sequence is fully self-contained and executable

3. **Output Format Adaptation:**
   - For **plan mode**: Structure outputs as business plan sections, executive summaries, strategic documents
   - For **build mode**: Structure outputs as technical specifications, code modules, implementation guides
   - For **mixed**: Separate plan and build components with clear delineation
   - Ask user about preferred document splitting (single consolidated vs. multiple separate files)

4. **Validation Focus:**
   - Structural completeness
   - Logical step order  
   - Consistency of inputs and outputs
   - Usefulness of usage notes
   - Usefulness of validation rules
   - Usefulness of failure handling
   - Output format appropriateness for sequence type
   - **Parallelization readiness**: Check if sequence cleanly separates critical path (single-owner surfaces) from parallelizable sidecar lanes
   - **Single-owner surfaces**: Identify steps that modify critical surfaces (database schemas, core APIs, config files) requiring exclusive ownership
   - **Dependency clarity**: Verify blocking vs non-blocking dependencies are explicitly defined
   - **Integration gates**: Ensure appropriate synchronization points for parallel lanes

**Rules:**
- Do not only critique; provide complete improved sequence
- Preserve original intent when possible
- Call out weak assumptions explicitly
- Identify when steps are too broad, too vague, or out of order
- Ensure improved sequence is production-ready and fully self-contained

## Standard format

The expected prompt-sequence structure is:

1. Metadata
2. Objective
3. Success Criteria
4. Assumptions
5. Usage Notes
6. Inputs Required
7. Outputs Required
8. Sequence Steps
9. Final Assembly
10. Validation Rules
11. Failure Handling
12. Final Deliverable Format

## Next Level Features

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


## Recommended companion files

Use these files if present:
- `references/format-spec.md`
- `references/validation-rules.md`
- `references/sequence-type-detection.md`
- `assets/prompt-sequence.schema.json`
- `assets/workflow-context.schema.json`