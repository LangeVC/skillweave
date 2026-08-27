"""Contract tests tying SkillWeave skill *assets* to the format the ecosystem
actually produces.

This file exists because skill assets describe structures and, left
unchecked, silently describe structures nobody produces any more. Two assets
were measured stale (SW-SKILL-001):

- ``skills/skillweave-blueprint/assets/prd.schema.json`` claimed tasks carry
  ``acceptance_criteria`` plus an ``estimated_minutes`` time field, while the
  ecosystem produces ``acceptanceCriteria`` and Fibonacci ``points`` and has
  no time field.
- ``skills/skillweave-promptchain-validate`` required a twelve-section
  topic contract for every sequence, while the build format the ecosystem
  ships is ``phases``/``parallel_lanes``/``mutual_exclusion``/
  ``gate_pass_requires``/``session_boundary``.

The two named production PRDs (ops-002 mirror-rollout, Forgejo-first) are
treated as unchanged fixtures under ``tests/fixtures/prd-schema/``. They are
verbatim copies of the documents produced in ``lvc-planning``; do not edit
them to make tests pass.
"""

from pathlib import Path

import jsonschema

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCHEMA = _REPO_ROOT / "skills" / "skillweave-blueprint" / "assets" / "prd.schema.json"
_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "prd-schema"

# regen-sequence.py reads at most this many acceptance criteria per dispatch.
# See planning/scripts/regen-sequence.py (MAX_CRITERIA_PER_DISPATCH).
_MAX_CRITERIA_PER_DISPATCH = 3

FIBONACCI = (1, 2, 3, 5, 8, 13, 21)


def _load_schema():
    import json

    return json.loads(_SCHEMA.read_text())


def _validator():
    return jsonschema.Draft202012Validator(_load_schema())


def _errors(doc):
    return list(_validator().iter_errors(doc))


def _fixture(name):
    import json

    return json.loads((_FIXTURE_DIR / name).read_text())


# Keys regen-sequence.py's ``_sequence`` and ``_briefs`` read unconditionally
# from the ``sequence`` block (``cfg[key]``). Their absence makes the real
# generator raise ``KeyError`` before a single brief is written, so a PRD that
# omits any of them fails closed with zero dispatches regardless of task shape.
# See planning/scripts/regen-sequence.py (_sequence/_briefs).
_SEQUENCE_REQUIRED_KEYS = (
    "sequence_id",
    "sequence_type",
    "execution_mode",
    "worktree",
    "branch",
    "base",
    "state_file",
    "runner_shell",
)


def _sequence_fail_closed(prd):
    """True if the real generator fails before writing any dispatch brief.

    Mirrors regen-sequence.py: ``load`` aborts without a ``sequence`` block,
    and ``_sequence``/``_briefs`` read these keys directly, so any missing key
    raises ``KeyError`` before a brief exists.
    """
    cfg = prd.get("sequence")
    if not isinstance(cfg, dict):
        return True
    return any(key not in cfg for key in _SEQUENCE_REQUIRED_KEYS)


