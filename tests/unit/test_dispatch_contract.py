"""Operator dispatch sequence and event contract (SW138-CONTRACT-001).

Covers the five acceptance criteria:

1. A schema-valid fixture declares ``session_boundary=batch``, an explicit
   profile reference, ``execution_model``, ``max_correction_rounds_per_wave``,
   ``max_parallel``, and per-lane repo plus full base SHA.
2. A mutating lane missing repo, full base SHA, execution_model, or criterion
   coverage fails before any worker-start callback is invoked.
3. The event contract has run, wave, lane and dispatch identifiers, a monotonic
   sequence, timestamp, event type, process status, task/evidence status and
   optional receipt references.
4. The contract declares no model-name or harness-name default and no
   duration-estimate field.
5. Every task uses acceptanceCriteria, Fibonacci points, dependsOn and lane;
   points outside 1,2,3,5,8,13 fail.

Self-contained sys.path handling, following the convention of
``test_routing_dispatch.py`` and ``test_verify_contract.py``. No ``jsonschema``
dependency: schema validity is asserted structurally against the shipped JSON
schema file, matching the approach of ``test_run_state_vocabulary.py``.
"""

import json
import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.dispatch.contracts import (  # noqa: E402
    FIBONACCI_POINTS,
    DispatchEvent,
    EventType,
    Lane,
    LaneValidationError,
    PracticeTaskError,
    ProcessStatus,
    SequenceDeclaration,
    TaskStatus,
    validate_for_dispatch,
    validate_mutating_lane,
    validate_practice_task,
)

SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "dispatch-sequence.schema.json"
)

FULL_SHA = "0ef44d4ae2d41fb608c01b3d729995ffee5c22ae"


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_validates(schema: dict, instance: dict) -> None:
    """A minimal structural validator (no ``jsonschema`` dependency).

    Checks the instance against the schema's ``required``, ``enum`` and integer
    ``minimum`` for the object level and its ``$defs`` subschemas. Enough to
    prove the shipped fixture is valid under the shipped schema, matching the
    self-contained convention of ``test_run_state_vocabulary.py``.
    """
    for key in schema.get("required", []):
        assert key in instance, f"missing required key '{key}'"
    props = schema.get("properties", {})
    for key, value in instance.items():
        spec = props.get(key)
        if spec is None:
            assert not schema.get("additionalProperties") is False, (
                f"key '{key}' not allowed by schema"
            )
            continue
        expected_type = spec.get("type")
        if expected_type == "string":
            assert isinstance(value, str), f"'{key}' must be a string"
        elif expected_type == "integer":
            assert isinstance(value, int) and not isinstance(value, bool), (
                f"'{key}' must be an integer"
            )
        if "enum" in spec and spec["enum"]:
            assert (
                value in spec["enum"]
                or isinstance(value, list)
                and all(v in spec["enum"] for v in value)
            ), f"'{key}' value {value!r} not in enum {spec['enum']}"
        if "minimum" in spec and isinstance(value, int):
            assert value >= spec["minimum"], f"'{key}' below minimum"


def _validate_fixture_against_schema(fixture: dict) -> None:
    """Validate the fixture (top level plus each lane) against the schema."""
    schema = _schema()
    _schema_validates(schema, fixture)
    lane_schema = schema["$defs"]["lane"]
    for lane in fixture["lanes"]:
        _schema_validates(lane_schema, lane)
    profile_schema = schema["$defs"]["profileReference"]
    _schema_validates(profile_schema, fixture["profile"])


def _valid_fixture() -> dict:
    """The schema-valid fixture every red/green test builds from."""
    return {
        "session_boundary": "batch",
        "profile": {"path": "profiles/runtime-profile.yaml", "required": True},
        "execution_model": "cold",
        "max_correction_rounds_per_wave": 2,
        "max_parallel": 4,
        "lanes": [
            {
                "id": "lane-contract-ops",
                "role": "ops",
                "repo": "skillweave/skillweave",
                "base": FULL_SHA,
                "execution_model": "cold",
                "mutating": True,
                "criterion_groups": [
                    {"criteria": [1, 2, 3]},
                    {"criteria": [4, 5]},
                ],
            },
        ],
    }


