#!/usr/bin/env python3
"""check-manifest — check SkillWeave's capabilities: manifest against the member files.

Where version-sync asks "does every location agree with the source", this tool
asks a different question: "does a declaration agree with what it declares". The
capabilities: block of the bundle capability.yaml is a MANIFEST: each entry
promises which version of a member the bundle ships. Per member it checks:

    the value declared in the capabilities: block
        == version: in skills/<name>/capability.yaml

with no reference to source_of_truth at all. Member versions that differ from the
bundle are permitted and must stay permitted — that is the normal state of a
bundle. The only thing forbidden is a manifest and a member file contradicting
each other.

Stdlib only; runs on a bare ubuntu-latest runner.

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

# The bundle capability.yaml carries a capabilities: block of entries shaped:
#   - name: skillweave-blueprint
#     source: ./skills/skillweave-blueprint
#     version: 1.3.0
# Each entry is a PIN onto the corresponding skill artefact on disk, not the
# version authority for that skill. Three fields are therefore checked against
# the member file skills/<name>/capability.yaml:
#   name    == the member file's own `name:` key
#   source  == ./skills/<name>
#   version == the member file's own `version:` key
ENTRY_NAME_RE = re.compile(r"^-\s+name:\s*(\S+)")
ENTRY_SOURCE_RE = re.compile(r"^source:\s*(\S+)")
VERSION_RE = re.compile(r"^version:\s*(\S+)")


def _die(msg: str) -> NoReturn:
    print(f"check-manifest: ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def load_member_field(repo: Path, name: str, field: str) -> str | None:
    """Read `field:` from skills/<name>/capability.yaml; None when absent."""
    p = repo / "skills" / name / "capability.yaml"
    if not p.exists():
        return None
    m = re.search(rf"^{field}:\s*(\S+)", p.read_text(), re.MULTILINE)
    return m.group(1) if m else None


def parse_manifest(repo: Path) -> list[tuple[str, str, str]]:
    """Read (name, source, version) for each capabilities: entry."""
    p = repo / BUNDLE_MANIFEST
    if not p.exists():
        _die(f"no {BUNDLE_MANIFEST}")
    entries: list[tuple[str, str, str]] = []
    cur_name: str | None = None
    cur_source: str | None = None
    in_caps = False
    for raw in p.read_text().splitlines():
        if raw.strip() == "capabilities:":
            in_caps = True
            continue
        if in_caps and raw.strip() and not raw.startswith((" ", "\t", "-")):
            # End of the block: the next top-level key.
            break
        if not in_caps:
            continue
        m = ENTRY_NAME_RE.match(raw)
        if m:
            cur_name = m.group(1)
            continue
        m = ENTRY_SOURCE_RE.match(raw.strip())
        if m:
            cur_source = m.group(1)
            continue
        if cur_name is not None:
            v = VERSION_RE.match(raw.strip())
            if v:
                entries.append((cur_name, cur_source or "", v.group(1)))
                cur_name = None
                cur_source = None
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
    for name, source, declared in entries:
        on_disk_name = load_member_field(repo, name, "name")
        actual = load_member_field(repo, name, "version")
        expected_source = f"./skills/{name}"
        if on_disk_name is None or actual is None:
            print(f"  MISSING   {name}: skills/{name}/capability.yaml is absent (manifest says {declared})")
            failed = True
            continue
        if on_disk_name != name:
            print(f"  MISMATCH  {name}: manifest name {name}, file name {on_disk_name}")
            failed = True
        if source != expected_source:
            print(f"  MISMATCH  {name}: manifest source {source!r}, expected {expected_source!r}")
            failed = True
        if actual != declared:
            print(f"  MISMATCH  {name}: manifest says {declared}, file says {actual}")
            failed = True
        if on_disk_name == name and source == expected_source and actual == declared:
            print(f"  ok        {name} = {actual}")

    if failed:
        print(f"check-manifest: FAIL — {sum(1 for _ in entries)} members, manifest disagrees")
        return 1
    print(f"check-manifest: OK — {len(entries)} members, manifest == member files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
