#!/bin/bash

# SkillWeave Multi-Agent Skill Installer
# Installs SkillWeave skills to all detected AI agent skill directories

set -e

SKILLWEAVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$SKILLWEAVE_DIR/skills"
INSTALL_LOG="$SKILLWEAVE_DIR/install.log"

# Common agent skill directories
declare -a AGENT_DIRS=(
    "$HOME/.config/opencode/skills"
    "$HOME/.config/claude-code/skills"
    "$HOME/.config/codex/skills"
    "$HOME/.config/gemini-cli/skills"
    "$HOME/.config/antigravity/skills"
    "$HOME/.config/openclaw/skills"
    "$HOME/.config/agent/skills"
    "$HOME/.config/aider/skills"
    "$HOME/.config/windsurf/skills"
    "$HOME/.config/cursor/skills"
    "$HOME/.config/zed/skills"
    "$HOME/.config/vscode/skills"
    "$HOME/.config/copilot/skills"
)

# SkillWeave skills to install
declare -a SKILLS=(
    "skillweave-promptchain-generate"
    "skillweave-promptchain-validate"
    "skillweave-promptchain-execute"
    "prompt-chain"  # Legacy skill for compatibility
)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$INSTALL_LOG"
}

install_skill() {
    local skill="$1"
    local source_dir="$SKILLS_DIR/$skill"
    local target_dir="$2/$skill"
    
    if [ ! -d "$source_dir" ]; then
        log "ERROR: Source skill directory not found: $skill"
        return 1
    fi
    
    if [ -L "$target_dir" ]; then
        log "  Updating symlink: $skill"
        rm "$target_dir"
    elif [ -d "$target_dir" ]; then
        log "  Updating directory: $skill"
        rm -rf "$target_dir"
    fi
    
    # Create symlink for easy updates
    ln -sf "$source_dir" "$target_dir"
    log "  ✓ Installed: $skill"
}

main() {
    log "Starting SkillWeave multi-agent skill installation"
    log "SkillWeave directory: $SKILLWEAVE_DIR"
    log "Skills available: ${SKILLS[*]}"
    
    local installed_count=0
    local agent_count=0
    
    for agent_dir in "${AGENT_DIRS[@]}"; do
        if [ -d "$agent_dir" ]; then
            ((agent_count++))
            log "Found agent directory: $agent_dir"
            
            # Create skills directory if it doesn't exist
            mkdir -p "$agent_dir"
            
            # Install all skills
            for skill in "${SKILLS[@]}"; do
                if install_skill "$skill" "$agent_dir"; then
                    ((installed_count++))
                fi
            done
        fi
    done
    
    log "Installation complete"
    log "Found $agent_count agent directories"
    log "Installed $installed_count skill instances"
    
    if [ $agent_count -eq 0 ]; then
        log "WARNING: No agent directories found. Creating default directory: $HOME/.config/opencode/skills"
        mkdir -p "$HOME/.config/opencode/skills"
        
        for skill in "${SKILLS[@]}"; do
            if install_skill "$skill" "$HOME/.config/opencode/skills"; then
                ((installed_count++))
            fi
        done
        
        log "Created default directory and installed skills"
    fi
    
    # Display installation summary
    echo ""
    echo "========================================="
    echo "SkillWeave Installation Summary"
    echo "========================================="
    echo "Skills installed:"
    for skill in "${SKILLS[@]}"; do
        echo "  - $skill"
    done
    echo ""
    echo "Usage examples:"
    echo "  /skillweave-promptchain-generate topic=\"Business analysis\" domain=\"strategy\""
    echo "  /skillweave-promptchain-validate sequence=\"[prompt sequence]\""
    echo "  /skillweave-promptchain-execute sequence=\"[sequence]\" inputs='{\"key\": \"value\"}'"
    echo ""
    echo "Note: Restart your agent tool to detect new skills"
    echo "========================================="
}

# Run main function
main "$@"