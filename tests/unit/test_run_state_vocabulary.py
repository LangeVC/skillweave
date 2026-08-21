"""SW-STATE-VOCAB-001: canonical lowercase state vocabulary.

The code enum and the schema enum must be exactly equal, every value lowercase.
``STOPPED_BEFORE_B06`` must no longer exist anywhere in the core vocabulary;
stop reasons travel in ``metadata["stop_reason"]`` instead. Terminal semantics
are explicit and tested.
"""

import json
import sys
import tempfile
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runtime.store import RunStateModel, SQLiteRunStore


SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "run-state.schema.json"
)


def _model_values() -> set[str]:
    return {member.value for member in RunStateModel}


def _schema_values() -> set[str]:
    raw = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return set(raw["properties"]["state"]["enum"])


def test_run_state_vocabulary_is_single_source_of_truth():
    model = _model_values()
    schema = _schema_values()
    assert model == schema, (
        f"code<->schema enum drift: model-only={sorted(model - schema)}, "
        f"schema-only={sorted(schema - model)}"
    )


def test_all_values_are_lowercase():
    for value in _model_values():
        assert value == value.lower(), (
            f"non-canonical value '{value}' is not lowercase"
        )


def test_stopped_before_b06_is_absent_from_core_vocabulary():
    assert "STOPPED_BEFORE_B06" not in _model_values()
    assert "STOPPED_BEFORE_B06" not in _schema_values()
    # The placeholder is not reachable even as a legal target.
    assert not any(
        "STOPPED_BEFORE_B06" in (s.value if hasattr(s, "value") else s)
        for s in RunStateModel
    )


def test_terminal_semantics_are_explicit():
    terminal = RunStateModel.terminal_values()
    assert terminal == {"advance_or_stop", "failed"}
    assert RunStateModel.is_terminal("advance_or_stop") is True
    assert RunStateModel.is_terminal("failed") is True
    assert RunStateModel.is_terminal("in_progress") is False
    # Terminal states have no outgoing transitions.
    for value in terminal:
        assert RunStateModel.legal_transitions(value) == []


def test_legacy_uppercase_rows_migrate_on_open():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "store.db")
        store = SQLiteRunStore(db_path=db_path)
        store._conn.execute(
            "INSERT INTO runs (run_id, root_run_id, parent_run_id, state, version, "
            "created_at, updated_at, ended_at, role, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-1", "root", None, "STOPPED_BEFORE_B06", 1, "t", "t", None, "ops", "{}"),
        )
        store._conn.execute(
            "INSERT INTO runs (run_id, root_run_id, parent_run_id, state, version, "
            "created_at, updated_at, ended_at, role, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("legacy-2", "root", None, "IN_PROGRESS", 1, "t", "t", None, "ops", "{}"),
        )
        store._conn.commit()
        store.close()

        # Reopen: migration runs at init.
        store2 = SQLiteRunStore(db_path=db_path)
        r1 = store2.get_run("legacy-1")
        r2 = store2.get_run("legacy-2")
        assert r1.state == "advance_or_stop"
        assert r1.metadata.get("stop_reason") == "before_gate"
        assert r2.state == "in_progress"
        store2.close()


if __name__ == "__main__":
    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in _tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
