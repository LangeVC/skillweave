"""Generic Lifecycle Extension — standalone lifecycle contracts (SW-160).

These contracts are *bytes at a path*: an external consumer validates them with
only the contract directory and a JSON Schema engine. Nothing here imports
``skillweave``; the whole suite resolves the contract set relative to this file
and drives it through ``jsonschema`` + ``referencing`` alone.

Acceptance criteria proven here:

* **AC1** — an external consumer validates every contract without installing
  SkillWeave core (cross-schema ``$ref`` resolution is satisfied purely from the
  contract directory, and a child interpreter reproduces it).
* **AC2** — legacy software delivery stays representable without semantic loss
  (the canonical seven-phase substrate maps onto kernel stages with every id,
  order, skill, capability and phase type preserved).
* **AC3** — the model and search provider contracts name no concrete provider;
  a provider is an opaque, consumer-supplied identifier.
* **AC4** — unknown contract versions and unknown categories fail closed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

CONTRACTS_DIR = (
    Path(__file__).resolve().parents[2] / "schemas" / "lifecycle-contracts"
)
LOCK = json.loads((CONTRACTS_DIR / "contract-lock.json").read_text(encoding="utf-8"))

# The seven canonical legacy software-delivery phases, in order, with the
# kernel stage each one collapses onto. Domain-neutral consumers read the
# kernel stage; legacy consumers keep reading the phase id.
LEGACY_PHASE_TO_KERNEL = {
    "discovery": "K0",
    "blueprint": "K1",
    "design": "K2",
    "build": "K3",
    "release": "K4",
    "launch": "K5",
    "post-release": "K6",
}

# Names that must never appear in a provider-neutral contract. A contract that
# hard-codes any of these would bind SkillWeave to a concrete vendor.
FORBIDDEN_PROVIDER_NAMES = (
    "openrouter",
    "faigate",
    "omniroute",
    "kilo",
    "9router",
    "anthropic",
    "openai",
    "google",
    "gemini",
    "brave",
    "tavily",
    "serpapi",
    "bing",
    "duckduckgo",
)


def _load(name: str) -> dict:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


def _registry() -> Registry:
    """Every contract registered by its own ``$id``.

    Cross-schema ``$ref``s resolve from *this directory only* — the exact
    capability an external consumer needs, with no Core on the import path.
    """
    resources = []
    for schema_file in CONTRACTS_DIR.glob("*.schema.json"):
        doc = _load(schema_file.name)
        resources.append(
            (doc["$id"], Resource.from_contents(doc, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def _validator(contract: str) -> Draft202012Validator:
    entry = LOCK["contracts"][contract]
    assert entry["supportedVersions"] == ["1.0.0"], entry
    return Draft202012Validator(_load(entry["schema"]), registry=_registry())


def _minimal_instances() -> dict[str, dict]:
    """One smallest-legal instance per contract, derived from the lock."""
    return {
        "work-profile": {
            "contractVersion": "1.0.0",
            "id": "example-work",
            "category": "build",
            "kernelStages": ["K3"],
        },
        "lifecycle-profile": {
            "contractVersion": "1.0.0",
            "id": "example-lifecycle",
            "phases": [{"id": "phase-one", "order": 1, "kernelStage": "K0"}],
        },
        "deliverable-contract": {
            "contractVersion": "1.0.0",
            "id": "example-deliverable",
            "entrypoints": [
                {"id": "artifact", "surface": "code", "acceptance": "tests pass"}
            ],
        },
        "evidence-contract": {
            "contractVersion": "1.0.0",
            "id": "example-evidence",
            "requirements": [
                {"id": "proof", "kind": "test-run", "strength": "reproduced"}
            ],
        },
        "category-pack": {
            "contractVersion": "1.0.0",
            "id": "example-pack",
            "category": "assure",
        },
        "category-taxonomy": {
            "contractVersion": "1.0.0",
            "categories": LOCK["vocabulary"]["categories"],
            "kernelStages": LOCK["vocabulary"]["kernelStages"],
            "topologies": LOCK["vocabulary"]["topologies"],
            "humanCoupling": LOCK["vocabulary"]["humanCoupling"],
            "changeSurfaces": LOCK["vocabulary"]["changeSurfaces"],
        },
        "model-provider": {
            "contractVersion": "1.0.0",
            "id": "example-model",
            "hostFrameworkIdentifier": "consumer-supplied-host",
            "catalogueIdentifier": "consumer-supplied-catalogue",
        },
        "search-provider": {
            "contractVersion": "1.0.0",
            "id": "example-search",
            "hostFrameworkIdentifier": "consumer-supplied-host",
            "catalogueIdentifier": "consumer-supplied-catalogue",
        },
    }


def test_ac1_external_consumer_validates_every_contract_without_core():
    """AC1: every locked contract validates from the directory alone."""
    assert set(_minimal_instances()) == set(LOCK["contracts"])
    for contract, instance in _minimal_instances().items():
        errors = sorted(
            _validator(contract).iter_errors(instance), key=lambda e: list(e.path)
        )
        assert errors == [], f"{contract}: {[e.message for e in errors]}"


CHILD_SCRIPT = '''\
import json
import pathlib
import sys

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

d = pathlib.Path(sys.argv[1])
resources = []
docs = {}
by_file = {}
for f in d.glob("*.schema.json"):
    doc = json.loads(f.read_text())
    docs[doc["$id"]] = doc
    by_file[f.name] = doc
    resources.append((doc["$id"], Resource.from_contents(doc)))

assert "skillweave" not in sys.modules, "Core leaked onto the import path"
lock = json.loads((d / "contract-lock.json").read_text())
registry = Registry().with_resources(resources)

# One smallest-legal instance per locked contract, resolved purely from the
# contract directory. The taxonomy instance is the lock vocabulary verbatim.
instances = {
    "work-profile": {"contractVersion": "1.0.0", "id": "w", "category": "build", "kernelStages": ["K3"]},
    "lifecycle-profile": {"contractVersion": "1.0.0", "id": "l", "phases": [{"id": "p", "order": 1, "kernelStage": "K0"}]},
    "deliverable-contract": {"contractVersion": "1.0.0", "id": "d", "entrypoints": [{"id": "a", "surface": "code", "acceptance": "tests pass"}]},
    "evidence-contract": {"contractVersion": "1.0.0", "id": "e", "requirements": [{"id": "r", "kind": "test-run", "strength": "reproduced"}]},
    "category-pack": {"contractVersion": "1.0.0", "id": "c", "category": "assure"},
    "category-taxonomy": {"contractVersion": lock["contractSet"]["version"], **lock["vocabulary"]},
    "model-provider": {"contractVersion": "1.0.0", "id": "m", "hostFrameworkIdentifier": "h", "catalogueIdentifier": "c"},
    "search-provider": {"contractVersion": "1.0.0", "id": "s", "hostFrameworkIdentifier": "h", "catalogueIdentifier": "c"},
}

for name, entry in lock["contracts"].items():
    validator = Draft202012Validator(by_file[entry["schema"]], registry=registry)
    errors = list(validator.iter_errors(instances[name]))
    if errors:
        print(f"{name}: {errors[0].message}")
        sys.exit(1)

print("OK")
'''


def test_ac1_standalone_child_interpreter_validates_contracts(tmp_path):
    """AC1: a fresh interpreter with no Core on the path validates the set."""
    script = tmp_path / "external_consumer.py"
    script.write_text(CHILD_SCRIPT, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(script), str(CONTRACTS_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "OK", proc.stdout


def test_ac2_legacy_software_delivery_representable_without_semantic_loss():
    """AC2: the canonical seven-phase substrate survives a lossless mapping."""
    substrate = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "substrate-root"
        / ".skillweave"
        / "phases.yaml"
    )
    legacy = yaml.safe_load(substrate.read_text(encoding="utf-8"))
    legacy_phases = legacy["phases"]
    assert [p["id"] for p in legacy_phases] == list(LEGACY_PHASE_TO_KERNEL)

    profile = {
        "contractVersion": "1.0.0",
        "id": "software-product-delivery",
        "title": "Legacy software product delivery",
        "category": "build",
        "topology": "linear",
        "humanCoupling": "supervised",
        "changeSurfaces": ["code", "configuration", "documents"],
        "phases": [
            {
                "id": p["id"],
                "order": p["order"],
                "kernelStage": LEGACY_PHASE_TO_KERNEL[p["id"]],
                "phaseType": p["phase_type"],
                "skills": p["skills"],
                "capabilities": p["capabilities"],
            }
            for p in legacy_phases
        ],
        "globalSkills": [
            {"id": g["id"], "type": g["type"], "description": g["description"]}
            for g in legacy["global_skills"]
        ],
    }

    validator = _validator("lifecycle-profile")
    errors = sorted(validator.iter_errors(profile), key=lambda e: list(e.path))
    assert errors == [], [e.message for e in errors]

    # No semantic loss: ids, order, phase type, skills and capabilities are
    # carried across verbatim, and every phase names a kernel stage.
    by_id = {p["id"]: p for p in profile["phases"]}
    assert len(by_id) == len(legacy_phases) == 7
    for original in legacy_phases:
        mapped = by_id[original["id"]]
        assert mapped["order"] == original["order"]
        assert mapped["phaseType"] == original["phase_type"]
        assert mapped["skills"] == original["skills"]
        assert mapped["capabilities"] == original["capabilities"]
        assert mapped["kernelStage"] in LOCK["vocabulary"]["kernelStages"]

    # Global skills are still representable (a legacy-only notion kept whole):
    # the accepted profile carries every fixture global across verbatim.
    carried = {g["id"]: g for g in profile["globalSkills"]}
    assert len(carried) == len(legacy["global_skills"])
    for original in legacy["global_skills"]:
        assert carried[original["id"]]["type"] == original["type"]
        assert carried[original["id"]]["description"] == original["description"]


def test_ac3_provider_contracts_accept_opaque_ids_and_name_no_provider():
    """AC3: providers are opaque consumer identifiers, never concrete names."""
    for contract in ("model-provider", "search-provider"):
        validator = _validator(contract)
        for opaque in ("acme-host", "internal-gateway", "vendor-neutral.catalog"):
            instance = {
                "contractVersion": "1.0.0",
                "id": "binding",
                "hostFrameworkIdentifier": opaque,
                "catalogueIdentifier": opaque,
            }
            errors = list(validator.iter_errors(instance))
            assert errors == [], [e.message for e in errors]

    # No contract in the set names a concrete provider.
    for schema_file in CONTRACTS_DIR.rglob("*"):
        if not schema_file.is_file():
            continue
        text = schema_file.read_text(encoding="utf-8").lower()
        for banned in FORBIDDEN_PROVIDER_NAMES:
            assert banned not in text, f"{schema_file.name} names provider {banned!r}"


@pytest.mark.parametrize("contract", sorted(_minimal_instances()))
def test_ac4_unknown_contract_versions_fail_closed(contract):
    """AC4: an unsupported contractVersion is rejected, never coerced."""
    instance = dict(_minimal_instances()[contract])
    instance["contractVersion"] = "9.9.9"
    assert list(_validator(contract).iter_errors(instance)), (
        f"{contract} accepted an unknown contract version"
    )
    # The registry itself agrees: the version is simply not supported.
    assert "9.9.9" not in LOCK["contracts"][contract]["supportedVersions"]


def test_ac4_unknown_categories_and_vocabulary_fail_closed():
    """AC4: unknown categories and unknown vocabulary members are rejected."""
    work = dict(_minimal_instances()["work-profile"])
    work["category"] = "unknown_category"
    assert list(_validator("work-profile").iter_errors(work))

    pack = dict(_minimal_instances()["category-pack"])
    pack["category"] = "not-a-category"
    assert list(_validator("category-pack").iter_errors(pack))

    for field, value in (
        ("kernelStages", ["K99"]),
        ("topology", "teleport"),
        ("humanCoupling", "unbounded"),
        ("changeSurfaces", ["emotions"]),
    ):
        instance = dict(_minimal_instances()["work-profile"])
        instance[field] = value
        assert list(_validator("work-profile").iter_errors(instance)), (
            f"unknown {field} accepted"
        )

    # Taxonomy is a closed enum on every dimension.
    tax = dict(_minimal_instances()["category-taxonomy"])
    tax["categories"] = LOCK["vocabulary"]["categories"] + ["unknown_category"]
    assert list(_validator("category-taxonomy").iter_errors(tax))

    # The lock advertises exactly the canonical 11 categories.
    assert LOCK["vocabulary"]["categories"] == [
        "research",
        "decide",
        "design",
        "author",
        "facilitate",
        "build",
        "transform",
        "assure",
        "operate",
        "publish",
        "learn",
    ]


def test_every_locked_contract_file_exists_and_is_self_describing():
    """The lock and the directory cannot drift: every entry resolves."""
    for contract, entry in LOCK["contracts"].items():
        schema_path = CONTRACTS_DIR / entry["schema"]
        assert schema_path.is_file(), f"{contract}: missing {entry['schema']}"
        doc = json.loads(schema_path.read_text(encoding="utf-8"))
        assert doc["$id"].startswith("https://skillweave.dev/schemas/lifecycle/")
        assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"
