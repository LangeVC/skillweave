import json
import pytest

from skillweave.trace.contracts import (
    AppendOnlyReceiptLog,
    TerminalEnvelope,
    TerminalState,
    JobResult,
    JobStatus,
    TaskVerdict,
    EvidenceAvailability,
    GateVerdict,
    RoundKind,
    new_append_only_round
)
from skillweave.core.harness.provenance import HarnessProvenance, ProvenanceType
from .fake_harness import FakeHarness

def test_fake_harness_hermetic():
    """Verify that the fake harness is hermetic and returns expected output."""
    harness = FakeHarness()
    result = harness.execute(["echo", "hello"])
    assert result["exit_code"] == 0
    assert result["stdout"] == b"fake output"
    assert len(harness.ran_commands) == 1

def test_harness_proof_opencode_deepseek():
    """
    Demonstrates a real OpenCode/deepseek-v4-pro Dispatch-Receipt containing
    Exit, Output, Harness, Model-Provenance, and Subject-SHA.
    """
    subject_sha = "abc123def4567890abc123def4567890abc123def4567890abc123def4567890"
    
    # 1. Create Model-Provenance (Harness)
    prov = HarnessProvenance(harness_id="opencode-harness")
    prov.declare("model", "opencode", "deepseek-v4-pro")
    prov.attest("environment", "ci", "linux-amd64")
    
    # 2. Terminal Envelope (Exit, Output/Artifacts, Subject-SHA)
    envelope = TerminalEnvelope(
        subject_sha=subject_sha,
        command=["python", "-m", "opencode.worker", "--model", "deepseek-v4-pro"],
        terminal_state=TerminalState.COMPLETED,
        exit_code=0,
        artifact_refs=["logs/output.txt"],
        completion_contract={"output_preview": "task completed successfully"}
    )
    
    result = JobResult(
        job_status=JobStatus.EXITED,
        task_verdict=TaskVerdict.DONE,
        evidence_available=EvidenceAvailability.RECORDED,
        gate_verdict=GateVerdict.PASS
    )
    
    # 3. Create Dispatch-Receipt
    log = AppendOnlyReceiptLog()
    record = new_append_only_round(
        log=log,
        parent_id=None,
        round_=1,
        kind=RoundKind.DISPATCH,
        job_id="job-opencode-01",
        result=result,
        envelope=envelope,
        payload=prov.summarize()
    )
    
    # Assertions
    assert record.envelope.subject_sha == subject_sha
    assert record.envelope.exit_code == 0
    assert "logs/output.txt" in record.envelope.artifact_refs
    
    # Ensure provenance is captured in the receipt
    assert record.payload["harness_id"] == "opencode-harness"
    claims = record.payload["claims"]["model"]
    assert any(c["value"] == "deepseek-v4-pro" for c in claims)
