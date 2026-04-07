---
name: skillweave-releasechain
description: Development pipeline for build outputs from SkillWeave execution. Handles review, testing, iteration, commit, push, PR, release, and changelog management.
argument-hint: inputs="[JSON with build outputs]" target="[humanize/machinize/mixed]"
---

# /skillweave-releasechain

Development pipeline for processing build outputs from SkillWeave execution.

**Usage:**
```
/skillweave-releasechain inputs="[JSON with build outputs and context]" target="[humanize/machinize/mixed]"
```

**Parameters:**
- `inputs` (required): JSON containing build outputs, file paths, and execution context
- `target` (optional): Target audience - humanize (human readable), machinize (machine optimized), mixed (default: mixed)
- `repo_path` (optional): Path to git repository (default: current directory)
- `auto_confirm` (optional): Automatically confirm safe operations (default: false)

**Pipeline Stages:**

1. **Review & Analysis**
   - Code quality analysis
   - Architecture review
   - Dependency checking
   - Security scanning

2. **Testing & Validation**
   - Unit test generation/execution
   - Integration testing
   - Performance validation
   - User acceptance criteria checking

3. **Iteration & Improvement**
   - Bug fixing
   - Performance optimization
   - Code refactoring
   - Documentation improvement

4. **Version Control**
   - Git status check
   - Commit with descriptive messages
   - Branch management
   - Tag creation

5. **Collaboration**
   - Push to remote repository
   - Pull request creation
   - Code review facilitation
   - Merge conflict resolution

6. **Release Management**
   - Version bumping (semantic versioning)
   - Release note generation
   - Changelog updates
   - Asset packaging

7. **Deployment Preparation**
   - Build artifact creation
   - Deployment configuration
   - Environment setup
   - Rollback planning

**Output Adaptation:**

- **Humanize**: Focus on explanations, summaries, documentation, and human-readable reports
- **Machinize**: Focus on structured data, APIs, automation scripts, and machine-readable formats
- **Mixed**: Balance between human and machine needs with clear separation

**Integration with Execute Skill:**

Called automatically by `/skillweave-promptchain-execute` when build components are detected and user requests development pipeline. Can also be called standalone with build outputs.

**Examples:**

**Automated from execute:**
```
# execute skill detects build components and user requests pipeline
Initiating /skillweave-releasechain with build outputs...
```

**Standalone usage:**
```
/skillweave-releasechain inputs='{"files": ["src/app.js", "docs/api.md"], "context": "webapp prototype", "changes": "Added user authentication"}'
```

**With repository path:**
```
/skillweave-releasechain inputs='{"files": ["package.json", "src/"]}' repo_path="/projects/myapp" target="mixed"
```

**Safety Features:**
- Confirmation required for destructive operations
- Dry-run mode available
- Rollback capability
- Audit logging
- Configuration validation