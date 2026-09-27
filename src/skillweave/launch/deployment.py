"""Launch receipt and deployment orchestration (SW-157-LAUNCH-001).

A launch receipt is a tamper-evident, deterministic record of one deployment
attempt. It binds the artifact (sha256-pinned), target environment, commands
run, and outcome to a content digest. An unavailable result must declare at
least one limit; a failed verification cannot be recorded as success.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

RESULT_AVAILABLE = "available"
RESULT_UNAVAILABLE = "unavailable"
_RESULT_STATUSES = frozenset({RESULT_AVAILABLE, RESULT_UNAVAILABLE})

OUTCOME_SUCCESS = "success"
OUTCOME_FAILURE = "failure"
OUTCOME_UNAVAILABLE = "unavailable"
_OUTCOME_STATUSES = frozenset({OUTCOME_SUCCESS, OUTCOME_FAILURE, OUTCOME_UNAVAILABLE})

_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")

_CORE_FIELDS = (
    "schema_version",
    "result",
    "target",
    "artifact",
    "commands",
    "outcome",
    "provenance",
    "limits",
)
_TOP_LEVEL_KEYS = frozenset(_CORE_FIELDS) | {"digest"}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LaunchReceiptError(ValueError):
    """A launch receipt is missing, malformed or self-contradictory."""


class LaunchReceiptTamperError(LaunchReceiptError):
    """A receipt's recomputed digest does not match the digest it carries."""


# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------


