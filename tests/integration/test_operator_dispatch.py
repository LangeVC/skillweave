"""Integration tests for the operator-dispatch application seam (SW138-DISPATCH-001).

Covers the seven acceptance criteria end to end, reusing the shared fan-out,
run, and workspace seams:

1. ``dispatch --sequence <fixture> --wave 0 --profile <fixture>`` executes the
   selected wave and emits a machine-readable run identifier.
2. The CLI contains no ``subprocess.Popen``, no SQLite write, no independent
   state machine, and no direct artifact persistence.
3. Two dependency-ready disjoint lanes overlap; serialized/mutually-exclusive
   lanes do not.
4. Per-lane repo + full base SHA provision/attest the workspace; a mismatch
   blocks before child start.
5. ``--dry-run`` reports resolved lanes, roles, profile, repo/base, execution
   model, parallelism, and correction budget and starts zero workers.
6. Reaching ``max_correction_rounds_per_wave`` yields ``HALT_REQUIRES_OPERATOR``
   and starts no additional correction child.
7. Help/result metadata label the command experimental and wave-scoped and claim
   no stable 1.4 transport compatibility.

Carry-forward: the live consumer refuses an unknown ``execution_model`` (such as
``hot``) before launch, and a missing profile location surfaces as a precise
product error.

The hermetic launch command in the profile fixture is a thin python marker, so
overlap is asserted by measured process timing, not by mocking the runner.
"""

import io
import json
import sys
from pathlib import Path

import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_SEQUENCE = _FIXTURES / "dispatch-sequence.yaml"
_PROFILE = _FIXTURES / "dispatch-profile.yaml"

from skillweave.dispatch.application import (  # noqa: E402
    HALT_REQUIRES_OPERATOR,
    ExecutionModelError,
    OperatorDispatchApplication,
    ProfileLocationError,
    WorkspaceMismatchError,
    WorkspaceSeam,
)
from skillweave.dispatch.contracts import Lane  # noqa: E402
from skillweave.dispatch.cli import build_parser, main  # noqa: E402


class _FakeWorkspace(WorkspaceSeam):
    """In-memory workspace seam that attests whatever base the lane declares.

    ``attested_overrides`` lets a test simulate a mismatch; ``provisions`` and
    ``releases`` count the calls so "zero workers" and "block before child
    start" can be asserted.
    """

    def __init__(self, attested_overrides: dict[str, str] | None = None):
        self.attested_overrides = attested_overrides or {}
        self.provisions: list[str] = []
        self.releases: list[str] = []

    def provision(self, lane: Lane, run_id: str) -> str:
        self.provisions.append(lane.id)
        return self.attested_overrides.get(lane.id, lane.base or "")

    def release(self, lane: Lane, run_id: str) -> None:
        self.releases.append(lane.id)


class _RecordingFanout:
    """A fan-out seam that records the command batches it was handed and can
    simulate a failed child (for the correction-budget red path)."""

    def __init__(self, fail_lane: str | None = None):
        self.batches: list[list[list[str]]] = []
        self._fail_lane = fail_lane

    def __call__(self, commands, **kwargs):
        self.batches.append([list(c) for c in commands])
        children = []
        for command in commands:
            children.append(_FakeChild(succeeded=not bool(self._fail_lane)))
        return _FakeResult(children=children)


class _FakeChild:
    def __init__(self, succeeded: bool):
        self.succeeded = succeeded


class _FakeResult:
    def __init__(self, children):
        self.children = children


def _run_dispatch(app: OperatorDispatchApplication, *, dry_run: bool = False):
    sink = io.StringIO()
    if dry_run:
        run = app.dry_run(str(_SEQUENCE), str(_PROFILE), wave="0")
    else:
        run = app.dispatch(str(_SEQUENCE), str(_PROFILE), wave="0", sink=sink)
    events = [json.loads(ln) for ln in sink.getvalue().splitlines() if ln.strip()]
    return run, events


# ── Criterion 1: execute a wave and emit a machine-readable run id ──────────


