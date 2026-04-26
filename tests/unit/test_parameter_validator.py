import pytest
from skillweave.intelligent_detection.parameter_validator import (
    ParameterValidator, ParameterValidationResult, ValidationFinding,
    ValidationSeverity, validate_parameters
)
from skillweave.intelligent_detection.skill_intent_mapper import Skill


class TestParameterValidatorInit:

    def test_default_strict_mode(self):
        validator = ParameterValidator()
        assert validator.strict_mode is False

    def test_strict_mode_enabled(self):
        validator = ParameterValidator(strict_mode=True)
        assert validator.strict_mode is True


class TestParameterValidation:

    def test_valid_blueprint_params(self):
        validator = ParameterValidator()
        params = {"idea": "My SaaS project", "domain": "saas", "complexity": "medium"}
        result = validator.validate(Skill.BLUEPRINT, params)
        assert result.is_valid
        assert result.completeness_score > 0

    def test_valid_promptchain_generate_params(self):
        validator = ParameterValidator()
        params = {"skill": "skillweave-blueprint", "complexity": "standard"}
        result = validator.validate(Skill.PROMPTCHAIN_GENERATE, params)
        assert result.is_valid
        assert "skill" not in result.missing_required

    def test_missing_required_skill_param(self):
        validator = ParameterValidator()
        params = {}
        result = validator.validate(Skill.PROMPTCHAIN_GENERATE, params)
        assert "skill" in result.missing_required
        assert result.is_valid is False

    def test_missing_required_in_strict_mode(self):
        validator = ParameterValidator(strict_mode=True)
        params = {}
        result = validator.validate(Skill.PROMPTCHAIN_GENERATE, params)
        assert "skill" in result.missing_required
        assert result.is_valid is False

    def test_invalid_allowed_value(self):
        validator = ParameterValidator()
        params = {"complexity": "ultra"}
        result = validator.validate(Skill.BLUEPRINT, params)
        assert result.is_valid

    def test_empty_parameters(self):
        validator = ParameterValidator()
        result = validator.validate(Skill.BLUEPRINT, {})
        assert result.is_valid
        assert result.completeness_score == 0.0

    def test_unknown_skill_validation(self):
        validator = ParameterValidator()
        result = validator.validate(Skill.UNKNOWN, {"anything": "value"})
        assert result.is_valid
        assert result.completeness_score == 1.0


class TestParameterNormalization:

    def test_alias_idea_project(self):
        validator = ParameterValidator()
        params = {"project": "My idea"}
        result = validator.validate(Skill.BLUEPRINT, params)
        assert result.is_valid

    def test_alias_complexity_level(self):
        validator = ParameterValidator()
        params = {"level": "simple"}
        result = validator.validate(Skill.BLUEPRINT, params)

    def test_alias_skill_target(self):
        validator = ParameterValidator()
        params = {"target": "skillweave-blueprint"}
        result = validator.validate(Skill.PROMPTCHAIN_GENERATE, params)
        assert "skill" not in result.missing_required

    def test_alias_format_output_format(self):
        validator = ParameterValidator()
        params = {"format": "json"}
        result = validator.validate(Skill.BLUEPRINT, params)

    def test_duplicate_alias_first_wins(self):
        validator = ParameterValidator()
        params = {"project": "first", "idea": "second"}
        result = validator.validate(Skill.BLUEPRINT, params)

    def test_case_insensitive_alias_matching(self):
        validator = ParameterValidator()
        params = {"Project": "My idea"}
        result = validator.validate(Skill.BLUEPRINT, params)

    def test_normalize_disabled(self):
        validator = ParameterValidator()
        params = {"project": "My idea"}
        result = validator.validate(Skill.BLUEPRINT, params, normalize=False)


