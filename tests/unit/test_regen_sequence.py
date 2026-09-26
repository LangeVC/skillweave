#!/usr/bin/env python3
"""Unit tests for the canonical dispatch script (SW-BRIEF-001).

Covers the review-brief generator, the ``--from-prd`` sequence generator, and
the PRD-injection seam without touching the network. The criteria exercised:

1. ``--generate-review-briefs`` writes exactly one
   ``review-brief-<lane_id>.md`` per lane, and each brief carries the lane ID,
   the task IDs (``dispatches`` / ``steps``), the acceptance criteria
   (``criteria`` / ``gates``), suggested verification steps, and a VERDICT
   template.
2. ``--inject-prd`` copies the governing artifact ``prd.json`` (and ``prd.md``
   when present) from a PRD directory into the worktree root's ``.skillweave/``.
   The injection is keyed to the same ``prd.json`` that ``--from-prd`` consumes.
3. ``build_execution_sequences`` round-trips a real, operator-authored PRD
   (``sw-route-001-dispatch-seam-prd.json``) end to end: PRD JSON -> sequence ->
   review briefs, and the generated sequence + injected PRD are the artifacts a
   live dispatch consumes.

The briefs YAML is a build-format fixture (``final_assembly`` is not required;
the build contract is ``phases`` + ``parallel_lanes``/``serialized_lanes``).
Self-contained ``sys.path`` handling follows the ``test_dispatch_contract.py``
convention.
"""

import json
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "regen-sequence.py"
_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
_FIXTURE = _FIXTURES / "regen-sequence-brief-input.yaml"
#: A real, operator-authored PRD in the generator's expected shape (a
#: ``sequence`` block plus one ``acceptanceCriteria`` per task). Copied verbatim
#: from skillweave-planning/.skillweave/planning/prds/sw-route-001-dispatch-seam.
_REAL_PRD_DIR = _FIXTURES / "sw-route-001-dispatch-seam"
_REAL_PRD_JSON = _REAL_PRD_DIR / "prd.json"

import importlib.util

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_spec = importlib.util.spec_from_file_location("regen_sequence", _SCRIPT)
rs = importlib.util.module_from_spec(_spec)
sys.modules["regen_sequence"] = rs  # dataclasses resolves __module__ via sys.modules
_spec.loader.exec_module(rs)  # type: ignore[union-attr]


def _run_cli(argv):
    import io
    from contextlib import redirect_stderr, redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(io.StringIO()):
        rc = rs.main(argv)
    return rc, buf.getvalue()


def test_generate_review_briefs_writes_one_brief_per_lane():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        written = rs.generate_review_briefs(_FIXTURE, out)
        names = {p.name for p in written}
        assert "review-brief-lane-alpha.md" in names
        assert "review-brief-lane-beta.md" in names
        assert "review-brief-lane-gamma.md" in names
        assert len(written) == 3
        for path in written:
            assert path.exists()
            text = path.read_text(encoding="utf-8")
            assert "## VERDICT" in text
            assert "VERDICT: PASS | FAIL | DEFER" in text


def test_brief_carries_lane_id_task_ids_and_criteria():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        rs.generate_review_briefs(_FIXTURE, out)
        alpha = (out / "review-brief-lane-alpha.md").read_text(encoding="utf-8")
        assert "- Lane ID: lane-alpha" in alpha
        assert "- ALPHA-001" in alpha
        assert "- ALPHA-002" in alpha
        assert "alpha criterion one" in alpha
        assert "alpha criterion two" in alpha
        assert "run tests/test_alpha.py" in alpha
        assert "## Suggested Verification Steps" in alpha


def test_brief_reads_gates_as_acceptance_criteria():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        rs.generate_review_briefs(_FIXTURE, out)
        gamma = (out / "review-brief-lane-gamma.md").read_text(encoding="utf-8")
        assert "gamma criterion one" in gamma
        assert "gamma criterion two" in gamma
        assert "gamma criterion three" in gamma
        assert "gamma gate" in gamma
        assert "GAMMA-001" in gamma


def test_cli_generate_review_briefs_flag():
    with tempfile.TemporaryDirectory() as tmp:
        rc, out = _run_cli(["--generate-review-briefs", str(_FIXTURE), "--out", tmp])
        assert rc == 0
        files = list(Path(tmp).glob("review-brief-*.md"))
        assert len(files) == 3
        assert "regen-sequence: wrote" in out


def test_inject_prd_copies_governing_prd_json_into_worktree():
    with tempfile.TemporaryDirectory() as tmp:
        prd_dir = Path(tmp) / "prd"
        repo = Path(tmp) / "repo"
        prd_dir.mkdir()
        (prd_dir / "prd.json").write_text(
            '{"tasks": [{"id": "T1", "acceptanceCriteria": ["must be green"]}]}',
            encoding="utf-8",
        )
        (prd_dir / "prd.md").write_text("# My PRD\nbody\n", encoding="utf-8")
        target = rs.inject_prd(prd_dir, repo)
        # The governing artifact is prd.json, and the narrative is carried too.
        assert target == repo / ".skillweave" / "prd.json"
        assert target.read_text(encoding="utf-8") == (
            '{"tasks": [{"id": "T1", "acceptanceCriteria": ["must be green"]}]}'
        )
        assert (repo / ".skillweave" / "prd.md").read_text(
            encoding="utf-8"
        ) == "# My PRD\nbody\n"


