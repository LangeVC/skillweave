"""Tests for ``run.py --rework`` and the rework CLI exit-code contract.

Covers findings 5 and 6 of the SW-151 CLI rework round:
  * ``run.py --rework`` produces the single structured brief artifact and is
    routed through ``ReworkBriefWriter`` (not a diverging inline string).
  * ``skillweave rework`` returns exit code 2 on unexpected system errors so
    that the CLI contract (1 = user error, 2 = system error) is actually held.

Self-contained sys.path handling follows the sibling-test convention.
The suite stays hermetic: no network and no live provider.
"""

import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.cli import run as run_cli_module  # noqa: E402
from skillweave.cli import rework as rework_module  # noqa: E402


def _write_gate_log(root: Path, lane: str, checks) -> None:
    """Write a failing release-gate JSON carrying candidate/base SHAs."""
    data = {
        "can_release": False,
        "candidate_sha": "0" * 40,
        "base_sha": "1" * 40,
        "checks": checks,
    }
    (root / "release-gate-data.json").write_text(
        json.dumps(data, sort_keys=True), encoding="utf-8"
    )


def _failing_command():
    return [sys.executable, "-c", "raise ValueError('boom')"]


def test_run_rework_writes_structured_brief_from_failed_gate(tmp_path, monkeypatch):
    """simulate-failed-gate + --rework path (SW-CLI-REWORK PRD verification)."""
    checks = [
        {
            "id": "capacium-manifests",
            "name": "Capacium manifests synced",
            "passed": False,
            "detail": "2 manifest(s) out of sync",
            "required": True,
        },
    ]
    _write_gate_log(tmp_path, "SW-CLI-001", checks)

    # Writer resolves project_root from cwd; run in the fixture dir.
    monkeypatch.chdir(tmp_path)

    db = str(tmp_path / "s.db")
    art = str(tmp_path / "artifacts")
    argv = [
        "skillweave.cli.run",
        "--tool", "test-tool",
        "--model", "test-model",
        "--subject-repo", "test-repo",
        "--subject-commit", "0" * 40,
        "--db-path", db,
        "--artifacts-path", art,
        "--lane", "SW-CLI-001",
        "--rework",
        "--",
    ] + _failing_command()

    monkeypatch.setattr(sys, "argv", argv)
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)

    rc = run_cli_module.main()

    assert rc == 0
    payload = json.loads(out.getvalue().strip())
    assert payload.get("gate_state") == "fail"
    rework_brief = payload["rework_brief"]
    # The brief is a structured dict pointing at the single .md artifact,
    # not a weaker inline string.
    assert isinstance(rework_brief, dict)
    assert rework_brief["lane"] == "SW-CLI-001"
    brief_path = Path(rework_brief["brief_path"])
    assert brief_path.exists()
    text = brief_path.read_text(encoding="utf-8")
    assert "## VERDICT" in text
    assert "capacium-manifests" in text
    # The candidate SHA is carried from the gate log into the brief.
    assert "0" * 40 in text


def test_run_rework_absent_without_failed_gate(tmp_path, monkeypatch):
    """A passing gate must not emit a rework brief even with --rework."""
    monkeypatch.chdir(tmp_path)
    db = str(tmp_path / "s.db")
    art = str(tmp_path / "artifacts")
    argv = [
        "skillweave.cli.run",
        "--tool", "test-tool",
        "--model", "test-model",
        "--subject-repo", "test-repo",
        "--subject-commit", "0" * 40,
        "--db-path", db,
        "--artifacts-path", art,
        "--lane", "SW-CLI-001",
        "--rework",
        "--",
        sys.executable, "-c", "print('ok')",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    rc = run_cli_module.main()
    assert rc == 0
    payload = json.loads(out.getvalue().strip())
    assert payload.get("gate_state") != "fail"
    assert "rework_brief" not in payload


def test_rework_exit_code_2_on_unexpected_error(tmp_path, monkeypatch):
    """Finding 6: unexpected errors return exit code 2, not 1."""
    from skillweave.rework.brief import ReworkBriefWriter

    def _boom(_lane):
        raise RuntimeError("unexpected system failure")

    monkeypatch.setattr(ReworkBriefWriter, "write", _boom)

    err = io.StringIO()
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = rework_module.main(["--lane", "SW-CLI-001", "--project-root", str(tmp_path)])
    assert rc == 2
    assert "Unexpected error" in err.getvalue()
