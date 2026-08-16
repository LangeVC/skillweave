import json
from pathlib import Path

from skillweave.runtime.store import RunStateModel


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

    assert len(model) == len(schema), (
        f"count mismatch: model has {len(model)} values, schema has {len(schema)}"
    )

    missing_in_schema = model - schema
    assert not missing_in_schema, (
        f"model states missing from schema enum: {sorted(missing_in_schema)}"
    )

    extra_in_schema = schema - model
    assert not extra_in_schema, (
        f"schema enum values absent from model: {sorted(extra_in_schema)}"
    )