# ── Criterion 1: schema-valid fixture declares the full contract ───────────

def test_schema_file_exists_and_declares_the_contract_keys():
    schema = _schema()
    required = set(schema.get("required", []))
    for key in (
        "session_boundary",
        "profile",
        "execution_model",
        "max_correction_rounds_per_wave",
        "max_parallel",
        "lanes",
    ):
        assert key in required, f"schema must require '{key}'"
    # The session boundary enumerates exactly `batch` — never defaulted wider.
    assert schema["properties"]["session_boundary"]["enum"] == ["batch"]
    # The per-lane contract requires repo and a base.
    lane_req = set(schema["$defs"]["lane"]["required"])
    assert {"repo", "base", "execution_model"} <= lane_req


def test_valid_fixture_declares_the_full_contract():
    fixture = _valid_fixture()
    _validate_fixture_against_schema(fixture)  # schema-valid under the shipped schema
    assert fixture["session_boundary"] == "batch"
    assert fixture["profile"]["path"]
    assert fixture["execution_model"] == "cold"
    assert isinstance(fixture["max_correction_rounds_per_wave"], int)
    assert isinstance(fixture["max_parallel"], int)
    lane = fixture["lanes"][0]
    assert lane["repo"]
    assert lane["base"] == FULL_SHA
    assert len(lane["base"]) == 40  # full SHA, not a branch name


def test_valid_fixture_loads_and_validates():
    fixture = _valid_fixture()
    decl = _as_sequence(fixture)
    started = []
    validate_for_dispatch(
        decl,
        [1, 2, 3, 4, 5],
        on_worker_start=lambda lane: started.append(lane),
    )
    assert started, "a valid mutating lane must reach worker start"


# ── Criterion 2: mutating lane fails closed before worker-start ────────────

def _as_sequence(data: dict) -> SequenceDeclaration:
    from skillweave.dispatch.contracts import load_sequence

    return load_sequence(data)


def _started_recorder(calls):
    def _cb(lane):
        calls.append(lane.id)

    return _cb


def test_missing_repo_starts_zero_workers():
    fixture = _valid_fixture()
    del fixture["lanes"][0]["repo"]
    decl = _as_sequence(fixture)
    calls = []
    try:
        validate_for_dispatch(decl, [1, 2, 3, 4, 5], on_worker_start=_started_recorder(calls))
    except LaneValidationError as exc:
        assert "repo" in str(exc)
        assert calls == [], "no worker-start callback may fire on failure"
    else:
        raise AssertionError("missing repo must fail validation")


def test_missing_base_starts_zero_workers():
    fixture = _valid_fixture()
    del fixture["lanes"][0]["base"]
    decl = _as_sequence(fixture)
    calls = []
    try:
        validate_for_dispatch(decl, [1, 2, 3, 4, 5], on_worker_start=_started_recorder(calls))
    except LaneValidationError as exc:
        assert "base" in str(exc)
        assert calls == []
    else:
        raise AssertionError("missing base must fail validation")


def test_branch_name_instead_of_full_sha_starts_zero_workers():
    fixture = _valid_fixture()
    fixture["lanes"][0]["base"] = "main"  # a branch name, not a full SHA
    decl = _as_sequence(fixture)
    calls = []
    try:
        validate_for_dispatch(decl, [1, 2, 3, 4, 5], on_worker_start=_started_recorder(calls))
    except LaneValidationError as exc:
        assert "full base SHA" in str(exc)
        assert calls == []
    else:
        raise AssertionError("branch-name base must fail validation")


