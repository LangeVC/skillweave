from skillweave.runsvc.service import RunApplicationService
from skillweave.runtime.store import SQLiteRunStore
from skillweave.runtime.journal import EventJournal
from skillweave.runtime.registry import RawArtifactStore

class PromptchainExecutor:
    """
    Binds promptchain-execute to the canonical RunApplicationService.
    Ensures identical Run-ID/Receipts are produced and avoids the Markdown-only path.
    """
    
    def __init__(self, db_path: str = ":memory:", artifacts_path: str = ".skillweave/artifacts"):
        self.store = SQLiteRunStore(db_path)
        self.journal = EventJournal(db_path)
        self.raw_artifacts = RawArtifactStore(artifacts_path)
        self.svc = RunApplicationService(self.store, self.journal, self.raw_artifacts)

    def execute(self, command, run_id, tool="promptchain-execute", model="default", subject_repo="", subject_commit=""):
        """
        Execute promptchain-execute via RunApplicationService.
        This ensures there is no Markdown-only execution path.
        """
        if tool == "markdown" or (command and command[0].endswith(".md")):
            raise ValueError("Markdown-only execution path is not allowed.")

        return self.svc.execute(
            command=command,
            run_id=run_id,
            tool=tool,
            model=model,
            subject_repo=subject_repo,
            subject_commit=subject_commit
        )
