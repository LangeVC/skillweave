---
name: skillweave-promptchain-execute
description: Execute SkillWeave prompt sequences with dependency-aware batching, Ralph Loop execution, binary gates, and safe parallel subagent orchestration. Use when a validated prompt sequence or PRD-derived task set should be carried through real execution, especially for multi-step build, review, verification, release, or mixed plan/build work.
argument-hint: sequence="[prompt sequence]" inputs="[JSON]" execution_mode="[auto/rex/ralph_attended/ralph_overnight]" audience_mode="[auto/humanize/machinize/mixed]" (or attach .md/.txt file)
---

# /skillweave-promptchain-execute

**Execute structured prompt sequences with real delivery discipline.**

This skill is the execution engine for SkillWeave prompt sequences. It does not just "run steps"; it resolves execution mode, plans batches, identifies safe parallel lanes, applies Ralph Loop when the work is substantial, and advances only through binary gates.

## Usage

```text
/skillweave-promptchain-execute sequence="[prompt sequence text]" inputs="[JSON inputs]"
```

Or attach a `.md` / `.txt` sequence file and provide:

```text
/skillweave-promptchain-execute inputs='{"key":"value"}'
```

## Parameters

- `sequence` (optional if file attached): Prompt sequence text
- `inputs` (required): JSON object with required runtime inputs
- `execution_mode` (optional): `auto`, `rex`, `ralph_attended`, `ralph_overnight`
- `audience_mode` (optional): `auto`, `humanize`, `machinize`, `mixed`

Default:

- `execution_mode = auto`
- `audience_mode = auto`

## Core Distinctions

### 1. Sequence Type

Sequence type describes the nature of the work:

- `plan`: strategy, analysis, PRD, architecture, research-led planning
- `build`: code, config, tests, infra, docs tied to implementation
- `mixed`: both plan and build steps are materially present

### 2. Execution Mode

Execution mode describes how the work should be carried out:

- `rex`: fast path for small, low-risk, mostly linear work
- `ralph_attended`: default for substantial repo work with active checkpoints
- `ralph_overnight`: autonomous multi-batch execution for large, well-structured sequences

`mixed` is **not** an execution mode. It is only a sequence-type classification.

## Mode Resolution

If `execution_mode=auto`, choose as follows:

### Use `rex` when:

- there are 1-3 steps
- total work is small
- dependencies are mostly linear
- there is no meaningful public/private or release boundary risk
- verification is lightweight

### Use `ralph_attended` when:

- there are 4+ steps
- the work mutates a repository
- code, tests, docs, or release flow are all involved
- binary gates are required
- public/private or product-tier boundaries are involved
- multiple safe parallel lanes exist

### Use `ralph_overnight` when:

- the sequence is already decomposed into explicit batches
- batch gates are well-defined
- retries and carry-forward logic are already specified
- long autonomous execution is acceptable

Rule of thumb:

- default to `ralph_attended` for real product development unless the task is obviously tiny

## Next Level Features

SkillWeave Next Level provides advanced capabilities that can enhance prompt chain execution. These features are controlled by `.skillweave/config.yaml` and can be accessed via the `SkillWeaveNextLevel` class.

### Risk Mode Integration
Check `.skillweave/config.yaml` for `mode` setting (`conservative`, `medium`, `unicorn`). Adjust execution behavior accordingly:
- **Conservative**: Extra validation, explicit approvals, strict safety checks
- **Medium**: Balanced approach with standard validation
- **Unicorn**: Optimistic assumptions, minimal confirmations, maximum speed

### Checklist-Based Execution
If `checklist: true` is set in the config, the skill will:
- Parse markdown checklists (`- [ ]` and `- [x]`) from sequence inputs
- Track checklist item completion across batches using `.skillweave/tracking-log/`
- Loop until all checklist items are marked complete
- Provide progress reports and remaining items

### Design-Thinking Lens  
If `design_thinking: true` is set in the config, apply these cognitive ergonomics principles to outputs:
1. **Value ≥ Noise**: Ensure every execution output provides clear user value
2. **Scan Before Read**: Structure batch reports for quick scanning with clear headings
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
- Load and combine templates from `.skillweave/templates/` for batch planning
- Use template inheritance for consistent execution reports
- Generate custom sequence sections from reusable components

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


## Execution Process

### Phase 1: Preflight

1. Detect sequence type: `plan`, `build`, or `mixed`
2. Validate required inputs
3. Parse dependencies
4. Identify:
   - critical path
   - safe parallel lanes
   - review gates
   - release or deployment risk
5. Resolve execution mode
6. Determine whether the sequence should run:
   - as one batch
   - as multiple batches
   - with sidecar subagents