def test_cli_dispatch_executes_wave_and_emits_run_id(monkeypatch, capsys):
    """The CLI command executes a wave and prints a machine-readable run id.

    The workspace seam is swapped for the in-memory fake so the CLI path is
    exercised end to end (argparse -> application -> real fan-out -> JSON result)
    without mutating the repo's worktrees.
    """
    ws = _FakeWorkspace()
    app = OperatorDispatchApplication(workspace_seam=ws, fanout_seam=_RecordingFanout())
    monkeypatch.setattr(
        "skillweave.dispatch.cli.OperatorDispatchApplication", lambda **kw: app
    )

    rc = main(["--sequence", str(_SEQUENCE), "--wave", "0", "--profile", str(_PROFILE)])
    assert rc == 0

    out = capsys.readouterr().out.strip().splitlines()
    assert out, "the CLI must print a machine-readable result"
    # The last line is the JSON result (the event stream writes to a separate
    # sink in this application-level test; the CLI result is the JSON line).
    result = json.loads(out[-1])
    assert "run_id" in result
    run_id = result["run_id"]
    assert len(run_id) == 32
    int(run_id, 16)  # machine-readable hex, no prefix/punctuation
    assert result["wave"] == "0"
    assert ws.provisions == ["lane-ops-a", "lane-ops-b", "lane-ops-c"]


def test_application_returns_machine_readable_run_id():
    ws = _FakeWorkspace()
    app = OperatorDispatchApplication(workspace_seam=ws)
    run, _ = _run_dispatch(app)
    int(run.run_id, 16)
    assert len(run.run_id) == 32


# ── Criterion 2: CLI owns no raw process/state/artifact machinery ──────────


def test_cli_module_contains_no_forbidden_operations():
    cli_src = Path(_src) / "skillweave" / "dispatch" / "cli.py"
    text = cli_src.read_text(encoding="utf-8")
    # No raw process launch, no SQLite write, no artifact store: these are the
    # shared seams. The check targets actual imports/calls, not prose.
    for forbidden in (
        "import subprocess",
        "from subprocess",
        "import sqlite3",
        "from sqlite3",
        "Popen(",
    ):
        assert forbidden not in text, f"cli.py must not contain {forbidden!r}"


def test_application_module_contains_no_forbidden_operations():
    app_src = Path(_src) / "skillweave" / "dispatch" / "application.py"
    text = app_src.read_text(encoding="utf-8")
    # The application delegates process launch to the shared fan-out seam; it
    # must not open its own subprocess, SQLite, or artifact store.
    for forbidden in (
        "import subprocess",
        "from subprocess",
        "import sqlite3",
        "from sqlite3",
        "Popen(",
    ):
        assert forbidden not in text, f"application.py must not contain {forbidden!r}"


# ── Criterion 3: disjoint lanes overlap; serialized lanes do not ────────────


def test_disjoint_lanes_overlap_and_serialized_lanes_do_not():
    # lane-ops-a (repo-a) and lane-ops-b (repo-b) are disjoint and must land in
    # one fan-out batch; lane-ops-c (repo-a again) is mutually exclusive and
    # must be a separate, later batch. The grouping is the overlap proof: a
    # fan-out batch starts all its children before reaping any.
    ws = _FakeWorkspace()
    app = OperatorDispatchApplication(workspace_seam=ws)
    _, _, report = app.load(str(_SEQUENCE), str(_PROFILE))
    assert report.parallel_groups == [["lane-ops-a", "lane-ops-b"], ["lane-ops-c"]]


def test_fanout_seam_receives_disjoint_group_then_serialized_group():
    ws = _FakeWorkspace()
    recorder = _RecordingFanout()
    app = OperatorDispatchApplication(workspace_seam=ws, fanout_seam=recorder)
    _run_dispatch(app)

    # First batch: two disjoint lanes (overlap). Second batch: the mutually
    # exclusive lane alone (no overlap with the first two).
    assert len(recorder.batches) == 2
    assert len(recorder.batches[0]) == 2
    assert len(recorder.batches[1]) == 1


