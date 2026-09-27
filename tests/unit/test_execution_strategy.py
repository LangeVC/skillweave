"""Unit tests for composable execution strategies (SW-160-STRAT-001).

Proves all four acceptance criteria:

1. Execution strategies are composable capabilities rather than one exclusive
   enum — capabilities can be combined with bitwise OR, and the ``compose_strategy``
   factory accepts arbitrary subsets without a named recipe.
2. Fresh context, independent reviewer and named reference can be enabled
   together — ``FRESH_CONTEXT | INDEPENDENT_REVIEWER | NAMED_REFERENCE`` is a
   valid, testable combination.
3. Named recipes are projections over capabilities and contain no private
   runtime path — every recipe in ``NAMED_RECIPES`` holds only capability flags
   and a human label, never a file path, store URI or runtime address.
4. Both verticals execute through the same strategy contract — the
   ``ExecutionStrategy`` class is used identically for research-synthesis and
   software-delivery; the ``resolve_recipe`` function returns the same type
   regardless of the recipe name.
"""

from __future__ import annotations

import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import pytest

from skillweave.runtime.strategy import (
    ExecutionCapability,
    ExecutionStrategy,
    from_capabilities,
    compose_strategy,
    resolve_recipe,
    from_execution_model,
    NAMED_RECIPES,
    RECIPE_COLD,
    RECIPE_WARM,
    RECIPE_RESUME,
    RECIPE_MINIMAL,
    RECIPE_FULL,
)


# ---------------------------------------------------------------------------
# Criterion 1: Strategies are composable capabilities, not an exclusive enum
# ---------------------------------------------------------------------------

class TestCapabilitiesAreComposable:
    """Capabilities combine freely via bitwise OR — the opposite of an enum."""

    def test_capabilities_are_bit_flags(self):
        """Bit flags compose: FRESH_CONTEXT | INDEPENDENT_REVIEWER produces
        a value that carries both."""
        combined = ExecutionCapability.FRESH_CONTEXT | ExecutionCapability.INDEPENDENT_REVIEWER
        assert bool(combined & ExecutionCapability.FRESH_CONTEXT)
        assert bool(combined & ExecutionCapability.INDEPENDENT_REVIEWER)

    def test_capabilities_are_not_mutually_exclusive(self):
        """Any two capabilities can coexist — no enum-like mutual exclusion."""
        for a in ExecutionCapability:
            for b in ExecutionCapability:
                if a and b:  # skip NONE
                    combined = a | b
                    assert bool(combined & a)
                    assert bool(combined & b)

    def test_compose_strategy_accepts_arbitrary_subsets(self):
        """``compose_strategy`` accepts any subset of capabilities, proving
        strategies are composable rather than a single exclusive value."""
        s1 = compose_strategy(ExecutionCapability.FRESH_CONTEXT)
        assert s1.has_fresh_context
        assert not s1.has_independent_reviewer

        s2 = compose_strategy(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
            ExecutionCapability.PERSISTENT_STORE,
        )
        assert s2.has_fresh_context
        assert s2.has_independent_reviewer
        assert s2.has_persistent_store
        assert not s2.has_resume

    def test_empty_strategy_is_valid(self):
        """An empty (NONE) strategy is valid and carries no capability."""
        s = ExecutionStrategy()
        assert s.capabilities == ExecutionCapability.NONE
        assert not s.has_fresh_context
        assert not s.has_independent_reviewer
        assert not s.has_named_reference

    def test_with_capability_returns_new_instance(self):
        """``with_capability`` is immutable — returns a new strategy."""
        s = ExecutionStrategy()
        s2 = s.with_capability(ExecutionCapability.FRESH_CONTEXT)
        assert s is not s2
        assert not s.has_fresh_context
        assert s2.has_fresh_context

    def test_without_capability_removes_only_the_given_capability(self):
        """``without_capability`` removes exactly the requested capability."""
        s = from_capabilities(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
            recipe_name="test",
        )
        s2 = s.without_capability(ExecutionCapability.FRESH_CONTEXT)
        assert not s2.has_fresh_context
        assert s2.has_independent_reviewer
        assert s2.recipe_name == "test"

    def test_has_all_checks_multiple_capabilities(self):
        """``has_all`` returns True only when every listed capability is present."""
        s = from_capabilities(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
            ExecutionCapability.NAMED_REFERENCE,
        )
        assert s.has_all(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
        )
        assert not s.has_all(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.RESUME,
        )

    def test_to_dict_serializes_capability_names(self):
        """``to_dict`` serialises capability names (not opaque ints)."""
        s = from_capabilities(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
        )
        d = s.to_dict()
        assert "FRESH_CONTEXT" in d["capabilities"]
        assert "INDEPENDENT_REVIEWER" in d["capabilities"]
        assert d["recipe_name"] is None

    def test_to_dict_with_recipe(self):
        s = from_capabilities(
            ExecutionCapability.FRESH_CONTEXT,
            recipe_name="my-recipe",
        )
        d = s.to_dict()
        assert d["recipe_name"] == "my-recipe"

    def test_equality(self):
        """Two strategies with the same capabilities and recipe are equal."""
        a = from_capabilities(ExecutionCapability.FRESH_CONTEXT, recipe_name="x")
        b = from_capabilities(ExecutionCapability.FRESH_CONTEXT, recipe_name="x")
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality(self):
        """Different capabilities or recipes make strategies unequal."""
        a = from_capabilities(ExecutionCapability.FRESH_CONTEXT, recipe_name="x")
        b = from_capabilities(ExecutionCapability.INDEPENDENT_REVIEWER, recipe_name="x")
        assert a != b


