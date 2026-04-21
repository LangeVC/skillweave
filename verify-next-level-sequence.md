# SkillWeave Next Level Verification Sequence

## Sequence Type: mixed (plan + build verification)

## Objective
Verify that all 16 Next Level tasks from PRD (prd-skillweave-next-level.json) are properly implemented and meet acceptance criteria. Since implementation already exists in src/skillweave/, verify each module works as expected.

## Inputs
- PRD tasks: 16 tasks with acceptance criteria
- Implementation: src/skillweave/next_level.py and related modules
- Tests: tests/test_*.py
- GitHub Issues: Issues #2-17 created

## Phases (following execution-sequences.yaml)

### Phase 1: Infrastructure & Analysis
1. **ARCH-001**: Verify .skillweave folder structure design
   - Check that persistence.py defines SUBDIRS: ["handover", "specs", "tracking-log", "manifesto"]
   - Verify ensure_folder_structure() creates directories
   - Check gitignore entry excludes tracking-log/*
   - Acceptance: Folder structure documented, gitignore rules correct

2. **REFACTOR-001**: Analyze redundancies between PromptChain and ReleaseChain
   - Review src/skillweave/ for shared components
   - Check if duplicate code exists between skills
   - Document overlap areas
   - Acceptance: Analysis complete, recommendations produced

3. **ENHANCE-001**: Verify capability-based routing enhancement
   - Check capability.py for dynamic agent detection
   - Verify CapabilityRouter class exists
   - Test route_task function
   - Acceptance: Works with at least 2 agent types

### Phase 2: Core Implementation
4. **ARCH-002**: Verify Persistent State Manager
   - Test SkillWeavePersistence class
   - Verify config loading/saving
   - Check tracking-log functionality
   - Acceptance: State can be saved/loaded after restart

5. **ARCH-003**: Verify Configuration Manager
   - Test SkillWeaveConfig dataclass
   - Verify mode interpretation (conservative, medium, unicorn)
   - Check feature flags
   - Acceptance: Three modes recognized, default values work

6. **ENHANCE-002**: Verify modular templates foundation
   - Check templates.py and .skillweave/templates/ directory
   - Verify template loading mechanism
   - Test variable substitution
   - Acceptance: 3 example templates exist (web_app, api_service, cli_tool)

7. **REFACTOR-002**: Verify shared library components extraction
   - Check if shared modules exist (skillweave.core or similar)
   - Verify PromptChain and ReleaseChain use shared components
   - Measure code duplication reduction
   - Acceptance: Code duplication reduced by 50%

### Phase 3: Feature Integration
8. **ENHANCE-003**: Verify community know-how prototype
   - Check community_knowhow.py
   - Test PatternExtractor and RepoCleanupRecommender
   - Verify pattern extraction works
   - Acceptance: Prototype demonstrates concept

9. **FEAT-004**: Verify optional checklist execution
   - Test checklist.py
   - Verify ChecklistParser.parse_markdown()
   - Check loop execution until complete
   - Acceptance: Feature can be disabled in config

10. **ENHANCE-004**: Verify GitHub Issues integration
    - Check create_github_issues.py script
    - Verify issues created successfully (#2-17)
    - Check Fibonacci point estimation (1 point = 2 hours)
    - Acceptance: Issues created with components, priorities, roadmap mapping

11. **FEAT-001**: Verify three risk modes in Blueprint skill
    - Check mode_manager.py integration with Blueprint
    - Test get_mode_guidance("blueprint")
    - Verify mode-specific behavior differences
    - Acceptance: Blueprint reads mode from config

12. **FEAT-002**: Verify three risk modes in PromptChain skills
    - Check PromptChain skills interpret mode
    - Test conservative vs unicorn behavior
    - Verify behavior differences testable
    - Acceptance: Conservative mode adds extra validation

13. **FEAT-003**: Verify three risk modes in ReleaseChain skill
    - Check ReleaseChain mode interpretation
    - Test automation level adjustment
    - Verify integration tests pass for all modes
    - Acceptance: Unicorn mode runs more autonomously

14. **FEAT-005**: Verify optional Design-Thinking Lens
    - Check design_thinking.py
    - Test DesignThinkingLens.apply_to_content()
    - Verify rules customizable per project
    - Acceptance: Output shows reduced clutter

### Phase 4: Testing & Documentation
15. **DOCS-001**: Verify documentation updates
    - Check README for new capabilities
    - Verify configuration guide exists
    - Check migration guide
    - Acceptance: Examples of three modes documented

16. **TEST-001**: Verify comprehensive testing suite
    - Run all Next Level tests
    - Check test coverage >80%
    - Verify integration tests
    - Acceptance: Unit tests for new components

## Verification Commands
- `pytest tests/test_next_level.py -v`
- `pytest tests/test_integration_next_level.py -v`
- `python -c "from src.skillweave.persistence import ensure_skillweave_folder; ensure_skillweave_folder()"`
- `python -c "from src.skillweave.next_level import SkillWeaveNextLevel; nl = SkillWeaveNextLevel(); print(nl.get_mode())"`

## Success Criteria
All 16 tasks pass acceptance criteria. Implementation matches PRD specifications. Tests pass. GitHub issues properly created.

## Risk Assessment
Low risk - verification only, no code changes.

## Output Format
For each task:
- Task ID
- Status: PASS/FAIL
- Evidence: Code references, test output
- Acceptance Criteria Met: Y/N
- Notes: Any discrepancies