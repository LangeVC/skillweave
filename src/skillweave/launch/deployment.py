import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class DeploymentResult:
    success: bool
    environment: str
    version: str
    timestamp: str
    health_status: dict
    rollback_plan: dict


def trigger_deployment(workflow_id: str, environment: str = "staging") -> DeploymentResult:
    version = _read_version()
    timestamp = datetime.now(timezone.utc).isoformat()

    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not gh_token:
        raise RuntimeError("GITHUB_TOKEN or GH_TOKEN required for workflow_dispatch")

    repo = _detect_repo()
    url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/"
        f"{workflow_id}/dispatches"
    )
    payload = json.dumps({"ref": "main", "inputs": {"environment": environment}}).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {gh_token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=30)
        dispatch_ok = True
    except urllib.error.HTTPError as exc:
        if exc.code == 204:
            dispatch_ok = True
        else:
            dispatch_ok = False
    except urllib.error.URLError:
        dispatch_ok = False

    health_status = {}
    if dispatch_ok:
        endpoint = _resolve_health_endpoint(environment)
        health_status = health_check(endpoint)

    rollback_plan = _build_rollback_plan(version, environment)

    return DeploymentResult(
        success=dispatch_ok,
        environment=environment,
        version=version,
        timestamp=timestamp,
        health_status=health_status,
        rollback_plan=rollback_plan,
    )


def health_check(endpoint: str) -> dict:
    start = time.monotonic()
    try:
        req = urllib.request.Request(endpoint, method="GET")
        resp = urllib.request.urlopen(req, timeout=10)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if resp.status == 200:
            status = "ok"
        elif resp.status < 500:
            status = "degraded"
        else:
            status = "down"
        return {
            "status": status,
            "response_time_ms": elapsed_ms,
            "http_status": resp.status,
        }
    except urllib.error.HTTPError as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        status = "down" if exc.code >= 500 else "degraded"
        return {"status": status, "response_time_ms": elapsed_ms, "http_status": exc.code}
    except (urllib.error.URLError, TimeoutError, OSError):
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {"status": "down", "response_time_ms": elapsed_ms, "http_status": 0}


def rollback(version: str, environment: str) -> dict:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1", "--format=%H"],
            capture_output=True, text=True, timeout=10,
        )
        current_hash = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        current_hash = "unknown"

    return {
        "success": True,
        "previous_version": version,
        "current_version": version,
        "environment": environment,
        "plan": {
            "git_revert_cmd": f"git revert {current_hash}",
            "db_restore": f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.sql",
            "estimated_downtime_sec": 30,
            "trigger": "health_check.status != 'ok' after deploy",
        },
        "note": "Rollback plan documented only — no automatic revert executed.",
    }


def _read_version() -> str:
    for candidate in ("CHANGELOG.md", "pyproject.toml", "package.json"):
        if os.path.isfile(candidate):
            try:
                with open(candidate) as f:
                    for line in f:
                        if line.startswith("## ") and "[" in line:
                            return line.strip().split("[")[1].split("]")[0]
                        if candidate == "pyproject.toml" and 'version = "' in line:
                            return line.split('"')[1]
                        if candidate == "package.json" and '"version"' in line:
                            return line.split('"')[3]
            except (OSError, IndexError):
                pass
    return "0.0.0"


def _detect_repo() -> str:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        url = result.stdout.strip()
        if "github.com" in url:
            parts = url.rstrip(".git").split("github.com/")
            if len(parts) > 1:
                return parts[-1]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return "skillweave/skillweave-launch"


def _resolve_health_endpoint(environment: str) -> str:
    return (
        "https://staging.skillweave.dev/health"
        if environment == "staging"
        else "https://skillweave.dev/health"
    )


def _build_rollback_plan(version: str, environment: str) -> dict:
    return {
        "strategy": "git-revert",
        "git_revert_cmd": "git revert <deploy-hash>",
        "db_restore": f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.sql",
        "estimated_downtime_sec": 30,
        "trigger": "health_check.status != 'ok' after deploy",
        "environment": environment,
        "version": version,
    }
