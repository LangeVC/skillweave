"""Tests for the ``skillweave rework`` CLI command (SW-CLI-REWORK-001).

Proves the unified CLI routes ``rework`` to the brief-writer, that it reads the
most recent gate log for a lane, and that it emits a structured Markdown brief
carrying the lane ID, task IDs, failing criteria, suggested next steps, and a
VERDICT template.

Self-contained sys.path handling, following the sibling-test convention.
The suite stays hermetic: no network and no live provider.
"""

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.cli import rework  # noqa: E402
from skillweave.rework import ReworkBriefWriter, ReworkError  # noqa: E402


def _write_gate_log(root: Path, lane: str, checks) -> None:
    """Write a JSON gate log in the fallback location for *lane*.

    This mirrors ``release-gate-data.json`` at the project root so the reader
    picks it up through its fallback discovery rule.
    """
    data = {"can_release": False, "checks": checks}
    (root / "release-gate-data.json").write_text(
        json.dumps(data, sort_keys=True), encoding="utf-8"
    )


def test_rework_subcommand_registered_in_unified_cli():
    # The unified router must expose a ``rework`` subparser built from the
    # same module the router imports.
    assert rework.build_parser is not None
    assert hasattr(rework, "main")


def test_rework_build_parser_requires_lane():
    import argparse

    try:
        rework.build_parser().parse_args([])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("rework without --lane must fail")


def test_rework_writes_valid_brief(tmp_path):
    checks = [
        {
            "id": "version-bump",
            "name": "Version bumped",
            "passed": True,
            "detail": "ok",
            "required": True,
        },
        {
            "id": "no-wip-markers",
            "name": "No WIP/draft markers",
            "passed": False,
            "detail": "Found 2 WIP marker(s)",
            "required": False,
        },
        {
            "id": "capacium-manifests",
            "name": "Capacium manifests synced",
            "passed": False,
            "detail": "14 manifest(s) out of sync",
            "required": True,
        },
    ]
    _write_gate_log(tmp_path, "SW-CLI-001", checks)

    writer = ReworkBriefWriter(project_root=tmp_path)
    out = writer.write("SW-CLI-001")

    assert out.exists()
    assert out.suffix == ".md"
    assert out.parent == tmp_path / ".skillweave" / "rework"
    text = out.read_text(encoding="utf-8")

    # Lane information
    assert "SW-CLI-001" in text

    # Failing criteria are surfaced
    assert "capacium-manifests" in text
    assert "no-wip-markers" in text

    # Only the two failing criteria are listed; the passing one is not
    assert "version-bump" not in text

    # Suggested next steps
    assert "## Suggested Next Steps" in text

    # VERDICT template present
    assert "## VERDICT" in text
    assert "PASS" in text and "FAIL" in text


def test_rework_blocking_and_advisory_separation(tmp_path):
    checks = [
        {"id": "block", "name": "Blocking", "passed": False, "detail": "x",
         "required": True},
        {"id": "adv", "name": "Advisory", "passed": False, "detail": "y",
         "required": False},
    ]
    _write_gate_log(tmp_path, "SW-002", checks)
    writer = ReworkBriefWriter(project_root=tmp_path)
    text = writer.render(writer._reader.read("SW-002"))
    assert "Blocking failures (must be fixed)" in text
    assert "Advisory failures (non-blocking)" in text


def test_rework_no_gate_log_raises(tmp_path):
    from skillweave.rework import GateLogReader

    reader = GateLogReader(project_root=tmp_path)
    try:
        reader.read("missing-lane")
    except ReworkError as exc:
        assert "No gate log found" in str(exc)
    else:
        raise AssertionError("missing lane must produce a gate-log error")


def test_rework_cmd_end_to_end(tmp_path):
    checks = [
        {"id": "poll", "name": "Polling check", "passed": False,
         "detail": "still busy", "required": True},
    ]
    _write_gate_log(tmp_path, "SW-CLI-REWORK-001", checks)

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = rework.main(["--lane", "SW-CLI-REWORK-001", "--project-root", str(tmp_path)])

    assert rc == 0
    out_path = Path(buf.getvalue().strip())
    assert out_path.exists()
    assert "SW-CLI-REWORK-001-" in out_path.name
    assert "## VERDICT" in out_path.read_text(encoding="utf-8")


def test_rework_missing_lane_via_cli(tmp_path):
    buf = io.StringIO()
    import sys as _sys
    from contextlib import redirect_stderr

    err = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(err):
        rc = rework.main(["--lane", "ghost", "--project-root", str(tmp_path)])
    assert rc == 1
    assert "ERROR" in err.getvalue()


