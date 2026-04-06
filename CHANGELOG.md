# Changelog

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
