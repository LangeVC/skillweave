from pathlib import Path
import sys

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


def validate_markdown(path: Path) -> int:
    content = path.read_text(encoding="utf-8")
    missing = [header for header in REQUIRED_HEADERS if header not in content]
    if missing:
        print("INVALID")
        for item in missing:
            print(f"- missing: {item}")
        return 1
    print("VALID")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: validate.py <sequence.md>")
        raise SystemExit(2)
    raise SystemExit(validate_markdown(Path(sys.argv[1])))