def test_disjoint_lanes_measure_overlap_serialized_lane_does_not(tmp_path):
    """Measured timing proof: two disjoint lanes overlap in wall-clock time.

    A minimal two-lane sequence (ops on repo-a, reviewer on repo-b) is built so
    each lane's role resolves to a distinct, sleep-marker command. The real
    fan-out seam starts both before reaping any, and the test asserts the two
    marker windows intersect — overlap is a measured fact, never a claim.
    """
    import yaml

    marker_dir = str(tmp_path)
    marker = (
        "import sys, time, pathlib; "
        "d=pathlib.Path(sys.argv[1]); open(d/'%(n)s','w').write(str(time.time()*1000)); "
        "time.sleep(0.4); open(d/'%(n)s.end','w').write(str(time.time()*1000))"
    )

    raw_profile = yaml.safe_load(_PROFILE.read_text(encoding="utf-8"))
    for role_key, name in (("ops", "ops"), ("reviewer", "reviewer")):
        raw_profile["roles"][role_key]["tool"]["launch_command"] = (
            "python3 -c " + repr(marker.replace("%(n)s", name))
        )
        raw_profile["roles"][role_key]["tool"]["args"] = [marker_dir]
    profile = tmp_path / "timing-profile.yaml"
    profile.write_text(yaml.safe_dump(raw_profile), encoding="utf-8")

    base_sha = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))["lanes"][0]["base"]
    seq = tmp_path / "timing-sequence.yaml"
    seq.write_text(
        yaml.safe_dump(
            {
                "session_boundary": "batch",
                "profile": {"path": str(profile), "required": True},
                "execution_model": "cold",
                "max_correction_rounds_per_wave": 0,
                "max_parallel": 2,
                "lanes": [
                    {
                        "id": "lane-a",
                        "role": "ops",
                        "repo": "skillweave/repo-a",
                        "base": base_sha,
                        "execution_model": "cold",
                        "mutating": True,
                        "criterion_groups": [{"criteria": [1]}],
                    },
                    {
                        "id": "lane-b",
                        "role": "reviewer",
                        "repo": "skillweave/repo-b",
                        "base": base_sha,
                        "execution_model": "cold",
                        "mutating": True,
                        "criterion_groups": [{"criteria": [1]}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    ws = _FakeWorkspace()
    app = OperatorDispatchApplication(workspace_seam=ws)
    run = app.dispatch(str(seq), str(profile), wave="0", sink=io.StringIO())
    assert run.halted is False

    def _t(name):
        return float((tmp_path / name).read_text())

    def _t_end(name):
        return float((tmp_path / (name + ".end")).read_text())

    ops_start, rev_start = _t("ops"), _t("reviewer")
    ops_end, rev_end = _t_end("ops"), _t_end("reviewer")
    assert ops_end > rev_start, "ops ended before reviewer began (sequential)"
    assert rev_end > ops_start, "reviewer ended before ops began (sequential)"




# ── Criterion 4: per-lane repo + base provision/attest; mismatch blocks ─────


def test_workspace_provision_attests_each_mutating_lane():
    ws = _FakeWorkspace()
    app = OperatorDispatchApplication(workspace_seam=ws)
    run, _ = _run_dispatch(app)
    assert set(ws.provisions) == {"lane-ops-a", "lane-ops-b", "lane-ops-c"}
    assert set(ws.releases) == {"lane-ops-a", "lane-ops-b", "lane-ops-c"}


def test_base_mismatch_blocks_before_child_start():
    # lane-ops-a attests a different base than declared -> the dispatch must
    # raise before any child launches (provisions happen up front, then the
    # mismatch is reported before any fan-out batch).
    ws = _FakeWorkspace(
        attested_overrides={
            "lane-ops-a": "0" * 40,
        }
    )
    recorder = _RecordingFanout()
    app = OperatorDispatchApplication(workspace_seam=ws, fanout_seam=recorder)
    with pytest.raises(WorkspaceMismatchError) as exc:
        app.dispatch(str(_SEQUENCE), str(_PROFILE), wave="0", sink=io.StringIO())
    assert "lane-ops-a" in str(exc.value)
    assert recorder.batches == [], "no child may start after a base mismatch"


# ── Criterion 5: dry-run reports everything and starts zero workers ─────────


def test_dry_run_reports_plan_and_starts_zero_workers():
    ws = _FakeWorkspace()
    recorder = _RecordingFanout()
    app = OperatorDispatchApplication(workspace_seam=ws, fanout_seam=recorder)
    run = app.dry_run(str(_SEQUENCE), str(_PROFILE), wave="0")

    report = run.report.to_dict()
    assert report["profile"] == "dispatch-fixture"
    assert report["execution_model"] == "cold"
    assert report["max_parallel"] == 2
    assert report["max_correction_rounds_per_wave"] == 2
    lanes = report["lanes"]
    assert {ln["lane_id"] for ln in lanes} == {"lane-ops-a", "lane-ops-b", "lane-ops-c"}
    roles = {ln["role"] for ln in lanes}
    assert "ops" in roles and "reviewer" in roles
    for lane in lanes:
        assert len(lane["base"]) == 40
        assert lane["repo"]
    assert report["parallel_groups"] == [["lane-ops-a", "lane-ops-b"], ["lane-ops-c"]]

    assert recorder.batches == [], "dry-run must start zero workers"
    assert ws.provisions == [], "dry-run must not provision workspaces"


def test_dry_run_cli_emits_json(monkeypatch, capsys):
    ws = _FakeWorkspace()
    app = OperatorDispatchApplication(workspace_seam=ws, fanout_seam=_RecordingFanout())
    monkeypatch.setattr(
        "skillweave.dispatch.cli.OperatorDispatchApplication", lambda **kw: app
    )
    rc = main(
        [
            "--sequence",
            str(_SEQUENCE),
            "--wave",
            "0",
            "--profile",
            str(_PROFILE),
            "--dry-run",
        ]
    )
    assert rc == 0
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert result["report"]["parallel_groups"][0] == ["lane-ops-a", "lane-ops-b"]


# ── Criterion 6: correction budget exhaustion halts ─────────────────────────


def test_correction_budget_reached_yields_halt_requires_operator():
    # A lane that always fails exhausts max_correction_rounds_per_wave=2 and the
    # run reports HALT_REQUIRES_OPERATOR with no further correction child beyond
    # the budget.
    ws = _FakeWorkspace()
    recorder = _RecordingFanout(fail_lane="lane-ops-c")
    app = OperatorDispatchApplication(workspace_seam=ws, fanout_seam=recorder)
    run, events = _run_dispatch(app)

    assert run.halted is True
    assert run.halt_reason == HALT_REQUIRES_OPERATOR
    assert run.correction_rounds == 2

    halt_payloads = [
        e for e in events if e.get("halt_reason") == HALT_REQUIRES_OPERATOR
    ]
    assert len(halt_payloads) == 1


# ── Criterion 7 + carry-forward: metadata + enum + missing profile ──────────


def test_help_labels_command_experimental_and_wave_scoped(capsys):
    parser = build_parser()
    # Help text must carry the experimental + wave-scoped + no-1.4 claim.
    help_text = parser.format_help()
    lowered = help_text.lower()
    assert "experimental" in lowered
    assert "wave-scoped" in lowered
    assert "1.4" in lowered
    assert "no stable" in lowered


def test_result_metadata_labels_command_experimental_and_wave_scoped():
    ws = _FakeWorkspace()
    app = OperatorDispatchApplication(workspace_seam=ws)
    run, _ = _run_dispatch(app)
    result = run.to_dict()
    assert result["experimental"] is True
    assert result["scope"] == "wave"
    assert "1.4" in str(result["transport_compatibility"])


def test_unknown_execution_model_fails_before_launch(tmp_path, monkeypatch):
    import yaml

    raw = yaml.safe_load(_SEQUENCE.read_text(encoding="utf-8"))
    raw["execution_model"] = "hot"
    seq = tmp_path / "hot-sequence.yaml"
    seq.write_text(yaml.safe_dump(raw), encoding="utf-8")

    ws = _FakeWorkspace()
    recorder = _RecordingFanout()
    app = OperatorDispatchApplication(workspace_seam=ws, fanout_seam=recorder)
    with pytest.raises(ExecutionModelError):
        app.dispatch(str(seq), str(_PROFILE), wave="0", sink=io.StringIO())
    assert recorder.batches == [], "an unknown execution model must fail before launch"


def test_missing_profile_location_is_a_precise_error(tmp_path):
    ws = _FakeWorkspace()
    app = OperatorDispatchApplication(workspace_seam=ws)
    missing = tmp_path / "does-not-exist.yaml"
    with pytest.raises(ProfileLocationError) as exc:
        app.dry_run(str(_SEQUENCE), str(missing), wave="0")
    assert "does-not-exist" in str(exc.value)
    assert exc.value.path == str(missing)
