#!/bin/bash

# SkillWeave installer entrypoint.
# The Python installer is the single source of truth; this shell wrapper keeps
# the historical script interface stable.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CAP_BUNDLE_ROOT="$HOME/.capacium/packages/global/skillweave"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "SkillWeave installer requires python3 (or python)." >&2
    exit 1
fi

has_source_arg() {
    for arg in "$@"; do
        if [ "$arg" = "--source" ]; then
            return 0
        fi
    done
    return 1
}

resolve_skillweave_root() {
    if [ -f "$SOURCE_DIR/capability.yaml" ] && [ -f "$SOURCE_DIR/src/skillweave/installer.py" ]; then
        echo "$SOURCE_DIR"
        return 0
    fi

    if [ -d "$CAP_BUNDLE_ROOT" ]; then
        "$PYTHON_BIN" - "$CAP_BUNDLE_ROOT" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1]).expanduser()
versions = [path for path in root.iterdir() if path.is_dir()]
if not versions:
    raise SystemExit(1)

def version_key(path: Path):
    parts = []
    for piece in path.name.split("."):
        if piece.isdigit():
            parts.append(int(piece))
        else:
            parts.append(piece)
    return tuple(parts)

latest = max(versions, key=version_key)
print(str(latest))
PY
        return 0
    fi

    echo "Could not locate a SkillWeave source root. Run from the repository root or install the bundle with Capacium first." >&2
    return 1
}

ROOT="$(resolve_skillweave_root)"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

ARGS=("$@")
if ! has_source_arg "$@"; then
    ARGS=(--source "$ROOT" "${ARGS[@]}")
fi

exec "$PYTHON_BIN" -m skillweave.installer "${ARGS[@]}"
