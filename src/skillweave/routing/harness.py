"""The harness as a recorded fact, and profiles loaded from a place.

SW-RT-003, dispatch 1. Two acceptance criteria, nothing else:

1. **The executing harness is determined and recorded on the run.** The
   determination is *explicit*: either the caller set it or it was detected,
   and the record says which of the two. A detected harness that was actually
   only guessed must never read as a declared one, so the source is a first-class
   field on the record, not an inference the reader has to re-derive.

2. **Profiles are loaded from a declared location, and a harness maps to one
   or more profile names as DATA.** The caller names the location to load from
   (a path, never a bare dict handed in), and the harness -> profile mapping is
   a plain table a caller supplies. Adding a harness or a profile edits data;
   it never adds a branch.

Design notes
------------

``HarnessSource`` has exactly two values: ``DECLARED`` (the caller set it) and
``DETECTED`` (resolved by inspecting the environment). There is no third state
because a value that cannot be pinned to one of these two is refused, not
labelled. A guessed value surfaces as ``DETECTED`` and carries whatever evidence
it was gleaned from, so a reader can always tell "the harness was supplied" from
"the harness was worked out".

None of this mutates ``profile.py`` or ``store.py``. The harness record is
attached into the run's ``metadata`` dict (``store.RunRecord.metadata`` is
already a free-form ``dict[str, Any]``), and profile loading reuses
``profile.load_profiles`` rather than re-implementing it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import os

import yaml

from skillweave.routing.profile import (
    RoutingProfile,
    RoutingProfileError,
    load_profiles,
)


class HarnessSource(str, Enum):
    """How a harness name was arrived at: supplied, or worked out."""

    DECLARED = "declared"
    DETECTED = "detected"


class HarnessError(ValueError):
    """Raised when a harness name, profile location, or mapping is invalid."""


@dataclass
class HarnessDetermination:
    """The harness name plus the source that produced it, as a durable record.

    ``source`` is the whole point: a ``DETECTED`` name never reads as
    ``DECLARED``, because the distinction is stored, not inferred.
    """

    name: str
    source: HarnessSource
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source.value,
            "evidence": dict(self.evidence),
        }


def _validate_name(name: Any) -> str:
    """Return ``name`` as a non-empty string, refusing anything else.

    An empty, non-string, or bare-whitespace name cannot be a legitimate
    harness and is refused rather than coerced into one.
    """
    if not isinstance(name, str) or not name.strip():
        raise HarnessError(f"harness name must be a non-empty string, got {name!r}")
    return name.strip()


def determine_harness(
    declared: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    env_key: str = "SKILLWEAVE_HARNESS",
) -> HarnessDetermination:
    """Determine the executing harness, explicit about the source.

    If ``declared`` is a non-empty string, it wins and is recorded as
    ``DECLARED``. Otherwise the harness is detected from the environment
    (``env``, or ``os.environ`` when omitted) under ``env_key``, recorded as
    ``DETECTED`` together with the variable that supplied it. If neither a call
    nor the environment names one, the result is a ``DETECTED`` record with an
    empty name, so a caller can never mistake "no data" for "the caller said so".
    """
    if declared:
        name = _validate_name(declared)
        return HarnessDetermination(
            name=name,
            source=HarnessSource.DECLARED,
            evidence={"via": "caller"},
        )

    environment = os.environ if env is None else env
    raw = environment.get(env_key)
    if raw is not None and raw.strip():
        return HarnessDetermination(
            name=_validate_name(raw),
            source=HarnessSource.DETECTED,
            evidence={"via": "environment", "key": env_key},
        )

    return HarnessDetermination(
        name="",
        source=HarnessSource.DETECTED,
        evidence={"via": "none"},
    )


@dataclass
class HarnessProfileMap:
    """A DATA table mapping a harness name to one or more profile names.

    Built from a plain mapping, never from code. ``profiles_for`` returns the
    names; adding a harness or a profile is a data change and touches no branch.
    """

    _by_harness: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HarnessProfileMap":
        if not isinstance(data, Mapping):
            raise HarnessError(
                "harness map must be a mapping of harness -> profile names"
            )
        by_harness: dict[str, list[str]] = {}
        for harness, profiles in data.items():
            name = _validate_name(harness)
            if isinstance(profiles, str):
                entries = [profiles]
            elif isinstance(profiles, Sequence):
                entries = list(profiles)
            else:
                raise HarnessError(
                    f"profiles for harness '{name}' must be a name or a list of names"
                )
            for entry in entries:
                _validate_name(entry)
            by_harness[name] = entries
        return cls(_by_harness=by_harness)

    def profiles_for(self, harness: str) -> list[str]:
        name = _validate_name(harness)
        return list(self._by_harness.get(name, []))

    def harnesses(self) -> list[str]:
        return list(self._by_harness.keys())

    def to_dict(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._by_harness.items()}


def load_profiles_from_location(
    location: str | Path,
) -> dict[str, RoutingProfile]:
    """Load profiles from the caller-declared ``location`` (a path or URI).

    The location is stated, never implied: a caller passes where to read from,
    and a missing or non-mapping file is refused. YAML parsing is done here;
    interpretation is delegated to ``profile.load_profiles`` so profiles stay a
    single responsibility.
    """
    path = Path(location)
    if not path.exists():
        raise HarnessError(f"profile location does not exist: {location}")
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise HarnessError(f"profile location is not valid YAML: {location}") from exc

    try:
        return load_profiles(data)
    except RoutingProfileError as exc:
        raise HarnessError(f"invalid profiles at {location}: {exc}") from exc


def attach_harness(
    record_or_metadata: Any,
    determination: HarnessDetermination,
) -> dict[str, Any]:
    """Attach the determination onto a run record's ``metadata`` and return it.

    Accepts a ``store.RunRecord`` (whose ``metadata`` is a free-form dict) or a
    bare metadata dict. The harness record lives under the ``"harness"`` key as
    the ``to_dict`` payload, so provenance travels with the run.
    """
    metadata: dict[str, Any]
    if hasattr(record_or_metadata, "metadata") and isinstance(
        getattr(record_or_metadata, "metadata", None), dict
    ):
        metadata = record_or_metadata.metadata
    elif isinstance(record_or_metadata, dict):
        metadata = record_or_metadata
    else:
        raise HarnessError("attach_harness expects a RunRecord or a metadata dict")

    metadata["harness"] = determination.to_dict()
    return metadata
