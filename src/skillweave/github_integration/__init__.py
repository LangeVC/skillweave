"""GitHub integration subpackage for CI/CD automation layer."""

from .inventory import WorkflowInventory
from .autotag import AutoTagger
from .changelog import ChangelogGenerator
from .issue_manager import IssueManager
from .pr_description import PRDescriptionGenerator
from .docs_sync import DocsSynchronizer
from .capability_sync import CapaciumManifestSync
from .release_gate import ReleaseReadinessGate
from .release_notes import ReleaseNotesGenerator

__all__ = [
    "WorkflowInventory",
    "AutoTagger",
    "ChangelogGenerator",
    "IssueManager",
    "PRDescriptionGenerator",
    "DocsSynchronizer",
    "CapaciumManifestSync",
    "ReleaseReadinessGate",
    "ReleaseNotesGenerator",
]
