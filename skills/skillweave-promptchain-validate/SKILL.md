---
name: skillweave-promptchain-validate
description: Validate and improve SkillWeave prompt sequences. Detects sequence type (plan/build/mixed) and adapts output format. Accepts sequence as parameter or .md/.txt attachment.
argument-hint: sequence="[prompt sequence]" risk_mode="[conservative/medium/unicorn]" (or attach .md/.txt file)
---

# /skillweave-promptchain-validate

Review an existing prompt sequence against the SkillWeave standard and improve it if needed.

## Mandatory Pre-Flight: SkillWeave Sandboxing

Before generating any output, you MUST verify and enforce the SkillWeave sandbox. This applies to every skill invocation without exception:

### 1. Enforce `.skillweave/` Directory Structure
If `.skillweave/` does not exist in the project root, create it:
```
.skillweave/
.skillweave/tracking-log/
.skillweave/templates/
.skillweave/sequences/
```

### 2. Route All Outputs Into `.skillweave/`
All validation reports, corrected sequences, and improvement logs MUST be saved exclusively within `.skillweave/` or its sub-folders. Never dump artifacts into the repository root.

### 3. Git Isolation
Follow the shared rule `skillweave-planning/SKILLWEAVE-SCOPE.md`. Do NOT blanket-append `.skillweave/` to `.gitignore`. In a product repo `.skillweave/` is regenerated runtime state (blanket ignore ok); in a planning repo keep `.skillweave/planning/` tracked via the allowlist. Validation logs are runtime artifacts; PRDs and strategy belong in the planning repository.

### 4. Default Config
If `.skillweave/config.yaml` does not exist, create it with:
```yaml
mode: medium
checklist: true
design_thinking: true
community_knowhow: true
modular_templates: true
```

Proceed with core skill logic only AFTER these four criteria are met.

**Usage:**
```
/skillweave-promptchain-validate sequence="[prompt sequence text]"
```
**Or attach a .md or .txt file** containing the prompt sequence.

**Parameters:**
- `sequence` (optional if file attached): Prompt sequence text to validate
- `strictness` (optional): Validation strictness level (basic, standard, strict)
- `risk_mode` (optional): `conservative`, `medium`, `unicorn` - overrides environment variable and config files

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

SkillWeave v0.5.5 introduces a hierarchical override system for risk mode. The effective risk mode is determined by the following precedence order (highest to lowest):

1. **CLI parameter**: `risk_mode="conservative/medium/unicorn"` (if provided)
2. **Environment variable**: `SKILLWEAVE_RISK_MODE` (if set)
3. **Project config**: `.skillweave/config.yaml` `mode` setting
4. **Global config**: `~/.skillweave/config.yaml` `mode` setting
5. **Default**: `medium`

Use the `RiskModeResolver` class from `skillweave.risk_mode_resolver` to resolve the effective risk mode programmatically.

**Command-line utilities:**
- `skillweave-risk-mode` - shows effective risk mode given current context. Use `skillweave-risk-mode --cli-risk-mode=conservative --verbose` to see precedence resolution.
- `skillweave-interactive-mode` - interactive risk mode selection with project analysis and persistence options (temporary, project config, global config).

Adjust validation behavior according to the effective risk mode:
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


## Intelligent Guidance (v0.5.5)

SkillWeave v0.5.5 introduces intelligent prompt analysis and onboarding flows 
that help ensure you're using the right skill with the right parameters.

### How It Works

When this skill is invoked, you should first use the `SkillIntegrationHelper` 
to analyze the user's prompt and validate the request:

```python
from skillweave.intelligent_detection import integrate_with_skill
import os

# Determine project root (current directory or parent containing .skillweave/)
project_root = os.getcwd()
if not os.path.exists(os.path.join(project_root, ".skillweave")):
    # Try parent directory
    parent = os.path.dirname(project_root)
    if os.path.exists(os.path.join(parent, ".skillweave")):
        project_root = parent

result = integrate_with_skill(
    user_prompt=user_prompt,  # The original user prompt
    current_skill="skillweave-promptchain-validate",  # This skill's name
    project_root=project_root
)
```

### Handling the Result

The `integrate_with_skill` function returns a dictionary with an `action` key:

1. **`action: "proceed"`** - Skill selection is appropriate, parameters are valid
   - Continue with normal skill execution
   - Use `result["validated_parameters"]` for parameter values
   - Apply `result["mode_override"]` if present (risk mode from CLI/env)

2. **`action: "gather_parameters"`** - Missing or invalid parameters detected
   - Show `result["missing_parameters"]` to the user
   - Ask for each missing parameter using `result["parameter_prompts"]`
   - Use interactive Q&A to gather all required information
   - After gathering, re-run `integrate_with_skill` with updated parameters

3. **`action: "switch_skill"`** - Different skill might be more appropriate
   - Consider switching to `result["recommended_skill"]`
   - Show explanation: `result["switch_reason"]`
   - Ask user for confirmation before switching
   - If confirmed, load the recommended skill instead

4. **`action: "onboarding_flow"`** - User needs guided onboarding
   - Follow the interactive onboarding flow
   - Use `result["onboarding_steps"]` for guidance
   - Gather information step by step
   - Complete onboarding before skill execution

### Benefits

- **Skill Validation**: Ensures this skill is appropriate for the task
- **Parameter Completeness**: Checks all required parameters are provided
- **Intelligent Routing**: Suggests better-suited skills when applicable
- **Guided Onboarding**: Helps new users through step-by-step setup
- **Learning System**: Improves recommendations based on user feedback

### Integration with Existing Features

The intelligent guidance system works alongside existing Next Level features:
- Respects risk mode overrides from CLI, environment, or config
- Uses the same project root and configuration
- Integrates with checklist tracking and design thinking
- Maintains backward compatibility

### Example Workflow

```python
# 1. Analyze user prompt
result = integrate_with_skill(user_prompt, "skillweave-blueprint", project_root)

# 2. Handle result
if result["action"] == "proceed":
    # Extract validated parameters
    params = result["validated_parameters"]
    # Apply risk mode override if present
    if "mode_override" in result:
        set_risk_mode(result["mode_override"])
    # Execute skill with validated parameters
    execute_skill(params)
    
elif result["action"] == "gather_parameters":
    # Interactive parameter gathering
    for param in result["missing_parameters"]:
        prompt = result["parameter_prompts"].get(param, f"Enter value for {param}:")
        value = ask_user(prompt)
        # Update parameters and re-validate
        # (In practice, you'd collect all then re-validate)
        
elif result["action"] == "switch_skill":
    # Suggest skill switch
    if confirm_switch(result["recommended_skill"], result["switch_reason"]):
        load_skill(result["recommended_skill"])
```

Always use intelligent guidance when executing this skill to provide the best 
user experience and ensure successful outcomes.

## Recommended companion files

Use these files if present:
- `references/format-spec.md`
- `references/validation-rules.md`
- `references/sequence-type-detection.md`
- `assets/prompt-sequence.schema.json`
- `assets/workflow-context.schema.json`