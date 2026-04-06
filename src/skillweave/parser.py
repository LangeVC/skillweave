from pathlib import Path


REQUIRED_HEADERS = [
    "## Metadata",
    "## Objective",
    "## Success Criteria",
    "## Assumptions",
    "## Usage Notes",
    "## Inputs Required",
    "## Outputs Required",
    "## Sequence Steps",
    "## Final Assembly",
    "## Validation Rules",
    "## Failure Handling",
    "## Final Deliverable Format",
]


def load_markdown(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def detect_missing_headers(content: str) -> list[str]:
    return [header for header in REQUIRED_HEADERS if header not in content]
