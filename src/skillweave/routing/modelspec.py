"""Per-child model specification for fan-out (SW-FANOUT-001-MODELSPEC).

A fan-out child may resolve its own model instead of sharing one parent model.
``ModelSpec`` is the declarative seam: it is either a *concrete* model id
(``concrete("faigate/deepseek-v4-pro")``) or a *delegated* router + scenario
(``delegated("faigate", "auto")``) that an adapter resolves later against its
provider list. A single, shared ``model: str`` remains a valid backward-compatible
way to name one concrete model for every child; the seam lifts it to
``concrete(model)``.

The two variants are guaranteed distinct: a ``ModelSpec`` can never be both
concrete and delegated, and a value that is ambiguous or empty is refused
*at construction* (falls closed) rather than surfacing later as a silent bad
model. This is the same "fall closed" discipline the routing layer already
applies to capabilities and tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


class ModelSpecError(ValueError):
    """Raised when a ``ModelSpec`` is built from an ambiguous or empty value."""


@dataclass(frozen=True)
class ModelSpec:
    """One fan-out child's model resolution: concrete id or delegated scenario.

    Exactly one of ``model`` (concrete id) and ``router``/``scenario`` (delegated)
    is set; the other side is ``None``. The public constructors
    :func:`concrete` and :func:`delegated` enforce this, plus the empty/ambiguous
    refusal, so an invalid spec never reaches a resolver.

    ``kind`` is ``"concrete"`` or ``"delegated"`` — the explicit variant tag a
    later reader (and the evidence record) keys on, so the two cases are never
    collapsed into one field.
    """

    kind: str
    model: Optional[str] = None
    router: Optional[str] = None
    scenario: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Dict form for evidence: the variant plus its payload, never a guess."""
        out: dict[str, Any] = {"kind": self.kind}
        if self.kind == "concrete":
            out["model"] = self.model
        else:
            out["router"] = self.router
            out["scenario"] = self.scenario
        return out


def concrete(model: str) -> ModelSpec:
    """Build a concrete-model spec, refusing an empty/ambiguous id (falls closed).

    A concrete spec pins one model id, e.g. ``"faigate/deepseek-v4-flash"``.
    Wiring it through this constructor means an empty string or a value that is
    actually a delegated spec (carrying a ``/`` router delimiter) is refused
    here, not silently resolved to something the caller did not ask for.
    """
    if not model or not model.strip():
        raise ModelSpecError("concrete model spec requires a non-empty model id")
    body = model.strip()
    if body.startswith("/") or body.endswith("/"):
        raise ModelSpecError(
            "concrete model spec requires a model body on both sides of a router delimiter"
        )
    return ModelSpec(kind="concrete", model=body)


def delegated(router: str, scenario: str) -> ModelSpec:
    """Build a delegated-router spec, refusing an empty router or scenario.

    A delegated spec names a router (e.g. ``"faigate"``) and a scenario (e.g.
    ``"auto"`` or ``"coding-fast"``) that an adapter resolves later. Both parts
    are required; an empty either one is refused (falls closed).
    """
    if not router or not router.strip():
        raise ModelSpecError("delegated model spec requires a non-empty router")
    if not scenario or not scenario.strip():
        raise ModelSpecError("delegated model spec requires a non-empty scenario")
    return ModelSpec(
        kind="delegated",
        router=router.strip(),
        scenario=scenario.strip(),
    )


def from_value(value: Any) -> ModelSpec:
    """Normalise a caller-supplied model value into a ``ModelSpec``.

    A plain ``str`` is a concrete model (backward compatible with the single
    ``model: str`` contract). A ``ModelSpec`` passes through unchanged. Anything
    else — including ``None``, an empty string, or an ambiguous value — is
    refused, so every fan-out child gets an explicit, non-empty resolution.
    """
    if isinstance(value, ModelSpec):
        return value
    if isinstance(value, str):
        return concrete(value)
    raise ModelSpecError(
        f"cannot build a ModelSpec from {value!r}: expected a str or a ModelSpec"
    )


def resolve(spec: ModelSpec) -> str:
    """Return a concrete model id for a spec, delegating via the adapter.

    This is the resolution seam :func:`skillweave.routing.faigate_adapter.
    resolve_model_spec` re-implements with provider knowledge; the plain helper
    here only unwraps a concrete spec and defers a delegated one to the adapter
    so the two stay in one place for evidence.
    """
    from .faigate_adapter import resolve_model_spec

    return resolve_model_spec(spec)


__all__ = [
    "ModelSpec",
    "ModelSpecError",
    "concrete",
    "delegated",
    "from_value",
    "resolve",
]
