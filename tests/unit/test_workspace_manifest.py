"""Workspace manifest contract (SW-155 / SW-WORKSPACE-001).

Covers the acceptance surface:

* the configurable default worktree path ``<collection>/.worktrees/<repo>/<run>/<lane>``;
* a manifest carrying repo, full base/head SHAs, branch, run, lane, session,
  write scope, lease, heartbeat, state and retention;
* legacy ``.sw-worktrees`` and ``wt-*`` locations are discoverable and never
  moved or deleted here;
* the primary checkout stays clean (the new path is outside it);
* compatibility: the new path can be handed to the existing
  ``skillweave.workspace.GitWorktreeProvider`` unchanged;
* a red schema/policy counterproof: the pre-contract attestation shape and the
  in-repo default path are rejected by the new contract.

Self-contained sys.path handling and a hand-rolled structural schema validator,
following the convention of ``test_dispatch_contract.py`` — no ``jsonschema``
dependency.
"""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.routing.workspace import (  # noqa: E402
    FULL_SHA_LENGTH,
    RETENTION_VALUES,
    WORKTREES_DIRNAME,
    WorkspaceManifest,
    WorkspaceManifestError,
    WorkspaceState,
    default_worktree_path,
    discover_legacy_worktree_locations,
    is_outside_primary_checkout,
    legacy_sw_worktrees_path,
    resolve_collection,
    worktree_path,
)
from skillweave.workspace import Attestation, GitWorktreeProvider  # noqa: E402

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "workspace-manifest.schema.json"
)

BASE_SHA = "1" * FULL_SHA_LENGTH
HEAD_SHA = "2" * FULL_SHA_LENGTH
ISO_TS = "2026-09-24T00:00:00+00:00"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_errors(instance: dict) -> list[str]:
    """Structural schema validator (no ``jsonschema`` dependency).

    Walks the shipped workspace-manifest schema and yields human-readable error
    strings for ``required``, ``additionalProperties: false``, ``type``,
    ``enum``, ``pattern`` and ``minItems``.
    """
    errors: list[str] = []

    def check(schema, value, path):
        if schema.get("type") == "object":
            if not isinstance(value, dict):
                errors.append(f"{path}: expected object, got {type(value).__name__}")
                return
            for key in schema.get("required", []):
                if key not in value:
                    errors.append(f"{path}: missing required '{key}'")
            if schema.get("additionalProperties") is False:
                for key in value:
                    if key not in schema.get("properties", {}):
                        errors.append(f"{path}: disallowed property '{key}'")
            for key, subschema in schema.get("properties", {}).items():
                if key in value:
                    check(subschema, value[key], f"{path}.{key}")
            return

        if schema.get("type") == "array":
            if not isinstance(value, list):
                errors.append(f"{path}: expected array, got {type(value).__name__}")
                return
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(f"{path}: expected at least {schema['minItems']} items")
            items = schema.get("items")
            if items:
                for i, item in enumerate(value):
                    check(items, item, f"{path}[{i}]")
            return

        if schema.get("type") == "string" and not isinstance(value, str):
            errors.append(f"{path}: expected string, got {type(value).__name__}")
            return
        if schema.get("type") == "integer" and (
            not isinstance(value, int) or isinstance(value, bool)
        ):
            errors.append(f"{path}: expected integer, got {type(value).__name__}")
            return

        if isinstance(value, str):
            if "enum" in schema and value not in schema["enum"]:
                errors.append(f"{path}: {value!r} not in enum {schema['enum']}")
            if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
                errors.append(
                    f"{path}: {value!r} does not match pattern {schema['pattern']!r}"
                )

    check(_schema(), instance, "$")
    return errors


def _valid_manifest_dict() -> dict:
    return {
        "repo": "skillweave",
        "base_sha": BASE_SHA,
        "head_sha": HEAD_SHA,
        "branch": "ops/SW-155-workspace-contract-big-pickle",
        "run": "sw155",
        "lane": "workspace-contract-big-pickle",
        "session": "session-001",
        "write_scope": ["src/skillweave/routing/", "schemas/", "tests/unit/"],
        "lease": {"lease_until": ISO_TS, "owner": "ops"},
        "heartbeat": ISO_TS,
        "state": "active",
        "retention": "project_lifetime",
    }


