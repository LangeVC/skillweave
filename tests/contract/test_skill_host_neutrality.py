"""Host-neutrality contract for shipped SKILL.md files.

SkillWeave skills are transport-agnostic: they are built to work with any AI
coding agent on any supported transport (Markdown or MCP). A shipped skill must
not bind to a specific host — no host executable used to invoke the skill, and
no concrete host or model as a default in task/agent assignment.

This file exists because shipped skills were found embedding ``opencode`` as an
executable prefix (SW-SKILL-003): ``skillweave-repo-health`` documented
``opencode skillweave-repo-health command=...`` in its Usage block, and the
blueprint skill showed ``"target_agent": "opencode"`` as a built-in task
default. Both imply a single host and undercut the host-neutral promise.

The contract is deliberately scoped to *shipped* ``skills/*/SKILL.md`` files on
three rules:

1. No literal ``opencode`` anywhere (the shipped SKILL.md surface must not name
   a host by its executable at all).
2. No host executable used as a command prefix to invoke a skill (host-specific
   executable syntax).
3. No concrete host or model default in task/agent assignment; task routing is
   capability-based and defers to ``target_agent: any`` or omits the field.

Host-specific invocation that is worth keeping lives under
``references/adapters/<host>.md`` and is explicitly labelled a non-binding
adapter example; that directory is not part of this scan.
"""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SKILLS_DIR = _REPO_ROOT / "skills"

# Host executables whose use as a command prefix to invoke a skill is
# host-specific executable syntax (rule 2).
_HOST_EXECUTABLES = {
    "opencode",
    "claude",
    "codex",
    "gemini",
    "gemini-cli",
    "cursor",
    "windsurf",
    "zed",
    "aider",
    "augment",
    "qwen",
}

# Host/model tokens accepted as a *default* in task/agent assignment. "any" is
# the only neutral default; a concrete host or model here is rejected.
_NEUTRAL_DEFAULTS = {"any", "all", "all-agent", "capability"}

# A fenced-markdown code block opener/closer.
_FENCE = re.compile(r"^(`{3}|\~{3})")


def _shipped_skills():
    """Return Paths to every shipped ``skills/*/SKILL.md``."""
    return sorted(_SKILLS_DIR.glob("*/SKILL.md"))


def _lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def _banned_literal(text):
    """rule 1: a bare ``opencode`` / ``open code`` token anywhere."""
    return re.search(r"\bopencode\b|\bopen[\s-]?code\b", text, re.IGNORECASE) is not None


_EXEC_CALL = re.compile(
    r"^\s*(?:#.*?:\s*)?(?P<bin>"
    + "|".join(re.escape(h) for h in sorted(_HOST_EXECUTABLES, key=len, reverse=True))
    + r")\s+(?:-{1,2}[a-zA-Z]+\s+)*?/?skillweave[-\w]*",
    re.IGNORECASE,
)

# A ``target_agent``/``agent`` assignment whose value is a concrete host or
# model. Accepts both JSON (``"target_agent": "opencode"``) and YAML
# (``target_agent: opencode``) shapes, including a quoted key.
_ASSIGNMENT = re.compile(
    r'["\']?target[_-]?agent["\']?\s*[:=]\s*["\']?(?P<val>[a-zA-Z][-a-zA-Z0-9_.]*)["\']?'
)


def _concrete_default(line):
    """rule 3: task/agent assignment defaulting to a concrete host or model."""
    for m in _ASSIGNMENT.finditer(line):
        value = m.group("val")
        if value in _NEUTRAL_DEFAULTS:
            continue
        return value
    return None


class TestShippedSkillsAreHostNeutral:
    def _content(self):
        return _shipped_skills()

    def test_all_skills_are_scanned(self):
        skills = self._content()
        assert skills, "no shipped SKILL.md files found to scan"
        assert len(skills) >= 13, f"expected 13+ shipped skills, found {len(skills)}"

    def test_no_opencode_literal_anywhere(self):
        offenders = []
        for path in self._content():
            if _banned_literal(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(_REPO_ROOT)))
        assert offenders == [], f"opencode literal found in: {offenders}"

    def test_no_host_executable_invokes_a_skill(self):
        offenders = []
        for path in self._content():
            lines = _lines(path)
            for n, line in enumerate(lines):
                if _FENCE.match(line):
                    continue
                if _EXEC_CALL.match(line):
                    offenders.append(
                        f"{path.relative_to(_REPO_ROOT)}:{n + 1}: {line.strip()}"
                    )
        assert offenders == [], "host-specific executable syntax:\n" + "\n".join(
            offenders
        )

    def test_no_concrete_host_or_model_default_in_assignment(self):
        offenders = []
        for path in self._content():
            lines = _lines(path)
            for n, line in enumerate(lines):
                if _FENCE.match(line):
                    # delimiter lines carry no assignments; content lines (both
                    # inside and outside code fences) are scrutinized below
                    continue
                value = _concrete_default(line)
                if value is not None:
                    offenders.append(
                        f"{path.relative_to(_REPO_ROOT)}:{n + 1}: target_agent/agent "
                        f"defaults to concrete host/model '{value}'"
                    )
        assert offenders == [], "concrete default found:\n" + "\n".join(offenders)


class TestHostSpecificInvocationLivesInAdapters:
    """rule 3 of the brief: retained host-specific invocation is moved to
    ``references/adapters/<host>.md`` and labelled non-binding."""

    def test_retained_host_invocation_is_moved_to_adapters(self):
        # The historical ``opencode`` repo-health invocation must no longer
        # appear in the shipped SKILL.md (proven above) and should exist only
        # as a non-binding adapter example.
        adapter = _REPO_ROOT / "skills" / "skillweave-repo-health" / "references" / "adapters" / "opencode.md"
        assert adapter.exists(), "expected retained OpenCode invocation in references/adapters/"
        text = adapter.read_text(encoding="utf-8")
        assert "non-binding" in text.lower(), "adapter must be labelled non-binding"
        assert "opencode skillweave-repo-health" in text, "adapter should retain the invocation"

    def test_no_shipped_skill_pins_a_host_default(self):
        # The blueprint skill must teach capability-first assignment and the
        # neutral "any" default, never a concrete host by default.
        blueprint = _REPO_ROOT / "skills" / "skillweave-blueprint" / "SKILL.md"
        text = blueprint.read_text(encoding="utf-8")
        assert '"target_agent": "any"' in text or "target_agent: any" in text
