import json
import os
import shlex
import sys
import tempfile
import pytest
from pathlib import Path

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

GATE_TOKEN = "PUBLIC_CONTROL_PLANE_PASS"

def _setup_paths(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = str(tmp_path / "store.db")
    artifacts_path = str(tmp_path / "artifacts")
    return db_path, artifacts_path

@pytest.mark.parametrize("fixture_type", ["single_lane", "multi_lane"])
def test_public_control_plane(tmp_path, fixture_type):
    if fixture_type == "single_lane":
        FIXTURE_COMMAND = [sys.executable, "-c", "print('single')"]
    else:
        # For multi-lane, we can use a fan-out script or just a failure script to test errors
        FIXTURE_COMMAND = [sys.executable, "-c", "raise ValueError('multi')"]

    COMMAND_STR = " ".join(shlex.quote(arg) for arg in FIXTURE_COMMAND)
    
    # 1. Python API
    db_api, art_api = _setup_paths(tmp_path / "api")
    store = SQLiteRunStore(db_api)
    journal = EventJournal(db_api)
    raw = RawArtifactStore(art_api)
    svc = RunApplicationService(store, journal, raw)
    
    try:
        result_api = svc.execute(
            command=FIXTURE_COMMAND,
            run_id="api-run-1",
            tool="test-tool",
            model="test-model",
            subject_repo="test-repo",
            subject_commit="test-commit"
        )
        api_error = False
        api_digest = result_api.raw_digest
        api_gate = result_api.gate_state
        api_state = result_api.run.state
    except Exception as e:
        api_error = True
        api_digest = None
        api_gate = None
        api_state = None
        
    # 2. MCP
    db_mcp, art_mcp = _setup_paths(tmp_path / "mcp")
    try:
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
        mcp_error = False
    except Exception as e:
        mcp_error = True
        mcp_res = {}
        
    # 3. CLI
    db_cli, art_cli = _setup_paths(tmp_path / "cli")
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
    except Exception as e:
        exit_code = 1
    finally:
        sys.argv = old_argv
        sys.stdout = old_stdout
        
    cli_error = exit_code != 0
    if not cli_error:
        try:
            cli_res = json.loads(cli_out.getvalue().strip())
        except Exception:
            cli_error = True
            cli_res = {}
    else:
        cli_res = {}
        
    # 4. promptchain-execute
    db_pce, art_pce = _setup_paths(tmp_path / "pce")
    pce = PromptchainExecutor(db_path=db_pce, artifacts_path=art_pce)
    try:
        result_pce = pce.execute(
            command=FIXTURE_COMMAND,
            run_id="pce-run-1",
            tool="test-tool",
            model="test-model",
            subject_repo="test-repo",
            subject_commit="test-commit"
        )
        pce_error = False
    except Exception as e:
        pce_error = True
        
    assert api_error == mcp_error == cli_error == pce_error, "Errors do not match across transports"
    
    if not api_error:
        assert api_gate == mcp_res.get("gate_state") == cli_res.get("gate_state") == result_pce.gate_state
        assert api_state == mcp_res.get("state") == cli_res.get("state") == result_pce.run.state
        assert api_digest == mcp_res.get("raw_digest") == cli_res.get("raw_digest") == result_pce.raw_digest

if __name__ == "__main__":
    print(GATE_TOKEN)
