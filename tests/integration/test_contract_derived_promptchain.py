"""Integration test for the contract-derived promptchain (SW-160-VERT-004).

Proves all four acceptance criteria:

1. Generated artifacts carry role, scope, target repo, full base SHA, criteria
   and settled decisions.
2. Artifact digests bind the handoff and review subject to the contract input.
3. Both verticals (a build profile and a research profile) produce distinct
   valid chains through the same generator.
4. A tampered brief is rejected before worker start.

Hermetic: reads the two in-repo profile YAMLs by *data*, never a real model.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import sys
from pathlib import Path

import pytest
import yaml

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.promptchain import (  # noqa: E402
    ContractArtifact,
    ContractDerivedChain,
    ContractInput,
    ContractInputError,
    TamperedBriefError,
    contract_input_from_profile,
    dispatch_contract_chain,
    generate_contract_promptchain,
    validate_brief,
    validate_contract_chain,
)

_PROFILES = Path(__file__).resolve().parent.parent.parent / "profiles"

_BASE_SHA = "abcdef1234567890abcdef1234567890abcdef12"
_TARGET_REPO = "skillweave"
_CRITERIA = (
    "artifact records the settled contract",
    "review binds to the same subject as the producer",
)
_DECISIONS = ("one generator for every vertical", "no profile-name branch")


# ── Helpers ─────────────────────────────────────────────────────────────────


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _build_contract() -> ContractInput:
    return ContractInput(
        role="ops",
        scope=("src/**", "tests/**"),
        target_repo=_TARGET_REPO,
        base_sha=_BASE_SHA,
        criteria=_CRITERIA,
        settled_decisions=_DECISIONS,
        category="build",
    )


def _software_contract() -> ContractInput:
    return contract_input_from_profile(
        _load(_PROFILES / "software-delivery.v2.yaml"),
        target_repo=_TARGET_REPO,
        base_sha=_BASE_SHA,
        criteria=_CRITERIA,
        settled_decisions=_DECISIONS,
    )


def _research_contract() -> ContractInput:
    return contract_input_from_profile(
        _load(_PROFILES / "research-synthesis.v1.yaml"),
        target_repo="research-notes",
        base_sha=_BASE_SHA,
        criteria=("every claim is source-attributed",),
        settled_decisions=("synthesis accepted only on independent tracing",),
    )


# ── Criterion 1: artifacts carry the contract fields ─────────────────────────


def test_generated_artifacts_carry_every_contract_field():
    contract = _build_contract()
    chain = generate_contract_promptchain(contract)

    assert isinstance(chain, ContractDerivedChain)
    assert len(chain.artifacts) >= 1
    for artifact in chain.artifacts:
        assert isinstance(artifact, ContractArtifact)
        assert artifact.role
        assert artifact.scope  # scope carried
        assert artifact.target_repo == _TARGET_REPO
        assert artifact.base_sha == _BASE_SHA
        assert len(artifact.base_sha) == 40  # full SHA, not abbreviated
        assert artifact.criteria == _CRITERIA
        assert artifact.settled_decisions == _DECISIONS


def test_artifact_to_dict_serializes_the_contract_fields():
    chain = generate_contract_promptchain(_build_contract())
    payload = chain.to_dict()

    assert payload["contract_digest"]
    for entry in payload["artifacts"]:
        assert entry["base_sha"] == _BASE_SHA
        assert entry["target_repo"] == _TARGET_REPO
        assert entry["criteria"] == list(_CRITERIA)
        assert entry["settled_decisions"] == list(_DECISIONS)
        assert entry["scope"]
        assert entry["role"]


def test_contract_is_frozen_and_rejects_an_abbreviated_base_sha():
    contract = _build_contract()
    with pytest.raises(dataclasses.FrozenInstanceError):
        contract.base_sha = "0" * 40  # type: ignore[misc]

    bad = dataclasses.replace(contract, base_sha=_BASE_SHA[:8])
    with pytest.raises(ContractInputError):
        generate_contract_promptchain(bad)


def test_valid_chain_reports_no_violations():
    chain = generate_contract_promptchain(_build_contract())
    assert validate_contract_chain(chain) == []


def test_validate_contract_chain_flags_a_dropped_contract_field():
    chain = generate_contract_promptchain(_build_contract())
    stripped = dataclasses.replace(chain.artifacts[0], base_sha="")
    broken = dataclasses.replace(chain, artifacts=(stripped, *chain.artifacts[1:]))
    violations = validate_contract_chain(broken)
    assert any("base SHA" in v for v in violations)


# ── Criterion 2: digests bind handoff and review subject ─────────────────────


def test_artifact_digest_binds_the_handoff_and_review_subject():
    chain = generate_contract_promptchain(_build_contract())
    for artifact in chain.artifacts:
        # The stored digest recomputes from exactly the fields it carries...
        assert artifact.digest == artifact.recompute_digest()
        # ...and the handoff it carries is itself sealed with a digest.
        assert artifact.handoff.digest
        # ...and it binds a review subject.
        assert len(artifact.review_subject_sha) == 40

    # Producer handoff is sourced from the contract; reviewer handoff is
    # sourced from the producer artifact — the chain is a real binding.
    producer, reviewer = chain.artifacts[0], chain.artifacts[1]
    assert producer.handoff.source_receipt_id == chain.contract_digest
    assert reviewer.handoff.source_receipt_id == producer.digest


def test_changing_a_contract_field_changes_every_artifact_digest():
    original = _build_contract()
    tampered = dataclasses.replace(
        original, settled_decisions=("a different settlement",)
    )
    original_chain = generate_contract_promptchain(original)
    tampered_chain = generate_contract_promptchain(tampered)

    assert original_chain.contract_digest != tampered_chain.contract_digest
    assert [a.digest for a in original_chain.artifacts] != [
        a.digest for a in tampered_chain.artifacts
    ]


def test_review_subject_is_derived_from_the_contract_input():
    contract = _build_contract()
    chain = generate_contract_promptchain(contract)
    for artifact in chain.artifacts:
        assert artifact.review_subject_sha == chain.contract_digest[:40]


def test_handoff_and_subject_are_immutable_review_bindings():
    """The review artifact's subject SHA is a full SHA tied to the contract."""
    chain = generate_contract_promptchain(_build_contract())
    reviewer = chain.artifacts[1]
    assert reviewer.handoff.kind.value == "review"
    assert reviewer.handoff.subject_sha == chain.contract_digest[:40]
    assert len(reviewer.handoff.subject_sha) == 40


