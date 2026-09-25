"""Run Application Service API contract (SW-API-001).

Acceptance Criteria:
1. Expose stable Python API for the Run Application Service.
2. Ensure there is no direct Store/Dispatcher bypass.
"""

import sys
from pathlib import Path
import pytest

_SRC = Path(__file__).resolve().parent.parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from skillweave.api import execute_run
from skillweave.runsvc import RunApplicationService

def test_stable_api_exposes_execute_run():
    """The stable API must expose execute_run as a single entry point."""
    assert callable(execute_run)


def test_api_prevents_store_dispatcher_bypass():
    """
    The API should encapsulate Store/Journal setup so callers
    are not forced or able to interact with the raw DB/Store directly
    to do a run.
    """
    import inspect
    sig = inspect.signature(execute_run)
    
    # Store, Journal, Dispatcher must not be part of the parameters
    # to prevent bypass through injection of raw primitives.
    assert "store" not in sig.parameters
    assert "journal" not in sig.parameters
    assert "dispatcher" not in sig.parameters
    assert "raw_artifacts" not in sig.parameters
    
    # The signature should only require logical input fields
    assert "command" in sig.parameters
    assert "run_id" in sig.parameters

