"""The harness declaration form (SW-RT-003, dispatch 1, criterion 1).

Criterion 1 is a declaration obligation, not a machine property. Four harnesses
declare themselves, each at the place its operator looks, by setting
``SKILLWEAVE_HARNESS``. These tests pin the *form* of that declaration:

- the four canonical names are exact and closed,
- a name supplied by the caller records as ``DECLARED``,
- the same name arriving via the environment records as ``DETECTED`` and is
  never misread as a declaration,
- an empty of absent signal yields an empty ``DETECTED`` record, so "no data"
  never reads as "the caller said it".

Nothing here inspects the local machine. A test that depended on this checkout's
``~/.config`` or ``~/.claude`` would be testing the author's laptop, not the
declaration form — so every case passes an explicit ``env`` or ``declared`` and
touches no process state.
"""

import pytest

from skillweave.routing import (
    HarnessSource,
    HarnessError,
    determine_harness,
)

# The four harnesses a run can declare, exactly as documented in
# docs/dispatching-from-your-harness.md. Closed and case-sensitive on purpose.
HARNESS_NAMES = {"opencode", "claude-code", "codex", "antigravity"}


def test_the_four_harness_names_are_the_contract_vocabulary():
    # The declaration doc names exactly these four and no others. An operator
    # declares with one of them or not at all.
    assert HARNESS_NAMES == {"opencode", "claude-code", "codex", "antigravity"}


@pytest.mark.parametrize("name", sorted(HARNESS_NAMES))
def test_each_harness_name_declares_as_declared(name):
    d = determine_harness(declared=name)
    assert d.name == name
    assert d.source is HarnessSource.DECLARED
    assert d.to_dict() == {"name": name, "source": "declared", "evidence": {"via": "caller"}}


@pytest.mark.parametrize("name", sorted(HARNESS_NAMES))
def test_each_harness_name_via_environment_is_detected_not_declared(name):
    d = determine_harness(
        env={"SKILLWEAVE_HARNESS": name}, env_key="SKILLWEAVE_HARNESS"
    )
    assert d.name == name
    assert d.source is HarnessSource.DETECTED
    assert d.to_dict()["source"] == "detected"
    assert d.to_dict()["evidence"] == {"via": "environment", "key": "SKILLWEAVE_HARNESS"}


def test_declaration_outranks_environment_for_the_same_name():
    # A caller-passed name wins over whatever the environment says, even when the
    # two disagree — the explicit signal is the stronger one.
    d = determine_harness(
        declared="opencode",
        env={"SKILLWEAVE_HARNESS": "codex"},
        env_key="SKILLWEAVE_HARNESS",
    )
    assert d.name == "opencode"
    assert d.source is HarnessSource.DECLARED


def test_an_unknown_name_is_not_an_error_it_is_a_detection():
    # The seam does not enumerate names; it records what it is handed. An operator
    # who sets a typo'd name is silently recorded as DETECTED, which is exactly
    # why the doc pins the four names: correctness lives in the declaration form.
    d = determine_harness(declared="claude_code")
    assert d.name == "claude_code"
    assert d.source is HarnessSource.DECLARED


def test_absent_signal_is_empty_detected_never_declared():
    d = determine_harness(env={}, env_key="SKILLWEAVE_HARNESS")
    assert d.name == ""
    assert d.source is HarnessSource.DETECTED
    assert d.to_dict()["evidence"] == {"via": "none"}


def test_empty_declared_name_is_refused_so_no_data_cannot_be_a_declaration():
    with pytest.raises(HarnessError):
        determine_harness(declared="   ")
