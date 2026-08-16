from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from .errors import InvalidTransitionError, VersionConflictError
from .checkpoint import Checkpoint, EnvironmentFingerprint
from .registry import ArtifactReceipt, EvidenceQuality
from .handoff import ColdStartBundle, HandoffOffer

import sqlite3


class RunStateModel(str, Enum):
    PREFLIGHT = "preflight"
    BATCH_SELECTION = "batch_selection"
    LANE_PLAN = "lane_plan"
    IMPLEMENT = "implement"
    VERIFY = "verify"
    REVIEW_GATE = "review_gate"
    FIX_RETRY = "fix_retry"
    INTEGRATE = "integrate"
    ADVANCE_OR_STOP = "advance_or_stop"
    SANDBOX_PREFLIGHT = "SANDBOX_PREFLIGHT"
    IN_PROGRESS = "IN_PROGRESS"
    PREFLIGHT_COMPLETE = "PREFLIGHT_COMPLETE"
    BLOCKED_WAITING_FOR_GATE = "BLOCKED_WAITING_FOR_GATE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAILED = "FAILED"
    STOPPED_BEFORE_B06 = "STOPPED_BEFORE_B06"

    @classmethod
    def legal_transitions(cls, from_state):
        transition_map = {
            cls.PREFLIGHT: [cls.BATCH_SELECTION],
            cls.BATCH_SELECTION: [cls.LANE_PLAN, cls.ADVANCE_OR_STOP],
            cls.LANE_PLAN: [cls.IMPLEMENT],
            cls.IMPLEMENT: [cls.VERIFY],
            cls.VERIFY: [cls.REVIEW_GATE, cls.FIX_RETRY],
            cls.REVIEW_GATE: [cls.INTEGRATE, cls.FIX_RETRY, cls.ADVANCE_OR_STOP],
            cls.FIX_RETRY: [cls.IMPLEMENT, cls.REVIEW_GATE, cls.ADVANCE_OR_STOP],
            cls.INTEGRATE: [cls.VERIFY, cls.ADVANCE_OR_STOP],
            cls.ADVANCE_OR_STOP: [],
            cls.SANDBOX_PREFLIGHT: [cls.IN_PROGRESS, cls.FAILED],
            cls.IN_PROGRESS: [cls.PREFLIGHT_COMPLETE, cls.BLOCKED_WAITING_FOR_GATE, cls.REVIEW_REQUIRED, cls.FAILED],
            cls.PREFLIGHT_COMPLETE: [cls.IN_PROGRESS, cls.REVIEW_REQUIRED, cls.FAILED],
            cls.BLOCKED_WAITING_FOR_GATE: [cls.IN_PROGRESS, cls.REVIEW_REQUIRED, cls.FAILED],
            cls.REVIEW_REQUIRED: [cls.IN_PROGRESS, cls.FAILED],
            cls.FAILED: [cls.SANDBOX_PREFLIGHT],
            cls.STOPPED_BEFORE_B06: [cls.IN_PROGRESS],
        }
        from_state = cls(from_state) if isinstance(from_state, str) else from_state
        return transition_map.get(from_state, [])


@dataclass
class RunRecord:
    run_id: str
    root_run_id: str
    parent_run_id: Optional[str]
    state: str
    version: int
    created_at: str
    updated_at: str
    ended_at: Optional[str]
    role: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class RunStore(ABC):
    @abstractmethod
    def get_run(self, run_id: str) -> Optional[RunRecord]:
        ...

    @abstractmethod
    def save_run(self, record: RunRecord) -> RunRecord:
        ...

    @abstractmethod
    def transition(
        self,
        run_id: str,
        target_state: str,
        expected_state: str,
        expected_version: int,
        reason: str = "",
        role: Optional[str] = None,
    ) -> RunRecord:
        ...

    @abstractmethod
    def list_runs(self, state: Optional[str] = None, limit: int = 100) -> list[RunRecord]:
        ...


