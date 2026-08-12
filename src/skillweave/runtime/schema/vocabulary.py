from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from skillweave.runtime.store import RunStateModel


RUN_STATE_COVERAGE_STATUSES = {
    "externally_satisfied",
    "not_applicable",
    "implemented",
    "amendment_required",
    "deferred",
    "blocked",
}


class StatusRejectedError(ValueError):
    def __init__(self, value, schema_version, valid_values):
        self.value = value
        self.schema_version = schema_version
        self.valid_values = valid_values
        super().__init__(
            f"Status value '{value}' rejected by schema v{schema_version}. "
            f"Valid values: {valid_values}"
        )


@dataclass
class AmendmentRecord:
    added_value: str
    reason: str
    schema_version: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    amended_by: str = "ops"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "added_value": self.added_value,
            "reason": self.reason,
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "amended_by": self.amended_by,
            "metadata": self.metadata,
        }


@dataclass
class StatusSchema:
    version: int
    valid_values: set[str]
    description: str = ""
    changelog: list[AmendmentRecord] = field(default_factory=list)

    def accepts(self, value: str) -> bool:
        return value in self.valid_values

    def to_dict(self):
        return {
            "version": self.version,
            "valid_values": sorted(self.valid_values),
            "description": self.description,
            "changelog": [a.to_dict() for a in self.changelog],
        }


class StatusVocabulary:
    def __init__(self):
        self._schemas: dict[int, StatusSchema] = {}
        self._init_base_schema()

    def _init_base_schema(self):
        base = StatusSchema(
            version=1,
            valid_values={s.value for s in RunStateModel},
            description="SkillWeave Runtime Status Vocabulary v1",
        )
        self._schemas[1] = base

    def current_schema(self) -> StatusSchema:
        return self._schemas[max(self._schemas.keys())]

    def get_schema(self, version: int) -> Optional[StatusSchema]:
        return self._schemas.get(version)

    def validate(self, value: str, schema_version: Optional[int] = None) -> bool:
        version = schema_version or max(self._schemas.keys())
        schema = self._schemas.get(version)
        if schema is None:
            raise ValueError(f"Unknown schema version: {version}")
        if not schema.accepts(value):
            raise StatusRejectedError(value, version, sorted(schema.valid_values))
        return True

    def amend(self, new_value: str, reason: str, amended_by: str = "ops") -> AmendmentRecord:
        current = self.current_schema()
        if new_value in current.valid_values:
            raise ValueError(f"Value '{new_value}' already exists in schema v{current.version}")

        new_version = current.version + 1
        new_valid = current.valid_values | {new_value}

        amendment = AmendmentRecord(
            added_value=new_value,
            reason=reason,
            schema_version=new_version,
            amended_by=amended_by,
        )

        new_schema = StatusSchema(
            version=new_version,
            valid_values=new_valid,
            description=f"SkillWeave Runtime Status Vocabulary v{new_version}",
            changelog=list(current.changelog) + [amendment],
        )
        self._schemas[new_version] = new_schema
        return amendment

    def amend_bulk(self, values: list[str], reason: str, amended_by: str = "ops") -> AmendmentRecord:
        current = self.current_schema()
        new_values = [v for v in values if v not in current.valid_values]
        if not new_values:
            raise ValueError("All values already exist in current schema")

        new_version = current.version + 1
        new_valid = current.valid_values | set(new_values)

        amendment = AmendmentRecord(
            added_value=",".join(new_values),
            reason=reason,
            schema_version=new_version,
            amended_by=amended_by,
        )

        new_schema = StatusSchema(
            version=new_version,
            valid_values=new_valid,
            description=f"SkillWeave Runtime Status Vocabulary v{new_version}",
            changelog=list(current.changelog) + [amendment],
        )
        self._schemas[new_version] = new_schema
        return amendment


_vocabulary = StatusVocabulary()


def validate_status(value: str, schema_version: Optional[int] = None) -> bool:
    return _vocabulary.validate(value, schema_version)


def get_vocabulary() -> StatusVocabulary:
    return _vocabulary