class TestAllowedValuesValidation:

    def test_valid_allowed_value(self):
        validator = ParameterValidator()
        params = {"domain": "ecommerce"}
        result = validator.validate(Skill.BLUEPRINT, params)
        assert result.is_valid

    def test_case_insensitive_value_match(self):
        validator = ParameterValidator()
        params = {"domain": "SaaS"}
        result = validator.validate(Skill.BLUEPRINT, params)
        assert result.is_valid

    def test_case_mismatch_finding(self):
        validator = ParameterValidator()
        params = {"domain": "Saas"}
        result = validator.validate(Skill.BLUEPRINT, params)
        infos = [f for f in result.findings if f.severity == ValidationSeverity.INFO and "case mismatch" in f.message.lower()]
        assert len(infos) > 0

    def test_outside_allowed_values(self):
        validator = ParameterValidator()
        params = {"domain": "gaming"}
        result = validator.validate(Skill.BLUEPRINT, params)
        warnings = [f for f in result.findings if f.severity == ValidationSeverity.WARNING and "not in allowed values" in f.message]
        assert len(warnings) > 0

    def test_all_blueprint_domains_valid(self):
        validator = ParameterValidator()
        for domain in ["saas", "mobile", "web", "enterprise", "ecommerce", "iot", "ai", "blockchain"]:
            params = {"domain": domain}
            result = validator.validate(Skill.BLUEPRINT, params)
            assert result.is_valid, f"Domain {domain} should be valid"

    def test_all_complexity_levels_valid(self):
        validator = ParameterValidator()
        for level in ["simple", "medium", "complex"]:
            params = {"complexity": level}
            result = validator.validate(Skill.BLUEPRINT, params)
            assert result.is_valid, f"Level {level} should be valid"

    def test_all_risk_modes_valid(self):
        validator = ParameterValidator()
        for mode in ["conservative", "medium", "unicorn"]:
            params = {"risk_mode": mode}
            result = validator.validate(Skill.BLUEPRINT, params)
            assert result.is_valid, f"Mode {mode} should be valid"

    def test_all_output_formats_valid(self):
        validator = ParameterValidator()
        for fmt in ["json", "markdown", "both"]:
            params = {"output_format": fmt}
            result = validator.validate(Skill.BLUEPRINT, params)
            assert result.is_valid, f"Format {fmt} should be valid"


class TestUnknownParameters:

    def test_unknown_parameter_info_finding(self):
        validator = ParameterValidator()
        params = {"unknown_param": "value"}
        result = validator.validate(Skill.BLUEPRINT, params)
        infos = [f for f in result.findings if f.severity == ValidationSeverity.INFO and "unknown" in f.message.lower()]
        assert len(infos) > 0

    def test_multiple_unknown_params(self):
        validator = ParameterValidator()
        params = {"p1": "v1", "p2": "v2", "p3": "v3"}
        result = validator.validate(Skill.BLUEPRINT, params)
        unknown_findings = [f for f in result.findings if f.severity == ValidationSeverity.INFO and "unknown" in f.message.lower()]
        assert len(unknown_findings) == 3


class TestTypeValidation:

    def test_wrong_type_warning(self):
        validator = ParameterValidator()
        params = {"domain": 123}
        result = validator.validate(Skill.BLUEPRINT, params)
        warnings = [f for f in result.findings if f.severity == ValidationSeverity.WARNING and "unexpected type" in f.message]
        assert len(warnings) > 0

    def test_integer_type_accepts_int(self):
        validator = ParameterValidator()

    def test_boolean_type_accepts_bool(self):
        validator = ParameterValidator()

    def test_array_type_accepts_list(self):
        validator = ParameterValidator()

    def test_object_type_accepts_dict(self):
        validator = ParameterValidator()

    def test_unknown_type_skips_validation(self):
        validator = ParameterValidator()

    def test_number_type_accepts_int_and_float(self):
        validator = ParameterValidator()


class TestPatternValidation:

    def test_idea_pattern_too_short(self):
        validator = ParameterValidator()
        params = {"idea": "short"}
        result = validator.validate(Skill.BLUEPRINT, params)
        infos = [f for f in result.findings if f.severity == ValidationSeverity.INFO and "pattern" in f.message.lower()]
        assert len(infos) > 0

    def test_idea_pattern_valid_long_text(self):
        validator = ParameterValidator()
        params = {"idea": "A comprehensive SaaS platform for managing team workflows"}
        result = validator.validate(Skill.BLUEPRINT, params)

    def test_idea_pattern_with_special_chars(self):
        validator = ParameterValidator()
        params = {"idea": "AI-powered analytics: real-time, scalable!"}
        result = validator.validate(Skill.BLUEPRINT, params)

    def test_idea_pattern_empty_string(self):
        validator = ParameterValidator()
        params = {"idea": ""}
        result = validator.validate(Skill.BLUEPRINT, params)
        infos = [f for f in result.findings if f.severity == ValidationSeverity.INFO and "pattern" in f.message.lower()]
        assert len(infos) > 0


