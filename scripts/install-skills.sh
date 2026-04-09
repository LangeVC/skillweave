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
    "qwen"
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
    "directory" # qwen
)

AGENT_PATHS=(
    "$HOME/.config/opencode/commands"     # opencode
    "$HOME/.claude/skills"                # claude-code
    "$HOME/.codex/skills"                 # codex
    "$HOME/.gemini/skills"                # gemini-cli
    "$HOME/.antigravity/skills"           # antigravity
    "$HOME/.config/openclaw/skills"       # openclaw
    "$HOME/.config/aider/skills"          # aider
    "$HOME/.config/windsurf/skills"       # windsurf
    "$HOME/.qwen/skills"                  # qwen
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
    ""      # qwen
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

show_agent_status() {
    echo "SkillWeave Agent Detection"
    echo "=========================="
    echo "Available agents:"
    for i in "${!AGENT_NAMES[@]}"; do
        local agent="${AGENT_NAMES[$i]}"
        local path="${AGENT_PATHS[$i]}"
        if [ -d "$path" ] || [ -f "$path" ] || [ "$agent" = "opencode" ]; then
            echo "  ✓ $agent: $path (exists)"
        else
            echo "  ○ $agent: $path (not found)"
        fi
    done
    echo ""
}

# Check if an agent exists (directory exists or is opencode)
agent_exists() {
    local agent_name="$1"
    local agent_path=""
    
    for i in "${!AGENT_NAMES[@]}"; do
        if [ "${AGENT_NAMES[$i]}" = "$agent_name" ]; then
            agent_path="${AGENT_PATHS[$i]}"
            break
        fi
    done
    
    if [ -z "$agent_path" ]; then
        return 1  # Agent not in list
    fi
    
    if [ "$agent_name" = "opencode" ]; then
        return 0  # opencode is always considered existing (will be created)
    fi
    
    if [ -d "$agent_path" ] || [ -f "$agent_path" ]; then
        return 0
    else
        return 1
    fi
}

# Interactive selection of agents
interactive_select_agents() {
    # Output to stderr for user interaction
    echo "SkillWeave Interactive Installation" >&2
    echo "==================================" >&2
    echo "" >&2
    echo "Available agents:" >&2
    
    local agents=()
    local agent_paths=()
    local agent_status=()
    
    # Build arrays of agents with their status
    for i in "${!AGENT_NAMES[@]}"; do
        local agent="${AGENT_NAMES[$i]}"
        local path="${AGENT_PATHS[$i]}"
        
        if agent_exists "$agent"; then
            agents+=("$agent")
            agent_paths+=("$path")
            agent_status+=("exists")
            echo "  $(( ${#agents[@]} )). ✓ $agent: $path (exists)" >&2
        else
            agents+=("$agent")
            agent_paths+=("$path")
            agent_status+=("not found")
            echo "  $(( ${#agents[@]} )). ○ $agent: $path (not found)" >&2
        fi
    done
    
    echo "" >&2
    echo "Select agents to install (enter numbers separated by commas, 'all', or 'none'):" >&2
    echo -n "> " >&2
    
    local selection=""
    read selection
    
    case "$selection" in
        [Aa][Ll][Ll])
            # Install all existing agents
            local selected_agents=()
            for i in "${!agents[@]}"; do
                if [ "${agent_status[$i]}" = "exists" ]; then
                    selected_agents+=("${agents[$i]}")
                fi
            done
            echo "Selected: all existing agents (${#selected_agents[@]} agents)" >&2
            echo "${selected_agents[@]}"
            ;;
        [Nn][Oo][Nn][Ee])
            echo "No agents selected. Exiting." >&2
            exit 0
            ;;
        *)
            # Parse comma-separated numbers
            local selected_agents=()
            IFS=',' read -ra numbers <<< "$selection"
            for num in "${numbers[@]}"; do
                # Trim whitespace
                num=$(echo "$num" | tr -d '[:space:]')
                if [[ "$num" =~ ^[0-9]+$ ]]; then
                    local index=$((num - 1))
                    if [ $index -ge 0 ] && [ $index -lt ${#agents[@]} ]; then
                        if [ "${agent_status[$index]}" = "exists" ]; then
                            selected_agents+=("${agents[$index]}")
                        else
                            echo "Warning: Agent ${agents[$index]} not found. Skipping." >&2
                        fi
                    else
                        echo "Warning: Invalid number $num. Skipping." >&2
                    fi
                fi
            done
            if [ ${#selected_agents[@]} -eq 0 ]; then
                echo "No valid agents selected. Exiting." >&2
                exit 0
            fi
            echo "Selected: ${selected_agents[*]}" >&2
            echo "${selected_agents[@]}"
            ;;
    esac
}

# Uninstall skills from specific agents
uninstall_skills() {
    local agents=("$@")
    
    if [ ${#agents[@]} -eq 0 ]; then
        echo "No agents specified for uninstallation."
        return 1
    fi
    
    echo "Uninstalling SkillWeave skills from selected agents..."
    
    local total_removed=0
    local agents_processed=0
    
    for agent in "${agents[@]}"; do
        if ! agent_exists "$agent"; then
            echo "  ○ $agent: not found, skipping"
            continue
        fi
        
        # Get agent path
        local agent_path=""
        for i in "${!AGENT_NAMES[@]}"; do
            if [ "${AGENT_NAMES[$i]}" = "$agent" ]; then
                agent_path="${AGENT_PATHS[$i]}"
                break
            fi
        done
        
        if [ -z "$agent_path" ]; then
            echo "  ✗ $agent: unknown agent"
            continue
        fi
        
        echo "  Processing $agent..."
        local agent_removed=0
        
        for skill in "${SKILLS[@]}"; do
            local target=""
            if [ "$agent" = "opencode" ]; then
                target="$agent_path/$skill.md"
            else
                target="$agent_path/$skill"
            fi
            
            if [ -L "$target" ] || [ -f "$target" ] || [ -d "$target" ]; then
                echo "    Removing: $skill"
                if [ -z "$DRY_RUN" ]; then
                    rm -rf "$target"
                fi
                ((agent_removed++))
            fi
        done
        
        if [ $agent_removed -gt 0 ]; then
            echo "    ✓ Removed $agent_removed skills from $agent"
            ((total_removed+=agent_removed))
            ((agents_processed++))
        else
            echo "    ○ No skills found for $agent"
        fi
    done
    
    echo ""
    echo "Uninstallation complete"
    echo "Agents processed: $agents_processed"
    echo "Total skills removed: $total_removed"
}

# Update skills (recreate symlinks)
update_skills() {
    local agents=("$@")
    
    if [ ${#agents[@]} -eq 0 ]; then
        echo "No agents specified for update."
        return 1
    fi
    
    echo "Updating SkillWeave skills for selected agents..."
    
    local total_updated=0
    local agents_processed=0
    
    for agent in "${agents[@]}"; do
        if ! agent_exists "$agent"; then
            echo "  ○ $agent: not found, skipping"
            continue
        fi
        
        # Get agent path
        local agent_path=""
        for i in "${!AGENT_NAMES[@]}"; do
            if [ "${AGENT_NAMES[$i]}" = "$agent" ]; then
                agent_path="${AGENT_PATHS[$i]}"
                break
            fi
        done
        
        if [ -z "$agent_path" ]; then
            echo "  ✗ $agent: unknown agent, skipping"
            continue
        fi
        
        echo "  Processing $agent..."
        local agent_updated=0
        
        # Remove old symlinks and create new ones
        for skill in "${SKILLS[@]}"; do
            local source_dir="$SKILLS_DIR/$skill"
            local target=""
            
            if [ "$agent" = "opencode" ]; then
                target="$agent_path/$skill.md"
                source_file="$source_dir/SKILL.md"
                
                if [ ! -f "$source_file" ]; then
                    continue
                fi
                
                # Remove existing
                if [ -L "$target" ] || [ -f "$target" ]; then
                    if [ -z "$DRY_RUN" ]; then
                        rm -f "$target"
                    fi
                fi
                
                # Create symlink
                if [ -z "$DRY_RUN" ]; then
                    ln -sf "$source_file" "$target"
                fi
            else
                target="$agent_path/$skill"
                
                if [ ! -d "$source_dir" ]; then
                    continue
                fi
                
                # Remove existing
                if [ -L "$target" ] || [ -d "$target" ]; then
                    if [ -z "$DRY_RUN" ]; then
                        rm -rf "$target"
                    fi
                fi
                
                # Create symlink
                if [ -z "$DRY_RUN" ]; then
                    ln -sf "$source_dir" "$target"
                fi
            fi
            
            ((agent_updated++))
        done
        
        if [ $agent_updated -gt 0 ]; then
            echo "    ✓ Updated $agent_updated skills for $agent"
            ((total_updated+=agent_updated))
            ((agents_processed++))
        else
            echo "    ○ No skills updated for $agent"
        fi
    done
    
    echo ""
    echo "Update complete"
    echo "Agents processed: $agents_processed"
    echo "Total skills updated: $total_updated"
}

# Troubleshoot skills
troubleshoot_skills() {
    echo "SkillWeave Troubleshooting"
    echo "=========================="
    echo ""
    
    local issues_found=0
    
    # Check SkillWeave directory
    echo "1. Checking SkillWeave directory..."
    if [ ! -d "$SKILLS_DIR" ]; then
        echo "   ✗ Skills directory not found: $SKILLS_DIR"
        ((issues_found++))
    else
        echo "   ✓ Skills directory exists"
        
        # Check each skill
        for skill in "${SKILLS[@]}"; do
            local skill_dir="$SKILLS_DIR/$skill"
            if [ ! -d "$skill_dir" ]; then
                echo "   ✗ Skill directory not found: $skill"
                ((issues_found++))
            else
                if [ ! -f "$skill_dir/SKILL.md" ]; then
                    echo "   ⚠ Skill missing SKILL.md: $skill"
                    ((issues_found++))
                fi
            fi
        done
    fi
    
    # Check agent directories
    echo ""
    echo "2. Checking agent directories..."
    for i in "${!AGENT_NAMES[@]}"; do
        local agent="${AGENT_NAMES[$i]}"
        local path="${AGENT_PATHS[$i]}"
        
        if [ -d "$path" ] || [ -f "$path" ]; then
            echo "   ✓ $agent: directory exists"
            
            # Check symlinks
            for skill in "${SKILLS[@]}"; do
                local target=""
                if [ "$agent" = "opencode" ]; then
                    target="$path/$skill.md"
                else
                    target="$path/$skill"
                fi
                
                if [ -L "$target" ]; then
                    if [ -e "$target" ]; then
                        echo "     ✓ $skill: symlink OK"
                    else
                        echo "     ✗ $skill: broken symlink"
                        ((issues_found++))
                    fi
                elif [ -f "$target" ] || [ -d "$target" ]; then
                    echo "     ⚠ $skill: not a symlink (manual file/dir)"
                    ((issues_found++))
                fi
            done
        else
            echo "   ○ $agent: directory not found (not installed)"
        fi
    done
    
    echo ""
    echo "Troubleshooting complete"
    if [ $issues_found -eq 0 ]; then
        echo "✓ No issues found"
    else
        echo "⚠ Found $issues_found potential issues"
    fi
}

# Install skills for specific agents
install_for_agents() {
    local agents=("$@")
    
    if [ ${#agents[@]} -eq 0 ]; then
        echo "No agents specified for installation."
        return 1
    fi
    
    echo "Installing SkillWeave skills for selected agents..."
    
    local total_installed=0
    local agents_processed=0
    
    for agent in "${agents[@]}"; do
        if ! agent_exists "$agent"; then
            echo "  ○ $agent: not found, skipping"
            continue
        fi
        
        local installed_count=$(install_for_agent "$agent" || echo 0)
        installed_count=${installed_count:-0}
        
        if (( installed_count > 0 )); then
            echo "  ✓ $agent: $installed_count skills installed"
            ((total_installed+=installed_count))
            ((agents_processed++))
        else
            echo "  ○ $agent: no skills installed (directory may not exist)"
        fi
    done
    
    echo ""
    echo "Installation complete"
    echo "Agents processed: $agents_processed"
    echo "Total skills installed: $total_installed"
}

main() {
    # Parse arguments
    for arg in "$@"; do
        case "$arg" in
            --dry-run)
                DRY_RUN=1
                log "DRY RUN MODE ENABLED - no changes will be made"
                ;;
            --list)
                show_agent_status
                exit 0
                ;;
            --interactive|-i)
                MODE="interactive"
                ;;
            --uninstall)
                MODE="uninstall"
                ;;
            --update)
                MODE="update"
                ;;
            --troubleshoot)
                MODE="troubleshoot"
                ;;
            *)
                log "Unknown argument: $arg"
                ;;
        esac
    done
    
    # Set default mode if not specified
    MODE=${MODE:-auto}
    
    log "Starting SkillWeave multi-agent skill installation"
    [ -n "$DRY_RUN" ] && log "DRY RUN MODE - simulating installation only"
    log "SkillWeave directory: $SKILLWEAVE_DIR"
    log "Skills available: ${SKILLS[*]}"
    log ""
    
    case "$MODE" in
        interactive)
            show_agent_status
            local selected_agents
            selected_agents=$(interactive_select_agents)
            if [ $? -eq 0 ] && [ -n "$selected_agents" ]; then
                # Convert string to array
                IFS=' ' read -ra agents_array <<< "$selected_agents"
                install_for_agents "${agents_array[@]}"
            fi
            ;;
        uninstall)
            show_agent_status
            echo ""
            echo "Select agents to uninstall from:"
            local selected_agents
            selected_agents=$(interactive_select_agents)
            if [ $? -eq 0 ] && [ -n "$selected_agents" ]; then
                IFS=' ' read -ra agents_array <<< "$selected_agents"
                uninstall_skills "${agents_array[@]}"
            fi
            ;;
        update)
            show_agent_status
            echo ""
            echo "Select agents to update:"
            local selected_agents
            selected_agents=$(interactive_select_agents)
            if [ $? -eq 0 ] && [ -n "$selected_agents" ]; then
                IFS=' ' read -ra agents_array <<< "$selected_agents"
                update_skills "${agents_array[@]}"
            fi
            ;;
        troubleshoot)
            troubleshoot_skills
            ;;
        auto|*)
            # Auto mode: install for all existing agents
            show_agent_status
            
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
            ;;
    esac
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