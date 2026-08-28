#!/usr/bin/env python3
"""check-manifest — checks SkillWeave's capabilities:-manifest against the member files.

Unlike version-sync (the question: "do all locations agree with the source"),
this tool asks: "does a declaration agree with what is declared". The
capabilities:-block of the Bundle capability.yaml is a MANIFEST: per entry it
promises which revision of a member the bundle ships. It checks per member:

    declared value in the capabilities:-block
        == version: in skills/<name>/capability.yaml

With no reference to source_of_truth at all. Divergent member versions are
allowed and must stay allowed (the normal case for a bundle); the only thing
forbidden is the manifest and the member file contradicting each other.

Stdlib only, runs on an empty ubuntu-latest runner.

Usage:
    check-manifest.py [--repo PATH]
Exit 0 = manifest and member files agree.
Exit 1 = at least one member contradicts its manifest entry.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NoReturn

BUNDLE_MANIFEST = "capability.yaml"

# The Bundle capability.yaml has a capabilities:-block with entries of the form:
#   - name: skillweave-blueprint
#     source: ./skills/skillweave-blueprint
#     version: 1.3.0
# We read name + version per entry and compare version against
# skills/<name>/capability.yaml line "version: X".
ENTRY_NAME_RE = re.compile(r"^-\s+name:\s*(\S+)")
VERSION_RE = re.compile(r"^version:\s*(\S+)")


def _die(msg: str) -> NoReturn:
    print(f"check-manifest: ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def load_member_version(repo: Path, name: str) -> str:
    """Read version: from skills/<name>/capability.yaml; None if missing."""
    p = repo / "skills" / name / "capability.yaml"
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        s = line.strip()
        m = VERSION_RE.match(s)
        if m:
            return m.group(1)
    return None


def parse_manifest(repo: Path) -> list[tuple[str, str]]:
    """Read name + version per capabilities:-entry of the Bundle capability.yaml."""
    p = repo / BUNDLE_MANIFEST
    if not p.exists():
        _die(f"no {BUNDLE_MANIFEST}")
    entries: list[tuple[str, str]] = []
    cur_name: str | None = None
    in_caps = False
    for raw in p.read_text().splitlines():
        if raw.strip() == "capabilities:":
            in_caps = True
            continue
        if in_caps and raw.strip() and not raw.startswith((" ", "\t", "-")):
            # Block ended (next top-level key).
            break
        if not in_caps:
            continue
        m = ENTRY_NAME_RE.match(raw)
        if m:
            cur_name = m.group(1)
            continue
        if cur_name is not None:
            v = VERSION_RE.match(raw.strip())
            if v:
                entries.append((cur_name, v.group(1)))
                cur_name = None
    if not entries:
        _die(f"no capabilities entries found in {BUNDLE_MANIFEST}")
    return entries


def main() -> int:
    ap = argparse.ArgumentParser(prog="check-manifest")
    ap.add_argument("--repo", type=Path, default=Path("."))
    args = ap.parse_args()
    repo = args.repo

    entries = parse_manifest(repo)
    failed = False
    for name, declared in entries:
        actual = load_member_version(repo, name)
        if actual is None:
            print(f"  MISSING   {name}: skills/{name}/capability.yaml missing (manifest says {declared})")
            failed = True
        elif actual != declared:
            print(f"  MISMATCH  {name}: manifest says {declared}, file says {actual}")
            failed = True
        else:
            print(f"  ok        {name} = {actual}")

    if failed:
        print(f"check-manifest: FAIL — {sum(1 for _ in entries)} members, manifest diverges")
        return 1
    print(f"check-manifest: OK — {len(entries)} members, manifest == member files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
