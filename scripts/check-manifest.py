#!/usr/bin/env python3
"""check-manifest — prueft SkillWeaves capabilities:-Manifest gegen die Mitgliedsdateien.

Anders als version-sync (Frage: "stimmen alle Orte mit der Quelle ueberein")
stellt dieses Werkzeug die Frage: "stimmt eine Deklaration mit dem Deklarierten
ueberein". Der capabilities:-Block der Bundle-capability.yaml ist ein MANIFEST:
je Eintrag wird zugesichert, welche Fassung eines Mitglieds das Bundle
ausliefert. Geprueft wird je Mitglied:

    deklarierter Wert im capabilities:-Block
        == version: in skills/<name>/capability.yaml

Ohne jeden Bezug auf source_of_truth. Abweichende Mitgliedsversionen sind
erlaubt und muessen erlaubt bleiben (der Normalfall eines Bundles); verboten
ist nur, dass Manifest und Mitgliedsdatei sich widersprechen.

Stdlib only, laeuft auf leerem ubuntu-latest-Runner.

Usage:
    check-manifest.py [--repo PATH]
Exit 0 = Manifest und Mitgliedsdateien stimmen ueberein.
Exit 1 = mindestens ein Mitglied widerspricht seinem Manifest-Eintrag.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NoReturn

BUNDLE_MANIFEST = "capability.yaml"

# In der Bundle-capability.yaml steht ein capabilities:-Block mit Eintraegen
# der Form:
#   - name: skillweave-blueprint
#     source: ./skills/skillweave-blueprint
#     version: 1.3.0
# Wir lesen name + version je Eintrag und vergleichen version gegen
# skills/<name>/capability.yaml Zeile "version: X".
ENTRY_NAME_RE = re.compile(r"^-\s+name:\s*(\S+)")
VERSION_RE = re.compile(r"^version:\s*(\S+)")


def _die(msg: str) -> NoReturn:
    print(f"check-manifest: ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def load_member_version(repo: Path, name: str) -> str:
    """Lese version: aus skills/<name>/capability.yaml; None wenn fehlt."""
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
    """Lies name + version je capabilities:-Eintrag der Bundle-capability.yaml."""
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
            # Block zu Ende (naechster Top-Level-Schlüssel).
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
            print(f"  MISSING   {name}: skills/{name}/capability.yaml fehlt (Manifest sagt {declared})")
            failed = True
        elif actual != declared:
            print(f"  MISMATCH  {name}: Manifest sagt {declared}, Datei sagt {actual}")
            failed = True
        else:
            print(f"  ok        {name} = {actual}")

    if failed:
        print(f"check-manifest: FAIL — {sum(1 for _ in entries)} Mitglieder, Manifest weicht ab")
        return 1
    print(f"check-manifest: OK — {len(entries)} Mitglieder, Manifest == Mitgliedsdateien")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
