"""Sandbox/Remote Workspace provisioning.

Implements the WorkspaceProvider contract over a remote sandbox environment
(e.g., container or remote machine). It guarantees the same contract locally
and remotely, providing the environment without introducing foreign orchestration
truth (like DAG, Gate, or Authority state).
"""

from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional

from skillweave.workspace.provider import (
    WorkspaceProvider,
    WorkspaceProviderError,
    Workspace,
    Attestation,
    _digest
)


class RemoteWorkspaceProvider(WorkspaceProvider):
    """Remote sandbox adapter for Workspace provisioning.
    
    Creates and tears down exclusive remote workspaces via a sandbox API,
    maintaining the same attestation contract as GitWorktreeProvider.
    It provisions the environment but delegates orchestration state back to
    the core engine.
    """

    def __init__(self, api_endpoint: str, api_token: Optional[str] = None):
        self.api_endpoint = api_endpoint.rstrip("/")
        self.api_token = api_token or os.environ.get("SKILLWEAVE_REMOTE_TOKEN", "")

    def _request(self, method: str, path: str, data: Optional[dict] = None) -> dict:
        url = f"{self.api_endpoint}{path}"
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
            
        req_data = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        
        try:
            with urllib.request.urlopen(req) as response:
                if response.status in (200, 201):
                    body = response.read().decode("utf-8")
                    return json.loads(body) if body else {}
                raise WorkspaceProviderError(f"Remote API error: HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            raise WorkspaceProviderError(f"Remote API error: {exc.reason}") from exc
        except Exception as exc:
            raise WorkspaceProviderError(f"Remote connection error: {exc}") from exc

    def acquire(
        self,
        base_sha: str,
        branch: str,
        *,
        path: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Workspace:
        created_at = created_at or datetime.now(timezone.utc).isoformat()
        
        try:
            resp = self._request("POST", "/workspaces", data={
                "base_sha": base_sha,
                "branch": branch,
                "requested_path": path,
            })
        except WorkspaceProviderError as e:
            raise WorkspaceProviderError(f"Failed to acquire remote workspace: {e}") from e
            
        remote_path = resp.get("path", f"/sandbox/{branch.replace('/', '__')}")
        actual_sha = resp.get("base_sha", base_sha)
        
        if actual_sha != base_sha:
            raise WorkspaceProviderError(
                f"Remote workspace HEAD '{actual_sha}' != pinned base '{base_sha}'"
            )

        attestation = Attestation(
            base_sha=actual_sha,
            branch=branch,
            path=remote_path,
            created_at=created_at,
            digest=_digest(actual_sha, branch, remote_path),
        )
        return Workspace(provider=self, attestation=attestation)

    def release(self, attestation: Attestation) -> bool:
        try:
            self._request("DELETE", f"/workspaces/{attestation.branch}")
            return True
        except Exception:
            return False

    def attest(self, path: str, branch: str) -> Attestation:
        try:
            resp = self._request("GET", f"/workspaces/{branch}")
        except WorkspaceProviderError as e:
            raise WorkspaceProviderError(f"Failed to attest remote workspace '{branch}': {e}") from e
            
        head = resp.get("base_sha")
        if not head:
            raise WorkspaceProviderError("could not resolve remote worktree HEAD")
            
        actual_path = resp.get("path", path)
        created_at = resp.get("created_at") or datetime.now(timezone.utc).isoformat()
        
        return Attestation(
            base_sha=head,
            branch=branch,
            path=actual_path,
            created_at=created_at,
            digest=_digest(head, branch, actual_path),
        )
