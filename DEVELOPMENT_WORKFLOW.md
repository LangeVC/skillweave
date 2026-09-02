# SkillWeave Development Workflow & Release Process

This document outlines the standard development workflow, release process, and naming conventions for SkillWeave.

## Versioning Convention

### Release Naming
- **Format**: `SkillWeave vX.Y.Z`
- **Example**: `SkillWeave v0.4.0`
- **Tag**: `vX.Y.Z` (Git tag)
- **Release Title**: `SkillWeave vX.Y.Z` (GitHub release title)

### Semantic Versioning (SemVer)
- **MAJOR** (`X`): Breaking changes, major feature additions
- **MINOR** (`Y`): New features, enhancements (backward compatible)
- **PATCH** (`Z`): Bug fixes, patches (backward compatible)

## Standard Development Workflow

### 1. Feature Development
```bash
# Create feature branch from main
git checkout main
git pull origin main
git checkout -b feature/descriptive-name

# Example branch names:
# - feature/parallel-execution
# - feature/blueprint-skill
# - fix/dependency-analysis-bug
```

### 2. Development & Testing
```bash
# Make changes, add tests
# Run tests
python3 -m pytest tests/ -v

# Stage changes
git add .

# Commit with descriptive message
git commit -m "feat: Add parallel execution engine

- Implement dependency graph analysis
- Add execution grouping with Kahn's algorithm
- Add timeout handling and error recovery
- Update tests for parallel execution"
```

### 3. Create Pull Request
```bash
# Push branch to remote
git push origin feature/descriptive-name

# Create PR using GitHub CLI
gh pr create \
  --title "feat: Add parallel execution engine" \
  --body "$(cat <<'EOF'
## Summary
Adds parallel execution engine with dependency analysis and subagent triggering.

## Changes
- **Dependency Analysis**: Kahn's algorithm for topological sorting
- **Execution Groups**: Identify steps that can run in parallel
- **Subagent Integration**: Task tool abstraction for parallel execution
- **Error Handling**: Timeout management and recovery strategies

## Testing
- [x] Unit tests for orchestrator and executor
- [x] Integration tests for full workflow
- [x] Performance tests for large sequences

## Impact
- Accelerates execution by 70% for independent tasks
- Enables complex project workflows
- Maintains backward compatibility
EOF
)"

# Or create PR via GitHub web interface
```

### 4. PR Review & Merge
- **Reviewers**: At least one maintainer must approve
- **CI/CD**: All tests must pass
- **Merge Strategy**: Squash merge preferred for feature branches
- **Commit Message**: Use PR title as squash commit message

```bash
# After approval, merge via GitHub UI or CLI
gh pr merge <pr-number> --squash

# Or rebase and merge for linear history
gh pr merge <pr-number> --rebase
```

## Release Process

### 1. Release Preparation
```bash
# Ensure main is up to date
git checkout main
git pull origin main

# Verify tests pass
python3 -m pytest tests/ -v

# --- Version bump (REQUIRED — see "Version bump contract" below) ---
# Fetch the canonical, tag-pinned version-sync helper and write the new version
# into every location declared in .version.yaml (16 locations: pyproject.toml,
# capability.yaml — both its own version: and the 13 capabilities[] member pins —
# and all 13 skills/*/capability.yaml).
# This MUST happen before the tag is created, or the tag gate rejects the push.
curl -fsSL \
  "https://raw.githubusercontent.com/LangeVC/ops-engine/v3.0.0/scripts/version-sync.py" \
  -o /tmp/version-sync.py
python3 /tmp/version-sync.py bump X.Y.Z --repo .
# The bump self-verifies: it re-runs `check` and fails if any location drifted.

# Commit the written versions; the tag gate compares the tag against
# source_of_truth (pyproject.toml) at the commit the tag points at.
git add pyproject.toml capability.yaml skills/
git commit -m "chore: bump version to X.Y.Z"

# Sync Capacium manifests to the new version (distribution-bundle step)
python3 scripts/sync-capacium-manifests.py

# Verify Capacium manifests are in sync
python3 scripts/sync-capacium-manifests.py --check

# Check CHANGELOG.md is updated
# Verify documentation is current
```

### Version bump contract

The release gate (`.forgejo/workflows/mirror.yml`, `version-gate` job) rejects
any `v*` tag whose `source_of_truth` (`pyproject.toml`) does not equal the tag
number. Five releases (v1.3.12 through v1.5.0) shipped a tag with no written
version because nothing ever called the bump. The required order is therefore:

1. `python3 version-sync.py bump X.Y.Z --repo .` — writes every declared location.
2. Commit the written versions.
3. `git tag vX.Y.Z` and push — only now can the gate pass.

The bump tool is fetched from the pinned ops-engine tag `v3.0.0` (not the moving
`master` branch), and the workflow re-proves the fetched file is Python and
carries the `bump` subcommand before use. Do not hand-edit version strings: the
`.version.yaml` `locations` list is the single inventory, and the bump writes it
in full.

