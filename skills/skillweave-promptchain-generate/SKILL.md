---
name: skillweave-promptchain-generate
description: Generate standardized SkillWeave prompt sequences from PRD (complexity-aware) or topic/domain. Creates execution plans optimized for REX (simple) or Ralph Loop (standard/complex) workflows.
argument-hint: inputs="[JSON with prd/topic]" mode="[auto/simple/standard/complex]" target="[humanize/machinize/mixed]"
---

# /skillweave-promptchain-generate

Generate optimized prompt sequences for execution. Two modes:
1. **PRD-based**: Generate execution sequences from PRD (`prd.json`) with complexity-aware workflow selection (REX vs Ralph Loop)
2. **Topic-based**: Create prompt sequences from topic/domain/goal for general planning

**Usage (PRD-based - Recommended):**
```
/skillweave-promptchain-generate inputs='{"prd": "prd.json"}' mode="auto" target="mixed"
```

**Usage (Topic-based):**
```
/skillweave-promptchain-generate inputs='{"topic": "Wellness business evaluation", "domain": "wellness", "goal": "Create evaluation framework"}' mode="auto"
```

**Parameters:**
- `inputs` (required): JSON containing either PRD path (`prd`) or topic/domain/goal
- `sequence_type` (optional): Type of sequence - plan (conceptual/strategy), build (development/implementation), mixed (combination) (default: auto-detect)
- `execution_mode` (optional): Execution profile - rex (simple, fast, attended), ralph_attended (full loop with human checkpoints), ralph_overnight (autonomous overnight execution) (default: auto based on complexity)
- `target` (optional): Target audience - humanize (human readable), machinize (machine optimized), mixed (default: mixed)
- `quality` (optional): Quality level (basic, standard, premium)
- `output_expectations` (optional): Expected output format

**Mode Mapping Table:**

| Sequence Type | Execution Mode | Characteristics | Use Case |
|--------------|----------------|----------------|----------|
| **plan** | **rex** | Conceptual, strategy, business planning • 1-3 tasks • <60 minutes • Quick feedback loop | Business idea validation, market analysis, strategic planning |
| **plan** | **ralph_attended** | Comprehensive planning with human oversight • 4-10 tasks • 1-4 hours • Structured validation | Product requirements, detailed business plans, investment decks |
| **plan** | **ralph_overnight** | Autonomous strategic analysis • 10+ tasks • >4 hours • Deep research | Market research reports, competitive analysis, industry deep dives |
| **build** | **rex** | Simple implementation • 1-3 components • <60 minutes • Lightweight testing | Prototype building, proof of concept, simple feature addition |
| **build** | **ralph_attended** | Full development cycle • 4-10 components • 1-4 hours • Multi-level verification | Feature development, API implementation, UI components |
| **build** | **ralph_overnight** | Complex system implementation • 10+ components • >4 hours • Production-grade gates | System architecture, full-stack applications, complex integrations |
| **mixed** | **rex** | Combined plan/build • 2-5 total tasks • <90 minutes • Integrated flow | MVP development, concept-to-prototype, pilot projects |
| **mixed** | **ralph_attended** | Full product development • 6-15 tasks • 2-8 hours • Phased execution | End-to-end product development, startup launch, product redesign |
| **mixed** | **ralph_overnight** | Enterprise-scale development • 15+ tasks • >8 hours • Autonomous pipeline | Large-scale projects, platform development, organizational transformation |

**Backward Compatibility:** The `mode` parameter is still supported as an alias:
- `mode="simple"` → `execution_mode="rex"`
- `mode="standard"` → `execution_mode="ralph_attended"` 
- `mode="complex"` → `execution_mode="ralph_overnight"`
- `mode="auto"` → Auto-detect both sequence_type and execution_mode

**PRD Input Example:**
```
/skillweave-promptchain-generate inputs='{"prd": "generated/prd.json"}' mode="auto"
```