# ---------------------------------------------------------------------------
# Criterion 2: Fresh context, independent reviewer and named reference
#              can be enabled together
# ---------------------------------------------------------------------------

class TestThreeKeyCapabilitiesTogether:
    """The three key capabilities compose into a single strategy."""

    def test_fresh_context_and_reviewer_and_reference_together(self):
        """FRESH_CONTEXT, INDEPENDENT_REVIEWER and NAMED_REFERENCE can all
        be set on the same strategy simultaneously."""
        caps = (
            ExecutionCapability.FRESH_CONTEXT
            | ExecutionCapability.INDEPENDENT_REVIEWER
            | ExecutionCapability.NAMED_REFERENCE
        )
        s = ExecutionStrategy(capabilities=caps, recipe_name="triple-test")
        assert s.has_all(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
            ExecutionCapability.NAMED_REFERENCE,
        )
        assert s.has_fresh_context
        assert s.has_independent_reviewer
        assert s.has_named_reference

    def test_recipe_cold_has_all_three(self):
        """The ``cold`` recipe carries all three key capabilities."""
        s = resolve_recipe("cold")
        assert s.has_fresh_context
        assert s.has_independent_reviewer
        assert s.has_named_reference

    def test_reviewer_and_reference_without_fresh(self):
        """INDEPENDENT_REVIEWER and NAMED_REFERENCE without FRESH_CONTEXT
        is valid — matching the ``warm`` recipe."""
        caps = (
            ExecutionCapability.INDEPENDENT_REVIEWER
            | ExecutionCapability.NAMED_REFERENCE
        )
        s = ExecutionStrategy(capabilities=caps, recipe_name="warm-like")
        assert not s.has_fresh_context
        assert s.has_independent_reviewer
        assert s.has_named_reference


# ---------------------------------------------------------------------------
# Criterion 3: Named recipes are projections over capabilities and contain
#              no private runtime path
# ---------------------------------------------------------------------------