class SQLiteRunStore(RunStore):
    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        # 5000 is sqlite3.connect()'s built-in default. Stating it explicitly makes the
        # write-lock behavior visible and independent of the library default, so a caller
        # holding its own connection can no longer silently override it. Same value, no
        # behavior change.
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                root_run_id TEXT NOT NULL,
                parent_run_id TEXT,
                state TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                ended_at TEXT,
                role TEXT NOT NULL DEFAULT 'ops',
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS transitions_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'ops'
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                run_id TEXT PRIMARY KEY,
                root_run_id TEXT NOT NULL,
                parent_run_id TEXT,
                journal_offset INTEGER NOT NULL DEFAULT 0,
                environment TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS evidence (
                artifact_id TEXT NOT NULL UNIQUE,
                sha256 TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                producer_command TEXT NOT NULL,
                subject_repo TEXT NOT NULL,
                subject_commit TEXT NOT NULL,
                created_at TEXT NOT NULL,
                evidence_type TEXT NOT NULL,
                purpose TEXT NOT NULL,
                method TEXT NOT NULL DEFAULT '',
                system_source TEXT NOT NULL DEFAULT '',
                sensitivity TEXT NOT NULL DEFAULT 'internal',
                retention TEXT NOT NULL DEFAULT 'permanent',
                transformation_history TEXT NOT NULL DEFAULT '[]',
                quality TEXT NOT NULL DEFAULT '{}',
                supersedes TEXT,
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS handoffs (
                handoff_id TEXT PRIMARY KEY,
                from_role TEXT NOT NULL,
                to_role TEXT NOT NULL,
                scope TEXT NOT NULL,
                cold_start_bundle TEXT NOT NULL,
                allowed_actions TEXT NOT NULL DEFAULT '[]',
                input_digests TEXT NOT NULL DEFAULT '{}',
                state TEXT NOT NULL,
                owner TEXT,
                offered_at TEXT NOT NULL,
                accepted_at TEXT,
                completed_at TEXT,
                metadata TEXT NOT NULL DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS write_scope_claims (
                claim_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                resolved_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                released_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_write_scope_claims_run
                ON write_scope_claims(run_id);
            CREATE INDEX IF NOT EXISTS idx_write_scope_claims_path
                ON write_scope_claims(resolved_path);
        """)
        self._conn.commit()

    def _row_to_record(self, row) -> RunRecord:
        import json
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        return RunRecord(
            run_id=row["run_id"],
            root_run_id=row["root_run_id"],
            parent_run_id=row["parent_run_id"],
            state=row["state"],
            version=row["version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            ended_at=row["ended_at"],
            role=row["role"],
            metadata=meta,
        )

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def save_run(self, record: RunRecord) -> RunRecord:
        import json
        now = datetime.now(timezone.utc).isoformat()
        if record.created_at is None:
            record.created_at = now
        record.updated_at = now
        if record.version < 1:
            record.version = 1

        self._conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, root_run_id, parent_run_id, state, version,
                created_at, updated_at, ended_at, role, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.run_id, record.root_run_id, record.parent_run_id,
                record.state, record.version,
                record.created_at, record.updated_at, record.ended_at,
                record.role, json.dumps(record.metadata),
            ),
        )
        self._conn.commit()
        return record

    def set_authority_guard(self, guard) -> None:
        self._authority_guard = guard

    def transition(
        self,
        run_id: str,
        target_state: str,
        expected_state: str,
        expected_version: int,
        reason: str = "",
        role: Optional[str] = None,
    ) -> RunRecord:
        existing = self.get_run(run_id)
        if existing is None:
            raise InvalidTransitionError(
                "nonexistent", target_state, run_id,
                extra={"reason": "run does not exist"},
            )

        if expected_state is not None and existing.state != expected_state:
            raise InvalidTransitionError(
                existing.state, target_state, run_id,
                extra={
                    "expected": expected_state,
                    "actual": existing.state,
                    "reason": "run is not in the expected state",
                },
            )

        if expected_version is not None and existing.version != expected_version:
            raise VersionConflictError(run_id, expected_version, existing.version)

        if role and hasattr(self, '_authority_guard') and self._authority_guard is not None:
            from skillweave.runtime.authority import can_mutate_run_state
            if not can_mutate_run_state(role):
                from skillweave.runtime.authority import AuthorityError
                raise AuthorityError(role, "transition", f"Role '{role}' lacks mutate_run_state")

        allowed = RunStateModel.legal_transitions(existing.state)
        allowed_values = [s.value if isinstance(s, RunStateModel) else s for s in allowed]
        if target_state not in allowed_values:
            raise InvalidTransitionError(
                existing.state, target_state, run_id,
                extra={"allowed": allowed_values},
            )

        now = datetime.now(timezone.utc).isoformat()
        new_version = existing.version + 1
        ended_at = existing.ended_at
        if target_state in ("advance_or_stop", "FAILED"):
            ended_at = now

        cur = self._conn.execute(
            """UPDATE runs SET state = ?, version = ?, updated_at = ?, ended_at = ?,
               role = COALESCE(?, role)
               WHERE run_id = ? AND version = ?""",
            (target_state, new_version, now, ended_at, role, run_id, expected_version),
        )

        if cur.rowcount == 0:
            raise VersionConflictError(run_id, expected_version, existing.version)

        self._conn.execute(
            """INSERT INTO transitions_log
               (run_id, from_state, to_state, reason, version, timestamp, role)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, existing.state, target_state, reason, new_version, now, role or existing.role),
        )
        self._conn.commit()

        return self.get_run(run_id)

    def list_runs(self, state: Optional[str] = None, limit: int = 100) -> list[RunRecord]:
        if state:
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE state = ? ORDER BY updated_at DESC LIMIT ?",
                (state, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    # ---- Checkpoint persistence ----

    def save_checkpoint(self, checkpoint: Checkpoint) -> Checkpoint:
        import json
        if checkpoint.created_at is None:
            checkpoint.created_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO checkpoints
               (run_id, root_run_id, parent_run_id, journal_offset,
                environment, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                checkpoint.run_id,
                checkpoint.root_run_id,
                checkpoint.parent_run_id,
                checkpoint.journal_offset,
                json.dumps(checkpoint.environment.to_dict()),
                checkpoint.created_at,
                json.dumps(checkpoint.metadata),
            ),
        )
        self._conn.commit()
        return checkpoint

    def get_checkpoint(self, run_id: str) -> Optional[Checkpoint]:
        import json
        row = self._conn.execute(
            "SELECT * FROM checkpoints WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            return None
        env = json.loads(row["environment"]) if row["environment"] else {}
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        return Checkpoint(
            run_id=row["run_id"],
            root_run_id=row["root_run_id"],
            parent_run_id=row["parent_run_id"],
            journal_offset=row["journal_offset"],
            environment=EnvironmentFingerprint(
                hostname=env.get("hostname", ""),
                os_name=env.get("os_name", ""),
                python_version=env.get("python_version", ""),
                branch=env.get("branch", ""),
                commit_sha=env.get("commit_sha", ""),
                key_hashes=env.get("key_hashes", {}),
                captured_at=env.get("captured_at", ""),
            ),
            created_at=row["created_at"],
            metadata=meta,
        )

    # ---- Write-scope arbitration ----

    def claim_write_scope(
        self,
        run_id: str,
        scope_paths: list[str],
        claim_id: Optional[str] = None,
    ) -> list["WriteScopeClaim"]:
        """Claim a set of write scopes on behalf of a run, atomically.

        All scopes are resolved first (same resolution as 004), then every held
        claim is checked for overlap. If ANY scope overlaps an existing held
        claim, the whole claim operation fails and nothing is persisted. On
        success the claims are committed in a single transaction.
        """
        import uuid

        from .write_scope import (
            WriteScopeClaim,
            ScopeConflictError,
            resolve_scope_path,
            paths_overlap,
        )

        resolved = [resolve_scope_path(p) for p in scope_paths]
        if not resolved:
            return []

        now = datetime.now(timezone.utc).isoformat()

        # Single transaction: check-then-insert is atomic, so two concurrent
        # claimers cannot both succeed on an overlapping scope.
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            held_rows = self._conn.execute(
                "SELECT claim_id, run_id, resolved_path FROM write_scope_claims "
                "WHERE released_at IS NULL"
            ).fetchall()

            for new_path in resolved:
                for row in held_rows:
                    if paths_overlap(new_path, row["resolved_path"]):
                        raise ScopeConflictError(run_id, row["run_id"], new_path)

            claims: list[WriteScopeClaim] = []
            for i, new_path in enumerate(resolved):
                if len(resolved) == 1 and claim_id:
                    cid = claim_id
                else:
                    cid = claim_id + "::" + str(i) if claim_id else str(uuid.uuid4())
                self._conn.execute(
                    "INSERT INTO write_scope_claims "
                    "(claim_id, run_id, resolved_path, created_at, released_at) "
                    "VALUES (?, ?, ?, ?, NULL)",
                    (cid, run_id, new_path, now),
                )
                claims.append(WriteScopeClaim(
                    claim_id=cid,
                    run_id=run_id,
                    resolved_path=new_path,
                    created_at=now,
                    released_at=None,
                ))

            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

        return claims

    def release_write_scope(self, claim_id: str) -> bool:
        """Release a held (claim_id, run_id) claim; idempotent.

        Returns True if a held claim was released, False if it was already
        released or did not exist.
        """
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "UPDATE write_scope_claims SET released_at = ? "
            "WHERE claim_id = ? AND released_at IS NULL",
            (now, claim_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def list_write_scope_claims(
        self,
        run_id: Optional[str] = None,
        include_released: bool = False,
    ) -> list["WriteScopeClaim"]:
        """List claims. By default only HELD claims and all runs."""
        from .write_scope import WriteScopeClaim

        if run_id is not None:
            rows = self._conn.execute(
                "SELECT * FROM write_scope_claims WHERE run_id = ? "
                + ("" if include_released else "AND released_at IS NULL"),
                (run_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM write_scope_claims "
                + ("" if include_released else "WHERE released_at IS NULL")
            ).fetchall()

        return [
            WriteScopeClaim(
                claim_id=r["claim_id"],
                run_id=r["run_id"],
                resolved_path=r["resolved_path"],
                created_at=r["created_at"],
                released_at=r["released_at"],
            )
            for r in rows
        ]

    def resolve_orphaned_claims(self) -> list[str]:
        """Release held claims whose owning run no longer exists.

        A claim is orphaned when its run_id does not appear in ``runs``. Returns
        the claim_ids that were forcibly released.
        """
        orphaned = self._conn.execute(
            "SELECT c.claim_id FROM write_scope_claims c "
            "LEFT JOIN runs r ON r.run_id = c.run_id "
            "WHERE c.released_at IS NULL AND r.run_id IS NULL"
        ).fetchall()
        claim_ids = [r["claim_id"] for r in orphaned]

        if claim_ids:
            now = datetime.now(timezone.utc).isoformat()
            self._conn.executemany(
                "UPDATE write_scope_claims SET released_at = ? WHERE claim_id = ?",
                [(now, cid) for cid in claim_ids],
            )
            self._conn.commit()
        return claim_ids

    # ---- Evidence persistence ----

    def save_evidence(self, receipt: ArtifactReceipt) -> ArtifactReceipt:
        import json
        if receipt.created_at is None:
            receipt.created_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO evidence
               (artifact_id, sha256, schema_version, producer_command,
                subject_repo, subject_commit, created_at, evidence_type, purpose,
                method, system_source, sensitivity, retention,
                transformation_history, quality, supersedes, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.artifact_id,
                receipt.sha256,
                receipt.schema_version,
                receipt.producer_command,
                receipt.subject_repo,
                receipt.subject_commit,
                receipt.created_at,
                receipt.evidence_type,
                receipt.purpose,
                receipt.method,
                receipt.system_source,
                receipt.sensitivity,
                receipt.retention,
                json.dumps(receipt.transformation_history),
                json.dumps(receipt.quality.to_dict()),
                receipt.supersedes,
                json.dumps(receipt.metadata),
            ),
        )
        self._conn.commit()
        return receipt

    def get_evidence(self, artifact_id: str) -> Optional[ArtifactReceipt]:
        import json
        row = self._conn.execute(
            "SELECT * FROM evidence WHERE artifact_id = ?", (artifact_id,)
        ).fetchone()
        if row is None:
            return None
        history = json.loads(row["transformation_history"]) if row["transformation_history"] else []
        quality = json.loads(row["quality"]) if row["quality"] else {}
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        return ArtifactReceipt(
            artifact_id=row["artifact_id"],
            sha256=row["sha256"],
            schema_version=row["schema_version"],
            producer_command=row["producer_command"],
            subject_repo=row["subject_repo"],
            subject_commit=row["subject_commit"],
            created_at=row["created_at"],
            evidence_type=row["evidence_type"],
            purpose=row["purpose"],
            method=row["method"],
            system_source=row["system_source"],
            sensitivity=row["sensitivity"],
            retention=row["retention"],
            transformation_history=history,
            quality=EvidenceQuality(
                relevance=quality.get("relevance", "medium"),
                sufficiency=quality.get("sufficiency", "medium"),
                reliability=quality.get("reliability", "medium"),
                currency=quality.get("currency", "medium"),
                integrity=quality.get("integrity", "medium"),
                independence=quality.get("independence", "medium"),
            ),
            supersedes=row["supersedes"],
            metadata=meta,
        )

    # ---- Handoff persistence ----

    def save_handoff(self, offer: HandoffOffer) -> HandoffOffer:
        import json
        if offer.offered_at is None:
            offer.offered_at = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO handoffs
               (handoff_id, from_role, to_role, scope, cold_start_bundle,
                allowed_actions, input_digests, state, owner, offered_at,
                accepted_at, completed_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                offer.handoff_id,
                offer.from_role,
                offer.to_role,
                offer.scope,
                json.dumps(offer.cold_start_bundle.to_dict()),
                json.dumps(offer.allowed_actions),
                json.dumps(offer.input_digests),
                offer.state,
                offer.owner,
                offer.offered_at,
                offer.accepted_at,
                offer.completed_at,
                json.dumps(offer.metadata),
            ),
        )
        self._conn.commit()
        return offer

    def get_handoff(self, handoff_id: str) -> Optional[HandoffOffer]:
        import json
        row = self._conn.execute(
            "SELECT * FROM handoffs WHERE handoff_id = ?", (handoff_id,)
        ).fetchone()
        if row is None:
            return None
        bundle = json.loads(row["cold_start_bundle"]) if row["cold_start_bundle"] else {}
        actions = json.loads(row["allowed_actions"]) if row["allowed_actions"] else []
        digests = json.loads(row["input_digests"]) if row["input_digests"] else {}
        meta = json.loads(row["metadata"]) if row["metadata"] else {}
        return HandoffOffer(
            handoff_id=row["handoff_id"],
            from_role=row["from_role"],
            to_role=row["to_role"],
            scope=row["scope"],
            cold_start_bundle=ColdStartBundle(
                prd_uri=bundle.get("prd_uri", ""),
                prd_digest=bundle.get("prd_digest", ""),
                chain_uri=bundle.get("chain_uri", ""),
                chain_digest=bundle.get("chain_digest", ""),
                repo_uri=bundle.get("repo_uri", ""),
                worktree_path=bundle.get("worktree_path", ""),
                branch=bundle.get("branch", ""),
                target_role=bundle.get("target_role", ""),
                sequence_id=bundle.get("sequence_id", ""),
            ),
            allowed_actions=actions,
            input_digests=digests,
            state=row["state"],
            owner=row["owner"],
            offered_at=row["offered_at"],
            accepted_at=row["accepted_at"],
            completed_at=row["completed_at"],
            metadata=meta,
        )

    def ensure_storage(self):
        pass

    def create_run(self, run_id: str, **kwargs) -> RunRecord:
        from datetime import datetime, timezone
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        record = RunRecord(
            run_id=run_id,
            root_run_id=run_id,
            parent_run_id=None,
            state="preflight",
            version=1,
            created_at=now,
            updated_at=now,
            ended_at=None,
            role="ops",
            metadata=kwargs,
        )
        return self.save_run(record)

    def close(self):
        self._conn.close()
