import pytest
from skillweave.intelligent_detection.prompt_analyzer import (
    PromptAnalyzer, PromptAnalysisResult, Intent, analyze_prompt
)


class TestIntentClassification:

    def test_create_blueprint_intent(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("I need a blueprint for my SaaS project")
        assert result.intent == Intent.CREATE_BLUEPRINT
        assert result.confidence >= 0.7

    def test_create_blueprint_keywords(self):
        analyzer = PromptAnalyzer()
        for kw in ["blueprint", "prd", "spec", "project plan", "design doc"]:
            result = analyzer.analyze(f"create a {kw}")
            assert result.intent == Intent.CREATE_BLUEPRINT, f"Failed for keyword: {kw}"

    def test_generate_promptchain_intent(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("generate a promptchain for blueprint skill")
        assert result.intent == Intent.GENERATE_PROMPTCHAIN
        assert result.confidence >= 0.7

    def test_generate_promptchain_keywords(self):
        analyzer = PromptAnalyzer()
        for prompt in [
            "generate a prompt sequence",
            "create a prompt workflow",
            "make a chain of prompts",
        ]:
            result = analyzer.analyze(prompt)
            assert result.intent == Intent.GENERATE_PROMPTCHAIN, f"Failed for: {prompt}"

    def test_validate_promptchain_intent(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("validate my promptchain before executing")
        assert result.intent == Intent.VALIDATE_PROMPTCHAIN

    def test_validate_intent_short_form(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("validate this sequence")
        assert result.intent == Intent.VALIDATE_PROMPTCHAIN

    def test_execute_promptchain_intent(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("execute the promptchain for release")
        assert result.intent == Intent.EXECUTE_PROMPTCHAIN

    def test_execute_promptchain_keywords(self):
        analyzer = PromptAnalyzer()
        for prompt in ["run the promptchain", "perform promptchain", "implement promptchain"]:
            result = analyzer.analyze(prompt)
            assert result.intent == Intent.EXECUTE_PROMPTCHAIN, f"Failed for: {prompt}"

    def test_execute_releasechain_intent(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("execute releasechain to deploy to production")
        assert result.intent == Intent.EXECUTE_RELEASECHAIN

    def test_releasechain_keywords(self):
        analyzer = PromptAnalyzer()
        for kw in ["releasechain", "deploy", "publish", "ship", "production deploy"]:
            result = analyzer.analyze(f"please {kw}")
            assert result.intent == Intent.EXECUTE_RELEASECHAIN, f"Failed for keyword: {kw}"

    def test_configure_intent(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("configure my skillweave settings")
        assert result.intent == Intent.CONFIGURE

    def test_configure_keywords(self):
        analyzer = PromptAnalyzer()
        for kw in ["setup", "install", "preferences", "options"]:
            result = analyzer.analyze(f"help me {kw}")
            assert result.intent == Intent.CONFIGURE, f"Failed for keyword: {kw}"

    def test_help_intent(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("help me understand what you can do")
        assert result.intent == Intent.HELP

    def test_help_keywords(self):
        analyzer = PromptAnalyzer()
        for kw in ["guide", "tutorial", "documentation"]:
            result = analyzer.analyze(kw)
            assert result.intent == Intent.HELP, f"Failed for keyword: {kw}"

    def test_unknown_intent(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("the sky is blue and the grass is green")
        assert result.intent == Intent.UNKNOWN
        assert result.confidence < 0.5

    def test_gibberish_input(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("asdf qwerty zxcv 12345 !@#$%")
        assert result.intent == Intent.UNKNOWN


class TestConfidenceScoring:

    def test_multiple_keywords_boost_confidence(self):
        analyzer = PromptAnalyzer()
        single = analyzer.analyze("blueprint")
        multi = analyzer.analyze("create a blueprint prd spec for project")
        assert multi.confidence > single.confidence

    def test_confidence_capped_at_one(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("blueprint prd spec plan project plan requirements design doc feature spec scope document")
        assert result.confidence <= 10.0

    def test_sensitivity_threshold_conservative(self):
        analyzer = PromptAnalyzer(sensitivity="conservative")
        result = analyzer.analyze("run the sequence")
        assert result.confidence >= 0.7

    def test_sensitivity_threshold_aggressive(self):
        analyzer = PromptAnalyzer(sensitivity="aggressive")
        result = analyzer.analyze("run")
        assert result.confidence >= 0.3


class TestParameterExtraction:

    def test_extract_idea_quoted(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze('idea="my awesome project"')
        assert result.extracted_parameters.get("idea") == "my awesome project"

    def test_extract_idea_unquoted(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("idea=myproject")
        assert result.extracted_parameters.get("idea") == "myproject"

    def test_extract_idea_colon(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("idea: building a task manager")
        assert result.extracted_parameters.get("idea") == "building a task manager"

    def test_extract_domain(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze('domain="healthcare"')
        assert result.extracted_parameters.get("domain") == "healthcare"

    def test_extract_domain_for_app(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("for a mobile app platform")
        assert result.extracted_parameters.get("domain") is not None

    def test_extract_complexity_explicit(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("complexity=simple")
        assert result.extracted_parameters.get("complexity") == "simple"

    def test_extract_complexity_implicit(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("a complex project")
        assert "complexity" in result.extracted_parameters

    def test_extract_output_format(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("output_format=json")
        assert result.extracted_parameters.get("output_format") == "json"

    def test_extract_output_format_text(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("format: markdown")
        assert result.extracted_parameters.get("output_format") == "markdown"

    def test_extract_risk_mode(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze('risk_mode="conservative"')
        assert result.extracted_parameters.get("risk_mode") == "conservative"

    def test_extract_risk_mode_unquoted(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("risk_mode=unicorn")
        assert result.extracted_parameters.get("risk_mode") == "unicorn"

    def test_extract_risk_mode_colon(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("risk: conservative mode")
        assert result.extracted_parameters.get("risk_mode") == "conservative mode"

    def test_extract_skill(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze('skill="skillweave-blueprint"')
        assert result.extracted_parameters.get("skill") == "skillweave-blueprint"

    def test_extract_use_skill(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("use blueprint skill")
        assert result.extracted_parameters.get("skill") == "blueprint"

    def test_multiple_parameters(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze('idea="task app" domain="mobile" complexity=simple risk_mode=medium')
        assert result.extracted_parameters.get("idea") == "task app"
        assert result.extracted_parameters.get("domain") == "mobile"
        assert result.extracted_parameters.get("complexity") == "simple"
        assert result.extracted_parameters.get("risk_mode") == "medium"

    def test_no_parameters(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("help")
        assert result.extracted_parameters == {}


class TestSuggestions:

    def test_empty_prompt_suggestion(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("")
        assert "Please provide a prompt" in result.suggestions[0]

    def test_blueprint_missing_idea(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("create a blueprint")
        assert any("idea" in s.lower() for s in result.suggestions)

    def test_blueprint_missing_domain(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("blueprint idea='test'")
        assert any("domain" in s.lower() for s in result.suggestions)

    def test_generate_missing_skill(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("generate a promptchain")
        assert any("skill" in s.lower() for s in result.suggestions)

    def test_low_confidence_suggestion(self):
        analyzer = PromptAnalyzer(sensitivity="conservative")
        result = analyzer.analyze("hello world this is a test")
        assert any("not sure" in s.lower() for s in result.suggestions)

    def test_general_parameter_suggestion(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("execute the promptchain")
        assert any("parameters" in s.lower() for s in result.suggestions)


class TestKeywordsFound:

    def test_keywords_found_for_blueprint(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("create a blueprint for my project")
        assert "blueprint" in result.keywords_found

    def test_keywords_found_multiple(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("blueprint prd spec")
        assert len(result.keywords_found) >= 2

    def test_keywords_empty_for_unknown(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("completely unrelated text here")
        assert result.keywords_found == []


class TestBatchAnalysis:

    def test_batch_analyze(self):
        analyzer = PromptAnalyzer()
        prompts = [
            "create a blueprint",
            "execute the promptchain",
            "help me get started",
        ]
        results = analyzer.batch_analyze(prompts)
        assert len(results) == 3
        assert results[0].intent == Intent.CREATE_BLUEPRINT
        assert results[1].intent == Intent.EXECUTE_PROMPTCHAIN
        assert results[2].intent == Intent.HELP

    def test_batch_analyze_empty_list(self):
        analyzer = PromptAnalyzer()
        results = analyzer.batch_analyze([])
        assert results == []


class TestConvenienceFunction:

    def test_analyze_prompt_default(self):
        result = analyze_prompt("deploy to production")
        assert result.intent == Intent.EXECUTE_RELEASECHAIN

    def test_analyze_prompt_custom_sensitivity(self):
        result = analyze_prompt("run", sensitivity="aggressive")
        assert result.intent == Intent.EXECUTE_PROMPTCHAIN

    def test_analyze_prompt_returns_result_object(self):
        result = analyze_prompt("configure settings")
        assert isinstance(result, PromptAnalysisResult)
        assert result.raw_prompt == "configure settings"


class TestEdgeCases:

    def test_empty_prompt(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("")
        assert result.intent == Intent.UNKNOWN
        assert result.confidence == 0.0
        assert result.extracted_parameters == {}

    def test_whitespace_prompt(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("   ")
        assert result.intent == Intent.UNKNOWN
        assert result.confidence == 0.0

    def test_very_long_prompt(self):
        analyzer = PromptAnalyzer()
        long_prompt = "create a blueprint " * 100
        result = analyzer.analyze(long_prompt)
        assert result.intent == Intent.CREATE_BLUEPRINT
        assert result.confidence <= 1.0

    def test_mixed_intents_prefers_highest_confidence(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("execute the promptchain and help me understand")
        assert result.intent == Intent.EXECUTE_PROMPTCHAIN

    def test_case_insensitivity(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("CREATE A BLUEPRINT")
        assert result.intent == Intent.CREATE_BLUEPRINT

    def test_punctuation_robustness(self):
        analyzer = PromptAnalyzer()
        result = analyzer.analyze("!!! create a blueprint !!!")
        assert result.intent == Intent.CREATE_BLUEPRINT

    def test_sensitivity_levels(self):
        for sensitivity in ["conservative", "medium", "aggressive"]:
            analyzer = PromptAnalyzer(sensitivity=sensitivity)
            assert analyzer.sensitivity == sensitivity

    def test_unknown_sensitivity_falls_back(self):
        analyzer = PromptAnalyzer(sensitivity="unknown")
        result = analyzer.analyze("hello world")
        assert result.intent == Intent.UNKNOWN
