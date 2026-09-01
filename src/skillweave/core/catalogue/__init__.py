"""SkillWeave Model & Harness Catalogue (SW-CATALOG-001).

Reads ``config/catalogue.yaml`` — the single source of truth for which model
serves which role and which harnesses are proven — and exposes three lookup
functions:

- :func:`load_catalogue` — parse the tracked catalogue (shipped at
  ``config/catalogue.yaml``, resolvable from the module location).
- :func:`get_model_for_role` — resolve a role to a model id, honouring the
  ``!= ops`` constraint and ``cost_index`` preference.
- :func:`get_harness_config` — return the raw config dict for a named harness.

The catalogue is loaded lazily and cached per-process. A custom path can be
injected via :func:`load_catalogue` (e.g. in tests).

Constraint mini-language
------------------------
``role_defaults.<role>.constraints`` is a list of strings. Supported:

``!= ops``
    The resolved model for this role MUST NOT equal the model assigned to the
    ``ops`` role. This is the separation-of-duties guard: the reviewer never
    reviews with the same model that mutates run state.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# --- internal state ---------------------------------------------------------

_catalogue: dict[str, Any] | None = None
_catalogue_path: Path | None = None


def _default_path() -> Path:
    """Locate the tracked ``config/catalogue.yaml``, preferring an override.

    Resolution order:

    1. An operator-provided ``.skillweave/catalogue.yaml`` found by walking up
       from the current working directory (this is substrate IP and is never
       committed, but may be supplied at runtime).
    2. The deliverable shipped with the repository at ``config/catalogue.yaml``,
       anchored to the installed package so the lookup works from any ``cwd``.
    """
    candidate = Path.cwd()
    for parent in (candidate, *candidate.parents):
        probe = parent / ".skillweave" / "catalogue.yaml"
        if probe.exists():
            return probe
    return Path(__file__).resolve().parents[4] / "config" / "catalogue.yaml"


# --- public API -------------------------------------------------------------


def load_catalogue(path: str | Path | None = None) -> dict[str, Any]:
    """Load (or reload) the catalogue from *path*.

    If *path* is ``None`` the default catalogue is resolved: an operator
    ``.skillweave/catalogue.yaml`` if present, else ``config/catalogue.yaml``
    (see :func:`_default_path`).

    Args:
        path: Filesystem path to the catalogue YAML file.

    Returns:
        The raw parsed catalogue dict.

    Raises:
        FileNotFoundError: If the catalogue file does not exist.
        ValueError: If the YAML file is not a mapping.
    """
    global _catalogue, _catalogue_path

    resolved = Path(path) if path else _default_path()
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved

    if not resolved.exists():
        raise FileNotFoundError(
            f"SkillWeave catalogue not found at: {resolved!s}\n"
            "Create config/catalogue.yaml or supply a custom path."
        )

    with resolved.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not isinstance(data, dict):
        raise ValueError(
            f"catalogue.yaml at {resolved!s} must be a YAML mapping, "
            f"got: {type(data).__name__}"
        )

    _catalogue = data
    _catalogue_path = resolved
    return _catalogue


def _get_catalogue() -> dict[str, Any]:
    """Return the cached catalogue, loading the default if not yet loaded."""
    global _catalogue
    if _catalogue is None:
        load_catalogue()
    assert _catalogue is not None
    return _catalogue


def _role_model(role: str) -> str:
    """Return the declared model id for *role* in ``role_defaults``."""
    catalogue = _get_catalogue()
    role_defaults = catalogue.get("role_defaults", {})
    if role not in role_defaults:
        defined = sorted(role_defaults.keys())
        raise KeyError(
            f"Role {role!r} is not defined in the catalogue. "
            f"Available roles: {defined}"
        )
    return role_defaults[role]["model"]


# --- model resolution -------------------------------------------------------


def get_model_for_role(role: str, exclude: str = None) -> str:
    """Return the best model id for *role*.

    Resolution order:

    1. Look up the role's declared default model in ``role_defaults``.
    2. Evaluate the role's ``constraints``. ``!= ops`` means the declared
       model must not equal the ``ops`` role's model; if it would, fall back
       to the cheapest eligible model by ``cost_index``.
    3. If *exclude* names a role, the model serving that role is also banned
       (the same separation-of-duties rule, applied by caller).

    Args:
        role: Role name under ``catalogue.yaml -> role_defaults``.
        exclude: Optional role whose model must be avoided.

    Returns:
        The winning model id.

    Raises:
        KeyError: If *role* is not defined.
        LookupError: If no eligible model satisfies the constraints.
    """
    role_defaults = _get_catalogue().get("role_defaults", {})
    rejected = _allowed_role_names(role, exclude)

    candidate = role_defaults[role]["model"]

    banned_ops = False
    constraints = role_defaults[role].get("constraints", [])
    if "!= ops" in constraints:
        ops_model = _role_model("ops")
        banned_ops = candidate == ops_model

    if banned_ops or candidate in rejected:
        candidate = _cheapest_non_rejected(rejected)

    return candidate


def _allowed_role_names(role: str, exclude: str | None) -> set[str]:
    """Build the set of model ids the resolved role must avoid."""
    role_defaults = _get_catalogue().get("role_defaults", {})
    if role not in role_defaults:
        defined = sorted(role_defaults.keys())
        raise KeyError(
            f"Role {role!r} is not defined in the catalogue. "
            f"Available roles: {defined}"
        )

    rejected: set[str] = set()
    if exclude and exclude in role_defaults:
        rejected.add(role_defaults[exclude]["model"])
    return rejected


def _cheapest_non_rejected(rejected: set[str]) -> str:
    """Return the cheapest model in the catalogue not in *rejected*."""
    models = _get_catalogue().get("models", {})
    eligible = [
        mid
        for mid in models
        if mid not in rejected
    ]
    if not eligible:
        raise LookupError(
            "No eligible model satisfies the role constraints. "
            f"Rejected models: {sorted(rejected)}"
        )
    eligible.sort(key=lambda mid: models[mid].get("cost_index", 0))
    return eligible[0]


# --- harness config ---------------------------------------------------------


def get_harness_config(name: str) -> dict[str, Any]:
    """Return the harness configuration dict for *name*.

    Args:
        name: Harness name under ``catalogue.yaml -> harnesses``.

    Returns:
        A copy of the harness config (callers cannot mutate the cache).

    Raises:
        KeyError: If *name* is not defined.
    """
    catalogue = _get_catalogue()
    harnesses = catalogue.get("harnesses", {})
    if name not in harnesses:
        available = sorted(harnesses.keys())
        raise KeyError(
            f"Harness {name!r} is not defined in the catalogue. "
            f"Available harnesses: {available}"
        )
    return dict(harnesses[name])


# --- utilities ---------------------------------------------------------------


def list_roles() -> list[str]:
    """Return a sorted list of role names defined in the catalogue."""
    return sorted(_get_catalogue().get("role_defaults", {}).keys())


def list_models() -> list[str]:
    """Return a sorted list of model ids defined in the catalogue."""
    return sorted(_get_catalogue().get("models", {}).keys())


def list_harnesses() -> list[str]:
    """Return a sorted list of harness names defined in the catalogue."""
    return sorted(_get_catalogue().get("harnesses", {}).keys())