def test_artifact_digest_binds_the_handoff_digest():
    """A handoff with a different digest re-derives a different artifact digest."""
    chain = generate_contract_promptchain(_build_contract())
    producer = chain.artifacts[0]
    forged_handoff = dataclasses.replace(producer.handoff, digest="0" * 64)
    swapped = dataclasses.replace(producer, handoff=forged_handoff)
    assert swapped.recompute_digest() != producer.digest


def test_artifact_digest_binds_the_review_subject():
    """A different review subject re-derives a different artifact digest."""
    chain = generate_contract_promptchain(_build_contract())
    artifact = chain.artifacts[1]
    swapped = dataclasses.replace(artifact, review_subject_sha="1" * 40)
    assert swapped.recompute_digest() != artifact.digest


# ── Criterion 3: both verticals through the same generator ───────────────────


def test_both_verticals_derive_distinct_valid_chains():
    build_contract = _software_contract()
    research_contract = _research_contract()

    build_chain = generate_contract_promptchain(build_contract)
    research_chain = generate_contract_promptchain(research_contract)

    assert validate_contract_chain(build_chain) == []
    assert validate_contract_chain(research_chain) == []

    # Distinct: different contract digests, categories, scopes and artifacts.
    assert build_chain.contract_digest != research_chain.contract_digest
    assert build_chain.category == "build"
    assert research_chain.category == "research"
    assert build_chain.digest() != research_chain.digest()


def test_both_verticals_keep_their_own_change_surfaces():
    build_chain = generate_contract_promptchain(_software_contract())
    research_chain = generate_contract_promptchain(_research_contract())

    build_scope = set(build_chain.artifacts[0].scope)
    research_scope = set(research_chain.artifacts[0].scope)
    assert build_scope != research_scope
    # Each reflects its profile's declared changeSurfaces.
    assert any("code" in s for s in build_scope)
    assert any("knowledge" in s for s in research_scope)


def _stripped_code(source: str) -> str:
    """Return module code with every docstring removed.

    Docs may name a vertical; executable code may not branch on one. Stripping
    docstrings isolates the code that could actually branch.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.unparse(tree)


def test_generator_has_no_profile_name_branch():
    """The generator must branch on contract data, never on a profile name."""
    from skillweave import promptchain

    code = _stripped_code(inspect.getsource(promptchain)).lower()
    assert "software-delivery" not in code
    assert "research-synthesis" not in code


def test_same_contract_yields_the_same_chain():
    """Determinism: the generator is a pure function of the contract input."""
    contract = _software_contract()
    first = generate_contract_promptchain(contract)
    second = generate_contract_promptchain(
        contract_input_from_profile(
            _load(_PROFILES / "software-delivery.v2.yaml"),
            target_repo=_TARGET_REPO,
            base_sha=_BASE_SHA,
            criteria=_CRITERIA,
            settled_decisions=_DECISIONS,
        )
    )
    assert first.digest() == second.digest()


# ── Criterion 4: a tampered brief is rejected before worker start ────────────


def test_tampered_brief_is_rejected_before_worker_start():
    contract = _build_contract()
    chain = generate_contract_promptchain(contract)

    started: list[str] = []

    def _on_start(artifact: ContractArtifact) -> None:  # pragma: no cover
        started.append(artifact.id)

    # Dispatch of the intact brief starts workers (control).
    assert dispatch_contract_chain(chain, contract, on_worker_start=_on_start)
    assert len(started) == len(chain.artifacts)

    # A brief edited after generation is refused and starts zero workers.
    tampered = dataclasses.replace(contract, criteria=("a smuggled criterion",))
    started.clear()
    with pytest.raises(TamperedBriefError):
        dispatch_contract_chain(chain, tampered, on_worker_start=_on_start)
    assert started == []


def test_tampered_chain_artifact_is_rejected_before_worker_start():
    contract = _build_contract()
    chain = generate_contract_promptchain(contract)

    # Edit the artifact's digest but not its fields: the stored digest no longer
    # matches the contract-bound bytes.
    forged = dataclasses.replace(chain.artifacts[0], digest="0" * 64)
    tampered_chain = dataclasses.replace(
        chain, artifacts=(forged, *chain.artifacts[1:])
    )

    started: list[str] = []
    with pytest.raises(TamperedBriefError):
        dispatch_contract_chain(
            tampered_chain, contract, on_worker_start=lambda a: started.append(a.id)
        )
    assert started == []


def test_validate_brief_reports_reasons_for_a_tampered_brief():
    contract = _build_contract()
    chain = generate_contract_promptchain(contract)
    tampered = dataclasses.replace(contract, target_repo="somewhere-else")
    reasons = validate_brief(tampered, chain)
    assert reasons
    assert any("contract digest mismatch" in r for r in reasons)
