"""CLI entry point for ``skillweave hooks`` commands.

Subcommands:
  list      — Show all bindings (explicit + auto-discovered)
  bind      — Create an explicit binding YAML
  unbind    — Remove a binding
  test      — Dry-run all hooks for a phase/position
  discover  — Scan and show discoverable trigger bindings
  help      — Show help text

Usage::

    python -m skillweave.studio.cli hooks list
    python -m skillweave.studio.cli hooks list --phase build
    python -m skillweave.studio.cli hooks bind ci-gate test post
    python -m skillweave.studio.cli hooks unbind ci-gate test
    python -m skillweave.studio.cli hooks test build pre
    python -m skillweave.studio.cli hooks discover
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

import yaml


def hooks_main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the hooks CLI."""
    parser = argparse.ArgumentParser(
        prog="skillweave hooks",
        description="SkillWeave Studio hook management",
    )
    subparsers = parser.add_subparsers(dest="command", help="Hook commands")

    # list
    list_parser = subparsers.add_parser("list", help="Show all hook bindings")
    list_parser.add_argument("--phase", help="Filter by phase")
    list_parser.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON")

    # bind
    bind_parser = subparsers.add_parser("bind", help="Create an explicit binding")
    bind_parser.add_argument("capability", help="Capability or hook name")
    bind_parser.add_argument("phase", help="Lifecycle phase")
    bind_parser.add_argument("position", help="pre or post")
    bind_parser.add_argument("--type", default="capacium", help="Hook type (default: capacium)")
    bind_parser.add_argument("--priority", type=int, default=500, help="Priority (default: 500)")
    bind_parser.add_argument("--failure-mode", default="block", help="Failure mode (default: block)")

    # unbind
    unbind_parser = subparsers.add_parser("unbind", help="Remove a binding")
    unbind_parser.add_argument("capability", help="Capability or hook name")
    unbind_parser.add_argument("phase", help="Lifecycle phase")

    # test
    test_parser = subparsers.add_parser("test", help="Dry-run hooks for a phase/position")
    test_parser.add_argument("phase", help="Lifecycle phase")
    test_parser.add_argument("position", help="pre or post")

    # discover
    subparsers.add_parser("discover", help="Scan for auto-discoverable bindings")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    project_root = _find_project_root()

    if args.command == "list":
        return _cmd_list(project_root, args)
    elif args.command == "bind":
        return _cmd_bind(project_root, args)
    elif args.command == "unbind":
        return _cmd_unbind(project_root, args)
    elif args.command == "test":
        return _cmd_test(project_root, args)
    elif args.command == "discover":
        return _cmd_discover(project_root)
    else:
        parser.print_help()
        return 1


