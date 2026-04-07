# Changelog

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