def test_inject_prd_missing_prd_json_raises():
    with tempfile.TemporaryDirectory() as tmp:
        prd_dir = Path(tmp) / "empty"
        prd_dir.mkdir()
        try:
            rs.inject_prd(prd_dir, Path(tmp) / "repo")
        except FileNotFoundError as exc:
            assert "prd.json" in str(exc)
        else:
            raise AssertionError("expected FileNotFoundError")


def test_inject_prd_real_prd_carries_governing_requirements():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        target = rs.inject_prd(_REAL_PRD_DIR, repo)
        injected = json.loads(target.read_text(encoding="utf-8"))
        # The requirements a lane must honour live in prd.json: the task list,
        # the acceptance criteria, and the creates/modifies paths.
        assert any(t["id"] == "SW-RT-001" for t in injected["tasks"])
        task = next(t for t in injected["tasks"] if t["id"] == "SW-RT-001")
        assert task["acceptanceCriteria"], "governing acceptance criteria injected"
        assert (repo / ".skillweave" / "prd.md").is_file()


def test_cli_inject_prd_flag():
    with tempfile.TemporaryDirectory() as tmp:
        prd_dir = Path(tmp) / "prd"
        repo = Path(tmp) / "repo"
        prd_dir.mkdir()
        (prd_dir / "prd.json").write_text('{"tasks": []}', encoding="utf-8")
        rc, out = _run_cli(["--inject-prd", str(prd_dir), "--repo", str(repo)])
        assert rc == 0
        assert (repo / ".skillweave" / "prd.json").exists()
        assert "regen-sequence: injected" in out


def test_from_prd_builds_sequence_from_real_prd():
    """Finding 3: ``build_execution_sequences`` proven against real data."""
    prd = json.loads(_REAL_PRD_JSON.read_text(encoding="utf-8"))
    sequence = rs.build_execution_sequences(prd)
    assert sequence["sequence_id"] == "sw-route"
    assert sequence["sequence_type"] == "build"
    assert sequence["branch"] == prd["sequence"]["branch"]
    # Every phase carries lanes, and the report is empty (no dispatches were lost).
    all_lanes = [
        lane
        for phase in sequence["phases"]
        for lane in phase.get("parallel_lanes", []) + phase.get("serialized_lanes", [])
    ]
    assert all_lanes, "real PRD produced at least one lane"
    lane_ids = {lane["id"] for lane in all_lanes}
    assert "lane-sw-rt-001" in lane_ids
    assert "lane-sw-rt-r" in lane_ids  # the reviewer lane survives the round-trip
    # The generator flags the shared write surface as mutually exclusive.
    assert any(
        mx["surface"] == "src/skillweave/routing/faigate_adapter.py"
        for mx in sequence["mutual_exclusion"]
    )
    # Required top-level keys survive from the PRD's sequence block.
    for key in rs.SEQUENCE_REQUIRED_KEYS:
        assert key in sequence, f"sequence missing {key}"


def test_cli_from_prd_real_round_trip_to_briefs():
    """Findings 2+3: a live dispatch path consumes generated artifacts.

    Runs the exact flow a cold dispatch uses: PRD JSON -> sequence YAML ->
    one review brief per lane -> injected PRD, all via the CLI against real
    data. The generated sequence and the injected prd.json are the artifacts a
    dispatched lane reads.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        # --from-prd: PRD JSON -> execution-sequences.yaml
        rc, out = _run_cli(["--from-prd", str(_REAL_PRD_JSON), "--out", str(tmp_p)])
        assert rc == 0, out
        seq_path = tmp_p / "execution-sequences.yaml"
        assert seq_path.exists()
        assert seq_path.read_text(encoding="utf-8").startswith(
            "# generated by scripts/regen-sequence.py"
        )

        # --generate-review-briefs: sequence -> one brief per lane
        rc, out = _run_cli(
            ["--generate-review-briefs", str(seq_path), "--out", str(tmp_p)]
        )
        assert rc == 0, out
        brief = tmp_p / "review-brief-lane-sw-rt-001.md"
        assert brief.exists()
        text = brief.read_text(encoding="utf-8")
        assert "## VERDICT" in text
        # The brief carries the real task's governing acceptance criterion.
        assert "launch_command" in text

        # --inject-prd: the same prd.json is placed where a lane reads it.
        rc, out = _run_cli(["--inject-prd", str(_REAL_PRD_DIR), "--repo", str(tmp_p)])
        assert rc == 0, out
        injected = tmp_p / ".skillweave" / "prd.json"
        assert injected.exists()
        data = json.loads(injected.read_text(encoding="utf-8"))
        assert any(t["id"] == "SW-RT-001" for t in data["tasks"])


def test_from_prd_fails_closed_on_malformed_prd():
    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.json"
        bad.write_text('{"tasks": []}', encoding="utf-8")
        try:
            rs.build_execution_sequences(json.loads(bad.read_text()))
        except (KeyError, ValueError):
            pass
        else:
            raise AssertionError("expected a fail-closed error for sequence-less PRD")