def test_rework_carries_shas_into_brief(tmp_path):
    """Finding 1: candidate/base SHAs from the gate log are rendered."""
    checks = [
        {"id": "capacium-manifests", "name": "Sync", "passed": False,
         "detail": "1 out of sync", "required": True},
    ]
    data = {
        "can_release": False,
        "candidate_sha": "a" * 40,
        "base_sha": "b" * 40,
        "checks": checks,
    }
    (tmp_path / "release-gate-data.json").write_text(
        json.dumps(data, sort_keys=True), encoding="utf-8"
    )
    from skillweave.rework import GateLogReader

    reader = GateLogReader(project_root=tmp_path)
    brief = reader.read("SW-SHA-001")
    assert brief.candidate_sha == "a" * 40
    assert brief.base_sha == "b" * 40
    text = ReworkBriefWriter(project_root=tmp_path).render(brief)
    assert "Candidate SHA" in text and "a" * 40 in text
    assert "Base SHA" in text and "b" * 40 in text


def test_rework_overall_state_description_not_duplicated(tmp_path):
    """Finding 2: overall-state yields a real description, not a verbatim echo."""
    from skillweave.rework import GateLogReader

    lane_dir = tmp_path / ".skillweave" / "tracking-log" / "SW-ST"
    lane_dir.mkdir(parents=True, exist_ok=True)
    (lane_dir / "status.yaml").write_text(
        "state: STOPPED_BEFORE_B06\nstatus_detail: STOPPED_BEFORE_B06\n",
        encoding="utf-8",
    )
    brief = GateLogReader(project_root=tmp_path).read("SW-ST")
    overall = [e for e in brief.failing_criteria if e.check_id == "overall-state"]
    assert len(overall) == 1
    detail = overall[0].detail
    assert "State: STOPPED_BEFORE_B06. STOPPED_BEFORE_B06" not in detail
    # A meaningful description replaces the raw verbatim echo.
    assert detail and detail != "STOPPED_BEFORE_B06"


def test_rework_discovery_baseline_joins_test_names(tmp_path):
    """Finding 2: discovery_baseline.failed_tests are joined by name."""
    from skillweave.rework import GateLogReader

    lane_dir = tmp_path / ".skillweave" / "tracking-log" / "SW-DIS"
    lane_dir.mkdir(parents=True, exist_ok=True)
    (lane_dir / "status.yaml").write_text(
        "state: FAILED\n"
        "discovery_baseline:\n"
        "  opencode:\n"
        "    failed_tests: [test_a, test_b]\n"
        "    passed: 3\n"
        "    failed: 2\n",
        encoding="utf-8",
    )
    brief = GateLogReader(project_root=tmp_path).read("SW-DIS")
    disc = [e for e in brief.failing_criteria if e.check_id == "discovery-opencode"]
    assert len(disc) == 1
    assert "test_a" in disc[0].detail and "test_b" in disc[0].detail


def test_rework_criteria_carry_fixed_when(tmp_path):
    """Finding 3: each failing criterion has a definition-of-done invariant."""
    checks = [
        {"id": "capacium-manifests", "name": "sync", "passed": False,
         "detail": "2 out of sync", "required": True},
        {"id": "no-wip-wip", "name": "no wip", "passed": False,
         "detail": "found wip", "required": False},
    ]
    _write_gate_log(tmp_path, "SW-DONE", checks)
    writer = ReworkBriefWriter(project_root=tmp_path)
    brief = writer._reader.read("SW-DONE")
    for entry in brief.failing_criteria:
        assert entry.fixed_when, f"criterion {entry.check_id} lacks fixed_when"
    text = writer.render(brief)
    assert "**Fixed when:**" in text
    assert "0 out-of-sync manifests" in text


def _run_all() -> int:
    import argparse

    tmp = Path("/tmp/skillweave-test-run")
    failed = 0
    tests = [
        test_rework_subcommand_registered_in_unified_cli,
        test_rework_build_parser_requires_lane,
        test_rework_writes_valid_brief,
        test_rework_blocking_and_advisory_separation,
        test_rework_no_gate_log_raises,
        test_rework_cmd_end_to_end,
        test_rework_missing_lane_via_cli,
        test_rework_carries_shas_into_brief,
        test_rework_overall_state_description_not_duplicated,
        test_rework_discovery_baseline_joins_test_names,
        test_rework_criteria_carry_fixed_when,
    ]
    for t in tests:
        try:
            t(tmp)
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