# --- Red counterproof -----------------------------------------------------

def test_red_counterproof_legacy_attestation_shape_is_not_a_valid_manifest():
    # Before this contract there was only the workspace provider's Attestation,
    # whose serialised shape is {base_sha, branch, path, created_at, digest}.
    # That shape must now be REJECTED: it lacks the run/lane/session/write-scope/
    # lease/heartbeat/state/retention facts and carries disallowed keys.
    legacy = Attestation(
        base_sha=BASE_SHA, branch="ops/legacy", path="/tmp/legacy", created_at=ISO_TS
    ).to_dict()

    errors = _schema_errors(legacy)

    assert errors, "legacy attestation shape unexpectedly satisfies the new contract"
    assert any("missing required 'repo'" in e for e in errors)
    assert any("missing required 'head_sha'" in e for e in errors)
    assert any("missing required 'lease'" in e for e in errors)
    assert any("disallowed property 'path'" in e for e in errors)


def test_red_counterproof_old_in_repo_default_path_violates_new_contract():
    # The previous adapter materialised worktrees at <repo>/.sw-worktrees/...,
    # INSIDE the primary checkout. The new default must move that outside.
    old_path = legacy_sw_worktrees_path("/tmp/collection/skillweave") / "branch"
    new_path = default_worktree_path(
        "/tmp/collection", repo="skillweave", run="sw155", lane="lane-a"
    )

    assert not is_outside_primary_checkout(
        "/tmp/collection/skillweave", str(old_path)
    ), "legacy default path should be inside the primary checkout (the defect)"
    assert is_outside_primary_checkout(
        "/tmp/collection/skillweave", str(new_path)
    ), "new default path should be outside the primary checkout (the fix)"


# --- Default path ---------------------------------------------------------

def test_default_worktree_path_is_configurable_collection_repo_run_lane():
    p = default_worktree_path(
        "/srv/collections", repo="skillweave", run="sw155", lane="workspace-contract"
    )
    assert p == Path("/srv/collections/.worktrees/skillweave/sw155/workspace-contract")

    # Every segment is configurable: a different collection, repo, run or lane
    # yields a different location.
    other = default_worktree_path(
        "/srv/other", repo="other-repo", run="sw999", lane="other-lane"
    )
    assert str(other) != str(p)
    assert other.parts[-4:] == (WORKTREES_DIRNAME, "other-repo", "sw999", "other-lane")


def test_worktree_path_derives_collection_and_repo_from_checkout():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "skillweave"
        root.mkdir()

        p = worktree_path(str(root), run="sw155", lane="lane-a")
        assert p == Path(tmp) / ".worktrees" / "skillweave" / "sw155" / "lane-a"

        # Configurable overrides for both the collection and the repo name.
        overridden = worktree_path(
            str(root), repo="renamed", run="sw155", lane="lane-a", collection="/srv/c"
        )
        assert overridden == Path("/srv/c") / ".worktrees" / "renamed" / "sw155" / "lane-a"


def test_resolve_collection_defaults_to_parent_and_is_overridable():
    assert resolve_collection("/a/b/repo") == Path("/a/b")
    assert resolve_collection("/a/b/repo", collection="/srv/c") == Path("/srv/c")


def test_primary_checkout_stays_clean():
    # The new default lives under <collection>/.worktrees, a sibling of the
    # primary checkout — never inside it.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "skillweave"
        root.mkdir()
        p = worktree_path(str(root), run="sw155", lane="lane-a")

        assert is_outside_primary_checkout(str(root), str(p))
        assert root not in p.parents
        assert p != root


# --- Legacy discovery -----------------------------------------------------

