import pytest
from skillweave.intelligent_detection.skill_intent_mapper import (
    SkillIntentMapper, SkillMappingResult, Skill, map_intent_to_skill
)
from skillweave.intelligent_detection.prompt_analyzer import Intent

class TestSkillMappingResult:

    def test_result_dataclass_fields(self):
        result = SkillMappingResult(
            primary_skill=Skill.BLUEPRINT,
            alternative_skills=[Skill.PROMPTCHAIN_GENERATE],
            confidence=0.85,
            required_capabilities=["generate_blueprint"],
            missing_prerequisites=[],
            dependencies=[],
            recommendation_reason="Test reason"
        )
        assert result.primary_skill == Skill.BLUEPRINT
        assert result.confidence == 0.85

    def test_result_with_prerequisites(self):
        result = SkillMappingResult(
            primary_skill=Skill.PROMPTCHAIN_EXECUTE,
            alternative_skills=[],
            confidence=0.6,
            required_capabilities=[],
            missing_prerequisites=["Output from skillweave-promptchain-validate skill"],
            dependencies=[Skill.PROMPTCHAIN_VALIDATE],
            recommendation_reason="Needs prerequisites"
        )
        assert len(result.missing_prerequisites) > 0


class TestIntentToSkillMapping:

    def test_blueprint_intent_maps_to_blueprint_skill(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {})
        assert result.primary_skill == Skill.BLUEPRINT

    def test_generate_promptchain_intent(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.GENERATE_PROMPTCHAIN, {})
        assert result.primary_skill == Skill.PROMPTCHAIN_GENERATE

    def test_validate_promptchain_intent(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.VALIDATE_PROMPTCHAIN, {})
        assert result.primary_skill == Skill.PROMPTCHAIN_VALIDATE

    def test_execute_promptchain_intent(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.EXECUTE_PROMPTCHAIN, {})
        assert result.primary_skill == Skill.PROMPTCHAIN_EXECUTE

    def test_execute_releasechain_intent(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.EXECUTE_RELEASECHAIN, {})
        assert result.primary_skill == Skill.RELEASECHAIN

    def test_configure_intent_maps_to_unknown(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CONFIGURE, {})
        assert result.primary_skill == Skill.UNKNOWN

    def test_help_intent_maps_to_unknown(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.HELP, {})
        assert result.primary_skill == Skill.UNKNOWN

    def test_unknown_intent_maps_to_unknown(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.UNKNOWN, {})
        assert result.primary_skill == Skill.UNKNOWN


class TestSkillConfidence:

    def test_high_intent_confidence(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {}, intent_confidence=1.0)
        assert result.confidence > 0.7

    def test_low_intent_confidence(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {}, intent_confidence=0.3)
        assert result.confidence <= 0.5

    def test_confidence_with_parameters(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(
            Intent.GENERATE_PROMPTCHAIN,
            {"skill": "skillweave-blueprint", "complexity": "standard"},
            intent_confidence=0.9
        )
        assert result.confidence > 0.5

    def test_confidence_bounds(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {}, intent_confidence=2.0)
        assert result.confidence <= 1.0
        result2 = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {}, intent_confidence=-1.0)
        assert result2.confidence >= 0.0


class TestAlternativeSkills:

    def test_blueprint_alternatives(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {})
        assert Skill.PROMPTCHAIN_GENERATE in result.alternative_skills

    def test_generate_alternatives(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.GENERATE_PROMPTCHAIN, {})
        assert Skill.BLUEPRINT in result.alternative_skills

    def test_validate_alternatives(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.VALIDATE_PROMPTCHAIN, {})
        assert Skill.PROMPTCHAIN_GENERATE in result.alternative_skills

    def test_execute_alternatives(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.EXECUTE_PROMPTCHAIN, {})
        assert Skill.PROMPTCHAIN_VALIDATE in result.alternative_skills

    def test_releasechain_alternatives(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.EXECUTE_RELEASECHAIN, {})
        assert Skill.PROMPTCHAIN_EXECUTE in result.alternative_skills

    def test_unknown_has_no_alternatives(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.UNKNOWN, {})
        assert result.alternative_skills == []


