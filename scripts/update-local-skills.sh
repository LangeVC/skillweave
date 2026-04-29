#!/bin/bash

# Refresh a local SkillWeave development install with Capacium as the source of truth.

set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_DIR="$HOME/.skillweave"
INSTALLER="$SOURCE_DIR/scripts/install-skills.sh"

echo "SkillWeave Local Skills Update"
echo "=============================="
echo ""
echo "Source (development repo): $SOURCE_DIR"
echo "Local config dir:          $TARGET_DIR"
echo ""

if [ ! -x "$INSTALLER" ]; then
    echo "Installer not found: $INSTALLER" >&2
    exit 1
fi

if [ -d "$SOURCE_DIR/.git" ]; then
    echo "✓ Source is a git repository"
    echo "  Current branch: $(cd "$SOURCE_DIR" && git branch --show-current)"
    echo "  Latest commit:  $(cd "$SOURCE_DIR" && git log -1 --oneline)"
else
    echo "⚠ Source is not a git repository"
fi

mkdir -p "$TARGET_DIR/scripts"
cp "$INSTALLER" "$TARGET_DIR/scripts/install-skills.sh"
chmod +x "$TARGET_DIR/scripts/install-skills.sh"

echo ""
echo "Capacium-backed refresh is ready."
echo ""
echo "Next steps:"
echo "1. Refresh the local bundle and compatibility bridges:"
echo "   $SOURCE_DIR/scripts/install-skills.sh --update"
echo ""
echo "2. Or run the cached wrapper from ~/.skillweave:"
echo "   $TARGET_DIR/scripts/install-skills.sh --update"
echo ""
echo "Options:"
echo "  --dry-run        Preview changes without making them"
echo "  --interactive    Choose bridge agents after Capacium install"
echo "  --uninstall      Remove the bundle and compatibility links"
echo "  --troubleshoot   Diagnose installation issues"
echo ""

read -p "Run installer now? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Starting installer..."
    echo ""
    "$INSTALLER" --update
fi