class TestNamedRecipesArePureProjections:
    """Every named recipe holds only capability flags + a human label."""

    def test_all_recipes_have_no_private_runtime_path(self):
        """Every recipe in NAMED_RECIPES carries no file path, store URI,
        or runtime-specific address — only capabilities and a recipe_name."""
        for name, recipe in NAMED_RECIPES.items():
            assert isinstance(recipe, ExecutionStrategy), (
                f"recipe '{name}' is not an ExecutionStrategy"
            )
            d = recipe.to_dict()
            # Only capability names and recipe_name; no runtime-specific keys
            assert set(d.keys()) == {"capabilities", "recipe_name"}, (
                f"recipe '{name}' carries extra keys: {set(d.keys()) - {'capabilities', 'recipe_name'}}"
            )
            assert d["recipe_name"] == name, (
                f"recipe '{name}' has mismatched recipe_name {d['recipe_name']!r}"
            )
            for cap_name in d["capabilities"]:
                assert hasattr(ExecutionCapability, cap_name), (
                    f"recipe '{name}' references unknown capability '{cap_name}'"
                )

    def test_recipe_cold_projection(self):
        s = resolve_recipe("cold")
        assert s.recipe_name == "cold"
        assert s.has_fresh_context
        assert s.has_independent_reviewer
        assert s.has_named_reference
        assert not s.has_warm_start
        assert not s.has_resume
        assert not s.has_persistent_store
        assert not s.has_observer

    def test_recipe_warm_projection(self):
        s = resolve_recipe("warm")
        assert s.recipe_name == "warm"
        assert not s.has_fresh_context
        assert s.has_independent_reviewer
        assert s.has_named_reference
        assert s.has_warm_start
        assert not s.has_resume

    def test_recipe_resume_projection(self):
        s = resolve_recipe("resume")
        assert s.recipe_name == "resume"
        assert not s.has_fresh_context
        assert s.has_independent_reviewer
        assert s.has_named_reference
        assert s.has_resume

    def test_recipe_minimal_projection(self):
        s = resolve_recipe("minimal")
        assert s.recipe_name == "minimal"
        assert s.has_fresh_context
        assert not s.has_independent_reviewer
        assert not s.has_named_reference

    def test_recipe_full_projection(self):
        s = resolve_recipe("full")
        assert s.recipe_name == "full"
        assert s.has_fresh_context
        assert s.has_independent_reviewer
        assert s.has_named_reference
        assert s.has_warm_start
        assert s.has_resume
        assert s.has_persistent_store
        assert s.has_observer

    def test_unknown_recipe_raises(self):
        with pytest.raises(ValueError, match="unknown recipe"):
            resolve_recipe("nonexistent")


# ---------------------------------------------------------------------------
# Criterion 4: Both verticals execute through the same strategy contract
# ---------------------------------------------------------------------------

