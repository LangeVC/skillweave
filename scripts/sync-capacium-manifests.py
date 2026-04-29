#!/usr/bin/env python3
"""Sync or check Capacium capability manifests for SkillWeave."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from skillweave.github_integration.capability_sync import main


if __name__ == "__main__":
    raise SystemExit(main())
