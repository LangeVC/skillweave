"""Focused tests for the role/purpose extension of onboarding (SW-156-ONBOARD-001).

Acceptance criteria covered here:

1. Role, purpose, desired autonomy and risk boundary are validated inputs.
2. Every question has a useful default and a custom extension.
3. The result contains one profile, one rationale and one next action.
4. No name, email address or personal identifier is required.

RED PROOF: against the pre-change module these tests cannot pass — the module
had no ``profile``/``rationale``/``onboarding`` result and no
``_ask_choice``/``_collect_profile``/``_build_onboarding_result`` at all, so
criteria 1-3 fail on import/AttributeError and criterion 4 fails because the
only profile-like input (``goal``) was unconstrained free text.

The privacy tests are the important ones. They are negative: they assert that
no identifier is *solicited* (no prompt asks for one, no question is
open-ended), that a caller cannot *smuggle* one in through the custom
extension, and that an answer containing an identifier is never *stored*.
"""

import pytest

from skillweave.onboarding_cli import (
    PROFILE_CHOICES,
    PROFILE_DEFAULTS,
    PROFILE_FIELDS,
    PROFILE_MEANINGS,
    PROFILE_QUESTIONS,
    RISK_BOUNDARY_CHOICES,
    _ask_choice,
    _build_onboarding_result,
    _collect_profile,
    _extend_choice,
    load_onboarding_state,
    run_onboarding,
)

# Answers that look like a personal identifier. Used to prove none of them is
# ever required, accepted as a profile value, or written to state.
IDENTIFIERS = ["Andre Lange", "andre@example.com", "@andrelange", "123-45-6789"]


