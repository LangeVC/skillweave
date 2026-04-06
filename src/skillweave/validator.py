from dataclasses import dataclass

from .parser import detect_missing_headers


@dataclass
class ValidationResult:
    is_valid: bool
    findings: list[str]


def validate_markdown_sequence(content: str) -> ValidationResult:
    findings: list[str] = []
    missing = detect_missing_headers(content)
    if missing:
        findings.extend([f"Missing section: {item}" for item in missing])
    is_valid = len(findings) == 0
    return ValidationResult(is_valid=is_valid, findings=findings)