class TestSameStrategyContract:
    """Both verticals (research-synthesis, software-delivery) use the identical
    ``ExecutionStrategy`` type — there is no research-specific or delivery-specific
    strategy subclass."""

    def test_research_uses_same_type_as_software_delivery(self):
        """Research and software-delivery use the same ExecutionStrategy type."""
        research_caps = from_capabilities(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
            ExecutionCapability.NAMED_REFERENCE,
            ExecutionCapability.PERSISTENT_STORE,
        )
        delivery_caps = from_capabilities(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
            ExecutionCapability.NAMED_REFERENCE,
            ExecutionCapability.PERSISTENT_STORE,
        )
        assert type(research_caps) is type(delivery_caps)
        assert isinstance(research_caps, ExecutionStrategy)
        assert isinstance(delivery_caps, ExecutionStrategy)

    def test_resolve_recipe_returns_same_type_for_any_recipe(self):
        """``resolve_recipe`` returns ``ExecutionStrategy`` regardless of
        the recipe name — no vertical-specific subclasses."""
        for name in NAMED_RECIPES:
            s = resolve_recipe(name)
            assert type(s) is ExecutionStrategy

    def test_research_and_delivery_use_identical_compose_function(self):
        """The ``compose_strategy`` factory is the single entry point for
        both verticals; there is no separate research/delivery factory."""
        research_strat = compose_strategy(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
            recipe_name="research-test",
        )
        delivery_strat = compose_strategy(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
            recipe_name="delivery-test",
        )
        assert isinstance(research_strat, ExecutionStrategy)
        assert isinstance(delivery_strat, ExecutionStrategy)
        # Same capabilities (different names) produce structurally equal
        # strategy objects minus the recipe name.
        assert (
            research_strat.has_fresh_context
            == delivery_strat.has_fresh_context
        )
        assert (
            research_strat.has_independent_reviewer
            == delivery_strat.has_independent_reviewer
        )

    def test_from_execution_model_returns_execution_strategy(self):
        """Legacy execution-model string resolution returns the same
        ExecutionStrategy type."""
        for model in ("cold", "warm", "resume"):
            s = from_execution_model(model)
            assert type(s) is ExecutionStrategy
            assert s.recipe_name == model

    def test_from_execution_model_unknown_raises(self):
        with pytest.raises(ValueError, match="unknown execution_model"):
            from_execution_model("hot")

    def test_from_execution_model_cold(self):
        s = from_execution_model("cold")
        assert s.has_fresh_context
        assert s.has_independent_reviewer
        assert s.has_named_reference

    def test_from_execution_model_warm(self):
        s = from_execution_model("warm")
        assert not s.has_fresh_context
        assert s.has_independent_reviewer
        assert s.has_named_reference
        assert s.has_warm_start

    def test_from_execution_model_resume(self):
        s = from_execution_model("resume")
        assert not s.has_fresh_context
        assert s.has_independent_reviewer
        assert s.has_named_reference
        assert s.has_resume


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_strategy_is_immutable(self):
        """Strategy properties are read-only — no public setters."""
        s = ExecutionStrategy()
        with pytest.raises(AttributeError):
            s.capabilities = ExecutionCapability.FRESH_CONTEXT  # type: ignore

    def test_all_capabilities_can_be_combined(self):
        """All capabilities compose into a single strategy."""
        all_caps = ExecutionCapability.NONE
        for cap in ExecutionCapability:
            if cap:
                all_caps |= cap
        s = ExecutionStrategy(capabilities=all_caps, recipe_name="all")
        assert s.has_all(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
            ExecutionCapability.NAMED_REFERENCE,
            ExecutionCapability.WARM_START,
            ExecutionCapability.RESUME,
            ExecutionCapability.PERSISTENT_STORE,
            ExecutionCapability.OBSERVER,
        )

    def test_named_recipes_registry_is_complete(self):
        """NAMED_RECIPES contains all expected entries."""
        expected = {"cold", "warm", "resume", "minimal", "full"}
        assert set(NAMED_RECIPES) == expected

    def test_every_recipe_round_trips_through_to_dict(self):
        """Every named recipe serialises and the output contains only
        capabilities and recipe_name."""
        for name, recipe in NAMED_RECIPES.items():
            d = recipe.to_dict()
            assert d["recipe_name"] == name
            assert isinstance(d["capabilities"], list)
            for cap_name in d["capabilities"]:
                assert isinstance(cap_name, str)

    def test_repr_includes_active_capabilities(self):
        s = from_capabilities(
            ExecutionCapability.FRESH_CONTEXT,
            ExecutionCapability.INDEPENDENT_REVIEWER,
        )
        r = repr(s)
        assert "FRESH_CONTEXT" in r
        assert "INDEPENDENT_REVIEWER" in r

    def test_repr_includes_recipe_name_when_set(self):
        s = from_capabilities(
            ExecutionCapability.FRESH_CONTEXT,
            recipe_name="test-recipe",
        )
        r = repr(s)
        assert "test-recipe" in r

    def test_compose_strategy_without_args_is_empty(self):
        s = compose_strategy()
        assert s.capabilities == ExecutionCapability.NONE
        assert s.recipe_name is None


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:
            if type(e).__name__ == "Skipped":
                print(f"SKIP {t.__name__}")
                continue
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
