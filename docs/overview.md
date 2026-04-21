# Overview

SkillWeave is a complete product development ecosystem for AI-assisted development with five integrated skills:

## Core Skills
1. **Blueprint**: Guided PRD creation with complexity analysis
2. **PromptChain Generate**: Two-axis sequence generation (type: plan/build/mixed, mode: rex/ralph_attended/ralph_overnight)
3. **PromptChain Validate**: Comprehensive validation with parallelization readiness checks
4. **PromptChain Execute**: Ralph Loop state machine with write-scope based parallelization
5. **ReleaseChain**: Ralph Loop-powered development pipeline

## Key Architectural Innovations
- **Ralph Loop State Machine**: 9-state execution flow with binary gate policy
- **Write-Scope Based Parallelization**: Safe concurrent execution only for disjoint write scopes
- **Two-Axis Model**: Explicit separation of sequence type and execution mode
- **Binary Gate Policy**: Only hard completion signals accepted (tests passed, verifier passed, continue)
- **Agent-Agnostic Design**: Works with any AI coding agent through capability-based routing

## Complete Workflow
```
Idea → Blueprint → Generate → Validate → Execute → ReleaseChain → Production
```
