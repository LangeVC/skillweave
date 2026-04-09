---
name: skillweave-promptchain-execute
description: Execute SkillWeave prompt sequences with parallel execution, dependency analysis, subagent triggering, plan/build detection, and adaptive outputs. Product development flow on steroids.
argument-hint: sequence="[prompt sequence]" inputs="[JSON]" (or attach .md/.txt file)
---

# /skillweave-promptchain-execute

**Product development flow on steroids.**  
Run prompt sequences with intelligent parallel execution, dependency analysis, and subagent triggering for maximum efficiency.

**Usage:**
```
/skillweave-promptchain-execute sequence="[prompt sequence text]" inputs="[JSON inputs]"
```
**Or attach a .md or .txt file** containing the prompt sequence.

**Parameters:**
- `sequence` (optional if file attached): Prompt sequence text to execute
- `inputs` (required): JSON string containing required inputs

**Attachment detection:** If no `sequence` parameter is provided, check for attached .md/.txt files. If multiple options exist, ask for clarification.

**Examples:**

**With inline sequence:**
```
/skillweave-promptchain-execute sequence="[sequence]" inputs='{"business_idea": "Yoga studio", "target_region": "Berlin"}'
```

**With attached file:**
Attach `sequence.md` or `sequence.txt` and use:
```
/skillweave-promptchain-execute inputs='{"business_idea": "Yoga studio"}'
```

**Example Execution Interaction:**

1. **Skill analyzes sequence**: "Detected mixed sequence: 5 plan steps (business concept), 3 build steps (website prototype)"
2. **Skill analyzes dependencies**: "Dependency graph: Steps 1-2 parallel, Step 3 depends on 1-2, Steps 4-5 parallel after 3"
3. **Skill triggers parallel execution**:
   - Subagent A: Steps 1-2 (market research + user analysis) - running in parallel
   - Subagent B: Step 3 (business model) - waiting for A
   - Subagent C: Steps 4-5 (UI prototype + API design) - parallel after B
4. **Skill executes with adaptive outputs**:
   - Plan steps → Business plan .md sections
   - Build steps → Code files + technical report .md
5. **Skill asks post-execution questions**:
   - "Target audience for plan outputs? [Humanize/Machinize/Mixed]"
   - "Target audience for build outputs? [Humanize/Machinize/Mixed]"
   - "Initiate development pipeline for build components? [Yes/No]"
6. **If development pipeline requested**:
   - "Initiating `/skillweave-releasechain` with: review, testing, commit, push, PR, release, changelog"
   - Transfers build outputs to releasechain skill for processing
7. **Final deliverables presented** organized by type, audience, and execution timeline

**Execution Process:**

1. **Sequence Analysis & Dependency Mapping:**
   - Detect sequence type: **plan mode** (conceptual, strategy, business planning), **build mode** (development, coding, implementation), or **mixed**
   - Use detailed heuristics from `references/sequence-type-detection.md` for accurate detection
   - Analyze `depends_on` arrays to build dependency graph
   - Identify parallel execution opportunities using `references/parallel-execution.md`
   - Analyze step purposes and expected outputs
   - Identify which steps produce human-readable vs. machine-readable outputs

2. **Parallel Execution Planning:**
   - Determine optimal execution strategy (sequential/parallel/mixed)
   - Identify steps that can run concurrently in subagents
   - Group similar steps for efficient resource usage
   - Plan subagent triggering for maximum parallelization

3. **Adaptive Execution with Parallelization:**
   - Execute independent steps in parallel using Task tool subagents
   - Monitor subagent progress and collect results
   - Trigger dependent steps when prerequisites complete
   - For **plan mode steps**: Create well-structured .md documents (business plans, strategies, reports)
   - For **build mode steps**: Generate code/files with accompanying technical documentation
   - For **mixed sequences**: Separate plan and build outputs with appropriate parallelization

4. **Post-Execution Options:**
   - Ask about **target audience** for outputs:
     - **Humanize**: Optimize for human readability (explanations, summaries, formatting)
     - **Machinize**: Optimize for machine processing (structured data, APIs, code)
     - **Mixed**: Separate human and machine outputs appropriately
   - For **build components**: Offer to initiate development pipeline via `/skillweave-releasechain` (review, testing, commit, push, PR, release, changelog)
   - For **plan components**: Offer document consolidation and formatting options

5. **Output Structure with Execution Timeline:**
   - Step-by-step execution with progress tracking
   - Parallel execution visualization showing concurrent steps
   - Validation status per step with improvement suggestions
   - Error or fallback handling with recovery options
   - Final assembled deliverables organized by purpose, audience, and execution timeline

**Agent-Agnostic Execution:**

PromptChain Execute is **agent-agnostic** – it works with any AI coding agent through the Task tool's subagent capability. Instead of hardcoding specific agents, it uses:

1. **Subagent Abstraction**: Uses Task tool's generic subagent capability (`subagent_type: "explore"` or `"general"`)
2. **Capability-Based Routing**: When specific agent capabilities are needed, delegates to ReleaseChain for capability-based routing
3. **Fallback to Available Agents**: Uses whatever agents are available in the current environment
4. **Parallel Execution Compatibility**: Parallel subagents work with any agent type that supports Task tool execution

**Integration with ReleaseChain**: When build components are detected and development pipeline is requested, the skill automatically invokes `/skillweave-releasechain` which handles agent routing based on capabilities.

**Execution Rules:**
- Analyze `depends_on` arrays to determine execution order
- Execute independent steps in parallel when possible
- Use Task tool subagents for parallel execution of independent steps
- Respect usage notes before marking a step complete
- If `web_research: required`, do not complete the step without research
- If `citations: required`, do not complete the step without citations
- If `intermediate_validation: required`, validate before moving on
- If the sequence is blocked, follow failure handling rules
- Do not freestyle beyond the defined scope of the sequence
- Adapt output format based on detected sequence type and step purpose
- For parallel execution failures, implement retry logic or fallback to sequential
- Monitor subagent resources and adjust parallelization dynamically

## Recommended companion files

Use these files if present:
- `references/execution-rules.md`
- `references/format-spec.md`
- `references/sequence-type-detection.md`
- `references/parallel-execution.md`
- `assets/workflow-context.schema.json`