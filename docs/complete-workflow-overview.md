# SkillWeave: Complete Workflow Overview

**Product development flow on steroids** - From vague idea to production-ready code through structured AI-assisted development.

## Core Philosophy

SkillWeave bridges the gap between human ideas and AI execution by providing a **structured, complexity-aware development pipeline**. It combines:

1. **REX-style simplicity** for quick tasks (1-3 tasks, <60 minutes)
2. **Ralph Loop power** for complex projects (4+ tasks, >1 hour)
3. **Agent-agnostic design** that works with any AI coding agent
4. **Memory systems** that accumulate knowledge across projects

## The Complete Workflow

```
Idea → Blueprint → PromptChain → ReleaseChain → Production
```

### Phase 1: Blueprint - Structured Planning
**Skill**: `/skillweave-blueprint`

Transforms vague ideas into structured Product Requirements Documents (PRD) through guided interview:

```
Input: "AI meeting notes summarizer for remote teams"
Output: Complete PRD with:
  - prd.md (human-readable requirements)
  - prd.json (structured task list)
  - execution_recommendation (REX vs Ralph Loop analysis)
  - Memory system templates (progress.txt, agents.md)
```

**Key Innovation**: Automatic complexity assessment that recommends REX (simple) vs Ralph Loop (standard/complex) execution.

### Phase 2: PromptChain - Intelligent Sequencing  
**Skills**: `/skillweave-promptchain-generate`, `/skillweave-promptchain-execute`

Generates and executes optimized prompt sequences based on PRD complexity:

```
PRD Analysis → Complexity Assessment → Sequence Generation → Execution
```

**Two Modes**:
1. **PRD-based**: Generates execution sequences from `prd.json` with dependency analysis
2. **Topic-based**: Creates general prompt sequences from topic/domain/goal

**Intelligent Features**:
- **Parallel execution detection**: Identifies tasks that can run concurrently
- **Dependency graph analysis**: Ensures proper execution order
- **Capability-based routing**: Agent-agnostic task assignment
- **Adaptive outputs**: Humanize/machinize/mixed formatting

### Phase 3: ReleaseChain - Autonomous Execution
**Skill**: `/skillweave-releasechain`

Executes PRD tasks using Ralph Loop principles with REX fallback for simple tasks:

```
Task Selection → Execution → Verification → Memory Update → Completion
```

**Three Execution Levels**:
1. **Simple (REX-style)**: Plan → Implement → Review → Done (1-3 simple tasks)
2. **Standard (Attended)**: Ralph Loop with human checkpoints (4-10 tasks)
3. **Complex (Overnight)**: Fully autonomous overnight execution (10+ tasks)

**Ralph Loop Components**:
- **Completion Promise System**: `<skillweave-complete>` signaling
- **Memory System**: `progress-structured.yaml` + `agents-enhanced.md`
- **Verification Feedback Loops**: Multi-level quality gates
- **Task Execution Engine**: Dependency-aware scheduling

## Agent-Agnostic Architecture

SkillWeave works with **any AI coding agent**, not just specific ones:

### Capability-Based Routing
Instead of: `"agent": "opencode"`
SkillWeave uses: `"required_capabilities": ["code_generation", "testing"]`

**Available Capabilities**:
- `planning`: Strategic thinking, architecture design
- `code_generation`: Writing and modifying code
- `testing`: Creating and running tests
- `review`: Code review and quality assessment
- `research`: Information gathering and analysis
- `automation`: Scripting and workflow automation
- `infrastructure`: System setup and configuration

**Benefits**:
- **Future-proof**: Works with new, unknown agents
- **Flexible**: Can use different agents for different tasks
- **Resilient**: Continues if specific agents are unavailable
- **Optimized**: Routes tasks to best-suited agents automatically

## Complexity-Aware Execution

SkillWeave automatically selects the right execution strategy:

### Decision Matrix

| Factor | REX (Simple) | Ralph Loop (Standard) | Ralph Loop (Complex) |
|--------|--------------|----------------------|----------------------|
| **Tasks** | 1-3 | 4-10 | 10+ |
| **Duration** | <60 min | 1-4 hours | >4 hours |
| **Dependencies** | Simple, linear | Moderate, branching | Complex, graph |
| **Risk** | Low | Medium | High |
| **Memory** | Basic tracking | Structured progress | Advanced knowledge |
| **Verification** | Lightweight | Multi-level | Production-grade |
| **Best For** | Bug fixes, small features | Feature development | System builds, new projects |

### Automatic Recommendation
Blueprint analyzes PRD and adds `execution_recommendation`:
```json
{
  "mode": "standard",
  "reason": "7 tasks, 4.5 hours total, moderate dependencies",
  "suggested_workflow": "ralph-loop-attended",
  "estimated_iterations": 8,
  "parallel_opportunities": 2,
  "complexity_score": 55
}
```