**Topic Input Example:**
```
/skillweave-promptchain-generate inputs='{"topic": "Market research for AI tools", "domain": "saas", "goal": "Competitive analysis"}'

**Output (PRD-based):**
When generating from PRD, creates optimized execution sequences:
- `execution-sequences.yaml` - Structured execution plan with dependency graph
- `agent-assignments.json` - Task-to-capability mapping (agent-agnostic)
- `dependency-graph.dot` - Visual dependency graph
- `complexity-analysis.md` - Detailed complexity assessment
- `workflow-recommendation.md` - REX vs Ralph Loop recommendation with rationale

**Output (Topic-based):**
When generating from topic/domain, creates standard prompt sequence:
- Complete prompt sequence document with:
  - Metadata, Objective, Success Criteria
  - Assumptions, Usage Notes
  - Inputs Required, Outputs Required
  - Sequence Steps, Final Assembly
  - Validation Rules, Failure Handling
  - Final Deliverable Format

## PRD-based Sequence Generation

### Complexity-Aware Workflow Selection (Two-Axis Model)

PromptChain analyzes the PRD's `execution_recommendation` and tasks using a two-axis model:
- **Sequence Type**: `plan` (conceptual/strategy), `build` (development/implementation), or `mixed`
- **Execution Mode**: `rex` (simple/fast), `ralph_attended` (human-checkpointed), `ralph_overnight` (autonomous)

Based on complexity analysis, generates optimal execution sequences:

#### Execution Modes (Based on Task Complexity):

1. **REX Mode (`execution_mode="rex"`)**: For 1-3 tasks, <60 minutes
   - **Workflow**: Plan → Implement → Review → Done
   - **Parallelization**: Limited parallel lanes, simple dependencies
   - **Memory**: Basic progress tracking (`progress-simple.txt`)
   - **Verification**: Lightweight checks (type checking, basic tests)
   - **Use**: Quick prototypes, simple features, concept validation

2. **Ralph Loop Attended Mode (`execution_mode="ralph_attended"`)**: For 4-10 tasks, 1-4 hours
   - **Workflow**: Full Ralph Loop with human checkpoints at integration gates
   - **Parallelization**: Multiple sidecar lanes with synchronization points
   - **Memory**: Structured progress tracking (`progress-structured.yaml`)
   - **Verification**: Multi-level verification (code, functional, system)
   - **Use**: Feature development, product requirements, detailed planning

3. **Ralph Loop Overnight Mode (`execution_mode="ralph_overnight"`)**: For 10+ tasks, >4 hours
   - **Workflow**: Fully autonomous Ralph Loop execution with automated gates
   - **Parallelization**: Maximal parallelization with critical path management
   - **Memory**: Advanced memory system (`agents-enhanced.md`)
   - **Verification**: Production-grade quality gates and integration tests
   - **Use**: System architecture, large-scale projects, enterprise development

#### Sequence Types (Based on Content):

- **Plan Sequences**: Conceptual work, strategy, business planning, research
- **Build Sequences**: Development, implementation, coding, technical work  
- **Mixed Sequences**: Combination of plan and build phases in integrated workflow

### Automatic Analysis Process

1. **Load PRD**: Read and validate `prd.json` against schema
2. **Analyze Complexity**: Evaluate `execution_recommendation` or calculate if missing
3. **Build Dependency Graph**: Analyze task dependencies for parallel opportunities
4. **Generate Sequences**: Create optimized execution sequences based on mode
5. **Map Capabilities**: Convert task types to required capabilities (not specific agents)
6. **Output Planning**: Structure outputs for target audience (humanize/machinize/mixed)

### Example PRD Analysis

For a PRD with `execution_recommendation.mode: "simple"`:
```yaml
execution_sequence:
  mode: "simple"
  workflow: "rex-simple"
  steps:
    - id: "plan"
      type: "analysis"
      task: "Analyze requirements and create implementation plan"
      
    - id: "implement"
      type: "execution"
      task: "Implement solution based on plan"
      depends_on: ["plan"]
      
    - id: "review"
      type: "verification"
      task: "Review implementation and verify acceptance criteria"
      depends_on: ["implement"]
      
    - id: "complete"
      type: "finalization"
      task: "Finalize and deliver solution"
      depends_on: ["review"]