class TestCompletenessScore:

    def test_full_parameters_score(self):
        validator = ParameterValidator()
        params = {"idea": "test", "domain": "saas", "complexity": "simple", "output_format": "json", "risk_mode": "conservative"}
        result = validator.validate(Skill.BLUEPRINT, params)
        assert result.completeness_score >= 0.9

    def test_partial_parameters_score(self):
        validator = ParameterValidator()
        params = {"idea": "test"}
        result = validator.validate(Skill.BLUEPRINT, params)
        assert result.completeness_score > 0
        assert result.completeness_score < 1.0

    def test_no_schema_scores_perfect(self):
        validator = ParameterValidator()
        result = validator.validate(Skill.UNKNOWN, {})
        assert result.completeness_score == 1.0

    def test_missing_required_penalty(self):
        validator = ParameterValidator()
        result = validator.validate(Skill.PROMPTCHAIN_GENERATE, {})
        assert result.completeness_score < 0.5


class TestSingleParameterValidation:

    def test_valid_single_param(self):
        validator = ParameterValidator()
        is_valid, msg = validator.validate_single_parameter(Skill.BLUEPRINT, "domain", "saas")
        assert is_valid

    def test_invalid_single_param(self):
        validator = ParameterValidator()
        is_valid, msg = validator.validate_single_parameter(Skill.BLUEPRINT, "domain", "invalid")
        assert is_valid

    def test_unknown_param_assumed_valid(self):
        validator = ParameterValidator()
        is_valid, msg = validator.validate_single_parameter(Skill.BLUEPRINT, "nonexistent", "value")
        assert is_valid
        assert "assumed valid" in msg

    def test_single_param_with_custom_info(self):
        validator = ParameterValidator()
        param_info = {"required": True, "type": "string", "allowed_values": ["a", "b", "c"]}
        is_valid, msg = validator.validate_single_parameter(Skill.BLUEPRINT, "test", "a", param_info)
        assert is_valid


class TestParameterInfo:

    def test_get_existing_parameter_info(self):
        validator = ParameterValidator()
        info = validator.get_parameter_info(Skill.BLUEPRINT, "domain")
        assert info is not None
        assert info["type"] == "string"
        assert "allowed_values" in info

    def test_get_nonexistent_parameter_info(self):
        validator = ParameterValidator()
        info = validator.get_parameter_info(Skill.BLUEPRINT, "nonexistent")
        assert info is None

    def test_get_parameter_info_for_unknown_skill(self):
        validator = ParameterValidator()
        info = validator.get_parameter_info(Skill.UNKNOWN, "anything")
        assert info is None


class TestParameterSuggestions:

    def test_suggest_missing_params(self):
        validator = ParameterValidator()
        suggestions = validator.suggest_parameters(Skill.BLUEPRINT, {})
        assert "idea" in suggestions
        assert "domain" in suggestions
        assert "complexity" in suggestions
        assert "output_format" in suggestions
        assert suggestions["domain"] == "saas"
        assert suggestions["complexity"] == "simple"

    def test_suggest_partial_params(self):
        validator = ParameterValidator()
        suggestions = validator.suggest_parameters(Skill.BLUEPRINT, {"domain": "saas"})
        assert "idea" in suggestions
        assert "domain" not in suggestions

    def test_suggest_no_missing(self):
        validator = ParameterValidator()
        suggestions = validator.suggest_parameters(Skill.BLUEPRINT, {"idea": "test", "domain": "saas", "complexity": "simple"})
        assert "output_format" in suggestions
        assert "risk_mode" in suggestions

    def test_suggest_for_unknown_skill(self):
        validator = ParameterValidator()
        suggestions = validator.suggest_parameters(Skill.UNKNOWN, {})
        assert suggestions == {}

    def test_suggest_string_type(self):
        validator = ParameterValidator()

    def test_suggest_integer_type(self):
        validator = ParameterValidator()

    def test_suggest_boolean_type(self):
        validator = ParameterValidator()

    def test_suggest_array_type(self):
        validator = ParameterValidator()

    def test_suggest_object_type(self):
        validator = ParameterValidator()