def _canonical_json(payload: Mapping[str, Any]) -> str:
    """Canonical JSON: sorted keys, no insignificant whitespace, ASCII-safe."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_digest(receipt: Mapping[str, Any]) -> str:
    """Return the sha256 digest of ``receipt`` with any ``digest`` key excluded."""
    payload = {k: v for k, v in receipt.items() if k != "digest"}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise LaunchReceiptError(f"{label} must be a non-empty string, got {value!r}")
    return value


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise LaunchReceiptError(f"{label} must be a mapping, got {value!r}")
    return dict(value)


def _check_unknown_keys(mapping: Mapping[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = sorted((k for k in mapping if k not in allowed), key=repr)
    if unknown:
        raise LaunchReceiptError(
            f"{label} carries unknown key(s) {unknown}; only {sorted(allowed)} are allowed"
        )


def _normalize_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.match(value):
        raise LaunchReceiptError(
            f"{field} is not a canonical lowercase sha256 hex digest: {value!r}"
        )
    return value


def _normalize_commands(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise LaunchReceiptError(f"commands must be a list, got {value!r}")
    normalized: list[dict[str, Any]] = []
    for idx, entry in enumerate(value):
        entry = _require_mapping(entry, f"commands[{idx}]")
        _check_unknown_keys(entry, frozenset({"command", "exit"}), f"commands[{idx}]")
        if "command" not in entry:
            raise LaunchReceiptError(f"commands[{idx}] is missing 'command'")
        if "exit" not in entry:
            raise LaunchReceiptError(f"commands[{idx}] is missing 'exit'")
        exit_code = entry["exit"]
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise LaunchReceiptError(f"commands[{idx}].exit must be an integer, got {exit_code!r}")
        normalized.append({
            "command": _require_str(entry["command"], f"commands[{idx}].command"),
            "exit": exit_code,
        })
    return normalized


def _normalize_target(value: Any) -> dict[str, Any]:
    target = _require_mapping(value, "target")
    _check_unknown_keys(target, frozenset({"environment", "version", "host"}), "target")
    if "environment" not in target:
        raise LaunchReceiptError("target is missing 'environment'")
    if "version" not in target:
        raise LaunchReceiptError("target is missing 'version'")
    normalized: dict[str, Any] = {
        "environment": _require_str(target["environment"], "target.environment"),
        "version": _require_str(target["version"], "target.version"),
    }
    if "host" in target:
        normalized["host"] = _require_str(target["host"], "target.host")
    return normalized


def _normalize_artifact(value: Any) -> dict[str, Any]:
    artifact = _require_mapping(value, "artifact")
    _check_unknown_keys(artifact, frozenset({"artifact_id", "sha256"}), "artifact")
    if "artifact_id" not in artifact:
        raise LaunchReceiptError("artifact is missing 'artifact_id'")
    if "sha256" not in artifact:
        raise LaunchReceiptError("artifact is missing 'sha256'")
    return {
        "artifact_id": _require_str(artifact["artifact_id"], "artifact.artifact_id"),
        "sha256": _normalize_sha256(artifact["sha256"], field="artifact.sha256"),
    }


def _normalize_outcome(value: Any) -> dict[str, Any]:
    outcome = _require_mapping(value, "outcome")
    _check_unknown_keys(outcome, frozenset({"status", "health"}), "outcome")
    if "status" not in outcome:
        raise LaunchReceiptError("outcome is missing 'status'")
    status = outcome["status"]
    if not isinstance(status, str) or status not in _OUTCOME_STATUSES:
        raise LaunchReceiptError(
            f"outcome.status must be one of {sorted(_OUTCOME_STATUSES)}, got {status!r}"
        )
    normalized: dict[str, Any] = {"status": status}

    if "health" in outcome:
        health = _require_mapping(outcome["health"], "outcome.health")
        _check_unknown_keys(health, frozenset({"status", "response_time_ms"}), "outcome.health")
        health_normalized: dict[str, Any] = {}
        if "status" in health:
            hs = health["status"]
            if hs not in ("ok", "degraded", "down", "unchecked"):
                raise LaunchReceiptError(
                    f"outcome.health.status must be one of ok/degraded/down/unchecked, got {hs!r}"
                )
            health_normalized["status"] = hs
        if "response_time_ms" in health:
            rt = health["response_time_ms"]
            if not isinstance(rt, int) or isinstance(rt, bool):
                raise LaunchReceiptError(
                    f"outcome.health.response_time_ms must be an integer, got {rt!r}"
                )
            health_normalized["response_time_ms"] = rt
        normalized["health"] = health_normalized

    return normalized


def _normalize_provenance(value: Any) -> dict[str, Any]:
    provenance = _require_mapping(value, "provenance")
    _check_unknown_keys(
        provenance, frozenset({"launcher", "run_id", "produced_at", "model"}), "provenance"
    )
    normalized: dict[str, Any] = {}
    for required in ("launcher", "run_id", "produced_at"):
        if required not in provenance:
            raise LaunchReceiptError(f"provenance is missing '{required}'")
        normalized[required] = _require_str(provenance[required], f"provenance.{required}")
    if "model" in provenance:
        normalized["model"] = _require_str(provenance["model"], "provenance.model")
    return normalized


def _normalize_limits(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise LaunchReceiptError(f"limits must be a list, got {value!r}")
    return [_require_str(limit, f"limits[{idx}]") for idx, limit in enumerate(value)]


def _normalize_core(receipt: Any) -> dict[str, Any]:
    """Validate and canonicalize every digested field, excluding ``digest``."""
    if not isinstance(receipt, Mapping):
        raise LaunchReceiptError(f"receipt must be a mapping, got {receipt!r}")
    _check_unknown_keys(receipt, _TOP_LEVEL_KEYS, "receipt")
    for required in _CORE_FIELDS:
        if required not in receipt:
            raise LaunchReceiptError(f"receipt is missing '{required}'")

    version = receipt["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool) or version != SCHEMA_VERSION:
        raise LaunchReceiptError(f"schema_version must be {SCHEMA_VERSION}, got {version!r}")

    result = receipt["result"]
    if not isinstance(result, Mapping):
        raise LaunchReceiptError(f"result must be a mapping, got {result!r}")
    _check_unknown_keys(result, frozenset({"status", "summary"}), "result")
    if "status" not in result:
        raise LaunchReceiptError("result is missing 'status'")
    rstatus = result["status"]
    if not isinstance(rstatus, str) or rstatus not in _RESULT_STATUSES:
        raise LaunchReceiptError(
            f"result.status must be one of {sorted(_RESULT_STATUSES)}, got {rstatus!r}"
        )
    normalized_result: dict[str, Any] = {"status": rstatus}
    if "summary" in result:
        normalized_result["summary"] = _require_str(result["summary"], "result.summary")

    target = _normalize_target(receipt["target"])
    artifact = _normalize_artifact(receipt["artifact"])
    commands = _normalize_commands(receipt["commands"])
    outcome = _normalize_outcome(receipt["outcome"])
    limits = _normalize_limits(receipt["limits"])
    provenance = _normalize_provenance(receipt["provenance"])

    # Unavailable/failed verification cannot equal success.
    if rstatus == RESULT_UNAVAILABLE:
        if not limits:
            raise LaunchReceiptError("an unavailable receipt must declare at least one limit")
        if outcome["status"] == OUTCOME_SUCCESS:
            raise LaunchReceiptError(
                "an unavailable result cannot have a success outcome"
            )
    else:
        if not commands:
            raise LaunchReceiptError("an available receipt must declare at least one command")

    return {
        "schema_version": SCHEMA_VERSION,
        "result": normalized_result,
        "target": target,
        "artifact": artifact,
        "commands": commands,
        "outcome": outcome,
        "provenance": provenance,
        "limits": limits,
    }


# ---------------------------------------------------------------------------
# LaunchReceipt
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LaunchReceipt:
    """A deterministic, tamper-evident record of one deployment attempt.

    The digest binds the artifact (sha256-pinned), target, commands, and
    outcome so that any post-hoc mutation is detectable.
    """

    payload: Mapping[str, Any]
    digest: str

    def to_dict(self) -> dict[str, Any]:
        document = dict(self.payload)
        document["digest"] = self.digest
        return document

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def seal(receipt: Mapping[str, Any]) -> dict[str, Any]:
    """Validate ``receipt`` and return it sealed with a matching digest.

    Any ``digest`` on the input is ignored and replaced.
    """
    canonical = _normalize_core(receipt)
    canonical["digest"] = compute_digest(canonical)
    return canonical


def canonicalize(receipt: Mapping[str, Any]) -> LaunchReceipt:
    """Validate a sealed receipt, fail-closed, and verify its digest.

    Raises :class:`LaunchReceiptError` on any missing, unknown, malformed or
    self-contradictory field, and :class:`LaunchReceiptTamperError` when the
    recomputed digest does not match the carried ``digest``.
    """
    canonical = _normalize_core(receipt)
    if "digest" not in receipt:
        raise LaunchReceiptError("receipt is missing 'digest'")
    provided = _normalize_sha256(receipt["digest"], field="digest")
    expected = compute_digest(canonical)
    if provided != expected:
        raise LaunchReceiptTamperError(
            f"digest mismatch: receipt carries {provided} but its content hashes to {expected}"
        )
    return LaunchReceipt(payload=canonical, digest=expected)


# ---------------------------------------------------------------------------
# Deployment orchestration (original functionality)
# ---------------------------------------------------------------------------


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
    if environment == "staging":
        staging_url = os.environ.get("SKILLWEAVE_STAGING_HEALTH_URL")
        if not staging_url:
            raise RuntimeError(
                "Staging health endpoint not configured. "
                "Set SKILLWEAVE_STAGING_HEALTH_URL."
            )
        return staging_url
    return os.environ.get(
        "SKILLWEAVE_HEALTH_URL",
        "https://skillweave.xyz/health",
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


__all__ = [
    "SCHEMA_VERSION",
    "RESULT_AVAILABLE",
    "RESULT_UNAVAILABLE",
    "OUTCOME_SUCCESS",
    "OUTCOME_FAILURE",
    "OUTCOME_UNAVAILABLE",
    "LaunchReceipt",
    "LaunchReceiptError",
    "LaunchReceiptTamperError",
    "compute_digest",
    "seal",
    "canonicalize",
    "DeploymentResult",
    "trigger_deployment",
    "health_check",
    "rollback",
]
