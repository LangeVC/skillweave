from skillweave.parser import detect_missing_headers


def test_detect_missing_headers():
    content = "# x\n\n## Metadata\n"
    missing = detect_missing_headers(content)
    assert "## Objective" in missing