## Key Innovations

### 1. REX Integration
Recognizes that full Ralph Loop is overengineered for simple tasks. Implements REX-style (Ralph meets Rex) workflow for 1-3 task projects:
- **Plan → Implement → Review → Done** workflow
- **Quick feedback loops** with optional revisions
- **Minimal overhead** vs full Ralph Loop
- **Automatic escalation** if complexity increases

### 2. Parallel Execution Intelligence
Analyzes dependency graphs to identify concurrent execution opportunities:
```yaml
parallel_groups:
  - tasks: ["FEAT-001", "FEAT-002"]
    opportunity: "Audio processing can run in parallel"
    estimated_savings: "40 minutes"
```

### 3. Memory Systems That Learn
- **Short-term**: `progress-structured.yaml` - Iteration tracking
- **Long-term**: `agents-enhanced.md` - Knowledge accumulation
- **Cross-project**: Pattern sharing across organization
- **Continuous improvement**: Each project makes future projects better

### 4. Verification Feedback Loops
Multi-level quality assurance:
- **Code Level**: Type checking, linting, complexity analysis
- **Functional Level**: Unit tests, integration tests
- **System Level**: E2E tests, performance tests
- **Business Level**: Acceptance criteria validation

## Complete Example Workflow

### From Idea to Production
```bash
# 1. Create blueprint from idea
/skillweave-blueprint idea="AI meeting notes summarizer" domain="saas"

# 2. Generate execution sequences from PRD
/skillweave-promptchain-generate inputs='{"prd": "generated/prd.json"}' mode="auto"

# 3. Execute with Ralph Loop (based on complexity assessment)
/skillweave-releasechain inputs='{"prd": "generated/prd.json", "sequences": "execution-sequences.yaml"}' mode="attended"

# Result: Production-ready application in 4.5 hours
```

### Quick Bug Fix (REX-mode)
```bash
# 1. Create simple PRD for bug fix
/skillweave-blueprint idea="Fix login token expiration bug" domain="bug-fix"

# 2. Direct execution (auto-detects simple mode)
/skillweave-releasechain inputs='{"prd": "generated/prd.json"}' mode="simple"

# Result: Bug fixed in 30 minutes with minimal overhead
```

## Skill Reference

### Core Skills
- **`/skillweave-blueprint`**: Structured PRD creation with complexity assessment
- **`/skillweave-promptchain-generate`**: PRD/topic to execution sequence generation
- **`/skillweave-promptchain-execute`**: Sequence execution with parallelization
- **`/skillweave-promptchain-validate`**: Sequence validation and improvement
- **`/skillweave-releasechain`**: Ralph Loop execution with REX fallback

### Supporting Skills
- **`/skillweave-promptchain`** (legacy): General prompt sequence handling
- **Various `understand-*` skills**: Codebase analysis and documentation

## Getting Started

### Quick Start
1. **Install skills**: Use the installer script
2. **Start with blueprint**: `/skillweave-blueprint idea="Your project" domain="saas"`
3. **Follow recommendations**: SkillWeave will guide you through optimal execution path

### Best Practices
1. **Start simple**: Let SkillWeave recommend REX vs Ralph Loop
2. **Trust complexity assessment**: The system learns from historical data
3. **Use memory systems**: Accumulate knowledge across projects
4. **Review checkpoints**: Especially for attended mode execution
5. **Contribute patterns**: Share successful approaches in `agents-enhanced.md`

## Why SkillWeave?

### For Developers
- **10x faster development**: From idea to code in hours, not weeks
- **Higher quality**: Structured processes and verification gates
- **Less cognitive load**: AI handles implementation details
- **Continuous learning**: Memory systems make you better over time

### For Teams
- **Consistent processes**: Standardized development workflow
- **Knowledge sharing**: Cross-project pattern accumulation
- **Agent flexibility**: Use whatever AI tools you have available
- **Scalable execution**: From solo developer to team workflow

### For Organizations
- **Audit trail**: Structured progress tracking and decision documentation
- **Risk management**: Complexity-aware execution with checkpoints
- **Future-proof**: Agent-agnostic design adapts to AI evolution
- **Efficiency gains**: Parallel execution and dependency optimization

## The Future of AI-Assisted Development

SkillWeave represents the next evolution in AI coding:
1. **From prompts to processes**: Structured workflows instead of one-off prompts
2. **From agents to orchestrations**: Intelligent task routing across multiple agents
3. **From execution to learning**: Memory systems that accumulate organizational knowledge
4. **From simple to adaptive**: Complexity-aware execution strategies

**SkillWeave turns "product development flow on steroids" from a slogan into a reality** - accelerating development while maintaining quality through intelligent structure and automation.