"""Dispatch-order group 7 — architecture negatives (criterion 7).

Proves the static, read-only rejections the gate enforces:

* **copied schemas** — the SDK contract schemas are owned by ``skillweave-sdk``;
  a byte-identical copy under Core's ``schemas/`` is refused as a second truth;
* **CMS / provider branches in Core** — the dispatch contract and profile
  resolution name no ``cms`` subject and no provider branch;
* **weakened Pro-pack authority** — the Pro pack may only tighten gates, never
  weaken them; its authority separation (producer ≠ approver, reviewer read-only)
  is refused if relaxed;
* **implicit profile mode** — dispatch requires an explicit profile path with no
  default, and profiles declare themselves opt-in;
* **unsupported silent fallback** — unknown tier, unknown ``on_model_failure``,
  and unrecognised provider prefixes all raise rather than silently degrade.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from skillweave.routing.faigate_adapter import (
    ModelNamespaceError,
    translate_model_id,
)
from skillweave.routing.profile import (
    RoutingProfileError,
    VALID_TIERS,
    tier_to_router,
)

from tests.gate_1312 import _sibling as sib


def _core_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_criterion_07_static_rejects_and_architecture_negatives():
    """Rejects copied schemas, CMS/provider branches in Core, weakened Pro-pack
    authority, implicit profile mode, and unsupported silent fallback.
    """
    core = _core_root()

    # --- Copied schemas: Core must not vendor the SDK's preview contract -------
    # The four-way split assigns the *preview* contract schemas (lifecycle-
    # profile, work-profile, deliverables, evidence-contract, subject-ref) to
    # skillweave-sdk alone. Core owns execution schemas (dispatch-sequence,
    # dispatch-trace, transfer-entry, harness-capability). A byte-copy of any
    # preview schema into Core would be a second, drifting truth and is refused.
    sdk_schemas = sib.sdk_root() / "schemas"
    assert sdk_schemas.is_dir()
    core_schemas = core / "schemas"
    copies: list[str] = []
    for schema_file in sdk_schemas.rglob("*.preview.schema.json"):
        core_copy = core_schemas / schema_file.name
        if core_copy.is_file() and core_copy.read_bytes() == schema_file.read_bytes():
            copies.append(schema_file.name)
    assert copies == [], f"Core vendors byte-copies of SDK preview schemas: {copies}"

    # No preview schema is present under Core's schemas/ at all (the contract
    # is fully SDK-owned; Core imports none of it as its own schema).
    core_previews = sorted(
        p.name for p in core_schemas.rglob("*.preview.schema.json")
    )
    assert core_previews == [], f"Core carries preview schemas: {core_previews}"

    # --- CMS / provider branches in Core ---------------------------------------
    import skillweave.dispatch.contracts as dc
    import skillweave.dispatch.profile_resolution as pr
    for module in (dc, pr):
        low = inspect.getsource(module).lower()
        assert "cms" not in low, f"{module.__name__} contains a cms branch"
    # The profile resolver carries no provider branch: it never compares against
    # a literal provider name and never imports a concrete provider class. Model
    # id resolution is delegated to the model-spec seam.
    pr_src = inspect.getsource(pr)
    for provider in ("openrouter", "faigate", "omniroute", "claw", "kilo", "9router"):
        assert f'"{provider}"' not in pr_src, (
            f"profile_resolution hard-codes provider {provider!r}"
        )
        assert f"'{provider}'" not in pr_src, (
            f"profile_resolution hard-codes provider {provider!r}"
        )

    # --- Weakened Pro-pack authority -------------------------------------------
    import yaml
    process = yaml.safe_load((sib.cms_pack_dir() / "process.yaml").read_text())["process"]
    producer = next(r for r in process["roles"] if r["id"] == "cms-ops-producer")
    approver = next(r for r in process["roles"] if r["id"] == "publish-approver")
    # Authority separation is strict: producer cannot publish/self-approve, and
    # approver is distinct from producer.
    assert set(producer["cannot"]) == {"self_approve", "publish"}
    assert approver["distinctFrom"] == ["cms-ops-producer"]
    # The pack tightens, never weakens: required capabilities block before
    # mutation (no false success), optional degrade with explicit declaration.
    deg = process["degradation"]
    assert deg["noFalseSuccess"] is True
    assert all(c["onMissing"] == "block_before_mutation"
               for c in deg["requiredCapabilities"])

    # --- Implicit profile mode: explicit path, no default, opt-in ---------------
    # tier_to_router has no implicit default tier; an unknown tier raises.
    assert VALID_TIERS == frozenset({"fast", "balanced", "deep"})
    with pytest.raises(RoutingProfileError):
        tier_to_router("nonsense")
    # RoutingProfile requires an explicit name; profiles opt in via data.
    from skillweave.routing.profile import RoutingProfile
    with pytest.raises(RoutingProfileError):
        RoutingProfile.from_dict({"tier": "balanced"})

    # --- Unsupported silent fallback -------------------------------------------
    # An unknown on_model_failure is refused, not silently defaulted.
    from skillweave.routing.profile import Limits
    with pytest.raises(RoutingProfileError):
        Limits.from_dict({"on_model_failure": "whatever"})
    # An unrecognised provider prefix is refused, not silently collapsed.
    with pytest.raises(ModelNamespaceError):
        translate_model_id("openrouter/x")
    with pytest.raises(ModelNamespaceError):
        translate_model_id("faigate/faigate/x")
    with pytest.raises(ModelNamespaceError):
        translate_model_id("faigate/")


def test_core_schemas_dir_does_not_copy_sdk_preview_ids():
    """The Core ``schemas/`` dir carries execution schemas with their own $ids;
    no SDK *preview* contract $id is duplicated in Core (no silently duplicated
    authority). The legacy co-located schemas (run-state, evidence) predate the
    four-way split and are not preview-contract copies.
    """
    core = _core_root()
    schemas_dir = core / "schemas"
    sdk_schemas = sib.sdk_root() / "schemas"
    import json
    preview_ids = set()
    for f in sdk_schemas.rglob("*.preview.schema.json"):
        try:
            preview_ids.add(json.loads(f.read_text()).get("$id"))
        except (json.JSONDecodeError, OSError):
            continue
    assert preview_ids, "no SDK preview schema $ids resolved"
    for f in schemas_dir.rglob("*.schema.json"):
        doc = json.loads(f.read_text())
        assert doc.get("$id") not in preview_ids, (
            f"{f.name} duplicates an SDK preview contract $id {doc.get('$id')!r}"
        )