### 2. Create Release
```bash
# Create and push tag
git tag -a vX.Y.Z -m "SkillWeave vX.Y.Z"
git push origin vX.Y.Z

# Create GitHub release
gh release create vX.Y.Z \
  --title "SkillWeave vX.Y.Z" \
  --notes "$(cat <<'EOF'
# SkillWeave vX.Y.Z

## 🎯 Summary
Brief description of release highlights.

## 🚀 New Features
- Feature 1: Description
- Feature 2: Description

## 🐛 Bug Fixes
- Fix 1: Description

## 🔧 Technical Improvements
- Improvement 1: Description

## 📚 Documentation
- Updated documentation for new features

## 🧪 Testing
- Added/updated tests for new functionality

## 📦 Installation
```bash
git clone https://github.com/LangeVC/skillweave.git
cd skillweave
cap install skillweave --source .
# or use the compatibility wrapper
./scripts/install-skills.sh
```

## 🔗 Links
- [Full Documentation](https://github.com/LangeVC/skillweave/blob/main/README.md)
- [Examples](https://github.com/LangeVC/skillweave/tree/main/examples)
- [Changelog](https://github.com/LangeVC/skillweave/blob/main/CHANGELOG.md)
EOF
)"
```

### 3. Post-Release
```bash
# Update CHANGELOG.md with release details
# Announce release (if applicable)
# Monitor for any issues
```

## Branching Strategy

### Main Branches
- **`main`**: Production-ready code, always deployable
- **`develop`** (optional): Integration branch for features

### Supporting Branches
- **`feature/*`**: New features, enhancements
- **`fix/*`**: Bug fixes
- **`hotfix/*`**: Urgent production fixes
- **`release/*`**: Release preparation

## Commit Message Convention

### Format
```
type: Short description

Longer description if needed.
Additional details, context, or references.

- Bullet point 1
- Bullet point 2
```

### Types
- **`feat`**: New feature
- **`fix`**: Bug fix
- **`docs`**: Documentation changes
- **`style`**: Code style, formatting
- **`refactor`**: Code refactoring
- **`test`**: Test additions/modifications
- **`chore`**: Maintenance, tooling, dependencies
- **`perf`**: Performance improvements
- **`ci`**: CI/CD changes

### Examples
```bash
# Good commit messages
git commit -m "feat: Add blueprint skill with PRD generation

- Implement guided interview for requirements gathering
- Add complexity analysis and execution recommendations
- Create PRD schema and validation
- Add integration tests for full workflow"

git commit -m "fix: Resolve circular dependency detection

- Fix infinite loop in cycle detection algorithm
- Add test for complex dependency graphs
- Improve error messages for circular dependencies"

git commit -m "docs: Update development workflow

- Document release process and naming conventions
- Add PR creation template
- Update testing guidelines"
```

## Testing Requirements

### Before PR
```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific test suites
python3 -m pytest tests/test_orchestrator.py -v
python3 -m pytest tests/test_integration.py -v
python3 -m pytest tests/test_performance.py -v
```

### Test Coverage
- **Unit Tests**: Individual components (orchestrator, executor, etc.)
- **Integration Tests**: Full workflow (Blueprint → PromptChain → ReleaseChain)
- **Performance Tests**: Large sequences, memory usage, scalability
- **Example Scripts**: Verify examples work correctly

## Documentation Requirements

### Must Update
1. **README.md**: High-level overview, installation, quick start
2. **CHANGELOG.md**: Release notes, changes, migration notes
3. **Examples**: Working examples for new features
4. **Skill Documentation**: SKILL.md files for each skill

### Optional Updates
1. **API Documentation**: If exposing new APIs
2. **Architecture Docs**: For significant architectural changes
3. **Tutorials**: For complex new features

## Release Checklist

### Pre-Release
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Examples working
- [ ] CHANGELOG.md updated
- [ ] Capacium manifests synced and validated
- [ ] No breaking changes (or documented if necessary)
- [ ] Version numbers updated in code (if applicable)

### Release
- [ ] Tag created with correct version
- [ ] GitHub release created with proper title
- [ ] Release notes comprehensive and accurate
- [ ] Assets attached (if any)

### Post-Release
- [ ] Announcement (if applicable)
- [ ] Monitor for issues
- [ ] Update dependent projects (if any)

## Emergency Hotfix Process

### For Critical Production Issues
```bash
# Create hotfix branch from main
git checkout main
git pull origin main
git checkout -b hotfix/issue-description

# Fix the issue
# Add tests for the fix

# Create PR directly against main
gh pr create --base main --title "hotfix: Fix critical issue"

# After approval, merge and tag immediately
git checkout main
git pull origin main
git tag -a vX.Y.Z+1 -m "SkillWeave vX.Y.Z+1 hotfix"
git push origin vX.Y.Z+1
```

## Naming Conventions

### Files & Directories
- **Skills**: `skills/skillweave-[skill-name]/`
- **Examples**: `examples/[descriptive-name].md` or `.py`
- **Tests**: `tests/test_[module_name].py`
- **Schemas**: `schemas/[entity].schema.json`

### Code
- **Python**: snake_case for variables/functions, PascalCase for classes
- **Markdown**: Descriptive headings, consistent formatting
- **JSON**: camelCase for property names

## Tools & Dependencies

### Required
- **Python 3.8+**: Core runtime
- **pytest**: Testing framework
- **GitHub CLI (`gh`)**: Release management
- **Git**: Version control

### Recommended
- **pre-commit**: Code quality hooks
- **black**: Code formatting
- **mypy**: Type checking
- **ruff**: Linting

## Getting Help

- **Issues**: GitHub Issues for bugs and feature requests
- **Discussions**: GitHub Discussions for questions and ideas
- **Contributing**: See CONTRIBUTING.md for contribution guidelines
- **Security**: See SECURITY.md for security issues

---

*Last updated: April 2026*  
*Based on SkillWeave v0.4.0 release process*
