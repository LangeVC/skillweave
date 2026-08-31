import re

with open("src/skillweave/routing/dispatch.py", "r") as f:
    content = f.read()

# Remove the import block
content = re.sub(
    r"from skillweave\.runtime\.runner_adapter import ProcessResult, run_command\n",
    "",
    content,
)
content = re.sub(
    r"from skillweave\.runtime\.registry import \(\n    ArtifactReceipt,\n    EvidenceQuality,\n    EvidenceType,\n\)\n",
    "",
    content,
)

# Stringify annotations
content = content.replace("result: ProcessResult", 'result: "ProcessResult"')
content = content.replace("artifact: Optional[ArtifactReceipt]", 'artifact: Optional["ArtifactReceipt"]')
content = content.replace(") -> ArtifactReceipt:", ') -> "ArtifactReceipt":')

# Use importlib for run_command
content = content.replace(
    "        result = run_command(",
    '        import importlib\n        run_command = importlib.import_module("skillweave.runtime.runner_adapter").run_command\n        result = run_command('
)

# Use importlib for ArtifactReceipt
old_receipt = """    import hashlib

    return ArtifactReceipt(
        artifact_id=f"dispatch-{run_id}","""
new_receipt = """    import hashlib
    import importlib
    reg = importlib.import_module("skillweave.runtime.registry")

    return reg.ArtifactReceipt(
        artifact_id=f"dispatch-{run_id}","""
content = content.replace(old_receipt, new_receipt)

content = content.replace("evidence_type=EvidenceType.ARTIFACT.value,", "evidence_type=reg.EvidenceType.ARTIFACT.value,")

with open("src/skillweave/routing/dispatch.py", "w") as f:
    f.write(content)