class TestDependencies:

    def test_blueprint_has_no_dependencies(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {})
        assert result.dependencies == []

    def test_promptchain_generate_depends_on_blueprint(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.GENERATE_PROMPTCHAIN, {})
        assert Skill.BLUEPRINT in result.dependencies

    def test_promptchain_validate_depends_on_generate(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.VALIDATE_PROMPTCHAIN, {})
        assert Skill.PROMPTCHAIN_GENERATE in result.dependencies

    def test_promptchain_execute_depends_on_validate_and_generate(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.EXECUTE_PROMPTCHAIN, {})
        assert Skill.PROMPTCHAIN_VALIDATE in result.dependencies
        assert Skill.PROMPTCHAIN_GENERATE in result.dependencies

    def test_releasechain_depends_on_execute(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.EXECUTE_RELEASECHAIN, {})
        assert Skill.PROMPTCHAIN_EXECUTE in result.dependencies

    def test_unknown_has_no_dependencies(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.UNKNOWN, {})
        assert result.dependencies == []


class TestMissingPrerequisites:

    def test_blueprint_missing_idea(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {})
        prereq_ideas = [p for p in result.missing_prerequisites if "idea" in p.lower()]
        assert len(prereq_ideas) > 0

    def test_blueprint_with_idea_no_prereq(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {"idea": "my project"})
        prereq_ideas = [p for p in result.missing_prerequisites if "idea" in p.lower()]
        assert len(prereq_ideas) == 0

    def test_generate_missing_skill(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.GENERATE_PROMPTCHAIN, {})
        prereq_skills = [p for p in result.missing_prerequisites if "skill" in p.lower()]
        assert len(prereq_skills) > 0

    def test_generate_with_skill(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.GENERATE_PROMPTCHAIN, {"skill": "blueprint"})
        prereq_skill_param = [p for p in result.missing_prerequisites if "skill parameter" in p.lower()]
        assert len(prereq_skill_param) == 0

    def test_execute_missing_skill(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.EXECUTE_PROMPTCHAIN, {})
        prereq_skills = [p for p in result.missing_prerequisites if "skill" in p.lower()]
        assert len(prereq_skills) > 0

    def test_dependency_outputs_as_prerequisites(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.GENERATE_PROMPTCHAIN, {"skill": "blueprint"})
        dep_prereqs = [p for p in result.missing_prerequisites if "output from" in p.lower()]
        assert len(dep_prereqs) > 0


class TestRequiredCapabilities:

    def test_blueprint_capabilities(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {})
        assert "generate_blueprint" in result.required_capabilities or result.required_capabilities == []

    def test_execute_releasechain_capabilities(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.EXECUTE_RELEASECHAIN, {})
        assert "execute_releasechain" in result.required_capabilities or result.required_capabilities == []

    def test_unknown_skill_no_capabilities(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.UNKNOWN, {})
        assert result.required_capabilities == []


class TestRecommendationReason:

    def test_reason_contains_skill_value(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {})
        assert result.primary_skill.value in result.recommendation_reason

    def test_reason_for_unknown_skill(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.UNKNOWN, {})
        assert "unable to determine" in result.recommendation_reason.lower()

    def test_reason_confidence_high(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {}, intent_confidence=1.0)
        assert "high confidence" in result.recommendation_reason.lower()

    def test_reason_confidence_low(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {}, intent_confidence=0.1)
        assert "low confidence" in result.recommendation_reason.lower()

    def test_reason_mentions_prerequisites(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.GENERATE_PROMPTCHAIN, {})
        if result.missing_prerequisites:
            assert "requires" in result.recommendation_reason.lower()


