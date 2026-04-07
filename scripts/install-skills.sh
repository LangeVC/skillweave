#!/bin/bash

# SkillWeave Multi-Agent Skill Installer
# Installs SkillWeave skills to all detected AI agent skill directories

set -e

SKILLWEAVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$SKILLWEAVE_DIR/skills"
INSTALL_LOG="$SKILLWEAVE_DIR/install.log"

# Agent configuration - type, path, and installation method
declare -A AGENTS=(
    # Opencode: single .md files in commands directory
    ["opencode"]="type:single;path:$HOME/.config/opencode/commands;ext:.md"
    
    # Claude Code: directory structure in skills directory
    ["claude-code"]="type:directory;path:$HOME/.claude/skills;ext:"
    
    # Codex: directory structure in skills directory  
    ["codex"]="type:directory;path:$HOME/.codex/skills;ext:"
    
    # Gemini CLI: directory structure in skills directory
    ["gemini-cli"]="type:directory;path:$HOME/.config/gemini-cli/skills;ext:"
    
    # Antigravity: directory structure in skills directory
    ["antigravity"]="type:directory;path:$HOME/.antigravity/skills;ext:"
    
    # OpenClaw: directory structure in skills directory
    ["openclaw"]="type:directory;path:$HOME/.config/openclaw/skills;ext:"
    
    # Aider: directory structure in skills directory
    ["aider"]="type:directory;path:$HOME/.config/aider/skills;ext:"
    
    # WindSurf: directory structure in skills directory
    ["windsurf"]="type:directory;path:$HOME/.config/windsurf/skills;ext:"
)

# SkillWeave skills to install
declare -a SKILLS=(
    "skillweave-promptchain-generate"
    "skillweave-promptchain-validate"
    "skillweave-promptchain-execute"
    "skillweave-releasechain"
    "prompt-chain"  # Legacy skill for compatibility
)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$INSTALL_LOG"
}

parse_agent_config() {
    local agent="$1"
    local config="${AGENTS[$agent]}"
    
    # Parse type:directory or type:single
    local agent_type=$(echo "$config" | grep -oP 'type:\K[^;]+')
    local agent_path=$(echo "$config" | grep -oP 'path:\K[^;]+')
    local agent_ext=$(echo "$config" | grep -oP 'ext:\K[^;]*')
    
    echo "$agent_type|$agent_path|$agent_ext"
}

install_single_file() {
    local skill="$1"
    local agent_path="$2"
    local extension="$3"
    
    local source_file="$SKILLS_DIR/$skill/SKILL.md"
    local target_file="$agent_path/$skill$extension"
    
    if [ ! -f "$source_file" ]; then
        log "  ERROR: Source skill file not found: $source_file"
        return 1
    fi
    
    # Create target directory if it doesn't exist
    mkdir -p "$agent_path"
    
    if [ -L "$target_file" ] || [ -f "$target_file" ]; then
        log "  Updating file: $skill$extension"
        rm -f "$target_file"
    fi
    
    # Create symlink to the source file
    ln -sf "$source_file" "$target_file"
    log "  ✓ Installed as single file: $skill$extension"
}

install_directory() {
    local skill="$1"
    local agent_path="$2"
    
    local source_dir="$SKILLS_DIR/$skill"
    local target_dir="$agent_path/$skill"
    
    if [ ! -d "$source_dir" ]; then
        log "  ERROR: Source skill directory not found: $skill"
        return 1
    fi
    
    # Create target directory if it doesn't exist
    mkdir -p "$agent_path"
    
    if [ -L "$target_dir" ]; then
        log "  Updating symlink: $skill"
        rm "$target_dir"
    elif [ -d "$target_dir" ]; then
        log "  Updating directory: $skill"
        rm -rf "$target_dir"
    fi
    
    # Create symlink to the source directory
    ln -sf "$source_dir" "$target_dir"
    log "  ✓ Installed as directory: $skill"
}

install_for_agent() {
    local agent="$1"
    local config="$2"
    
    IFS='|' read -r agent_type agent_path extension <<< "$config"
    
    if [ ! -d "$agent_path" ] && [ "$agent" != "opencode" ]; then
        # Only log missing directories for non-opencode agents
        # Opencode commands directory might not exist yet
        return 0
    fi
    
    log "Processing agent: $agent ($agent_type)"
    log "  Path: $agent_path"
    
    # Create agent directory if it doesn't exist
    mkdir -p "$agent_path"
    
    local agent_install_count=0
    
    for skill in "${SKILLS[@]}"; do
        if [ "$agent_type" = "single" ]; then
            if install_single_file "$skill" "$agent_path" "$extension"; then
                ((agent_install_count++))
            fi
        elif [ "$agent_type" = "directory" ]; then
            if install_directory "$skill" "$agent_path"; then
                ((agent_install_count++))
            fi
        else
            log "  ERROR: Unknown agent type: $agent_type"
            return 1
        fi
    done
    
    log "  Installed $agent_install_count skills for $agent"
    echo $agent_install_count
}

main() {
    log "Starting SkillWeave multi-agent skill installation"
    log "SkillWeave directory: $SKILLWEAVE_DIR"
    log "Skills available: ${SKILLS[*]}"
    log ""
    
    local total_installed=0
    local agents_processed=0
    
    echo "Detecting and installing for agents:"
    echo "-----------------------------------"
    
    for agent in "${!AGENTS[@]}"; do
        local config=$(parse_agent_config "$agent")
        local installed_count=$(install_for_agent "$agent" "$config" 2>/dev/null || echo 0)
        
        if [ "$installed_count" -gt 0 ]; then
            echo "  ✓ $agent: $installed_count skills installed"
            ((total_installed+=installed_count))
            ((agents_processed++))
        fi
    done
    
    log ""
    log "Installation complete"
    log "Processed $agents_processed agents"
    log "Installed $total_installed skill instances total"
    
    # If no agents were found, create and install to opencode as default
    if [ "$agents_processed" -eq 0 ]; then
        log "WARNING: No agent directories found. Installing to opencode as default."
        
        local opencode_config=$(parse_agent_config "opencode")
        local installed_count=$(install_for_agent "opencode" "$opencode_config")
        
        if [ "$installed_count" -gt 0 ]; then
            echo "  ✓ opencode (default): $installed_count skills installed"
            ((total_installed+=installed_count))
            ((agents_processed++))
        fi
        
        log "Created default opencode installation"
    fi
    
    # Display installation summary
    echo ""
    echo "========================================="
    echo "SkillWeave Installation Summary"
    echo "========================================="
    echo "Agents processed: $agents_processed"
    echo "Total skill instances: $total_installed"
    echo ""
    echo "Installed skills:"
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
    echo ""
    echo "For manual installation or troubleshooting, see README.md"
    echo "========================================="
}

# Run main function
main "$@"