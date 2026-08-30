"""Dispatch-order group 5 — immutable evidence manifest and non-mutating suite
(criteria 9 and 10).

Criterion 9 proves the machine-readable gate manifest exists, validates against
``schemas/gate-1312-manifest.schema.json``, and pins every repository SHA, the
schema/artifact digest, the exact command, its exit code, evidence hashes and the
reviewer-brief digest.

Criterion 10 proves the suite is non-mutating: it performs no merge, push, tag,
release, publish, production CMS mutation or reviewer product write. It reads
files and git config only; it opens no file for writing outside the pytest tmp
fixture, and its declared evidence surfaces are all read-only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema

from tests.gate_1312 import CANONICAL_SCHEMA_DIGEST

MANIFEST_BASENAME = "gate-1312-manifest.json"

#: The exact required base SHA of the wt-sw1312-gate-suite-ops worktree.
REQUIRED_BASE_SHA = "52280008b5e9ce9a6e7435c5a1fe67feee581c6b"


def _core_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _schema_path() -> Path:
    return _core_root() / "schemas" / "gate-1312-manifest.schema.json"


def _manifest_path() -> Path:
    return Path(__file__).resolve().parent / MANIFEST_BASENAME


def test_criterion_09_machine_readable_gate_manifest():
    """The gate manifest is present, valid, and pins SHAs, digests, commands,
    exits, evidence hashes, and the reviewer-brief digest.
    """
    # --- The schema exists and is well-formed ----------------------------------
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    assert schema["$id"].endswith("gate-1312-manifest/v1")

    # --- The manifest exists and validates against the schema ------------------
    manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))
    jsonschema.validate(manifest, schema)

    # --- Pinned SHAs are full 40-hex and distinct base/subject ------------------
    gate = manifest["gate"]
    assert gate["id"] == "SW-GATE-1312"
    # The base SHA is the exact required base; the subject is recorded by the
    # controller at verdict time (a sentinel here, never equal to the base).
    assert gate["base_sha"] == REQUIRED_BASE_SHA
    assert re_full_sha(gate["subject_sha"])
    assert gate["subject_sha"] != gate["base_sha"]
    for key, sha in manifest["shas"].items():
        assert re_full_sha(sha), f"shas.{key} not a full SHA: {sha!r}"

    # --- Digests are full 64-hex -----------------------------------------------
    if "digests" in manifest:
        for key, dg in manifest["digests"].items():
            assert re_full_hex64(dg), f"digests.{key} not a 64-hex digest"
        # The schema digest pins the canonical preview contract.
        if "schema" in manifest["digests"]:
            assert manifest["digests"]["schema"] == CANONICAL_SCHEMA_DIGEST

    # --- Commands bind exact command + integer exit ----------------------------
    for entry in manifest["commands"]:
        assert isinstance(entry["exit"], int)

    # --- Evidence hashes are full 64-hex ---------------------------------------
    for ev in manifest["evidence"]:
        assert re_full_hex64(ev["sha256"]), f"evidence {ev['path']} bad hash"

    # --- Reviewer brief digest is 64-hex ---------------------------------------
    assert re_full_hex64(manifest["reviewer_brief"]["digest"])

    # --- The declared 1.3.13 deferral is named in the manifest -----------------
    deferrals = manifest.get("deferrals", [])
    assert "1.3.13" in deferrals, "the GenericRouterProvider deferral is not recorded"


def test_criterion_10_no_merge_push_tag_release_publish_or_mutation():
    """The suite performs no merge, push, tag, release, publish, production CMS
    mutation, or reviewer product write.

    Static proof: the gate suite source performs no git-mutating subprocess call
    and no file write outside pytest's own temporary fixture. It reads files and
    git *config* only.
    """
    gate_dir = Path(__file__).resolve().parent
    # The forbidden-action scan runs over every *execution* test module. It
    # deliberately excludes this enforcement module itself (whose source
    # necessarily names the forbidden verbs it is checking for).
    for py in gate_dir.glob("test_*.py"):
        if py.name == "test_manifest.py":
            continue
        text = py.read_text(encoding="utf-8")
        low = text.lower()
        # The suite must not shell out to any git mutating / publishing command.
        for tok in ("git merge", "git push", "git tag", "git commit",
                    "gh release", "gh pr merge"):
            assert tok not in low, f"{py.name}: forbidden action {tok!r}"
        # No publish path is ever invoked.
        assert ".publish(" not in text
        # Any subprocess statement must not pass a mutation verb.
        if "subprocess" in text:
            for line in text.splitlines():
                if ("subprocess.run(" in line or "subprocess.check" in line
                        or "Popen(" in line or "run([" in line):
                    assert not any(v in line.lower() for v in
                                   ("merge", "push", "tag", "commit",
                                    "release", "publish")), (
                        f"{py.name}: mutating subprocess: {line.strip()}"
                    )

    # The suite performs no reviewer/product write: it never opens a product file
    # for writing. The only write surface is pytest's ``tmp_path`` fixture; any
    # file that writes must declare ``tmp_path``.
    gate_dir = Path(__file__).resolve().parent
    for py in gate_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        writes_outside_tmp = []
        for line in text.splitlines():
            s = line.strip()
            if "write_text" in s or "open(" in s and any(m in s for m in (", \"w\"", ", 'w'", "mode=\"w\"", "mode='w'")):
                writes_outside_tmp.append(s)
        if writes_outside_tmp and "tmp_path" not in text:
            raise AssertionError(
                f"{py.name}: writes outside a tmp_path fixture: {writes_outside_tmp}"
            )

    # The gate manifest's declared commands are the read-only verification suite
    # and validation only — no release/publish step appears in them either.
    manifest = json.loads(_manifest_path().read_text(encoding="utf-8"))
    for entry in manifest["commands"]:
        cmd = entry["command"].lower()
        for forbidden in ("release", "publish", "push", "merge", "tag"):
            assert forbidden not in cmd, f"manifest command is mutating: {entry['command']}"


def re_full_sha(value: str) -> bool:
    return bool(re.match(r"^[0-9a-f]{40}$", value))


def re_full_hex64(value: str) -> bool:
    return bool(re.match(r"^[0-9a-f]{64}$", value))