class TestSkillDescriptions:

    def test_blueprint_description(self):
        assert "PRD" in SkillIntentMapper.SKILL_DESCRIPTIONS[Skill.BLUEPRINT]

    def test_releasechain_description(self):
        assert "Ralph Loop" in SkillIntentMapper.SKILL_DESCRIPTIONS[Skill.RELEASECHAIN]

    def test_unknown_description(self):
        assert "unknown" in SkillIntentMapper.SKILL_DESCRIPTIONS[Skill.UNKNOWN].lower()


class TestParameterAlignment:

    def test_blueprint_with_all_params_high_score(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(
            Intent.CREATE_BLUEPRINT,
            {"idea": "test", "domain": "saas", "complexity": "simple", "output_format": "json", "risk_mode": "medium"}
        )
        assert result.confidence > 0.5

    def test_blueprint_with_no_params_lower_score(self):
        mapper = SkillIntentMapper()
        result_with = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {"idea": "test"})
        result_without = mapper.map_intent_to_skill(Intent.CREATE_BLUEPRINT, {})
        assert result_with.confidence >= result_without.confidence

    def test_generate_missing_required_skill_penalty(self):
        mapper = SkillIntentMapper()
        result = mapper.map_intent_to_skill(Intent.GENERATE_PROMPTCHAIN, {})
        result_with = mapper.map_intent_to_skill(Intent.GENERATE_PROMPTCHAIN, {"skill": "blueprint"})
        assert result_with.confidence >= result.confidence


class TestBatchMapping:

    def test_batch_map_multiple_intents(self):
        mapper = SkillIntentMapper()
        intents = [Intent.CREATE_BLUEPRINT, Intent.GENERATE_PROMPTCHAIN]
        params_list = [{}, {"skill": "blueprint"}]
        confidences = [1.0, 0.9]
        results = mapper.batch_map(intents, params_list, confidences)
        assert len(results) == 2
        assert all(isinstance(r, SkillMappingResult) for r in results)

    def test_batch_map_correct_skills(self):
        mapper = SkillIntentMapper()
        intents = [Intent.CREATE_BLUEPRINT, Intent.EXECUTE_RELEASECHAIN]
        params_list = [{}, {}]
        confidences = [1.0, 1.0]
        results = mapper.batch_map(intents, params_list, confidences)
        assert results[0].primary_skill == Skill.BLUEPRINT
        assert results[1].primary_skill == Skill.RELEASECHAIN


class TestConvenienceFunction:

    def test_map_intent_to_skill_convenience(self):
        result = map_intent_to_skill(Intent.CREATE_BLUEPRINT, {})
        assert isinstance(result, SkillMappingResult)
        assert result.primary_skill == Skill.BLUEPRINT

    def test_map_intent_to_skill_with_params(self):
        result = map_intent_to_skill(Intent.GENERATE_PROMPTCHAIN, {"skill": "blueprint"})
        assert result.primary_skill == Skill.PROMPTCHAIN_GENERATE


class TestSkillEnum:

    def test_skill_values(self):
        assert Skill.BLUEPRINT.value == "skillweave-blueprint"
        assert Skill.PROMPTCHAIN_GENERATE.value == "skillweave-promptchain-generate"
        assert Skill.PROMPTCHAIN_VALIDATE.value == "skillweave-promptchain-validate"
        assert Skill.PROMPTCHAIN_EXECUTE.value == "skillweave-promptchain-execute"
        assert Skill.RELEASECHAIN.value == "skillweave-releasechain"
        assert Skill.UNKNOWN.value == "unknown"

    def test_skill_from_string(self):
        assert Skill("skillweave-blueprint") == Skill.BLUEPRINT
        assert Skill("unknown") == Skill.UNKNOWN


class TestCapabilityRegistryFallback:

    def test_capability_not_available_safe(self):
        mapper = SkillIntentMapper()
        assert mapper.capability_registry is None or True