def test_legacy_locations_are_discoverable_and_never_moved_or_deleted():
    with tempfile.TemporaryDirectory() as tmp:
        collection = Path(tmp)
        repo = collection / "skillweave"
        repo.mkdir()
        sw_legacy = repo / ".sw-worktrees" / "branch"
        sw_legacy.mkdir(parents=True)
        wt_direct = collection / "wt-152"
        wt_direct.mkdir()
        wt_nested = collection / ".worktrees" / "wt-sw152-022-ops"
        wt_nested.mkdir(parents=True)

        discovered = discover_legacy_worktree_locations(str(collection), repo="skillweave")

        paths = {str(p) for p in discovered}
        assert str(repo / ".sw-worktrees") in paths
        assert str(wt_direct) in paths
        assert str(wt_nested) in paths

        # Discovery is read-only: every location is still present afterwards.
        assert sw_legacy.exists()
        assert wt_direct.exists()
        assert wt_nested.exists()


# --- Manifest parsing/validation ------------------------------------------

def test_manifest_roundtrips_through_dict_and_json():
    data = _valid_manifest_dict()
    manifest = WorkspaceManifest.from_dict(data)

    assert manifest.repo == "skillweave"
    assert manifest.base_sha == BASE_SHA
    assert manifest.head_sha == HEAD_SHA
    assert manifest.write_scope == [
        "src/skillweave/routing/",
        "schemas/",
        "tests/unit/",
    ]
    assert manifest.lease.lease_until == ISO_TS
    assert manifest.lease.owner == "ops"
    assert manifest.state == WorkspaceState.ACTIVE.value
    assert manifest.retention == "project_lifetime"

    assert manifest.to_dict() == data
    assert json.loads(manifest.to_json()) == data


def test_manifest_validation_rejects_short_sha():
    data = _valid_manifest_dict()
    data["base_sha"] = "abc123"
    try:
        WorkspaceManifest.from_dict(data)
    except WorkspaceManifestError as exc:
        assert exc.field == "base_sha"
    else:
        raise AssertionError("short base SHA was accepted")


def test_manifest_validation_rejects_missing_field():
    data = _valid_manifest_dict()
    del data["session"]
    try:
        WorkspaceManifest.from_dict(data)
    except WorkspaceManifestError as exc:
        assert exc.field == "session"
    else:
        raise AssertionError("missing session was accepted")


def test_manifest_validation_rejects_out_of_vocabulary_values():
    for key, value in (("state", "bogus"), ("retention", "forever")):
        data = _valid_manifest_dict()
        data[key] = value
        try:
            WorkspaceManifest.from_dict(data)
        except WorkspaceManifestError as exc:
            assert exc.field == key
        else:
            raise AssertionError(f"illegal {key} value {value!r} was accepted")


def test_manifest_validation_rejects_empty_write_scope():
    data = _valid_manifest_dict()
    data["write_scope"] = []
    try:
        WorkspaceManifest.from_dict(data)
    except WorkspaceManifestError as exc:
        assert exc.field == "write_scope"
    else:
        raise AssertionError("empty write_scope was accepted")


def test_manifest_validation_rejects_missing_lease_until():
    data = _valid_manifest_dict()
    data["lease"] = {"owner": "ops"}
    try:
        WorkspaceManifest.from_dict(data)
    except WorkspaceManifestError as exc:
        assert exc.field == "lease.lease_until"
    else:
        raise AssertionError("lease without lease_until was accepted")


def test_manifest_rejects_sha_forms_the_schema_rejects():
    # Runtime/schema parity: the schema pattern is ^[0-9a-f]{40}$, so the
    # parser must not accept uppercase hex, underscores, or a 0x prefix that
    # Python's int(x, 16) would happily take.
    malformed = {
        "uppercase": "A" * FULL_SHA_LENGTH,
        "mixed_case": "aA" + "0" * (FULL_SHA_LENGTH - 2),
        "underscore": "1_" + "2" * (FULL_SHA_LENGTH - 2),
        "0x_prefix": "0x" + "1" * (FULL_SHA_LENGTH - 2),
    }
    for label, sha in malformed.items():
        assert len(sha) == FULL_SHA_LENGTH
        for field in ("base_sha", "head_sha"):
            data = _valid_manifest_dict()
            data[field] = sha
            assert any(
                "does not match pattern" in e for e in _schema_errors(data)
            ), f"schema unexpectedly accepted {label} {field}"
            try:
                WorkspaceManifest.from_dict(data)
            except WorkspaceManifestError as exc:
                assert exc.field == field
            else:
                raise AssertionError(
                    f"parser accepted schema-rejected {label} {field}: {sha!r}"
                )


