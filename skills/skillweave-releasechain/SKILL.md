---
name: skillweave-releasechain
description: Ralph Loop-powered development pipeline for autonomous AI development. Handles review, testing, iteration with completion promises, memory systems, and multi-agent execution.
argument-hint: inputs="[JSON with prd/tasks]" target="[humanize/machinize/mixed]" mode="[simple/manual/attended/overnight]"
---

# /skillweave-releasechain

**Ralph Loop-powered autonomous development pipeline.**  
Execute PRD tasks with completion promises, memory systems, and multi-agent coordination for overnight builds.

**Usage:**
```
/skillweave-releasechain inputs="[JSON with prd/tasks]" target="[humanize/machinize/mixed]" mode="[manual/attended/overnight]"
```

**Parameters:**
- `inputs` (required): JSON containing PRD (`prd.json`) and task list, or direct build outputs
- `target` (optional): Target audience - humanize (human readable), machinize (machine optimized), mixed (default: mixed)
- `mode` (optional): Execution mode - simple (REX-style), manual (Level 1), attended (Level 2), overnight (Level 3) (default: attended)
- `repo_path` (optional): Path to git repository (default: current directory)
- `max_iterations` (optional): Maximum iterations for Ralph Loop (default: 30)
- `completion_promise` (optional): Completion promise format (default: SkillWeave standard)
- `auto_confirm` (optional): Automatically confirm safe operations (default: false)

**Ralph Loop Pipeline Architecture:**

### Core Components

1. **Completion Promise System**
   - Standardized completion signaling: `<skillweave-complete>`
   - Verification before promise issuance
   - Multi-agent compatible format
   - Automatic loop termination on success

2. **Memory System**
   - **Short-term**: `progress-structured.yaml` - Iteration tracking
   - **Long-term**: `agents-enhanced.md` - Knowledge accumulation  
   - **Cross-project**: Organization-wide pattern sharing
   - Structured format for AI readability

3. **Task Execution Engine**
   - Atomic task execution (one iteration per task)
   - Dependency-aware scheduling
   - Multi-agent routing based on capabilities
   - Automatic retry with learning

4. **Verification Feedback Loops**
   - Multi-level verification (code, functional, system, business)
   - Automated testing integration
   - Quality gates before task completion
   - Continuous improvement from failures

### Agent-Agnostic Execution

ReleaseChain is **agent-agnostic** – it works with any AI coding agent, not just specific ones. Instead of hardcoding agent names, it uses **capability-based routing**:

1. **Capability Definitions**: Tasks specify required capabilities (planning, code_generation, testing, review, etc.)
2. **Agent Registry**: Available agents declare their capabilities at runtime
3. **Intelligent Routing**: Tasks are routed to agents that best match required capabilities
4. **Fallback Strategies**: Automatic fallback if preferred agents are unavailable

**Capability Mapping Examples**:
- `planning`: Strategic thinking, architecture design
- `code_generation`: Writing and modifying code  
- `testing`: Creating and running tests
- `review`: Code review and quality assessment
- `research`: Information gathering and analysis
- `automation`: Scripting and workflow automation
- `infrastructure`: System setup and configuration

**Benefits**:
- **Future-Proof**: Works with new agents as they emerge
- **Flexible**: Can use different agents for different tasks
- **Resilient**: Continues working even if specific agents are unavailable
- **Optimized**: Routes tasks to best-suited agents automatically

### Execution Levels

**Level 0: Simple (REX-style)**
- Direct execution for 1-3 simple tasks
- Plan → Implement → Review workflow
- Minimal memory system (basic progress tracking)
- Quick feedback loop with optional revisions
- Best for: Quick fixes, small features, proofs of concept

**Level 1: Manual (Learning)**
- Single task execution with observation
- Manual verification and approval
- Agent behavior understanding
- Task sizing validation

**Level 2: Attended (Confidence)**
- Multiple tasks in sequence
- Periodic human check-ins
- Semi-automated verification
- Error recovery testing

**Level 3: Overnight (Production)**
- Full autonomous execution
- Comprehensive verification
- Notification system
- Morning review process

### Simple Mode (REX-style) Workflow

For simple tasks (1-3 tasks, <60 minutes), ReleaseChain uses a streamlined workflow:

```
1. Task Analysis → 2. Planning → 3. Implementation → 4. Review → 5. Completion
       ↑                                                              ↓
       └─────────────────── Revision Loop ────────────────────────────┘
```

**Components:**
- **Planning**: Quick analysis and implementation plan
- **Implementation**: Direct execution with agent best suited for task
- **Review**: Automated verification + optional human review
- **Revision**: Loop back if issues found (max 2 revisions)

