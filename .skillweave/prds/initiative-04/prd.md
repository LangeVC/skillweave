# PRD: Initiative 04 — Repo Cleanup and Lean Core

## 1. Executive Summary

**Project:** SkillWeave Repository Cleanup and Lean Core  
**Initiative:** 04 of 06 (Master Roadmap Phase B)  
**Domain:** Developer Tooling / AI-Assisted Product Development  
**Risk Mode:** Medium  

As SkillWeave grows, the repository risks clutter, stale files, unclear ownership, and hidden valuable work getting lost. This initiative defines a structured cleanup process with classification, preservation, and controlled archival — aligning the repo to the future architecture defined in Phase A initiatives.

**Core Value:** Make the repo leaner without losing valuable work; active paths easy to identify; cleanup reversible and reviewable.

## 2. Problem Statement

### Current Situation
- Repository has grown organically with skills, prompt sequences, bundles, artifacts, and execution history
- Unclear which files are active core vs legacy vs experimental
- Potential for duplicated logic across skills
- Prior work that may still be valuable could be lost in aggressive cleanup
- Cleanup without strategy risks removing useful reference material

### Impact
- New contributors struggle to navigate the repo
- Refactoring is risky because ownership and status of files is unclear
- Maintenance overhead grows with unclassified files
- Valuable patterns and learnings hidden in legacy code

## 3. Solution Overview

### Cleanup Philosophy
**Classify → Preserve → Review → Archive → Remove**

Never destroy information casually. Every file gets classified before any action is taken.

### Classification Categories

| Category | Description | Action |
|----------|------------|--------|
| **Active Core** | Current canonical files for real operation | Keep in place |
| **Consolidation Candidate** | Useful but overlapping, may be merged | Review and merge |
| **Legacy Valuable** | Old but worth preserving for reference | Move to archive |
| **Deprecated** | No longer part of active direction | Archive with metadata |
| **Needs Review** | Not yet confidently classifiable | Flag for human review |

### Preservation Mechanism
```
.skillweave/archive/
  ├── legacy/           # Legacy but valuable artifacts
  ├── deprecated/       # Deprecated with metadata
  ├── review-queue/     # Items needing human classification
  └── manifest.yaml     # Archive index with classification rationale
```

## 4. Functional Requirements

### 5.1 Core Features

**F-01: Repository Inventory Scanner**
- Description: Automated scanner that catalogs all files in the repo with type, last modified, size, and classification suggestion
- Acceptance Criteria:
  - Scans entire repo and produces inventory file
  - Each file has: path, type, last_modified, size_bytes, suggested_category
  - Classification suggestions based on heuristics (age, location, naming patterns)
  - Output saved to `.skillweave/cleanup/inventory.yaml`

**F-02: Classification Engine**
- Description: Rule-based classifier that assigns categories to files based on patterns
- Acceptance Criteria:
  - Rules defined for: skills, prompt sequences, documentation, config, generated artifacts
  - Rules consider: file location, naming convention, age, reference count
  - Outputs classification per file with confidence score
  - Low-confidence items flagged as "Needs Review"

**F-03: Archive Manager**
- Description: Tool for moving files to structured archive locations with metadata preservation
- Acceptance Criteria:
  - Moves files to `.skillweave/archive/{category}/`
  - Creates manifest entry with: original path, category, rationale, date, reversible flag
  - Archive manifest is human-readable YAML
  - Restore function exists to move files back from archive

**F-04: Duplication Detector**
- Description: Identifies duplicated or highly similar logic across skills, prompts, and configurations
- Acceptance Criteria:
  - Scans for similar file names across directories
  - Identifies overlapping content in skill definitions
  - Reports duplication with file pairs and similarity indicator
  - Suggests consolidation candidates

**F-05: Cleanup Report Generator**
- Description: Produces a human-readable cleanup report summarizing inventory, classifications, recommendations, and actions taken
- Acceptance Criteria:
  - Report includes: total files, files per category, recommended actions, duplication findings
  - Report saved to `.skillweave/cleanup/report.md`
  - Report includes reversibility information for all actions
  - Report is reviewable before any destructive action

**F-06: Lean Core Definition**
- Description: Document defining what constitutes the "lean core" of SkillWeave — the minimal set of files needed for operation
- Acceptance Criteria:
  - Lean core manifest lists all essential files
  - Manifest distinguishes: required, recommended, optional
  - Non-core files are candidates for archive or removal
  - Lean core aligned with future architecture (Initiative 01)

## 5. Non-Functional Requirements

### Safety
- No file deletion without explicit human approval
- All moves are reversible via archive manifest
- Cleanup actions logged with timestamps

### Compatibility
- Cleanup must not break any active SkillWeave functionality
- Archive structure must be ignorable by active tools (e.g., in .gitignore patterns)

## 6. Success Metrics (Binary & Testable)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Inventory complete | All repo files cataloged | Inventory file exists with full coverage |
| Classification applied | Every file has a category | No "unclassified" entries in inventory |
| Archive structure exists | .skillweave/archive/ with manifest | Directory and file exist |
| Duplication report generated | Overlap identified | Report file exists with findings |
| Lean core defined | Essential files listed | Manifest validates |
| No functionality broken | All tests pass after cleanup | Test suite passes |

## 7. Timeline & Milestones

| Phase | Deliverable | Estimated Effort |
|-------|-------------|-----------------|
| Build | Repository inventory scanner | 1.5 hours |
| Build | Classification engine with rules | 2 hours |
| Build | Archive manager with manifest | 1.5 hours |
| Build | Duplication detector | 1 hour |
| Build | Cleanup report generator | 1 hour |
| Design | Lean core definition | 1.5 hours |
| Execution | Run cleanup process on repo | 2 hours |
| Testing | Verify no breakage | 1 hour |

**Total Estimated Effort:** ~11.5 hours

## 8. Scope & Constraints

### In Scope
- Repository inventory and classification
- Archive structure and manifest
- Duplication detection
- Cleanup reporting
- Lean core definition

### Out of Scope
- Automated deletion (human approval required)
- Git history rewriting
- Dependency graph analysis of external packages
- Performance optimization of remaining files

## 9. Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Archiving breaks active functionality | Medium | Critical | Run full test suite after every archive batch |
| Valuable files classified as deprecated | Medium | High | Conservative classification, human review for uncertain items |
| Cleanup scope creep | Medium | Medium | Strict category definitions, cleanup report before action |
| Archive grows large and unmaintained | Low | Low | Periodic archive review, retention policy |