def test_manifest_rejects_properties_the_schema_rejects():
    # additionalProperties: false at the top level.
    data = _valid_manifest_dict()
    data["extra"] = "nope"
    assert any("disallowed property 'extra'" in e for e in _schema_errors(data))
    try:
        WorkspaceManifest.from_dict(data)
    except WorkspaceManifestError as exc:
        assert exc.field == "extra"
    else:
        raise AssertionError("parser accepted a disallowed top-level property")

    # additionalProperties: false inside lease.
    data = _valid_manifest_dict()
    data["lease"]["holder"] = "ops"
    assert any("disallowed property 'holder'" in e for e in _schema_errors(data))
    try:
        WorkspaceManifest.from_dict(data)
    except WorkspaceManifestError as exc:
        assert exc.field == "lease.holder"
    else:
        raise AssertionError("parser accepted a disallowed lease property")


# --- Schema surface -------------------------------------------------------

def test_schema_requires_exactly_the_contract_fields_and_rejects_extras():
    schema = _schema()
    assert set(schema["required"]) == {
        "repo",
        "base_sha",
        "head_sha",
        "branch",
        "run",
        "lane",
        "session",
        "write_scope",
        "lease",
        "heartbeat",
        "state",
        "retention",
    }
    assert schema["additionalProperties"] is False
    assert schema["$id"] == "https://skillweave.dev/schemas/workspace-manifest/v1"

    data = _valid_manifest_dict()
    data["extra"] = "nope"
    errors = _schema_errors(data)
    assert any("disallowed property 'extra'" in e for e in errors)


def test_schema_accepts_a_complete_manifest():
    assert _schema_errors(_valid_manifest_dict()) == []


def test_schema_rejects_missing_and_malformed_fields():
    data = _valid_manifest_dict()
    del data["lease"]
    errors = _schema_errors(data)
    assert any("missing required 'lease'" in e for e in errors)

    data = _valid_manifest_dict()
    data["base_sha"] = "short"
    errors = _schema_errors(data)
    assert any("does not match pattern" in e for e in errors)

    data = _valid_manifest_dict()
    data["state"] = "bogus"
    errors = _schema_errors(data)
    assert any("not in enum" in e for e in errors)


def test_manifest_vocabulary_matches_schema_enums():
    schema = _schema()
    code_states = {member.value for member in WorkspaceState}
    schema_states = set(schema["properties"]["state"]["enum"])
    assert code_states == schema_states, (
        f"code<->schema state drift: code-only={sorted(code_states - schema_states)}, "
        f"schema-only={sorted(schema_states - code_states)}"
    )
    assert set(RETENTION_VALUES) == set(schema["properties"]["retention"]["enum"])


# --- Compatibility with the existing provider -----------------------------

def _make_repo() -> str:
    """Create a throwaway git repo with one commit; return its root path."""
    root = tempfile.mkdtemp(prefix="sw-ws-manifest-")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=root, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "test"], cwd=root, check=True
    )
    (Path(root) / "file.txt").write_text("one")
    subprocess.run(["git", "add", "file.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "c1"], cwd=root, check=True)
    return root


def test_new_default_path_hands_off_to_existing_provider():
    # The new contract is additive: GitWorktreeProvider already accepts a
    # ``path`` kwarg, so the configurable default path can be handed to it
    # unchanged. This proves compatibility without touching any real worktree.
    root = _make_repo()
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True
    ).stdout.strip()
    provider = GitWorktreeProvider(root)
    target = worktree_path(root, run="sw155", lane="lane-p")

    ws = provider.acquire(sha, "ops/SW-155-compat", path=str(target))
    try:
        assert ws.path == target
        assert ws.path.exists()
        assert is_outside_primary_checkout(root, str(ws.path))
    finally:
        ws.release()


def _run_all() -> int:
    tests = [
        v
        for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
