# Changelog

## 0.3.0
- separate skill directories for each command: `skillweave-promptchain-generate`, `-validate`, `-execute`
- multi-agent installer script `scripts/install-skills.sh` with correct paths and formats for each agent type
- **Opencode support**: installs as single `.md` files to `~/.config/opencode/commands/`
- **Claude Code/Codex/Antigravity support**: installs as directory symlinks to correct paths
- license changed from MIT to Apache 2.0
- updated README with correct installation paths and formats
- improved badges and documentation

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