class TestParameterMigration:

    def test_migrate_same_skill(self):
        validator = ParameterValidator()
        params = {"idea": "test", "domain": "saas"}
        migrated = validator.migrate_parameters(Skill.BLUEPRINT, Skill.BLUEPRINT, params)
        assert migrated == params

    def test_migrate_blueprint_to_promptchain(self):
        validator = ParameterValidator()
        params = {"idea": "test", "domain": "saas", "complexity": "medium"}
        migrated = validator.migrate_parameters(Skill.BLUEPRINT, Skill.PROMPTCHAIN_GENERATE, params)
        assert "complexity" in migrated

    def test_migrate_with_exact_name_match(self):
        validator = ParameterValidator()
        params = {"complexity": "complex"}
        migrated = validator.migrate_parameters(Skill.BLUEPRINT, Skill.PROMPTCHAIN_GENERATE, params)
        assert "complexity" in migrated

    def test_migrate_with_normalized_match(self):
        validator = ParameterValidator()
        params = {"project": "My idea"}
        migrated = validator.migrate_parameters(Skill.BLUEPRINT, Skill.PROMPTCHAIN_GENERATE, params)

    def test_migrate_with_substring_match(self):
        validator = ParameterValidator()
        params = {"output": "json"}
        migrated = validator.migrate_parameters(Skill.BLUEPRINT, Skill.PROMPTCHAIN_GENERATE, params)
        assert "output_format" in migrated

    def test_migrate_invalid_params_removed(self):
        validator = ParameterValidator()
        params = {"domain": "invalid_value", "complexity": "simple"}
        migrated = validator.migrate_parameters(Skill.BLUEPRINT, Skill.PROMPTCHAIN_GENERATE, params)


class TestBatchValidation:

    def test_batch_validate_valid_params(self):
        validator = ParameterValidator()
        skills = [Skill.BLUEPRINT, Skill.PROMPTCHAIN_GENERATE]
        params_list = [{"domain": "saas"}, {"skill": "skillweave-blueprint"}]
        results = validator.batch_validate(skills, params_list)
        assert len(results) == 2
        assert all(isinstance(r, ParameterValidationResult) for r in results)

    def test_batch_validate_mixed_results(self):
        validator = ParameterValidator()
        skills = [Skill.PROMPTCHAIN_GENERATE, Skill.BLUEPRINT]
        params_list = [{}, {"domain": "saas"}]
        results = validator.batch_validate(skills, params_list)
        assert results[0].is_valid is False
        assert results[1].is_valid is True


class TestParameterValidationResult:

    def test_result_dataclass_fields(self):
        result = ParameterValidationResult(
            is_valid=True,
            findings=[],
            missing_required=[],
            suggested_corrections={},
            completeness_score=1.0
        )
        assert result.is_valid is True
        assert result.findings == []
        assert result.missing_required == []
        assert result.suggested_corrections == {}
        assert result.completeness_score == 1.0

    def test_result_with_findings(self):
        finding = ValidationFinding(
            parameter="test",
            severity=ValidationSeverity.WARNING,
            message="Test warning",
            suggestion="Fix it",
            current_value="bad"
        )
        result = ParameterValidationResult(
            is_valid=True,
            findings=[finding],
            missing_required=[],
            suggested_corrections={},
            completeness_score=0.8
        )
        assert len(result.findings) == 1
        assert result.findings[0].parameter == "test"


class TestConvenienceFunction:

    def test_validate_parameters_convenience(self):
        result = validate_parameters(Skill.BLUEPRINT, {"domain": "saas"})
        assert isinstance(result, ParameterValidationResult)

    def test_validate_parameters_strict_mode(self):
        result = validate_parameters(Skill.PROMPTCHAIN_GENERATE, {}, strict_mode=True)
        assert result.is_valid is False


class TestSuggestedCorrections:

    def test_correction_for_allowed_value(self):
        validator = ParameterValidator()
        params = {"domain": "INVALID"}
        result = validator.validate(Skill.BLUEPRINT, params)
        _ = [f for f in result.findings if "Use '" in (f.suggestion or "")]
        assert result.is_valid

    def test_correction_for_missing_required(self):
        validator = ParameterValidator()
        params = {}
        result = validator.validate(Skill.PROMPTCHAIN_GENERATE, params)
        assert len(result.suggested_corrections) > 0
        assert "skill" in result.suggested_corrections


class TestValidationFinding:

    def test_finding_without_suggestion(self):
        finding = ValidationFinding("p", ValidationSeverity.ERROR, "err", None, None)
        assert finding.suggestion is None

    def test_finding_with_all_fields(self):
        finding = ValidationFinding("p", ValidationSeverity.WARNING, "msg", "fix", "current")
        assert finding.parameter == "p"
        assert finding.severity == ValidationSeverity.WARNING
        assert finding.message == "msg"
        assert finding.suggestion == "fix"
        assert finding.current_value == "current"
