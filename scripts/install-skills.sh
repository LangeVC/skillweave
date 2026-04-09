#!/bin/bash

# SkillWeave Multi-Agent Skill Installer
# Installs SkillWeave skills to all detected AI agent skill directories
# Compatible with Bash 3.x and later

set +e

SKILLWEAVE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$SKILLWEAVE_DIR/skills"
INSTALL_LOG="$SKILLWEAVE_DIR/install.log"

# Agent configuration arrays (Bash 3.x compatible)
# Using parallel arrays instead of associative arrays for compatibility
AGENT_NAMES=(
    "opencode"
    "claude-code"
    "codex"
    "gemini-cli"
    "antigravity"
    "openclaw"
    "aider"
    "windsurf"
)

AGENT_TYPES=(
    "single"    # opencode
    "directory" # claude-code
    "directory" # codex
    "directory" # gemini-cli
    "directory" # antigravity
    "directory" # openclaw
    "directory" # aider
    "directory" # windsurf
)

AGENT_PATHS=(
    "$HOME/.config/opencode/commands"     # opencode
    "$HOME/.claude/skills"                # claude-code
    "$HOME/.codex/skills"                 # codex
    "$HOME/.config/gemini-cli/skills"     # gemini-cli
    "$HOME/.antigravity/skills"           # antigravity
    "$HOME/.config/openclaw/skills"       # openclaw
    "$HOME/.config/aider/skills"          # aider
    "$HOME/.config/windsurf/skills"       # windsurf
)

AGENT_EXTS=(
    ".md"   # opencode
    ""      # claude-code
    ""      # codex
    ""      # gemini-cli
    ""      # antigravity
    ""      # openclaw
    ""      # aider
    ""      # windsurf
)

# SkillWeave skills to install
SKILLS=(
    "skillweave-promptchain-generate"
    "skillweave-promptchain-validate"
    "skillweave-promptchain-execute"
    "skillweave-releasechain"
    "prompt-chain"  # Legacy skill for compatibility
)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$INSTALL_LOG" >&2 || true
}

get_agent_config() {
    local agent_name="$1"
    local agent_type=""
    local agent_path=""
    local agent_ext=""
    
    # Find the agent in AGENT_NAMES array
    for i in "${!AGENT_NAMES[@]}"; do
        if [ "${AGENT_NAMES[$i]}" = "$agent_name" ]; then
            agent_type="${AGENT_TYPES[$i]}"
            agent_path="${AGENT_PATHS[$i]}"
            agent_ext="${AGENT_EXTS[$i]}"
            break
        fi
    done
    
    if [ -z "$agent_type" ]; then
        echo ""
        return 1
    fi
    
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
    [ -z "$DRY_RUN" ] && mkdir -p "$agent_path"
    
    if [ -L "$target_file" ] || [ -f "$target_file" ]; then
        log "  Updating file: $skill$extension"
        [ -z "$DRY_RUN" ] && rm -f "$target_file"
    fi
    
    # Create symlink to the source file
    if [ -z "$DRY_RUN" ]; then
        ln -sf "$source_file" "$target_file"
        log "  ✓ Installed as single file: $skill$extension"
    else
        log "  ✓ Would install as single file: $skill$extension"
    fi
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
    [ -z "$DRY_RUN" ] && mkdir -p "$agent_path"
    
    if [ -L "$target_dir" ]; then
        log "  Updating symlink: $skill"
        [ -z "$DRY_RUN" ] && rm "$target_dir"
    elif [ -d "$target_dir" ]; then
        log "  Updating directory: $skill"
        [ -z "$DRY_RUN" ] && rm -rf "$target_dir"
    fi
    
    # Create symlink to the source directory
    if [ -z "$DRY_RUN" ]; then
        ln -sf "$source_dir" "$target_dir"
        log "  ✓ Installed as directory: $skill"
    else
        log "  ✓ Would install as directory: $skill"
    fi
}

install_for_agent() {
    local agent_name="$1"
    local agent_type=""
    local agent_path=""
    local agent_ext=""
    
    # Get agent configuration
    for i in "${!AGENT_NAMES[@]}"; do
        if [ "${AGENT_NAMES[$i]}" = "$agent_name" ]; then
            agent_type="${AGENT_TYPES[$i]}"
            agent_path="${AGENT_PATHS[$i]}"
            agent_ext="${AGENT_EXTS[$i]}"
            break
        fi
    done
    
    if [ -z "$agent_type" ]; then
        log "  ERROR: Unknown agent: $agent_name"
        return 1
    fi
    
    # Only check for existing directory for non-opencode agents
    if [ ! -d "$agent_path" ] && [ "$agent_name" != "opencode" ]; then
        # Directory doesn't exist and it's not opencode (which we'll create)
        echo 0
        return 0
    fi
    
    log "Processing agent: $agent_name ($agent_type)"
    log "  Path: $agent_path"
    
    # Create agent directory if it doesn't exist
    [ -z "$DRY_RUN" ] && mkdir -p "$agent_path"
    
    local agent_install_count=0
    
    for skill in "${SKILLS[@]}"; do
        if [ "$agent_type" = "single" ]; then
            if install_single_file "$skill" "$agent_path" "$agent_ext"; then
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
    
    log "  Installed $agent_install_count skills for $agent_name"
    echo $agent_install_count
}

main() {
    # Parse arguments
    for arg in "$@"; do
        case "$arg" in
            --dry-run)
                DRY_RUN=1
                log "DRY RUN MODE ENABLED - no changes will be made"
                ;;
            *)
                log "Unknown argument: $arg"
                ;;
        esac
    done
    
    log "Starting SkillWeave multi-agent skill installation"
    [ -n "$DRY_RUN" ] && log "DRY RUN MODE - simulating installation only"
    log "SkillWeave directory: $SKILLWEAVE_DIR"
    log "Skills available: ${SKILLS[*]}"
    log ""
    
    local total_installed=0
    local agents_processed=0
    
    echo "Detecting and installing for agents:"
    echo "-----------------------------------"
    
    for i in "${!AGENT_NAMES[@]}"; do
        local agent="${AGENT_NAMES[$i]}"
        local installed_count=$(install_for_agent "$agent" || echo 0)
        installed_count=${installed_count:-0}
        
        if (( installed_count > 0 )); then
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
        
        local installed_count=$(install_for_agent "opencode")
        installed_count=${installed_count:-0}
        
        if (( installed_count > 0 )); then
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