"""Tests for tool-agnostic dispatch (SW-RT-001 dispatches 1+2).

Covers the four acceptance criteria of this lane:

1. A role carrying a ToolSpec is launched from its launch_command and args; the
   work is handed over to that process and the result is collected and bound to
   the run as evidence (an artifact carrying the stub tool's output), not free
   text.

2. The adapter is tool-agnostic: it receives tool name, launch command,
   arguments, and work, and branches on none of them. A test asserts that no
   concrete tool name appears in the adapter module.

3. A role WITHOUT a ToolSpec runs in place and is recorded as having done so —
   an explicit InPlaceRecord, not an absent one, distinguishable from a dispatch
   that silently did not happen.

4. A failing launch is a named failure carrying the command that failed. A tool
   that never starts is never recorded as a run without a result (RED PROOF
   below: a non-existent command fails naming that command, and the run carries
   a DispatchFailure, not an empty success).

Self-contained sys.path handling, independent of conftest/pytest, following the
convention of ``test_runner_adapter.py``.
"""

import inspect
import re
import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.routing.dispatch import (  # noqa: E402
    DispatchFailure,
    DispatchResult,
    InPlaceRecord,
    dispatch,
    launch_from_role,
    run_in_place,
    tokenize_launch,
)
from skillweave.routing import ToolSpec  # noqa: E402
from skillweave.runtime.registry import ArtifactReceipt, EvidenceType  # noqa: E402


def _tool_spec(name="stub-client", launch_command=None, args=None):
    return ToolSpec(
        name=name,
        launch_command=launch_command or f"{sys.executable} -c 'print(\"stub\")'",
        args=list(args or []),
    )


def _work():
    return b"the work handed to the tool"


# ── Criterion 1: launch from the spec, hand over work, bind as evidence ─────

def test_role_is_launched_from_its_launch_command_and_args():
    # A ToolSpec's launch_command is a full command line, not an argv. The stub
    # command prints a marker; the spec's args must be appended after the
    # tokenised launch command and actually reach the child.
    marker = "__args_seen__"
    tool = ToolSpec(
        name="stub-client",
        launch_command=(
            f"{sys.executable} -c 'import sys; print(sys.argv[1:], end=\"\")'"
        ),
        args=["--flag", marker],
    )
    result = dispatch(
        tool,
        _work(),
        run_id="run-d1",
        subject_repo="skillweave",
        subject_commit="abc123",
        model="model-xyz-7",
        created_at="2026-08-17T00:00:00Z",
    )
    assert isinstance(result, DispatchResult)
    assert result.succeeded is True
    # The child received the tokenised launch command plus the spec's args.
    assert marker.encode() in result.result.stdout


def test_work_is_handed_over_and_visible_to_the_child():
    # The work is delivered over stdin. The stub echoes stdin back and the
    # collected output proves the child received it verbatim.
    tool = ToolSpec(
        name="stub-client",
        launch_command=f"{sys.executable} -c 'import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())'",
        args=[],
    )
    result = dispatch(
        tool,
        b"payload-abc\n",
        run_id="run-d1",
        subject_repo="skillweave",
        subject_commit="abc123",
        model="model-xyz-7",
        created_at="2026-08-17T00:00:00Z",
    )
    assert result.result.stdout == b"payload-abc\n"


def test_result_is_bound_to_the_run_as_evidence_not_free_text():
    # The collected output must be promoted to an ArtifactReceipt (typed
    # artifact) bound to the run — addressed by digest and carrying the run id
    # and tool name in metadata — never left as bare free text.
    tool = ToolSpec(
        name="stub-client",
        launch_command=f"{sys.executable} -c 'print(\"stub-output-xyz\")'",
        args=[],
    )
    result = dispatch(
        tool,
        _work(),
        run_id="run-d1",
        subject_repo="skillweave",
        subject_commit="abc123",
        model="model-xyz-7",
        created_at="2026-08-17T00:00:00Z",
    )
    assert result.artifact is not None
    assert isinstance(result.artifact, ArtifactReceipt)
    assert result.artifact.evidence_type == EvidenceType.ARTIFACT.value
    assert result.artifact.metadata["run_id"] == "run-d1"
    assert result.artifact.metadata["tool"] == "stub-client"
    # The artifact is a digest reference; its identity is the hash, not text.
    assert len(result.artifact.sha256) == 64


def test_launch_from_role_without_a_tool_records_in_place():
    # Criterion 3 — a role without a ToolSpec runs in place and is recorded as
    # having done so: an explicit InPlaceRecord, not an absent one, and not a
    # dispatch that silently did not happen.
    record = launch_from_role(
        "observer",
        None,
        _work(),
        run_id="run-d1",
        subject_repo="skillweave",
        subject_commit="abc123",
        model="model-xyz-7",
    )
    assert isinstance(record, InPlaceRecord)
    assert record.in_place is True
    assert record.role == "observer"
    assert record.run_id == "run-d1"