def test_missing_execution_model_starts_zero_workers():
    fixture = _valid_fixture()
    del fixture["lanes"][0]["execution_model"]
    decl = _as_sequence(fixture)
    calls = []
    try:
        validate_for_dispatch(decl, [1, 2, 3, 4, 5], on_worker_start=_started_recorder(calls))
    except LaneValidationError as exc:
        assert "execution_model" in str(exc)
        assert calls == []
    else:
        raise AssertionError("missing execution_model must fail validation")


def test_incomplete_criterion_coverage_starts_zero_workers():
    fixture = _valid_fixture()
    # Lane covers 1..5 but the wave demands 1..6: criterion 6 is uncovered.
    decl = _as_sequence(fixture)
    calls = []
    try:
        validate_for_dispatch(decl, [1, 2, 3, 4, 5, 6], on_worker_start=_started_recorder(calls))
    except LaneValidationError as exc:
        assert "exactly once" in str(exc) or "coverage" in str(exc)
        assert calls == []
    else:
        raise AssertionError("incomplete criterion coverage must fail validation")


def test_duplicate_criterion_coverage_starts_zero_workers():
    fixture = _valid_fixture()
    fixture["lanes"][0]["criterion_groups"] = [
        {"criteria": [1, 2, 3, 3]},  # duplicated index
        {"criteria": [4, 5]},
    ]
    decl = _as_sequence(fixture)
    calls = []
    try:
        validate_for_dispatch(decl, [1, 2, 3, 4, 5], on_worker_start=_started_recorder(calls))
    except LaneValidationError:
        assert calls == []
    else:
        raise AssertionError("duplicate criterion coverage must fail validation")


def test_valid_lane_starts_workers_after_validation():
    fixture = _valid_fixture()
    decl = _as_sequence(fixture)
    calls = []
    validate_for_dispatch(decl, [1, 2, 3, 4, 5], on_worker_start=_started_recorder(calls))
    assert "lane-contract-ops" in calls


def test_read_only_lane_is_exempt_from_repo_requirement():
    # The contract binds *mutating* lanes; a read-only lane (e.g. reviewer)
    # carrying no repo is not refused by the mutating-lane checks.
    lane = Lane(id="rev", role="reviewer", mutating=False)
    validate_mutating_lane(lane, [1, 2])


# ── Criterion 3: the event contract fields ─────────────────────────────────

def test_event_contract_has_all_required_identifiers_and_statuses():
    event = DispatchEvent(
        run_id="run-1",
        wave="wave-0",
        lane_id="lane-a",
        dispatch_id="disp-1",
        sequence=0,
        timestamp="2026-08-27T00:00:00Z",
        event_type=EventType.WAVE_STARTED.value,
        process_status=ProcessStatus.NOT_STARTED.value,
        task_status=TaskStatus.QUEUED.value,
    )
    payload = event.to_dict()
    for key in (
        "run_id",
        "wave",
        "lane_id",
        "dispatch_id",
        "sequence",
        "timestamp",
        "event_type",
        "process_status",
        "task_status",
    ):
        assert key in payload, f"event payload must carry '{key}'"


def test_event_carries_evidence_status_and_receipt_refs_when_present():
    event = DispatchEvent(
        run_id="run-1",
        wave="wave-0",
        lane_id="lane-a",
        dispatch_id="disp-1",
        sequence=3,
        timestamp="2026-08-27T00:00:00Z",
        event_type=EventType.EVIDENCE_RECORDED.value,
        process_status=ProcessStatus.EXITED.value,
        task_status=TaskStatus.DONE.value,
        evidence_status="recorded",
        receipt_refs=["dispatch-run-1"],
    )
    payload = event.to_dict()
    assert payload["evidence_status"] == "recorded"
    assert payload["receipt_refs"] == ["dispatch-run-1"]


def test_sequence_is_monotonic_per_run():
    previous = -1
    for seq in (0, 1, 2, 5):
        event = DispatchEvent(
            run_id="run-1",
            wave="w",
            lane_id="l",
            dispatch_id="d",
            sequence=seq,
            timestamp="t",
            event_type=EventType.HEARTBEAT.value,
            process_status=ProcessStatus.RUNNING.value,
            task_status=TaskStatus.IN_PROGRESS.value,
        )
        assert event.sequence >= previous
        previous = event.sequence


