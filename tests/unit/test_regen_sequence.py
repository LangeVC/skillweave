#!/usr/bin/env python3
"""Unit tests for the canonical dispatch script (SW-BRIEF-001).

Covers the review-brief generator and the PRD-injection seam without touching
the network. Two criteria are exercised:

1. ``--generate-review-briefs`` writes exactly one
   ``review-brief-<lane_id>.md`` per lane, and each brief carries the lane ID,
   the task IDs (``dispatches`` / ``steps``), the acceptance criteria
   (``criteria`` / ``gates``), suggested verification steps, and a VERDICT
   template.
2. ``--inject-prd`` copies ``prd.md`` from a PRD directory into the worktree
   root as ``.skillweave/prd.md``.

The briefs YAML is a build-format fixture (``final_assembly`` is not required;
the build contract is ``phases`` + ``parallel_lanes``/``serialized_lanes``).
Self-contained ``sys.path`` handling follows the ``test_dispatch_contract.py``
convention.
"""

import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "regen-sequence.py"
_FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "regen-sequence-brief-input.yaml"
)

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


def test_inject_prd_copies_prd_md_into_worktree():
    with tempfile.TemporaryDirectory() as tmp:
        prd_dir = Path(tmp) / "prd"
        repo = Path(tmp) / "repo"
        prd_dir.mkdir()
        (prd_dir / "prd.md").write_text("# My PRD\nbody\n", encoding="utf-8")
        target = rs.inject_prd(prd_dir, repo)
        assert target == repo / ".skillweave" / "prd.md"
        assert target.read_text(encoding="utf-8") == "# My PRD\nbody\n"


def test_inject_prd_missing_prd_md_raises():
    with tempfile.TemporaryDirectory() as tmp:
        prd_dir = Path(tmp) / "empty"
        prd_dir.mkdir()
        try:
            rs.inject_prd(prd_dir, Path(tmp) / "repo")
        except FileNotFoundError as exc:
            assert "prd.md" in str(exc)
        else:
            raise AssertionError("expected FileNotFoundError")


def test_cli_inject_prd_flag():
    with tempfile.TemporaryDirectory() as tmp:
        prd_dir = Path(tmp) / "prd"
        repo = Path(tmp) / "repo"
        prd_dir.mkdir()
        (prd_dir / "prd.md").write_text("hi\n", encoding="utf-8")
        rc, out = _run_cli(["--inject-prd", str(prd_dir), "--repo", str(repo)])
        assert rc == 0
        assert (repo / ".skillweave" / "prd.md").exists()
        assert "regen-sequence: injected" in out
