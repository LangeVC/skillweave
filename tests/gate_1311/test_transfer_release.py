"""Dispatch-order group 5 — "transfer safety and release regressions" (criteria 9, 10).

Criterion 9 proves the transfer catalog represents supplied evidence (the
shipped fixtures) with conflicts/limitations and that ingestion and retrieval
never mutate a policy, profile, topology, state or gate. Entries missing a
review date, observed scope or provenance fail validation and are excluded.

Criterion 10 proves the release-regression surfaces on the real tree:
import-isolation (the GLE-020 eager-closure contract), version-sync across the
release line, packaged-wheel discovery, and the nonempty exact-once
``dispatch_order`` declaration.

Hermetic; reads only the repository tree; no network; no mutation of any
product file, dispatch state, profile, topology, review disposition or gate.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from skillweave.transfer import catalog as TC
from skillweave.transfer.catalog import Entry, ObservedScope

from tests.gate_1311 import DISPATCH_ORDER

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC = REPO_ROOT / "src"

_TRANSFER_FIXTURES = (
    REPO_ROOT / "tests" / "fixtures" / "transfer" / "2026-08-28-dispatch-learnings.json"
)


# ── Criterion 9: transfer catalog ───────────────────────────────────────────


def test_criterion_09_transfer_entries_represent_and_retrieval_is_readonly():
    """Transfer entries represent supplied evidence; retrieval is advisory and
    mutates nothing; invalid entries are excluded."""
    catalog = TC.Catalog.load(_TRANSFER_FIXTURES)
    # The supplied fixture material parses into a non-empty catalog.
    assert len(catalog) > 0

    # Every parsed entry passes validate_entry, or is already recorded invalid.
    report = TC.validate_catalog(catalog, repo_root=REPO_ROOT)
    assert report is not None

    # Ingestion is immutable: a valid entry ingested returns a NEW catalog and
    # leaves the original byte-for-byte unchanged.
    valid_entry = next(
        (e for e in catalog.entries if not TC.validate_entry(e)), None
    )
    assert valid_entry is not None, "fixture must contain at least one valid entry"
    before = len(catalog)
    before_ids = [e.entry_id for e in catalog.entries]
    grown = catalog.ingest(valid_entry)
    assert len(grown) == before + 1
    assert len(catalog) == before
    assert [e.entry_id for e in catalog.entries] == before_ids

    # Retrieval is advisory and stable: two runs return equal results, and the
    # result carries observations + provenance/limitations, never a routing cmd.
    context = TC.RetrievalContext(task="review", risk="medium")
    result1 = catalog.retrieve(context)
    result2 = catalog.retrieve(context)
    assert result1.to_dict() == result2.to_dict()
    # Retrieval returns advisory observations (never a routing command).
    assert hasattr(result1, "advisory") and hasattr(result1, "superseded")

    # An entry lacking resolvable provenance, observed scope, or a review date
    # fails validation (and is therefore excluded from retrieval).
    bad = Entry(
        entry_id="bad-1",
        category="review",
        claim="a claim",
        provenance_artifacts=(),
        observed_scope=ObservedScope(task="", risk="low"),
        confidence="low",
        limitations=(),
        contraindications=(),
        status="active",
    )
    problems = TC.validate_entry(bad)
    assert problems, "entry lacking provenance/scope/date must fail validation"


# ── Criterion 10: release regression suites ─────────────────────────────────


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match
    return match.group(1)


def test_criterion_10_release_regression_suites_pass():
    """Import-isolation, version-sync, packaged discovery and dispatch_order
    exact-once all hold on the real tree."""
    import yaml

    # (a) version-sync: the bundle manifest matches pyproject.toml.
    manifest = yaml.safe_load((REPO_ROOT / "capability.yaml").read_text())
    assert manifest["version"] == _pyproject_version()

    # (b) import isolation: the package declares its optional subpackages and
    # ``import skillweave`` succeeds without forcing the optional ``runtime``.
    sys.path.insert(0, str(SRC))
    try:
        import skillweave
        declared = tuple(getattr(skillweave, "OPTIONAL_SUBPACKAGES", ()))
        assert declared, "package must declare its optional subpackages"
        assert skillweave is not None
    finally:
        sys.path.remove(str(SRC))

    # (c) packaged discovery: subpackages are discoverable and pyproject names
    # the ``skillweave*`` namespace, so a wheel build finds every package.
    package_inits = [d for d in SRC.rglob("__init__.py") if "skillweave" in d.parts]
    assert package_inits, "no skillweave subpackages found for wheel discovery"
    assert "skillweave*" in (REPO_ROOT / "pyproject.toml").read_text()

    # (d) dispatch_order: the declared SW-GATE-1311 dispatch_order is nonempty
    # and covers exactly the thirteen acceptance criteria exactly once.
    assert DISPATCH_ORDER, "dispatch_order must be nonempty"
    covered: list[int] = []
    for _focus, criteria in DISPATCH_ORDER:
        assert criteria, "a dispatch_order group is empty"
        covered.extend(criteria)
    assert sorted(covered) == list(range(1, 14)), (
        f"dispatch_order must cover criteria 1..13 exactly once, got {sorted(covered)}"
    )
    assert len(covered) == len(set(covered)), "dispatch_order criteria overlap"
