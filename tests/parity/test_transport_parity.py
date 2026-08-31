import json
import os
import shlex
import sys
import tempfile
import pytest
from pathlib import Path

# Add src to python path for imports
_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from skillweave.runsvc.service import RunApplicationService
from skillweave.runtime.store import SQLiteRunStore
from skillweave.runtime.journal import EventJournal
from skillweave.runtime.registry import RawArtifactStore
from skillweave.mcp.server import create_run
from skillweave.skills.executor.service import PromptchainExecutor
from skillweave.cli.run import main as cli_main

# A stable fixture command that outputs a specific string.
FIXTURE_COMMAND = [sys.executable, "-c", "print('parity-fixture-output')"]
COMMAND_STR = " ".join(shlex.quote(arg) for arg in FIXTURE_COMMAND)

def _setup_paths(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = str(tmp_path / "store.db")
    artifacts_path = str(tmp_path / "artifacts")
    return db_path, artifacts_path

def test_transport_parity(tmp_path):
    """
    Test that running an identical Fixture-Run via all four transports
    yields semantically equal results and identical Artifact-Hashes.
    """
    
    # 1. Python API
    db_api, art_api = _setup_paths(tmp_path / "api")
    store = SQLiteRunStore(db_api)
    journal = EventJournal(db_api)
    raw = RawArtifactStore(art_api)
    svc = RunApplicationService(store, journal, raw)
    
    result_api = svc.execute(
        command=FIXTURE_COMMAND,
        run_id="api-run-1",
        tool="test-tool",
        model="test-model",
        subject_repo="test-repo",
        subject_commit="test-commit"
    )
    
    api_digest = result_api.raw_digest
    api_gate = result_api.gate_state
    api_state = result_api.run.state
    
    # 2. MCP
    db_mcp, art_mcp = _setup_paths(tmp_path / "mcp")
    mcp_res_str = create_run(
        tool="test-tool",
        model="test-model",
        subject_repo="test-repo",
        subject_commit="test-commit",
        command=COMMAND_STR,
        db_path=db_mcp,
        artifacts_path=art_mcp
    )
    mcp_res = json.loads(mcp_res_str)
    
    # 3. CLI
    db_cli, art_cli = _setup_paths(tmp_path / "cli")
    # Patch sys.argv and intercept stdout
    cli_args = [
        "skillweave.cli.run",
        "--tool", "test-tool",
        "--model", "test-model",
        "--subject-repo", "test-repo",
        "--subject-commit", "test-commit",
        "--db-path", db_cli,
        "--artifacts-path", art_cli,
        "--"
    ] + FIXTURE_COMMAND
    
    old_argv = sys.argv
    sys.argv = cli_args
    old_stdout = sys.stdout
    import io
    cli_out = io.StringIO()
    sys.stdout = cli_out
    
    try:
        exit_code = cli_main()
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
        
    assert exit_code == 0, "CLI run failed"
    cli_res = json.loads(cli_out.getvalue().strip())
    
    # 4. promptchain-execute
    db_pce, art_pce = _setup_paths(tmp_path / "pce")
    pce = PromptchainExecutor(db_path=db_pce, artifacts_path=art_pce)
    result_pce = pce.execute(
        command=FIXTURE_COMMAND,
        run_id="pce-run-1",
        tool="test-tool",
        model="test-model",
        subject_repo="test-repo",
        subject_commit="test-commit"
    )
    
    # Compare
    
    # Check Semantic equality: state and gate_state
    assert api_gate == mcp_res["gate_state"] == cli_res["gate_state"] == result_pce.gate_state == "pass"
    assert api_state == mcp_res["state"] == cli_res["state"] == result_pce.run.state == "advance_or_stop"
    
    # Check Artifact-Hashes
    assert api_digest is not None
    assert api_digest == mcp_res["raw_digest"], "API vs MCP digest mismatch"
    assert api_digest == cli_res["raw_digest"], "API vs CLI digest mismatch"
    assert api_digest == result_pce.raw_digest, "API vs PCE digest mismatch"