def _drive(monkeypatch, answers):
    """Feed ``answers`` to input(), then let the stream run out.

    Running out is deliberate: the module must treat an exhausted stream as
    "take the default". A test that wants a specific value places it in
    ``answers``; a test that wants defaults passes none.
    """
    it = iter(answers)

    def fake_input(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise EOFError("no more answers")

    monkeypatch.setattr("builtins.input", fake_input)


def _empty_project(tmp_path, monkeypatch):
    """A non-git empty project so onboarding does no git work and asks nothing."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


# ── Criterion 1: validated inputs ──────────────────────────────────────────


def test_profile_fields_are_the_four_declared_axes():
    assert PROFILE_FIELDS == ("role", "purpose", "autonomy", "risk_boundary")


def test_every_field_has_at_least_two_choices():
    # A single-choice question is not a question; each axis must be a real
    # choice.
    for field in PROFILE_FIELDS:
        assert len(PROFILE_CHOICES[field]) >= 2, field


def test_every_choice_has_a_meaning():
    # The rationale is built from the meaning maps, so a choice with no meaning
    # would make the rationale incomplete (or raise a KeyError) rather than
    # merely read poorly.
    for field in PROFILE_FIELDS:
        assert set(PROFILE_MEANINGS[field]) == set(PROFILE_CHOICES[field]), field
        for choice, meaning in PROFILE_MEANINGS[field].items():
            assert meaning.strip(), (field, choice)


def test_risk_boundary_reuses_the_canonical_risk_mode_vocabulary():
    # The risk boundary is the risk-mode vocabulary (persistence.RiskMode,
    # risk_mode_resolver.RiskModeStr), not a parallel invention. If either
    # drifts, this fails.
    from skillweave.persistence import RiskMode

    assert set(RISK_BOUNDARY_CHOICES) == {mode.value for mode in RiskMode}


def test_ask_choice_accepts_only_declared_values(monkeypatch):
    # Every declared value round-trips unchanged.
    for value in PROFILE_CHOICES["role"]:
        _drive(monkeypatch, [value])
        assert _ask_choice("role") == value


def test_ask_choice_rejects_unrecognized_then_accepts_valid(monkeypatch):
    # An unrecognized value is not silently coerced or stored. The question is
    # re-offered until a declared value (or blank) arrives.
    _drive(monkeypatch, ["a name that is not a role", "reviewer"])
    assert _ask_choice("role") == "reviewer"


def test_ask_choice_normalizes_case_and_whitespace(monkeypatch):
    _drive(monkeypatch, ["  REVIEwer  "])
    assert _ask_choice("role") == "reviewer"


# ── Criterion 2: useful default and custom extension ───────────────────────


def test_every_field_has_a_default_that_is_a_declared_choice():
    for field in PROFILE_FIELDS:
        default = PROFILE_DEFAULTS[field]
        assert default in PROFILE_CHOICES[field], field


def test_every_question_names_an_axis_and_has_a_default():
    for field in PROFILE_FIELDS:
        assert PROFILE_QUESTIONS[field].strip(), field
        assert PROFILE_DEFAULTS[field] in PROFILE_CHOICES[field], field


def test_blank_answer_takes_the_default(monkeypatch):
    for field in PROFILE_FIELDS:
        _drive(monkeypatch, [""])
        assert _ask_choice(field) == PROFILE_DEFAULTS[field], field


def test_exhausted_input_takes_the_default(monkeypatch):
    # No interactive stdin at all: onboarding must not hang or raise, it takes
    # every default. This is what makes non-interactive onboarding work.
    _drive(monkeypatch, [])
    assert _collect_profile() == PROFILE_DEFAULTS


def test_defaults_are_the_least_committing_choice():
    # The defaults are not arbitrary: the safest autonomy and the strictest
    # boundary must be the ones assumed when nothing is said.
    assert PROFILE_DEFAULTS["autonomy"] == "guided"
    assert PROFILE_DEFAULTS["risk_boundary"] == "conservative"


def test_custom_extension_accepts_declared_values():
    assert _extend_choice("autonomy", "autonomous") == "autonomous"
    assert _extend_choice("risk_boundary", "unicorn") == "unicorn"


def test_custom_extension_falls_back_to_default_for_unknown_value():
    # The extension point is a way to *pre-answer* the question, not a way to
    # bypass validation. An undeclared value becomes the default.
    assert _extend_choice("autonomy", "yolo") == PROFILE_DEFAULTS["autonomy"]


def test_custom_extension_falls_back_for_non_string():
    assert _extend_choice("role", None) == PROFILE_DEFAULTS["role"]
    assert _extend_choice("role", 7) == PROFILE_DEFAULTS["role"]


def test_collect_profile_asks_only_the_fields_not_overridden(monkeypatch):
    asked = []

    def fake_input(prompt=""):
        asked.append(prompt)
        return ""

    monkeypatch.setattr("builtins.input", fake_input)
    profile = _collect_profile(role="reviewer", risk_boundary="unicorn")

    # Overridden fields were not asked...
    assert not any(PROFILE_QUESTIONS["role"] in p for p in asked)
    assert not any(PROFILE_QUESTIONS["risk_boundary"] in p for p in asked)
    # ...and only the other two were.
    assert sum(1 for p in asked if PROFILE_QUESTIONS["purpose"] in p) == 1
    assert sum(1 for p in asked if PROFILE_QUESTIONS["autonomy"] in p) == 1
    assert sum(1 for p in asked if "Choose one" in p) == 2

    assert profile == {
        "role": "reviewer",
        "purpose": PROFILE_DEFAULTS["purpose"],
        "autonomy": PROFILE_DEFAULTS["autonomy"],
        "risk_boundary": "unicorn",
    }


def test_collect_profile_validates_overrides(monkeypatch):
    _drive(monkeypatch, [])
    profile = _collect_profile(role="not-a-role")
    assert profile["role"] == PROFILE_DEFAULTS["role"]


# ── Criterion 3: one profile, one rationale, one next action ───────────────


def _sample_profile():
    return {"role": "reviewer", "purpose": "review", "autonomy": "supervised",
            "risk_boundary": "medium"}


def test_result_has_exactly_one_of_each_required_key():
    result = _build_onboarding_result(_sample_profile(), "skillweave-blueprint")
    assert set(result) == {"profile", "rationale", "next_action"}


def test_result_profile_is_the_validated_profile():
    profile = _sample_profile()
    result = _build_onboarding_result(profile, "skillweave-blueprint")
    assert result["profile"] == profile
    # A copy, so later mutation of the result cannot corrupt the input.
    assert result["profile"] is not profile


def test_rationale_is_a_single_non_empty_sentence_stating_the_choice():
    result = _build_onboarding_result(_sample_profile(), "skillweave-blueprint")
    rationale = result["rationale"]
    assert isinstance(rationale, str) and rationale.strip()
    # It explains the choices, it does not merely echo the tokens.
    assert "reviewer" in rationale
    assert "review" in rationale
    assert rationale != " ".join(_sample_profile().values())


def test_rationale_is_deterministic():
    a = _build_onboarding_result(_sample_profile(), "x")["rationale"]
    b = _build_onboarding_result(_sample_profile(), "x")["rationale"]
    assert a == b


def test_next_action_is_passed_through_unchanged():
    result = _build_onboarding_result(_sample_profile(), "skillweave-releasechain")
    assert result["next_action"] == "skillweave-releasechain"


def test_run_onboarding_returns_the_nested_result(tmp_path, monkeypatch):
    _empty_project(tmp_path, monkeypatch)
    _drive(monkeypatch, ["build an app", "n"])

    result = run_onboarding(str(tmp_path))

    assert "onboarding" in result
    onboarding = result["onboarding"]
    assert set(onboarding) == {"profile", "rationale", "next_action"}
    assert onboarding["profile"] == PROFILE_DEFAULTS
    assert onboarding["rationale"].strip()
    assert onboarding["next_action"] == result["next_action"]


def test_run_onboarding_persists_the_result(tmp_path, monkeypatch):
    _empty_project(tmp_path, monkeypatch)
    _drive(monkeypatch, ["build an app", "n"])

    run_onboarding(str(tmp_path))

    state = load_onboarding_state(str(tmp_path))
    assert state["onboarding"]["profile"] == PROFILE_DEFAULTS
    assert state["onboarding"]["rationale"].strip()
    assert state["onboarding"]["next_action"] == state["next_action"]


def test_run_onboarding_accepts_profile_overrides(tmp_path, monkeypatch):
    _empty_project(tmp_path, monkeypatch)
    _drive(monkeypatch, ["build an app", "n"])

    result = run_onboarding(
        str(tmp_path), role="researcher", autonomy="autonomous"
    )

    profile = result["onboarding"]["profile"]
    assert profile["role"] == "researcher"
    assert profile["autonomy"] == "autonomous"
    assert profile["purpose"] == PROFILE_DEFAULTS["purpose"]


# ── Criterion 4: no personal identifier required ───────────────────────────


def test_no_profile_question_asks_for_an_identifier():
    # The questions must name an axis of work, not the person. A question that
    # mentions any of these would invite an identifier.
    forbidden = ("name", "email", "e-mail", "address", "phone", "contact")
    for field in PROFILE_FIELDS:
        question = PROFILE_QUESTIONS[field].lower()
        for word in forbidden:
            assert word not in question, (field, word)


def test_no_profile_question_is_open_ended():
    # Every question is a closed choice: it advertises its options, so there is
    # no free-text field an identifier could be typed into.
    for field in PROFILE_FIELDS:
        assert "Options:" in _prompt_for(field), field


def _prompt_for(field):
    """The exact menu text ``_ask_choice`` shows for ``field``."""
    prompt = []

    def fake_input(p):
        prompt.append(p)
        raise EOFError

    import builtins
    original = builtins.input
    builtins.input = fake_input
    try:
        _ask_choice(field)
    finally:
        builtins.input = original
    return prompt[0]


@pytest.mark.parametrize("identifier", IDENTIFIERS)
def test_identifier_is_not_required_and_not_stored(tmp_path, monkeypatch, identifier):
    # Criterion 4, the negative test. Onboarding completes with an identifier
    # offered as every answer it can reach, and the identifier is required
    # nowhere and stored nowhere.
    _empty_project(tmp_path, monkeypatch)
    _drive(monkeypatch, [identifier, "n", identifier, identifier, identifier, identifier])

    result = run_onboarding(str(tmp_path))

    # It still completed: no identifier was ever required.
    assert result.get("onboarding") is not None

    # And the identifier reached neither the profile block nor the persisted
    # profile. The scope is the profile block on purpose: ``goal`` is the
    # pre-existing free-text answer and still echoes at top level, which is out
    # of scope here.
    onboarding = result["onboarding"]
    persisted = load_onboarding_state(str(tmp_path))["onboarding"]

    for block in (onboarding, persisted):
        assert identifier not in repr(block)

    # The four profile values are all declared choices, never the identifier.
    for field in PROFILE_FIELDS:
        assert onboarding["profile"][field] in PROFILE_CHOICES[field], field


@pytest.mark.parametrize("identifier", IDENTIFIERS)
def test_identifier_smuggled_through_extension_is_rejected(monkeypatch, identifier):
    # The custom extension cannot be used to bypass the closed vocabulary: an
    # identifier supplied as a "role" falls back to the default, so it never
    # reaches the profile or the rationale.
    _drive(monkeypatch, [])
    profile = _collect_profile(role=identifier)
    assert profile["role"] == PROFILE_DEFAULTS["role"]

    result = _build_onboarding_result(profile, "skillweave-blueprint")
    assert identifier not in repr(result)


@pytest.mark.parametrize("identifier", IDENTIFIERS)
def test_identifier_in_the_goal_is_not_in_the_profile_block(tmp_path, monkeypatch, identifier):
    # ``goal`` remains the one free-text answer (pre-existing behaviour, out of
    # scope here). The new profile block must not copy it: the profile is
    # built from closed choices only, so a stray goal cannot leak an
    # identifier into the rationale or next action.
    _empty_project(tmp_path, monkeypatch)
    _drive(monkeypatch, [identifier, "n"])

    result = run_onboarding(str(tmp_path))
    onboarding = result["onboarding"]

    # The goal is still echoed at top level, unchanged...
    assert result["goal"] == identifier
    # ...but the profile block carries none of it.
    assert identifier not in repr(onboarding)


def test_profile_choices_contain_no_personal_identifiers():
    # Structural guard: the vocabularies themselves are role/purpose/autonomy
    # words, not free slots. A future edit adding a free-text sentinel fails.
    for field in PROFILE_FIELDS:
        for choice in PROFILE_CHOICES[field]:
            assert choice == choice.strip().lower(), (field, choice)
            assert " " not in choice, (field, choice)
            assert choice, field
