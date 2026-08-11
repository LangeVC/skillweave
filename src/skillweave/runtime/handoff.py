from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import json
import uuid


class HandoffState(str, Enum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    COMPLETED = "completed"


@dataclass
class ColdStartBundle:
    prd_uri: str
    prd_digest: str
    chain_uri: str
    chain_digest: str
    repo_uri: str
    worktree_path: str
    branch: str
    target_role: str
    sequence_id: str

    def to_dict(self):
        return {
            "prd_uri": self.prd_uri,
            "prd_digest": self.prd_digest,
            "chain_uri": self.chain_uri,
            "chain_digest": self.chain_digest,
            "repo_uri": self.repo_uri,
            "worktree_path": self.worktree_path,
            "branch": self.branch,
            "target_role": self.target_role,
            "sequence_id": self.sequence_id,
        }

    def validate_digests(self, prd_digest: str, chain_digest: str) -> list[str]:
        errors = []
        if self.prd_digest != prd_digest:
            errors.append(f"PRD digest mismatch: expected {self.prd_digest}, got {prd_digest}")
        if self.chain_digest != chain_digest:
            errors.append(f"Chain digest mismatch: expected {self.chain_digest}, got {chain_digest}")
        return errors


@dataclass
class HandoffOffer:
    handoff_id: str
    from_role: str
    to_role: str
    scope: str
    cold_start_bundle: ColdStartBundle
    allowed_actions: list[str]
    input_digests: dict[str, str] = field(default_factory=dict)
    state: str = HandoffState.OFFERED.value
    owner: Optional[str] = None
    offered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    accepted_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "handoff_id": self.handoff_id,
            "from_role": self.from_role,
            "to_role": self.to_role,
            "scope": self.scope,
            "cold_start_bundle": self.cold_start_bundle.to_dict(),
            "allowed_actions": self.allowed_actions,
            "input_digests": self.input_digests,
            "state": self.state,
            "owner": self.owner,
            "offered_at": self.offered_at,
            "accepted_at": self.accepted_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }


class HandoffError(Exception):
    def __init__(self, reason: str, code: str = "HANDOFF_ERROR", context: Optional[dict] = None):
        self.reason = reason
        self.code = code
        self.context = context or {}
        super().__init__(f"[{code}] {reason}")


class HandoffBroker:
    def __init__(self):
        self._offers: dict[str, HandoffOffer] = {}
        self._history: list[dict[str, Any]] = []

    def offer(
        self,
        from_role: str,
        to_role: str,
        scope: str,
        cold_start: ColdStartBundle,
        allowed_actions: Optional[list[str]] = None,
        input_digests: Optional[dict[str, str]] = None,
    ) -> HandoffOffer:
        handoff_id = str(uuid.uuid4())[:12]
        offer = HandoffOffer(
            handoff_id=handoff_id,
            from_role=from_role,
            to_role=to_role,
            scope=scope,
            cold_start_bundle=cold_start,
            allowed_actions=allowed_actions or [],
            input_digests=input_digests or {},
        )
        self._offers[handoff_id] = offer
        self._history.append({"action": "offer", "handoff_id": handoff_id, "to": to_role, "timestamp": offer.offered_at})
        return offer

    def accept(
        self,
        handoff_id: str,
        actor: str,
        product: str,
        repo: str,
        prd_digest: str,
        chain_digest: str,
    ) -> HandoffOffer:
        offer = self._offers.get(handoff_id)
        if offer is None:
            raise HandoffError(f"Handoff '{handoff_id}' not found", code="NOT_FOUND")

        if offer.state != HandoffState.OFFERED.value:
            raise HandoffError(
                f"Handoff '{handoff_id}' is in state '{offer.state}', not OFFERED",
                code="ALREADY_CLAIMED",
            )

        if actor != offer.to_role and actor not in (offer.from_role,):
            raise HandoffError(
                f"Actor '{actor}' is not the target role '{offer.to_role}'",
                code="WRONG_RECIPIENT",
            )

        bundle = offer.cold_start_bundle
        errors = bundle.validate_digests(prd_digest, chain_digest)
        if errors:
            raise HandoffError(
                "Digest validation failed",
                code="DIGEST_MISMATCH",
                context={"errors": errors},
            )

        if repo and bundle.repo_uri != repo:
            raise HandoffError(
                f"Wrong repo: expected '{bundle.repo_uri}', got '{repo}'",
                code="WRONG_REPO",
            )

        offer.state = HandoffState.ACCEPTED.value
        offer.owner = actor
        offer.accepted_at = datetime.now(timezone.utc).isoformat()
        self._history.append({"action": "accept", "handoff_id": handoff_id, "actor": actor, "timestamp": offer.accepted_at})
        return offer

    def reject(self, handoff_id: str, reason: str = "") -> HandoffOffer:
        offer = self._offers.get(handoff_id)
        if offer is None:
            raise HandoffError(f"Handoff '{handoff_id}' not found", code="NOT_FOUND")
        if offer.state != HandoffState.OFFERED.value:
            raise HandoffError(f"Handoff '{handoff_id}' is in state '{offer.state}', not OFFERED", code="ALREADY_CLAIMED")
        offer.state = HandoffState.REJECTED.value
        self._history.append({"action": "reject", "handoff_id": handoff_id, "reason": reason})
        return offer

    def complete(self, handoff_id: str) -> HandoffOffer:
        offer = self._offers.get(handoff_id)
        if offer is None:
            raise HandoffError(f"Handoff '{handoff_id}' not found", code="NOT_FOUND")
        if offer.state != HandoffState.ACCEPTED.value:
            raise HandoffError(f"Handoff '{handoff_id}' must be ACCEPTED to complete, is '{offer.state}'", code="WRONG_STATE")
        offer.state = HandoffState.COMPLETED.value
        offer.completed_at = datetime.now(timezone.utc).isoformat()
        self._history.append({"action": "complete", "handoff_id": handoff_id, "timestamp": offer.completed_at})
        return offer

    def get_offer(self, handoff_id: str) -> Optional[HandoffOffer]:
        return self._offers.get(handoff_id)

    def list_offers(self, state: Optional[str] = None) -> list[HandoffOffer]:
        if state:
            return [o for o in self._offers.values() if o.state == state]
        return list(self._offers.values())
