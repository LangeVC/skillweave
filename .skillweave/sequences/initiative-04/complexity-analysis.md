# Complexity Analysis: Initiative 04 — Repo Cleanup and Lean Core

## Overview
- **Total Tasks**: 8
- **Estimated Duration**: ~345 minutes (5.75 hours)
- **Dependency Graph**: Moderate (sequential pipeline with 2 parallel opportunities)
- **Agent Types**: 4 (code_generation, planning, documentation, testing)
- **Risk Level**: Medium (archive operations risk breaking functionality)
- **Task Types**: infrastructure (5), documentation (2), testing (1) — 3 types

## Component Scores

| Factor | Score (0-100) | Weight | Weighted |
|--------|--------------|--------|----------|
| Task Count (8) | 50 | 0.20 | 10.0 |
| Duration (~345 min) | 55 | 0.25 | 13.75 |
| Dependencies | 50 | 0.25 | 12.5 |
| Agent Diversity (4 types) | 70 | 0.15 | 10.5 |
| Risk Level | 45 | 0.10 | 4.5 |
| Task Type Variety (3 types) | 40 | 0.05 | 2.0 |

**Total Complexity Score: 53.25**

## Recommendation

| Aspect | Value |
|--------|-------|
| Mode | **Standard** |
| Workflow | **Ralph Loop Attended** |
| Estimated Iterations | 8-10 |
| Parallel Opportunities | 2 (TOOL-001 + TOOL-003; TOOL-004 + DESIGN-001) |

## Execution Notes
- TOOL-001 is the critical root — scanner output feeds classification, duplication detection, and the full pipeline
- TOOL-003 (archive manager) has no dependencies and can be built in parallel with TOOL-001
- TOOL-002 (classification) must complete before DESIGN-001 (lean core) can start
- TOOL-004 (duplication) and DESIGN-001 (lean core) can run in parallel after their respective deps
- TOOL-005 (report) depends on both TOOL-002 and TOOL-004 — synchronizes analysis phase
- EXEC-001 is the highest-risk task: orchestrating scan → classify → duplicate detect → report → review → archive

## Risk Assessment
- **Highest Risk**: EXEC-001 (archive operations may break active functionality; human approval gate critical)
- **Medium Risk**: TOOL-002 (classification accuracy with rule-based heuristics; many items may fall into needs-review)
- **Medium Risk**: TEST-001 (post-cleanup test suite must pass — any failure means restore needed)
- **Low Risk**: TOOL-001, TOOL-003 (pure infrastructure, well-understood patterns)
