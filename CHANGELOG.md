# Changelog

## 0.4.3
- **FIX**: Installed `skillweave-blueprint` for supported agents so Codex and related tools see the full five-skill SkillWeave set
- **FIX**: Cleaned up legacy SkillWeave duplicates under `~/.agents/skills` to prevent duplicate promptchain entries with stale descriptions
- **FIX**: Source/Target directory separation – installer now copies skills from development repo to `~/.skillweave` installation directory
- **FIX**: Removed duplicate git repository from `~/.skillweave` (target directory should be plain folder, not a git repo)
- **FIX**: Added warning when target directory is a git repository with cleanup instructions
- **NEW**: `update-local-skills.sh` script for developers to sync changes from development repo to installation
- **IMPROVEMENT**: Installer automatically copies skills from source to target when run from development repository
- **IMPROVEMENT**: Better logging and dry-run output for copying operations

## 0.4.2
- **FEATURE**: Interactive installer with agent selection modes (`--interactive`, `--uninstall`, `--update`, `--troubleshoot`)
- **FIX**: Correct agent paths for Gemini CLI (`~/.gemini/skills`) and Qwen Code (`~/.qwen/skills`)
- **FIX**: Prevent creating directories for non-existent agents (no "file-leichen")
- **IMPROVEMENT**: Smart agent detection with numeric selection, `all`, or `none` options
- **DOCS**: Updated README with interactive installation section and corrected agent paths

## 0.4.1
- **DOCS**: Complete README overhaul with "Product development flow on steroids" branding
- **DOCS**: Added DEVELOPMENT_WORKFLOW.md with standardized release process
- **DOCS**: Release conventions and "SkillWeave vX.Y.Z" naming standardization
- **IMPROVEMENT**: ASCII workflow diagram and enhanced architecture documentation
- **IMPROVEMENT**: Repository structure updates and clearer onboarding guidance

## 0.4.0
- **FEATURE**: Blueprint Skill (`/skillweave-blueprint`) for structured PRD creation
- **FEATURE**: Enhanced Execute Skill with parallel execution and dependency analysis
- **FEATURE**: Enhanced ReleaseChain Skill with dual-mode (REX/Ralph Loop) execution
- **ARCHITECTURE**: Parallel execution core with dependency graph analysis
- **ARCHITECTURE**: Capability-based agent-agnostic design for any AI coding agent
- **DOCS**: Full workflow example and comprehensive testing suite
- **PERFORMANCE**: Optimizations for large projects (50+ tasks)

## 0.3.5
- **FEATURE**: Intelligent `skillweave-promptchain-execute` with plan/build/mixed mode detection
- **NEW**: `skillweave-releasechain` development pipeline skill
- Execute skill now detects sequence type and adapts outputs accordingly
- Post-execution options: target audience (humanize/machinize/mixed)
- Build components can trigger automated development pipeline
- Releasechain handles: review, testing, iteration, commit, push, PR, release, changelog
- Better integration between execute and releasechain skills

## 0.3.4
- **IMPROVEMENT**: Enhanced `skillweave-promptchain-validate` with better output handling
- Added user prompts for output format: Validation Report, Improved sequence only, Both separate files
- Added sequence type detection: plan mode, build mode, mixed
- Improved sequence must be complete (no placeholder references)
- Output format adaptation based on sequence type
- Better documentation of validation interaction process

## 0.3.3
- **FEATURE**: Attachment detection for `skillweave-promptchain-execute` and `skillweave-promptchain-validate`
- Skills now accept prompt sequences as .md/.txt file attachments
- Updated descriptions, usage examples, and parameters
- Added attachment detection logic description
- Clarified that generate uses parameters only (no attachments)

## 0.3.2
- **FIX**: YAML parsing in `skillweave-promptchain-execute` argument-hint
- Changed `inputs='{\"key\": \"value\"}'` to `inputs=\"[JSON]\"` to avoid YAML parser errors
- Fixes Codex and other agent compatibility issues

## 0.3.1
- **FIX**: Multi-agent installer with correct paths and formats for all agents
- **FIX**: Opencode installation as single `.md` files to `~/.config/opencode/commands/`
- **FIX**: Claude Code/Codex/Antigravity paths to correct locations (`~/.claude/skills/`, `~/.codex/skills/`, `~/.antigravity/skills/`)
- **FIX**: Different installation formats per agent type (single files vs directories)
- **FIX**: Updated README with correct manual installation instructions
- **IMPROVEMENT**: Better error handling and logging in installer script

## 0.3.0
- separate skill directories for each command: `skillweave-promptchain-generate`, `-validate`, `-execute`
- initial multi-agent installer script (had incorrect paths for some agents)
- license changed from MIT to Apache 2.0
- initial README updates for multi-agent installation

## 0.2.0
- new `skillweave-promptchain` skill with direct `/skillweave-*` commands
- `/skillweave-promptchain-generate`, `-validate`, `-execute` commands
- improved README with new installation instructions
- updated multi-agent quickstart section

## 0.1.0
- initial repository structure
- first `prompt-chain` skill
- initial docs
- initial schemas
- initial parser, validator, orchestrator, executor
- first examples and templates
