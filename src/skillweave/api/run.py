"""Stable Python API for the Run Application Service.

``SW-API-001``. Exposes the single authoritative integration path (Run Application Service)
while strictly hiding the internal Store, Journal, and Dispatcher primitives to prevent
direct bypass.
"""

from typing import Any, Optional, Sequence

# We import the internal run application service, but we don't expose its dependencies.
from skillweave.runsvc import RunApplicationService, RunExecution
from skillweave.runtime.store import SQLiteRunStore
from skillweave.runtime.journal import EventJournal
from skillweave.runtime.registry import RawArtifactStore


def execute_run(
    command: Sequence[str],
    *,
    run_id: str,
    tool: str,
    model: str,
    subject_repo: str,
    subject_commit: str,
    created_at: Optional[str] = None,
    check_output: Optional[Any] = None,
) -> RunExecution:
    """Execute a run through the authoritative six-stage integration path.
    
    This stable API entry point encapsulates the underlying SQLiteRunStore, EventJournal,
    and RawArtifactStore so that callers cannot bypass the RunApplicationService.
    """
    store = SQLiteRunStore()
    journal = EventJournal()
    raw_artifacts = RawArtifactStore()
    
    service = RunApplicationService(
        store=store,
        journal=journal,
        raw_artifacts=raw_artifacts,
    )
    
    return service.execute(
        command=command,
        run_id=run_id,
        tool=tool,
        model=model,
        subject_repo=subject_repo,
        subject_commit=subject_commit,
        created_at=created_at,
        check_output=check_output,
    )
