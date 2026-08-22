"""Host support-claim contract (SW-HOST-CLAIM-001).

The support matrix in ``docs/support/support-matrix.md`` separates four
independently evidenced facts — installed, documented, dispatch-proven,
production — and pins the OpenCode launch command to data/example status rather
than allowing it to read as general product syntax.

These tests are claim checks against the shipped docs, not against the local
machine. They read files from the repository root and assert only what those
files actually say.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SUPPORT_DOC = REPO_ROOT / "docs" / "support" / "support-matrix.md"
EXAMPLE_PROFILE = REPO_ROOT / "profiles" / "example-standard.yaml"
DISPATCH_DOC = REPO_ROOT / "docs" / "dispatching-from-your-harness.md"
DISPATCH_REPORT = REPO_ROOT / "docs" / "dispatch-2-report.json"

_src = REPO_ROOT / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.installer import AGENT_CONFIG  # noqa: E402


def _read_text(path: Path) -> str:
    assert path.exists(), f"missing {path}"
    return path.read_text()


def _matrix_host_rows() -> list[str]:
    """Host names from the matrix ``| Host | ... |`` table rows."""
    text = _read_text(SUPPORT_DOC)
    return re.findall(r"^\|\s*`([^`]+)`\s*\|", text, re.MULTILINE)


def _agent_config_names() -> list[str]:
    return [target.name for target in AGENT_CONFIG]


class TestSupportMatrix:
    """The four levels exist and are distinct in the matrix document."""

    def test_support_doc_exists(self):
        assert SUPPORT_DOC.exists(), "docs/support/support-matrix.md is missing"

    def test_four_levels_are_named(self):
        text = _read_text(SUPPORT_DOC)
        for level in ("installed", "documented", "dispatch-proven", "production"):
            assert re.search(rf"\*\*{level}\*\*", text), f"level '{level}' not in matrix"

    def test_matrix_separates_open_report_from_proof(self):
        text = _read_text(SUPPORT_DOC)
        # dispatch-proven is scoped to one machine, never global syntax.
        assert "one machine" in text
        assert "portable evidence" in text


class TestOpenCodeNotGeneralSyntax:
    """The OpenCode launch command is data/example, never general syntax."""

    OPENCODE_LAUNCH = "opencode run --model"

    def test_example_profile_declares_opencode_command_is_an_example(self):
        text = _read_text(EXAMPLE_PROFILE)
        assert "EXAMPLE" in text and "example-standard" in text
        # The profile's own header disclaims the command as machine-specific.
        assert "assumes `opencode` is on PATH" in text

    def test_dispatch_report_is_evidence_not_guidance(self):
        text = _read_text(DISPATCH_REPORT)
        assert "verbatim record of one run on one machine" in text
        assert "evidence rather than as guidance" in text
    def test_dispatching_doc_scopes_the_opencode_command_to_one_machine(self):
        text = _read_text(DISPATCH_DOC)
        assert "one machine" in text

    def test_no_doc_emits_opencode_command_as_general_launch_contract(self):
        # The only product doc that mentions the command alongside a role launch
        # is the example profile; the general contract must not carry OpenCode
        # syntax. Check the docs directory for any markdown presenting the
        # command outside a disclaimer.
        for md in (REPO_ROOT / "docs").rglob("*.md"):
            body = md.read_text()
            if self.OPENCODE_LAUNCH in body:
                # If a doc mentions the OpenCode command, it must carry the
                # one-machine / example qualifier in the same file.
                assert ("one machine" in body or "EXAMPLE" in body or "example" in body), (
                    f"{md} mentions the OpenCode launch command without scoping "
                    f"it to an example or a single machine"
                )


class TestMatrixHostRowsAnchor:
    """The matrix host rows are exactly the installer's AGENT_CONFIG names."""

    def test_matrix_host_rows_equal_agent_config_names(self):
        matrix = _matrix_host_rows()
        config = _agent_config_names()
        assert len(matrix) == len(config), (
            f"matrix has {len(matrix)} host rows but AGENT_CONFIG has {len(config)}"
        )
        assert sorted(matrix) == sorted(config), (
            f"matrix host rows {sorted(matrix)} != AGENT_CONFIG names {sorted(config)}"
        )