If the sequence is malformed, underspecified, or contradicts the real repository baseline, stop and produce a baseline-alignment report before executing.

### Phase 2: Batch Planning

Before implementation, convert the sequence into executable batches.

For each batch, define:

- `batch_id`
- `goal`
- `included_steps`
- `critical_path_step`
- `parallel_lanes`
- `write_surfaces`
- `verification_commands`
- `review_gate`
- `completion_contract`
- `next_batch_if_pass`
- `fallback_if_fail`

Do not execute a multi-step build sequence without first producing an explicit batch plan.

### Phase 3: Ralph Loop State Machine

When execution mode is `ralph_attended` or `ralph_overnight`, use this loop:

1. `Preflight`
2. `Batch Selection`
3. `Lane Plan`
4. `Implement`
5. `Verify`
6. `Review Gate`
7. `Fix / Retry`
8. `Integrate`
9. `Advance or Stop`

Only advance when the current batch passes its binary gate.

## Parallelization Rules

Parallelism is allowed only when it is safe.

### Safe parallel lanes

Parallelize steps when they have:

- disjoint write scopes
- no unresolved dependency between them
- no shared ownership of fragile contract surfaces

Good sidecar lanes:

- read-only research
- documentation drafting
- isolated tests
- release notes
- audit and verification passes

### Keep local on the critical path

Keep the following local unless the sequence explicitly isolates them:

- product-tier registries
- tool index / tool registration
- shared contracts used across many modules
- release and export manifests
- other single-owner integration surfaces

### Subagent policy

Use subagents only for:

- independent sidecar lanes
- isolated implementation with disjoint write scope
- verification or review that does not block immediate local context-building

Do not delegate the immediate blocking task if the next local action depends on it.

## Required Build-Step Fields

For build-oriented execution, each implementation step should define or be normalized into:

- `id`
- `title`
- `depends_on`
- `required_capabilities`
- `write_scope`
- `verification`
- `integration_gate`
- `retry_budget`
- `handoff_contract`

If these are missing, infer them conservatively. If they cannot be inferred safely, stop and emit a sequence-hardening recommendation.

## Gate Policy

All meaningful completion decisions must be binary.

Allowed completion signals:

- tests passed
- verifier passed
- build succeeded
- review explicitly returned `continue`
- required artifact exists and matches the contract

Not sufficient on their own:

- "looks good"
- "seems fine"
- "mostly done"
- "probably works"

If verification is inconclusive, mark the batch `inconclusive`, explain why, and do not silently advance.

## Audience Handling

After execution, outputs may be shaped for:

- `humanize`: explanation-first deliverables
- `machinize`: structured machine-readable outputs
- `mixed`: both

Do not ask about audience mode if the sequence or context already makes it obvious.

## Output Contract

### For each batch, return:

- `batch_id`
- `steps_completed`
- `files_changed`
- `commands_run`
- `verification_results`
- `review_result`
- `blockers`
- `known_limitations`
- `next_executable_batch`

### For plan-oriented outputs, return:

- decision summary
- assumptions
- unresolved questions
- artifacts produced
- recommended next execution package

### For build-oriented outputs, return:

- implementation summary
- exact verification steps
- pass/fail/inconclusive status
- next slice recommendation

## Failure Handling

If a batch fails:

1. identify whether the failure is:
   - implementation
   - verification
   - environment
   - sequence-definition
2. apply the retry budget if appropriate
3. prefer narrow fixes over broad redesign
4. if still blocked, stop and emit:
   - blocker summary
   - affected batch
   - safe rollback or pause point
   - next required user or system action

Do not continue into the next batch after a failed gate.

## Integration with ReleaseChain

Offer `/skillweave-releasechain` only when:

- build-oriented work completed successfully
- outputs are in a reviewable state
- the next logical step is review, test hardening, commit, release, or PR flow

Do not automatically transfer partial or inconclusive build batches into ReleaseChain.

## Agent-Agnostic Execution

This skill is agent-agnostic.

It should prefer:

- capability-based routing
- lane-based task assignment
- central ownership of critical-path integration
- fallback to available agents when the preferred capability runner is unavailable

When multiple agents exist, assign by:

- capability fit
- write-scope safety
- dependency position
- verification needs

Do not encode vendor-specific assumptions into the execution logic.

## Recommended Companion Files

Use these files if present:

- `references/execution-rules.md`
- `references/format-spec.md`
- `references/sequence-type-detection.md`
- `references/parallel-execution.md`
- `references/ralph-loop-state-machine.md`
- `references/build-step-normalization.md`
- `references/gate-policy.md`