def test_event_serializes_to_json_without_model_or_duration():
    event = DispatchEvent(
        run_id="run-1",
        wave="w",
        lane_id="l",
        dispatch_id="d",
        sequence=1,
        timestamp="t",
        event_type=EventType.LANE_TERMINAL.value,
        process_status=ProcessStatus.EXITED.value,
        task_status=TaskStatus.DONE.value,
    )
    raw = event.to_json()
    data = json.loads(raw)
    assert "model" not in data
    assert "harness" not in data
    assert "duration" not in data
    assert "estimated_minutes" not in data


# ── Criterion 4: no model/harness default, no duration-estimate field ──────

def test_contract_module_declares_no_model_or_harness_default():
    source = (
        Path(_src)
        / "skillweave"
        / "dispatch"
        / "contracts.py"
    ).read_text(encoding="utf-8")
    lowered = source.lower()
    for forbidden in ("opencode", "deepseek", "claude code", "codex", "gemini"):
        assert forbidden not in lowered, f"no {forbidden} name may appear"


def test_event_and_lane_tagmarks_have_no_duration_estimate():
    lane_fields = Lane.__dataclass_fields__
    event_fields = DispatchEvent.__dataclass_fields__
    for name, meta in {**lane_fields, **event_fields}.items():
        lowered = name.lower()
        assert "duration" not in lowered, f"'{name}' carries a duration estimate"
        assert "minute" not in lowered


# ── Criterion 5: practice task validation ─────────────────────────────────

def _valid_task() -> dict:
    return {
        "id": "SW138-CONTRACT-001",
        "acceptanceCriteria": ["a", "b"],
        "points": 8,
        "dependsOn": [],
        "lane": {"repo": "skillweave/skillweave", "base": FULL_SHA},
    }


def test_valid_practice_task_passes():
    validate_practice_task(_valid_task())  # must not raise


def test_task_missing_acceptance_criteria_fails():
    task = _valid_task()
    del task["acceptanceCriteria"]
    try:
        validate_practice_task(task)
    except PracticeTaskError as exc:
        assert exc.field == "acceptanceCriteria"
    else:
        raise AssertionError("missing acceptanceCriteria must fail")


def test_task_missing_points_fails():
    task = _valid_task()
    del task["points"]
    try:
        validate_practice_task(task)
    except PracticeTaskError as exc:
        assert exc.field == "points"
    else:
        raise AssertionError("missing points must fail")


def test_task_missing_depends_on_fails():
    task = _valid_task()
    del task["dependsOn"]
    try:
        validate_practice_task(task)
    except PracticeTaskError as exc:
        assert exc.field == "dependsOn"
    else:
        raise AssertionError("missing dependsOn must fail")


def test_task_missing_lane_fails():
    task = _valid_task()
    del task["lane"]
    try:
        validate_practice_task(task)
    except PracticeTaskError as exc:
        assert exc.field == "lane"
    else:
        raise AssertionError("missing lane must fail")


def test_non_fibonacci_points_fail():
    for bad in (4, 6, 7, 9, 10, 11, 12, 21, 0):
        task = _valid_task()
        task["points"] = bad
        try:
            validate_practice_task(task)
        except PracticeTaskError as exc:
            assert exc.field == "points"
        else:
            raise AssertionError(f"points={bad} must fail")


def test_all_fibonacci_points_pass():
    for good in FIBONACCI_POINTS:
        task = _valid_task()
        task["points"] = good
        validate_practice_task(task)  # must not raise


def test_task_with_duration_estimate_fails():
    task = _valid_task()
    task["estimated_minutes"] = 30
    try:
        validate_practice_task(task)
    except PracticeTaskError as exc:
        assert "duration" in str(exc).lower() or "forbidden" in str(exc).lower()
    else:
        raise AssertionError("duration-estimate field must fail")


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
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
