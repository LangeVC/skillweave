#!/usr/bin/env python3
"""
Script to resolve effective risk mode using hierarchical override system.
Prints the effective risk mode to stdout for use in shell scripts or AI agents.
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from skillweave.risk_mode_resolver import RiskModeResolver

def main():
    """Parse command line arguments and print effective risk mode."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Resolve effective SkillWeave risk mode using hierarchical overrides"
    )
    parser.add_argument(
        "--cli-risk-mode",
        choices=["conservative", "medium", "unicorn"],
        help="Risk mode from CLI parameter (highest precedence)"
    )
    parser.add_argument(
        "--env-var",
        default=os.environ.get("SKILLWEAVE_RISK_MODE"),
        help="Environment variable value (optional, defaults to SKILLWEAVE_RISK_MODE)"
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Project root directory for .skillweave/config.yaml (default: current directory)"
    )
    parser.add_argument(
        "--no-global-config",
        dest="include_global_config",
        action="store_false",
        default=True,
        help="Exclude global config from ~/.skillweave/config.yaml"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print precedence resolution steps"
    )
    
    args = parser.parse_args()
    
    resolver = RiskModeResolver(
        project_root=args.project_root
    )
    
    effective_mode = resolver.resolve(
        cli_override=args.cli_risk_mode,
        env_override=args.env_var,
        include_global_config=args.include_global_config
    )
    
    if args.verbose:
        print(f"CLI risk mode: {args.cli_risk_mode}")
        print(f"Environment variable: {args.env_var}")
        print(f"Project config path: {args.project_root / '.skillweave/config.yaml'}")
        if args.include_global_config:
            print(f"Global config path: {Path.home() / '.skillweave/config.yaml'} (included)")
        else:
            print(f"Global config path: {Path.home() / '.skillweave/config.yaml'} (excluded)")
        print(f"Default: medium")
        print(f"Effective risk mode: {effective_mode}")
    else:
        print(effective_mode)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())