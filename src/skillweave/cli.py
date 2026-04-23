#!/usr/bin/env python3
"""
Command-line interface utilities for SkillWeave.
"""

import argparse
from typing import Optional
from .risk_mode_resolver import RiskModeResolver, RiskMode, get_effective_risk_mode


def add_risk_mode_argument(parser: argparse.ArgumentParser) -> None:
    """
    Add --risk-mode argument to an argparse parser.
    
    Args:
        parser: argparse.ArgumentParser instance
    """
    parser.add_argument(
        '--risk-mode',
        choices=['conservative', 'medium', 'unicorn'],
        help='Risk mode override (conservative, medium, unicorn). '
             'Overrides environment variable and config files.'
    )


def resolve_risk_mode_from_args(args, project_root: Optional[str] = None, include_global_config: bool = True) -> RiskMode:
    """
    Resolve effective risk mode from argparse namespace.
    
    Args:
        args: argparse.Namespace with optional risk_mode attribute
        project_root: Optional project root directory
        include_global_config: Whether to include global user configuration
        
    Returns:
        Effective RiskMode enum value
    """
    cli_override = getattr(args, 'risk_mode', None)
    return get_effective_risk_mode(
        project_root=project_root,
        cli_override=cli_override,
        env_override=None,  # Will be read from environment variable automatically
        interactive=False,
        include_global_config=include_global_config
    )


def parse_skill_arguments(arg_string: str) -> dict:
    """
    Parse key=value arguments from opencode skill invocation.
    
    This is a helper for skills that receive parameters as a string
    like 'sequence="..." inputs="..."'. Not all skills use this format.
    
    Args:
        arg_string: Raw argument string from skill invocation
        
    Returns:
        Dictionary of parsed parameters
    """
    # Simple parsing: split by spaces but respect quoted values
    # This is a naive implementation; opencode handles parsing internally.
    # Skills receive parameters as pre-parsed dictionary.
    # This function is kept for backward compatibility.
    import shlex
    try:
        parts = shlex.split(arg_string)
        params = {}
        for part in parts:
            if '=' in part:
                key, value = part.split('=', 1)
                params[key] = value.strip('"\'')
        return params
    except:
        return {}


def resolve_risk_mode_from_skill_args(skill_args: dict, project_root: Optional[str] = None, include_global_config: bool = True) -> RiskMode:
    """
    Resolve effective risk mode from skill arguments dictionary.
    
    Args:
        skill_args: Dictionary of skill arguments (e.g., from parse_skill_arguments)
        project_root: Optional project root directory
        include_global_config: Whether to include global user configuration
        
    Returns:
        Effective RiskMode enum value
    """
    cli_override = skill_args.get('risk_mode')
    return get_effective_risk_mode(
        project_root=project_root,
        cli_override=cli_override,
        env_override=None,
        interactive=False,
        include_global_config=include_global_config
    )


def main():
    """Test CLI utilities."""
    parser = argparse.ArgumentParser(description='Test risk mode resolution')
    add_risk_mode_argument(parser)
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()
    
    risk_mode = resolve_risk_mode_from_args(args)
    print(f'Effective risk mode: {risk_mode.value}')
    if args.verbose:
        resolver = RiskModeResolver()
        env_value = resolver._get_env_override()
        print(f'CLI argument: {args.risk_mode}')
        print(f'Environment variable: {env_value}')
        # Show config paths
        import os
        project_config_path = os.path.join(os.getcwd(), '.skillweave/config.yaml')
        global_config_path = os.path.expanduser('~/.skillweave/config.yaml')
        print(f'Project config path: {project_config_path}')
        print(f'Global config path: {global_config_path}')


if __name__ == '__main__':
    main()