#!/bin/bash

# SkillWeave Local Skills Update Script
# For developers who maintain a local fork/repo and want to update the installation

set -e

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="$HOME/.skillweave"

echo "SkillWeave Local Skills Update"
echo "=============================="
echo ""
echo "Source (development repo): $SOURCE_DIR"
echo "Target (installation dir): $TARGET_DIR"
echo ""

# Check if source has git
if [ -d "$SOURCE_DIR/.git" ]; then
    echo "✓ Source is a git repository"
    echo "  Current branch: $(cd "$SOURCE_DIR" && git branch --show-current)"
    echo "  Latest commit:  $(cd "$SOURCE_DIR" && git log -1 --oneline)"
else
    echo "⚠ Source is not a git repository"
fi

# Check target directory
if [ -d "$TARGET_DIR/.git" ]; then
    echo "⚠ WARNING: Target directory appears to be a git repository!"
    echo "  This is not recommended. Target should be a plain directory."
    echo "  Consider: rm -rf $TARGET_DIR/.git"
    read -p "  Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Update cancelled."
        exit 1
    fi
fi

echo ""
echo "Updating skills from source to target..."
echo ""

# Create target directories
mkdir -p "$TARGET_DIR/skills"
mkdir -p "$TARGET_DIR/scripts"

# Copy skills
echo "Copying skills directory..."
rm -rf "$TARGET_DIR/skills"/*
cp -r "$SOURCE_DIR/skills"/* "$TARGET_DIR/skills/"
echo "  ✓ Copied $(find "$SOURCE_DIR/skills" -type d | wc -l | tr -d ' ') skill directories"

# Copy installer
echo "Copying installer script..."
cp "$SOURCE_DIR/scripts/install-skills.sh" "$TARGET_DIR/scripts/"
chmod +x "$TARGET_DIR/scripts/install-skills.sh"
echo "  ✓ Copied installer script"

# Copy .gitignore if it exists
if [ -f "$SOURCE_DIR/.gitignore" ]; then
    cp "$SOURCE_DIR/.gitignore" "$TARGET_DIR/"
    echo "  ✓ Copied .gitignore"
fi

echo ""
echo "Update complete!"
echo ""
echo "Next steps:"
echo "1. Run the installer to update agent skills:"
echo "   $TARGET_DIR/scripts/install-skills.sh --interactive"
echo ""
echo "2. Or use the installer from the source directory:"
echo "   $SOURCE_DIR/scripts/install-skills.sh --interactive"
echo ""
echo "Options:"
echo "  --dry-run        Preview changes without making them"
echo "  --interactive    Interactive agent selection"
echo "  --update         Update existing installations"
echo "  --troubleshoot   Diagnose installation issues"
echo ""

# Offer to run installer
read -p "Run installer now? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Starting installer..."
    echo ""
    "$TARGET_DIR/scripts/install-skills.sh" --interactive
fi