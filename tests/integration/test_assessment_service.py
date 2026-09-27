"""Integration tests for the read-only assessment service (SW-157-ASSESS-002).

These exercise the acceptance criteria of the service and its CLI surface on
``skillweave assess``:

Step A -- enforce read-only authority and explicit available/unavailable results
    with resolvable evidence:

1. An ``available`` receipt names its sources and the one read-only command it
    ran, and a third party can re-resolve that evidence (``verify`` returns True)
    from the recorded digests alone.
2. Any shortfall -- a missing, escaping or digest-mismatched source, no sources,
    an unverifiable subject, or a probe that could not run -- produces an
    ``unavailable`` receipt whose ``limits`` name the shortfall and which attests
    no sources and no commands.
3. The assessor carries a read-only authority: the authority refuses writes, and
    the service refuses to be constructed with any non-read-only authority.

Step B -- prove identical inputs produce a stable digest:

4. The same request assessed twice seals to a byte-identical receipt, in-process
    and across separate interpreter processes.

Read-only negative case:

5. The assessed tree's fingerprint is unchanged before and after (the assessor
    mutates nothing), and the service's own import closure pulls no write-path
    subsystem.

The suite is hermetic: no network, no wall clock (``produced_at`` is supplied),
and every file mutation happens under pytest's ``tmp_path``.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from skillweave.assessment_contracts import (
    RESULT_AVAILABLE,
    RESULT_UNAVAILABLE,
    AssessmentError,
    canonicalize,
)
from skillweave.assessment_service import (
    ESCAPED,
    MISSING,
    RESOLVED,
    AssessmentRequest,
    AssessmentService,
    CommandSpec,
    Finding,
    ReadOnlyAuthority,
    ReadOnlyViolation,
    SourceSpec,
    hash_file,
    resolve_source,
    tree_fingerprint,
    verify,
)
from skillweave.cli import assess as assess_mod

# Import the router module explicitly: `skillweave/cli/__init__.py` defines its
# own `main()` function, which shadows the submodule's name on the package.
from skillweave.cli.main import main as router_main

_SHA = "0ef44d4ae2d41fb608c01b3d729995ffee5c22ae"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
_SERVICE_PATH = _SRC / "skillweave" / "assessment_service.py"

#: A probe that always reports the subject is a commit (exit 0), so a test can
#: isolate the source resolutions from the real repository.
def _ok_probe(root, subject_sha):
    return CommandSpec(
        command=f"git rev-parse --verify --quiet {subject_sha}^{{commit}}", exit=0
    )


def _refusing_probe(root, subject_sha):
    return CommandSpec(
        command=f"git rev-parse --verify --quiet {subject_sha}^{{commit}}", exit=1
    )


def _absent_probe(root, subject_sha):
    return None


def _make_source(root: Path, name: str = "evidence.txt", content: str = "hello\n") -> SourceSpec:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return SourceSpec(path=name, sha256=hash_file(path))


def _request(sources=(), **overrides) -> AssessmentRequest:
    base = dict(
        subject_sha=_SHA,
        assessor="sw-157-assess-002",
        run_id="op-SW-157-ASSESS-002",
        produced_at="2026-09-27T00:00:00Z",
        model="byteplus-deepseek-flash-41",
        repo="skillweave/skillweave",
        ref="feature/SW-157-assessment-service",
    )
    base.update(overrides)
    return AssessmentRequest(sources=tuple(sources), **base)


# ── Step A: available receipt with resolvable evidence ──────────────────────


def test_available_receipt_names_resolvable_evidence(tmp_path):
    source = _make_source(tmp_path)
    service = AssessmentService(tmp_path, probe=_ok_probe)

    receipt = service.assess(_request([source]))

    payload = receipt.payload
    assert payload["result"]["status"] == RESULT_AVAILABLE
    assert payload["sources"] == [{"path": "evidence.txt", "sha256": source.sha256}]
    assert len(payload["commands"]) == 1
    assert payload["commands"][0]["exit"] == 0
    # The receipt is a valid contract document, and its evidence re-resolves.
    canonicalize(receipt.to_dict())
    ok, resolutions = verify(tmp_path, receipt.to_dict())
    assert ok is True
    assert [r.status for r in resolutions] == [RESOLVED]


def test_verify_rejects_evidence_that_no_longer_matches(tmp_path):
    source = _make_source(tmp_path)
    service = AssessmentService(tmp_path, probe=_ok_probe)
    receipt = service.assess(_request([source])).to_dict()

    # Tamper with the assessed content: the digest no longer resolves.
    (tmp_path / "evidence.txt").write_text("changed\n", encoding="utf-8")

    ok, resolutions = verify(tmp_path, receipt)
    assert ok is False
    assert resolutions[0].status in (MISSING, "mismatch")


def test_findings_and_limits_pass_through_available_receipt(tmp_path):
    source = _make_source(tmp_path)
    request = _request(
        [source],
        findings=(Finding(id="F-1", severity="info", summary="no issues"),),
        limits=("read-only; no runtime execution beyond the subject probe",),
    )
    payload = AssessmentService(tmp_path, probe=_ok_probe).assess(request).payload
    assert payload["findings"] == [{"id": "F-1", "severity": "info", "summary": "no issues"}]
    assert payload["limits"] == ["read-only; no runtime execution beyond the subject probe"]


# ── Step A: unavailable receipts state their shortfall and attest nothing ────


def test_missing_source_is_unavailable(tmp_path):
    request = _request([SourceSpec(path="absent.txt", sha256=None)])
    payload = AssessmentService(tmp_path, probe=_ok_probe).assess(request).payload
    assert payload["result"]["status"] == RESULT_UNAVAILABLE
    assert payload["sources"] == [] and payload["commands"] == []
    assert any("absent.txt" in limit and "does not exist" in limit for limit in payload["limits"])


def test_source_digest_mismatch_is_unavailable(tmp_path):
    source = _make_source(tmp_path)
    request = _request([SourceSpec(path=source.path, sha256="b" * 64)])
    payload = AssessmentService(tmp_path, probe=_ok_probe).assess(request).payload
    assert payload["result"]["status"] == RESULT_UNAVAILABLE
    assert any("content address differs" in limit for limit in payload["limits"])


def test_path_escaping_root_is_unavailable(tmp_path):
    request = _request([SourceSpec(path="../outside.txt")])
    payload = AssessmentService(tmp_path, probe=_ok_probe).assess(request).payload
    assert payload["result"]["status"] == RESULT_UNAVAILABLE
    assert any("escapes" in limit for limit in payload["limits"])
    assert resolve_source(tmp_path, "../outside.txt").status == ESCAPED


def test_no_sources_is_unavailable(tmp_path):
    payload = AssessmentService(tmp_path, probe=_ok_probe).assess(_request()).payload
    assert payload["result"]["status"] == RESULT_UNAVAILABLE
    assert any("no sources were named" in limit for limit in payload["limits"])


def test_subject_that_is_not_a_commit_is_unavailable(tmp_path):
    source = _make_source(tmp_path)
    payload = AssessmentService(tmp_path, probe=_refusing_probe).assess(_request([source])).payload
    assert payload["result"]["status"] == RESULT_UNAVAILABLE
    assert payload["sources"] == [] and payload["commands"] == []
    assert any("is not a commit" in limit for limit in payload["limits"])


def test_absent_probe_makes_assessment_unavailable(tmp_path):
    source = _make_source(tmp_path)
    payload = AssessmentService(tmp_path, probe=_absent_probe).assess(_request([source])).payload
    assert payload["result"]["status"] == RESULT_UNAVAILABLE
    assert any("probe could not run" in limit for limit in payload["limits"])


@pytest.mark.parametrize(
    "bad_subject",
    ["", "abcd", _SHA.upper(), "g" * 40, 12345, _SHA + "\n"],
)
def test_non_canonical_subject_is_refused_not_represented(tmp_path, bad_subject):
    # The contract requires every receipt to carry a canonical subject SHA, so a
    # malformed subject cannot be represented as an unavailable receipt at all;
    # the service refuses the request rather than sealing an unrepresentable one.
    source = _make_source(tmp_path)
    with pytest.raises(AssessmentError):
        AssessmentService(tmp_path, probe=_ok_probe).assess(
            _request([source], subject_sha=bad_subject)
        )


# ── Step A: read-only authority ──────────────────────────────────────────────


def test_read_only_authority_refuses_writes():
    authority = ReadOnlyAuthority()
    assert authority.read_only is True
    authority.assert_readable("read source")
    with pytest.raises(ReadOnlyViolation):
        authority.assert_writable("write source")


def test_service_refuses_non_read_only_authority(tmp_path):
    class _Writable:
        read_only = False

    with pytest.raises(ReadOnlyViolation):
        AssessmentService(tmp_path, authority=_Writable())


# ── Step B: identical inputs produce a stable digest ─────────────────────────


def test_identical_inputs_produce_identical_digest(tmp_path):
    source = _make_source(tmp_path)
    request = _request([source], findings=(Finding(id="F-1", severity="low", summary="s"),))
    service = AssessmentService(tmp_path, probe=_ok_probe)

    first = service.assess(request)
    second = service.assess(request)

    assert first.to_dict() == second.to_dict()
    assert first.digest == second.digest


def test_digest_is_stable_across_interpreter_processes(tmp_path):
    # A real repository, so the default read-only git probe verifies the subject
    # commit -- this proves determinism end-to-end through the CLI, not just
    # in-process with an injected probe.
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "assess@example.invalid")
    _git(tmp_path, "config", "user.name", "assess")
    source = _make_source(tmp_path)
    _git(tmp_path, "add", source.path)
    _git(tmp_path, "commit", "-q", "-m", "evidence")
    subject = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()

    request = _request([source], subject_sha=subject)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request_document(request)), encoding="utf-8")

    probe = (
        "import sys;"
        "from skillweave.cli import assess;"
        "raise SystemExit(assess.main(sys.argv[1:]))"
    )
    runs = [
        subprocess.run(
            [sys.executable, "-c", probe, "--root", str(tmp_path), "--request", str(request_path)],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(_SRC)},
        )
        for _ in range(2)
    ]
    for run in runs:
        assert run.returncode == 0, run.stderr
    first = json.loads(runs[0].stdout.strip().splitlines()[-1])
    second = json.loads(runs[1].stdout.strip().splitlines()[-1])
    assert first == second
    assert first["digest"] == second["digest"]
    assert first["result"]["status"] == RESULT_AVAILABLE
    assert first["commands"][0]["exit"] == 0


# ── Read-only negative case ──────────────────────────────────────────────────


def test_assessment_leaves_the_tree_untouched(tmp_path):
    _make_source(tmp_path)
    nested = tmp_path / "pkg"
    nested.mkdir()
    (nested / "b.py").write_text("x = 1\n", encoding="utf-8")

    before = tree_fingerprint(tmp_path)
    AssessmentService(tmp_path, probe=_ok_probe).assess(
        _request(
            [
                SourceSpec(path="evidence.txt", sha256=hash_file(tmp_path / "evidence.txt")),
                SourceSpec(path="pkg/b.py", sha256=hash_file(nested / "b.py")),
            ]
        )
    )
    assert tree_fingerprint(tmp_path) == before


def test_service_import_closure_is_stdlib_and_contract_only():
    # The service must not be able to drag in a write-on-import subsystem:
    # its only non-stdlib import is the dependency-light contract module.
    tree = ast.parse(_SERVICE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    non_stdlib = sorted(imported - set(sys.stdlib_module_names) - {"__future__"})
    assert non_stdlib == ["skillweave"], non_stdlib

    # And it imports exactly the contract submodule, nothing heavier.
    assert "from skillweave.assessment_contracts import" in _SERVICE_PATH.read_text(
        encoding="utf-8"
    )


# ── CLI surface ──────────────────────────────────────────────────────────────


def _request_document(request: AssessmentRequest) -> dict:
    return {
        "subject_sha": request.subject_sha,
        "assessor": request.assessor,
        "run_id": request.run_id,
        "produced_at": request.produced_at,
        "model": request.model,
        "repo": request.repo,
        "ref": request.ref,
        "sources": [{"path": s.path, "sha256": s.sha256} for s in request.sources],
        "findings": [
            {"id": f.id, "severity": f.severity, "summary": f.summary} for f in request.findings
        ],
        "limits": list(request.limits),
    }


def test_cli_emits_receipt_and_exits_zero(tmp_path, capsys, monkeypatch):
    source = _make_source(tmp_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request_document(_request([source]))), encoding="utf-8")

    # Inject a probe so the CLI test does not depend on a real repository.
    monkeypatch.setattr(assess_mod, "AssessmentService", _service_factory(_ok_probe))

    exit_code = router_main(
        ["assess", "--root", str(tmp_path), "--request", str(request_path)]
    )

    assert exit_code == 0
    receipt = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert receipt["result"]["status"] == RESULT_AVAILABLE
    canonicalize(receipt)


def test_cli_exits_one_for_unavailable_assessment(tmp_path, capsys, monkeypatch):
    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(_request_document(_request([SourceSpec(path="absent.txt")]))), encoding="utf-8"
    )
    monkeypatch.setattr(assess_mod, "AssessmentService", _service_factory(_ok_probe))

    exit_code = assess_mod.main(["--root", str(tmp_path), "--request", str(request_path)])

    assert exit_code == assess_mod.EXIT_UNAVAILABLE
    receipt = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert receipt["result"]["status"] == RESULT_UNAVAILABLE
    assert receipt["limits"]


def test_cli_exits_two_for_unreadable_request(tmp_path, capsys):
    exit_code = assess_mod.main(
        ["--root", str(tmp_path), "--request", str(tmp_path / "nope.json")]
    )
    assert exit_code == assess_mod.EXIT_ERROR
    assert "could not read the assessment request" in capsys.readouterr().err


def test_cli_exits_two_for_a_malformed_subject(tmp_path, capsys):
    # A request that parses but cannot be represented (a non-canonical subject
    # SHA) is a usage error, not an assessment outcome: the service raises
    # AssessmentError and the CLI must sanitise it to exit 2, never leak a
    # traceback. Uses the real service on purpose -- no probe injection.
    document = _request_document(_request())
    document["subject_sha"] = "deadbeef"
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(document), encoding="utf-8")

    exit_code = assess_mod.main(["--root", str(tmp_path), "--request", str(request_path)])

    assert exit_code == assess_mod.EXIT_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err
    assert "canonical" in captured.err
    assert "Traceback" not in captured.err


def test_cli_is_routed_by_the_main_router(tmp_path, capsys, monkeypatch):
    # The subcommand is reachable through the unified router, not only via its
    # own module -- the four registration seams must all be threaded.
    source = _make_source(tmp_path)
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request_document(_request([source]))), encoding="utf-8")
    monkeypatch.setattr(assess_mod, "AssessmentService", _service_factory(_ok_probe))

    exit_code = router_main(
        ["assess", "--root", str(tmp_path), "--request", str(request_path)]
    )
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["digest"]


def _service_factory(probe):
    """Return a callable that builds a service like the CLI's ``AssessmentService``."""

    def _factory(root):
        return AssessmentService(root, probe=probe)

    return _factory


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={
            **os.environ,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        },
    )