def test_run_in_place_is_an_explicit_record_not_absence():
    record = run_in_place("observer", run_id="run-d1")
    assert isinstance(record, InPlaceRecord)
    assert record.role == "observer"
    assert record.recorded_at


def test_dispatch_failing_launch_names_the_command():
    # Criterion 4 — a tool that never starts is a named failure carrying the
    # command that failed, never a run without a result and never a silent
    # empty success.
    tool = ToolSpec(
        name="stub-client",
        launch_command="definitely-not-a-real-command-xyz",
        args=[],
    )
    result = dispatch(
        tool,
        _work(),
        run_id="run-d1",
        subject_repo="skillweave",
        subject_commit="abc123",
        model="model-xyz-7",
    )
    assert isinstance(result, DispatchFailure)
    assert result.succeeded is False
    assert result.tool == "stub-client"
    # The failed command is named in the message.
    assert "definitely-not-a-real-command-xyz" in result.message
    assert result.command == ["definitely-not-a-real-command-xyz"]


def test_launch_from_role_failing_launch_carries_the_role():
    tool = ToolSpec(
        name="stub-client",
        launch_command="definitely-not-a-real-command-xyz",
        args=[],
    )
    result = launch_from_role(
        "reviewer",
        tool,
        _work(),
        run_id="run-d1",
        subject_repo="skillweave",
        subject_commit="abc123",
        model="model-xyz-7",
    )
    assert isinstance(result, DispatchFailure)
    assert result.role == "reviewer"
    assert result.succeeded is False
    # A tool that never starts is never recorded as a run without a result.
    assert "definitely-not-a-real-command-xyz" in result.message


def test_launch_from_role_with_a_tool_still_dispatches():
    # Regression guard for dispatch 1 behaviour under the three-way outcome:
    # a role with a tool still launches and binds evidence.
    tool = ToolSpec(
        name="stub-client",
        launch_command=f"{sys.executable} -c 'print(\"stub\")'",
        args=[],
    )
    result = launch_from_role(
        "worker",
        tool,
        _work(),
        run_id="run-d1",
        subject_repo="skillweave",
        subject_commit="abc123",
        model="model-xyz-7",
        created_at="2026-08-17T00:00:00Z",
    )
    assert isinstance(result, DispatchResult)
    assert result.succeeded is True
    assert b"stub" in result.result.stdout


# ── Criterion 2: the adapter branches on none of its inputs ────────────────

def test_no_concrete_tool_name_appears_in_the_adapter_module():
    # The adapter must be tool-agnostic: it receives the tool name and records
    # it, but no concrete tool name (e.g. opencode) is hard-coded, so adding a
    # second consumer does not require touching the interface shape.
    module_path = Path(__file__).resolve().parent.parent.parent / "src" / "skillweave" / "routing" / "dispatch.py"
    source = module_path.read_text()
    # Strip comments and docstrings so only code-proper is inspected: a name in
    # a docstring is still a branch-worthy leak if it steers behaviour, so we
    # remove prose first and assert nothing concrete remains.
    source_no_docstrings = re.sub(r'(""".*?"""|\'\'\'.*?\'\'\')', "", source, flags=re.DOTALL)
    source_no_comments = re.sub(r"#.*", "", source_no_docstrings)
    lowered = source_no_comments.lower()
    for concrete in ("opencode", "claude code", "codex"):
        assert concrete not in lowered


def test_adapter_signature_receives_tool_and_work_and_branches_nowhere():
    # The public entry point takes the tool, the work, and the required run
    # identifiers; there is no branch on which tool it was handed (the module
    # has no if/elif on tool names — asserted structurally in the test above).
    params = inspect.signature(dispatch).parameters
    assert "tool" in params
    assert "work" in params
    assert "run_id" in params
    assert "subject_repo" in params
    assert "subject_commit" in params
    assert "model" in params


def test_tokenize_launch_splits_a_command_line():
    assert tokenize_launch("python3 -m skillweave.council") == [
        "python3",
        "-m",
        "skillweave.council",
    ]
    # Quotes are honoured (POSIX-like tokenisation).
    assert tokenize_launch('python3 -c "print(1)"') == ["python3", "-c", "print(1)"]


def _run_all() -> int:
    tests = [
        test_role_is_launched_from_its_launch_command_and_args,
        test_work_is_handed_over_and_visible_to_the_child,
        test_result_is_bound_to_the_run_as_evidence_not_free_text,
        test_launch_from_role_without_a_tool_records_in_place,
        test_run_in_place_is_an_explicit_record_not_absence,
        test_dispatch_failing_launch_names_the_command,
        test_launch_from_role_failing_launch_carries_the_role,
        test_launch_from_role_with_a_tool_still_dispatches,
        test_no_concrete_tool_name_appears_in_the_adapter_module,
        test_adapter_signature_receives_tool_and_work_and_branches_nowhere,
        test_tokenize_launch_splits_a_command_line,
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