def _dispatch_count(prd):
    """Number of dispatch briefs regen-sequence.py would write for a PRD.

    Mirrors planning/scripts/regen-sequence.py: one dispatch (one brief) is
    one invocation, capped at ``MAX_CRITERIA_PER_DISPATCH`` acceptance
    criteria; a lane with explicit ``dispatch_order`` emits one brief per
    entry instead of chunking. A task without ``acceptanceCriteria`` cannot
    be dispatched at all — regen-sequence.py raises ``KeyError`` and zero
    briefs are written. A ``sequence`` block missing any generator-required
    key also fails closed with zero, because ``_sequence``/``_briefs`` read
    them before any brief exists.
    """
    if _sequence_fail_closed(prd):
        return 0
    total = 0
    for task in prd["tasks"]:
        lane = task.get("lane") or {}
        if lane.get("dispatch_order"):
            total += len(lane["dispatch_order"])
            continue
        # A task written to the OLD schema uses acceptance_criteria
        # (snake_case), which regen-sequence.py does not read. It raises
        # KeyError on the first such task and writes ZERO briefs for the
        # whole PRD. Match that: any missing acceptanceCriteria aborts.
        try:
            n_acs = len(task["acceptanceCriteria"])
        except KeyError:
            return 0
        total += -(-n_acs // _MAX_CRITERIA_PER_DISPATCH)
    return total


class TestSchemaAcceptsProducedFormat:
    """Criterion 1: the shipped schema accepts the produced build format."""

    def test_no_time_estimate_field_is_required(self):
        doc = _fixture("corrected-build-format.json")
        assert _errors(doc) == []

    def test_produced_keys_are_allowed(self):
        schema = _load_schema()
        props = schema["properties"]
        assert "sequence" in props
        assert "totals" in props
        task = schema["properties"]["tasks"]["items"]
        for key in ("acceptanceCriteria", "points", "dependsOn", "lane"):
            assert key in task["properties"], key

    def test_blueprint_schema_has_no_time_field_at_all(self):
        schema = _load_schema()
        # No required key mentions time.
        required = [r for r in schema.get("required", []) if "time" in r]
        assert required == []
        # No task property is a time estimate.
        task_schema = schema["properties"]["tasks"]["items"]["properties"]
        assert "estimated_minutes" not in task_schema
        assert "estimated_tokens" not in task_schema

    def test_points_constrained_to_fibonacci(self):
        schema = _load_schema()
        points = schema["properties"]["tasks"]["items"]["properties"]["points"]
        assert sorted(points["enum"]) == sorted(FIBONACCI)


class TestSchemaValidatesProductionPRDs:
    """Criterion 2: the schema validates the two unchanged production PRDs
    and rejects non-Fibonacci points."""

    PROD_PRDS = ("ops-002-mirror-rollout.json", "forgejo-first.json")

    def test_ops_002_and_forgejo_first_pass_unchanged(self):
        for name in self.PROD_PRDS:
            assert _errors(_fixture(name)) == [], name

    def test_non_fibonacci_points_are_rejected(self):
        for name in self.PROD_PRDS:
            doc = _fixture(name)
            doc["tasks"][0]["points"] = 4
            errs = _errors(doc)
            assert len(errs) == 1, name
            assert list(errs[0].path) == ["tasks", 0, "points"], name


class TestValidateDetectsBuildSequence:
    """Criteria 3-4: promptchain-validate recognises the build format and
    validates its own keys instead of the twelve-section topic contract."""

    def test_skill_makes_build_keys_explicit(self):
        skill = (
            _REPO_ROOT / "skills" / "skillweave-promptchain-validate" / "SKILL.md"
        ).read_text()
        for key in (
            "phases",
            "parallel_lanes",
            "mutual_exclusion",
            "gate_pass_requires",
            "session_boundary",
        ):
            assert key in skill, key

    def test_skill_names_the_consuming_flow_for_each_format(self):
        skill = (
            _REPO_ROOT / "skills" / "skillweave-promptchain-validate" / "SKILL.md"
        ).read_text()
        # Both formats are supported, so each must name who consumes it.
        assert "regen-sequence" in skill or "regen-sequence.py" in skill
        assert "promptchain-execute" in skill


class TestRedAndCorrectedFixtures:
    """Criterion 5: a PRD valid under the previous schema yields zero
    dispatches; the corrected fixture yields at least one brief."""

    def test_red_fixture_produces_zero_dispatches(self):
        doc = _fixture("red-old-format.json")
        assert _dispatch_count(doc) == 0

    def test_corrected_fixture_produces_at_least_one_brief(self):
        doc = _fixture("corrected-build-format.json")
        assert _errors(doc) == []
        assert _dispatch_count(doc) >= 1