**Memory System**: Basic progress tracking (`progress-simple.txt`)
**Verification**: Lightweight checks (type checking, basic tests)
**Output**: Human-readable summary with machine-readable status

### Pipeline Stages with Ralph Loop Integration

1. **PRD & Task Analysis**
   - Load and validate `prd.json`
   - Build dependency graph
   - Identify parallel execution opportunities
   - Route tasks to appropriate agents

2. **Ralph Loop Execution**
   - **Iteration Cycle**: Task → Implementation → Verification → Promise
   - **Memory Updates**: progress-structured.yaml after each iteration
   - **Learning Capture**: agents-enhanced.md for patterns
   - **Completion Check**: All tasks `passes: true`

3. **Multi-Agent Coordination**
   - Agent capability matching
   - Parallel task execution
   - Resource management
   - Fallback strategies

4. **Verification & Quality Gates**
   - **Code Level**: Type checking, linting, static analysis
   - **Functional Level**: Unit tests, integration tests
   - **System Level**: E2E tests, performance tests
   - **Business Level**: Acceptance criteria validation

5. **Version Control Integration**
   - Atomic commits per successful task
   - Descriptive commit messages
   - Branch management for features
   - Tag creation for milestones

6. **Collaboration & Review**
   - Automated PR creation
   - Code review facilitation
   - Change documentation
   - Stakeholder notification

7. **Release Management**
   - Semantic versioning
   - Changelog generation
   - Release note creation
   - Asset packaging

8. **Deployment Readiness**
   - Build artifact creation
   - Environment configuration
   - Rollback planning
   - Monitoring setup

**Output Adaptation:**

- **Humanize**: Progress reports, executive summaries, documentation, human-readable completion reports
- **Machinize**: Structured data (YAML/JSON), API responses, automation scripts, machine-readable status
- **Mixed**: Combined human and machine outputs with clear separation, ideal for CI/CD integration

**Ralph Loop Pattern Support:**

1. **Feature Builder**: Complete feature development from PRD
2. **Test-Until-Green**: Automated test coverage improvement  
3. **Multi-Persona Review**: Comprehensive code quality review
4. **Proof of Concept Validator**: Rapid prototyping and validation
5. **Infrastructure as Code**: Automated infrastructure setup

**Integration with SkillWeave Workflow:**

Complete development chain: `Blueprint → PromptChain → ReleaseChain`

1. **Blueprint Integration**: Uses `prd.json` from `/skillweave-blueprint`
2. **PromptChain Integration**: Executes sequences from `/skillweave-promptchain-execute`
3. **Execute Skill Integration**: Called automatically for build components with parallel execution
4. **Standalone Mode**: Direct PRD execution without intermediate steps

**Examples:**

**Complete PRD Execution (Overnight Mode):**
```
/skillweave-releasechain inputs='{"prd": "prd.json"}' mode="overnight" max_iterations=50
```
*Runs full PRD overnight, emails completion report in morning*

**Attended Development (Level 2):**
```
/skillweave-releasechain inputs='{"tasks": ["API-001", "UI-001", "TEST-001"]}' mode="attended" target="mixed"
```
*Executes specific tasks with human checkpoints*

**Test-Until-Green Pattern:**
```
/skillweave-releasechain inputs='{"pattern": "test-until-green", "coverage_target": 80}' mode="attended"
```
*Improves test coverage to target percentage*

**Multi-Persona Review:**
```
/skillweave-releasechain inputs='{"pattern": "multi-persona-review", "cycles": 2}' mode="manual"
```
*Comprehensive code review with security, performance, accessibility personas*

**Simple Mode (REX-style) Execution:**
```
/skillweave-releasechain inputs='{"tasks": ["BUG-001"]}' mode="simple" target="humanize"
```
*Quick bug fix with plan-implement-review workflow, minimal overhead*

**From Blueprint Output:**
```
# After creating blueprint
/skillweave-blueprint idea="Task management API" domain="saas"
# Then execute PRD
/skillweave-releasechain inputs='{"prd": "generated/prd.json"}' mode="attended"
```

**Integration with Execute Skill:**
```
# Execute skill runs parallel execution
/skillweave-promptchain-execute sequence="..." inputs="..."
# When build components detected, offers:
"Build components detected. Initiate Ralph Loop pipeline? [Yes/No]"
# If Yes: Initiates /skillweave-releasechain automatically
```

**Safety Features:**
- Confirmation required for destructive operations
- Dry-run mode available
- Rollback capability
- Audit logging
- Configuration validation