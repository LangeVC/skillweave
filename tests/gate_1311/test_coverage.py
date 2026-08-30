"""Machine-readable exact-once coverage of all thirteen criteria and six groups.

This module lets a reviewer verify — without reading every test body — that:

* all thirteen ``SW-GATE-1311`` acceptance criteria are covered exactly once;
* every one of the six declared ``dispatch_order`` groups is nonempty;
* the declared criterion->test mapping in ``tests.gate_1311.__init__`` names a
  real, collectable test function in the mapped module.

It reads the single source of truth for the mapping (``tests.gate_1311``) and
asserts the mapping is a bijection over criteria 1..13 and the six groups.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from tests.gate_1311 import (
    DISPATCH_ORDER,
    CRITERION_TO_TEST,
    CRITERION_MODULE,
    CONTROLLER_ATTESTED_CRITERIA,
)


def test_thirteen_criteria_covered_exactly_once():
    """Every criterion 1..13 maps to exactly one test name; no extras."""
    assert set(CRITERION_TO_TEST) == set(range(1, 14))
    # Test names are unique (each criterion has its own named test).
    names = list(CRITERION_TO_TEST.values())
    assert len(set(names)) == len(names), "criterion->test mapping is not injective"


def test_six_dispatch_order_groups_nonempty():
    """All six dispatch_order groups are nonempty and cover 1..13 exactly once."""
    assert len(DISPATCH_ORDER) == 6
    covered = [c for _focus, criteria in DISPATCH_ORDER for c in criteria]
    for focus, criteria in DISPATCH_ORDER:
        assert focus and criteria, "a dispatch_order group is empty or unnamed"
    assert sorted(covered) == list(range(1, 14))


def test_controller_attested_criteria_are_the_review_process_ones():
    """Criteria 11, 12, 13 are the controller-/review-attested facts."""
    assert CONTROLLER_ATTESTED_CRITERIA == frozenset({11, 12, 13})


@pytest.mark.parametrize("criterion", range(1, 14))
def test_every_criterion_test_exists(criterion: int):
    """Each declared criterion->test mapping names a real test function in the
    module that dispatch_order assigns it to."""
    module = importlib.import_module(f"tests.gate_1311.{CRITERION_MODULE[criterion]}")
    test_name = CRITERION_TO_TEST[criterion]
    assert hasattr(module, test_name), (
        f"module {CRITERION_MODULE[criterion]!r} has no {test_name!r}"
    )
    assert callable(getattr(module, test_name))
    assert test_name.startswith("test_")


def test_every_group_module_is_collectable():
    """Each group module is importable and exposes its criterion tests."""
    for criterion in range(1, 14):
        module = importlib.import_module(f"tests.gate_1311.{CRITERION_MODULE[criterion]}")
        test_name = CRITERION_TO_TEST[criterion]
        assert callable(getattr(module, test_name))


def _default_collected_node_ids() -> set[str]:
    """The node ids pytest collects from this directory under default config.

    Runs ``python3 -m pytest tests/gate_1311 --collect-only -q`` under the
    repository root with no ``python_files`` override. This reproduces exactly
    the default collection that ``python3 -m pytest tests/gate_1311 -q``
    performs, so a criterion test that is present but silently uncollected
    becomes a hard failure instead of hiding in the suite.
    """
    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/gate_1311", "--collect-only", "-q"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=True,
    )
    collected: set[str] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("tests/gate_1311/") and "::" in line:
            collected.add(line)
    return collected


def test_every_criterion_test_is_reached_by_default_collection():
    """No criterion test may be present yet unreachable under default config.

    Every declared criterion->test mapping must resolve to a node id that
    ``python3 -m pytest tests/gate_1311 -q`` (default ``python_files``, no
    override) actually collects. This closes the defect where a criterion test
    lives in a file that default collection never touches.
    """
    node_ids = _default_collected_node_ids()
    for criterion in range(1, 14):
        module = CRITERION_MODULE[criterion]
        test_name = CRITERION_TO_TEST[criterion]
        node = f"tests/gate_1311/{module}.py::{test_name}"
        assert node in node_ids, (
            f"criterion {criterion} test {test_name!r} ({node}) is not collected "
            f"under the default pytest configuration"
        )