def _find_project_root() -> str:
    """Walk up from cwd to find the project root (.skillweave/ or .git/)."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".skillweave").exists() or (parent / ".git").exists():
            return str(parent)
    return str(cwd)


def _cmd_list(project_root: str, args: argparse.Namespace) -> int:
    """List all hook bindings."""
    from ..hooks.facade import list_hooks

    result = list_hooks(
        project_root=project_root,
        phase=args.phase,
    )

    if args.as_json:
        print(json.dumps(result, indent=2))
        return 0

    bindings = result["bindings"]
    if not bindings:
        print("No hooks configured.")
        return 0

    print(f"\n{'Name':<25} {'Type':<10} {'Phase':<12} {'Pos':<5} {'Pri':<5} {'Source':<8} {'Failure':<8}")
    print("-" * 78)
    for b in bindings:
        marker = " [auto]" if b["source"] == "auto" else ""
        print(
            f"{b['name']:<25} {b['type']:<10} {b['phase'] or '-':<12} "
            f"{b['position'] or '-':<5} {b['priority']:<5} {b['source']:<8} "
            f"{b['failureMode']:<8}{marker}"
        )
    print(f"\n{result['summary']}")
    return 0


def _cmd_bind(project_root: str, args: argparse.Namespace) -> int:
    """Create a new explicit binding YAML."""
    hooks_dir = Path(project_root) / ".skillweave" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{args.phase}-{args.position}.yaml"
    filepath = hooks_dir / filename

    # Load existing or create new
    if filepath.exists():
        with open(filepath) as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {
            "version": "1",
            "phase": args.phase,
            "position": args.position,
            "hooks": [],
        }

    # Check for duplicate
    existing_names = {h.get("name") for h in data.get("hooks", [])}
    if args.capability in existing_names:
        print(f"Binding '{args.capability}' already exists in {filename}")
        return 1

    # Build hook entry
    hook_entry = {
        "name": args.capability,
        "type": args.type,
        "priority": args.priority,
        "failureMode": args.failure_mode,
    }

    # Add type-specific field
    if args.type == "capacium":
        hook_entry["capability"] = args.capability
    elif args.type == "shell":
        hook_entry["command"] = args.capability
    elif args.type == "python":
        hook_entry["module"] = args.capability
    elif args.type == "skill_md":
        hook_entry["skill_md"] = args.capability

    data.setdefault("hooks", []).append(hook_entry)

    with open(filepath, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    print(f"Bound '{args.capability}' at {args.position}_{args.phase} → {filename}")
    return 0


def _cmd_unbind(project_root: str, args: argparse.Namespace) -> int:
    """Remove a binding from YAML files."""
    hooks_dir = Path(project_root) / ".skillweave" / "hooks"
    removed = False

    for pos in ("pre", "post"):
        filename = f"{args.phase}-{pos}.yaml"
        filepath = hooks_dir / filename

        if not filepath.exists():
            continue

        with open(filepath) as f:
            data = yaml.safe_load(f) or {}

        hooks = data.get("hooks", [])
        original_count = len(hooks)
        hooks = [h for h in hooks if h.get("name") != args.capability]

        if len(hooks) < original_count:
            data["hooks"] = hooks
            with open(filepath, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            print(f"Unbound '{args.capability}' from {filename}")
            removed = True

    if not removed:
        print(f"No binding found for '{args.capability}' in phase '{args.phase}'")
        return 1

    return 0


def _cmd_test(project_root: str, args: argparse.Namespace) -> int:
    """Dry-run all hooks for a phase/position."""
    from ..hooks.facade import run_hooks

    print(f"\nDry-running hooks for {args.position}_{args.phase}...")
    print("-" * 50)

    result = asyncio.run(
        run_hooks(
            phase=args.phase,
            position=args.position,
            project_root=project_root,
        )
    )

    if result is None:
        print("No hooks configured or tier gate blocked execution.")
        return 0

    for binding, hook_result in result.results:
        status_icon = "✓" if hook_result.passed else "✗" if hook_result.failed else "○"
        print(f"  {status_icon} {binding.name}: {hook_result.status} — {hook_result.message}")

    for binding in result.skipped:
        print(f"  ○ {binding.name}: skipped (condition false)")

    print(f"\n{result.pass_count}/{result.hook_count} passed", end="")
    if result.aborted:
        print(f" [ABORTED: {result.abort_reason}]")
    else:
        print()

    return 0 if result.all_passed else 1


def _cmd_discover(project_root: str) -> int:
    """Scan for auto-discoverable trigger bindings."""
    from ..hooks.discovery.scanner import TriggerScanner
    from ..hooks.discovery.registry import DismissalRegistry

    scanner = TriggerScanner()
    registry = DismissalRegistry(project_root=project_root)

    discovered = scanner.scan()

    if not discovered:
        print("No SkillWeave triggers found in installed Capacium capabilities.")
        return 0

    active = registry.filter_dismissed(discovered)
    dismissed = [d for d in discovered if registry.is_dismissed(d)]

    print(f"\nDiscovered {len(discovered)} trigger(s):")
    print(f"  Active: {len(active)}  |  Dismissed: {len(dismissed)}")
    print()

    for d in active:
        print(f"  ● {d.capability} → {d.position}_{d.phase}")

    if dismissed:
        print(f"\n  Dismissed ({len(dismissed)}):")
        for d in dismissed:
            print(f"  ○ {d.capability} → {d.position}_{d.phase}")

    return 0


if __name__ == "__main__":
    sys.exit(hooks_main())
