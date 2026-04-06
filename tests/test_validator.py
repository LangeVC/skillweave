from skillweave.validator import validate_markdown_sequence


def test_validator_reports_missing_sections():
    result = validate_markdown_sequence("# test")
    assert result.is_valid is False
    assert result.findings