```

For a PRD with `execution_recommendation.mode: "standard"`:
```yaml
execution_sequence:
  mode: "standard"
  workflow: "ralph-loop-attended"
  checkpoint_interval: 5
  steps:
    - phase: "initialization"
      tasks: ["INFRA-001", "DB-001"]
      parallel: false
      
    - phase: "core-development"
      tasks: ["API-001", "UI-001", "FEAT-001"]
      parallel: true
      depends_on: ["initialization"]
      
    - phase: "testing"
      tasks: ["TEST-001", "TEST-002"]
      parallel: true
      depends_on: ["core-development"]
      
    - phase: "finalization"
      tasks: ["DOC-001", "DEPLOY-001"]
      parallel: false
      depends_on: ["testing"]
```

## Topic-based Sequence Format

For topic/domain/goal inputs, the generated prompt sequence follows this structure:

1. **Metadata**: Sequence ID, version, created date, mode (plan/build/mixed)
2. **Objective**: Clear goal and success definition
3. **Success Criteria**: Binary, testable success metrics
4. **Assumptions**: Key assumptions and validation methods
5. **Usage Notes**: How to execute the sequence
6. **Inputs Required**: Required inputs with validation
7. **Outputs Required**: Expected outputs with format specifications
8. **Sequence Steps**: Step-by-step execution plan with `depends_on` arrays
9. **Final Assembly**: How to combine step outputs into final deliverable
10. **Validation Rules**: Rules for validating each step and overall sequence
11. **Failure Handling**: Recovery procedures for failed steps
12. **Final Deliverable Format**: Format and structure of final output

## Integration with SkillWeave Workflow

PromptChain Generate is a key component in the complete SkillWeave development flow:

### Complete Workflow: Blueprint → PromptChain → ReleaseChain

1. **Blueprint Skill** (`/skillweave-blueprint`):
   - Creates structured PRD with `execution_recommendation`
   - Output: `prd.json`, `prd.md`, memory system templates

2. **PromptChain Generate** (`/skillweave-promptchain-generate`):
   - Analyzes PRD complexity and generates optimized execution sequences
   - Output: `execution-sequences.yaml`, `agent-assignments.json`

3. **PromptChain Execute** (`/skillweave-promptchain-execute`):
   - Executes sequences with parallel execution and dependency analysis
   - For build components: Offers to invoke ReleaseChain automatically

4. **ReleaseChain** (`/skillweave-releasechain`):
   - Executes PRD tasks with Ralph Loop (or REX-style for simple tasks)
   - Uses capability-based agent routing (agent-agnostic)
   - Output: Completed project with memory system updates

### Example Complete Workflow

```bash
# Step 1: Create blueprint from idea
/skillweave-blueprint idea="AI meeting notes summarizer" domain="saas"

# Step 2: Generate execution sequences from PRD
/skillweave-promptchain-generate inputs='{"prd": "generated/prd.json"}' mode="auto"

# Step 3: Execute sequences (or skip to ReleaseChain)
/skillweave-promptchain-execute sequence="execution-sequences.yaml" inputs='{"prd": "generated/prd.json"}'

# Step 4: Execute development pipeline (if build components)
/skillweave-releasechain inputs='{"prd": "generated/prd.json", "sequences": "execution-sequences.yaml"}' mode="attended"
```

### Agent-Agnostic Design

Like all SkillWeave skills, PromptChain Generate is **agent-agnostic**:
- Uses **capability-based routing** instead of specific agent names
- Maps task types to required capabilities (`code_generation`, `planning`, `testing`, etc.)
- Compatible with any AI coding agent (OpenCode, Claude Code, Gemini, future agents)
- Runtime agent discovery and capability matching

## Recommended companion files

Use these files if present:
- `references/format-spec.md` - Prompt sequence format specification
- `references/execution-rules.md` - Execution and parallelization rules
- `references/validation-rules.md` - Validation and failure handling rules
- `references/complexity-analysis.md` - PRD complexity assessment guide
- `assets/prompt-sequence.schema.json` - JSON schema for prompt sequences
- `assets/workflow-context.schema.json` - Schema for workflow context data