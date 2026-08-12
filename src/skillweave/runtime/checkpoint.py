"""
RTF-008: Checkpoint and Resume with Revalidation.

Long-lived runs and agent swaps without chat dependency.

A checkpoint contains: DAG cursor, open and completed nodes, gate
states, pending commands, leases, artefact digests, git identity,
environment fingerprint, policy snapshot, budget consumption,
compensation stack, journal offset, rootRunId and parentRunId.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
import hashlib
import os
import platform
import sys


@dataclass
class EnvironmentFingerprint:
    hostname: str
    os_name: str
    python_version: str
    branch: str
    commit_sha: str
    key_hashes: dict[str, str] = field(default_factory=dict)
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "hostname": self.hostname,
            "os_name": self.os_name,
            "python_version": self.python_version,
            "branch": self.branch,
            "commit_sha": self.commit_sha,
            "key_hashes": self.key_hashes,
            "captured_at": self.captured_at,
        }

    def digest(self) -> str:
        return hashlib.sha256(
            f"{self.hostname}|{self.os_name}|{self.python_version}|{self.branch}|{self.commit_sha}|{self.key_hashes}".encode()
        ).hexdigest()

    def validate_against(self, other: "EnvironmentFingerprint") -> bool:
        return self.digest() == other.digest()

    def diff(self, other: "EnvironmentFingerprint") -> list[str]:
        changes = []
        if self.hostname != other.hostname:
            changes.append("hostname")
        if self.os_name != other.os_name:
            changes.append("os_name")
        if self.python_version != other.python_version:
            changes.append("python_version")
        if self.branch != other.branch:
            changes.append("branch")
        if self.commit_sha != other.commit_sha:
            changes.append("commit_sha")
        for key in set(self.key_hashes) | set(other.key_hashes):
            if self.key_hashes.get(key) != other.key_hashes.get(key):
                changes.append(f"key_hash:{key}")
        return changes


class ResumeRevalidationRequired(Exception):
    def __init__(self, field: str, before: str, after: str):
        self.field = field
        self.before = before
        self.after = after
        super().__init__(
            f"RESUME_REVALIDATION_REQUIRED: environment changed ({field}: {before} → {after})"
        )


@dataclass
class Checkpoint:
    run_id: str
    root_run_id: str
    parent_run_id: Optional[str]
    journal_offset: int
    environment: EnvironmentFingerprint
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "root_run_id": self.root_run_id,
            "parent_run_id": self.parent_run_id,
            "journal_offset": self.journal_offset,
            "environment": self.environment.to_dict(),
            "created_at": self.created_at,
            "metadata": self.metadata,
        }


def capture_environment(branch: str = "unknown", commit_sha: str = "unknown") -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        hostname=os.uname().nodename,
        os_name=f"{platform.system()} {platform.release()}",
        python_version=sys.version.split()[0],
        branch=branch,
        commit_sha=commit_sha,
        key_hashes={},
    )


def create_checkpoint(
    run_id: str,
    root_run_id: str,
    journal_offset: int,
    environment: EnvironmentFingerprint,
    parent_run_id: Optional[str] = None,
) -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        root_run_id=root_run_id,
        parent_run_id=parent_run_id,
        journal_offset=journal_offset,
        environment=environment,
    )


def validate_resume(
    checkpoint: Checkpoint,
    current_environment: EnvironmentFingerprint,
) -> bool:
    if not checkpoint.environment.validate_against(current_environment):
        changes = checkpoint.environment.diff(current_environment)
        raise ResumeRevalidationRequired(
            field=",".join(changes),
            before=checkpoint.environment.digest(),
            after=current_environment.digest(),
        )
    return True
