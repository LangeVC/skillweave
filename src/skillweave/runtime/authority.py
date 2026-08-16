from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class Role(str, Enum):
    OPS = "ops"
    REVIEWER = "reviewer"
    OBSERVER = "observer"
    OPERATOR = "operator"
    RELEASE_AUTHORITY = "release_authority"
    SUB_AGENT = "sub_agent"


@dataclass
class RoleAssignment:
    role: str
    actor_id: str
    scope: str
    valid_from: str
    valid_until: Optional[str]
    assigned_by: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "role": self.role,
            "actor_id": self.actor_id,
            "scope": self.scope,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "assigned_by": self.assigned_by,
            "metadata": self.metadata,
        }


@dataclass
class DelegationRecord:
    from_role: str
    to_role: str
    delegated_by: str
    accepted_by: Optional[str]
    state: str
    scope: str
    delegated_at: str
    accepted_at: Optional[str] = None
    returned_at: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "from_role": self.from_role,
            "to_role": self.to_role,
            "delegated_by": self.delegated_by,
            "accepted_by": self.accepted_by,
            "state": self.state,
            "scope": self.scope,
            "delegated_at": self.delegated_at,
            "accepted_at": self.accepted_at,
            "returned_at": self.returned_at,
            "metadata": self.metadata,
        }


@dataclass
class HumanApproval:
    actor: str
    timestamp: str
    scope: str
    policy_digest: str
    decision: str
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "actor": self.actor,
            "timestamp": self.timestamp,
            "scope": self.scope,
            "policy_digest": self.policy_digest,
            "decision": self.decision,
            "reason": self.reason,
            "metadata": self.metadata,
        }


ROLE_CAPABILITY_MATRIX = {
    Role.OPS.value: {
        "can_mutate_run_state": True,
        "can_approve_gate": False,
        "can_review_gate": False,
        "can_release": False,
        "can_tag": False,
        "can_delegate": True,
        "is_read_only": False,
        "forbidden_transitions": ["approve_own_gate", "merge", "release", "tag"],
    },
    Role.REVIEWER.value: {
        "can_mutate_run_state": False,
        "can_approve_gate": True,
        "can_review_gate": True,
        "can_release": False,
        "can_tag": False,
        "can_delegate": False,
        "is_read_only": False,
        "forbidden_transitions": ["release", "tag", "merge"],
    },
    Role.OBSERVER.value: {
        "can_mutate_run_state": False,
        "can_approve_gate": False,
        "can_review_gate": False,
        "can_release": False,
        "can_tag": False,
        "can_delegate": False,
        "is_read_only": True,
        "forbidden_transitions": ["write_run_state", "approve_gate", "release", "tag", "merge"],
    },
    Role.OPERATOR.value: {
        "can_mutate_run_state": False,
        "can_approve_gate": True,
        "can_review_gate": True,
        "can_release": True,
        "can_tag": True,
        "can_delegate": True,
        "is_read_only": False,
        "forbidden_transitions": [],
    },
    Role.RELEASE_AUTHORITY.value: {
        "can_mutate_run_state": False,
        "can_approve_gate": True,
        "can_review_gate": True,
        "can_release": True,
        "can_tag": True,
        "can_delegate": False,
        "is_read_only": False,
        "forbidden_transitions": [],
    },
}

ROLE_CAPABILITY_VERSION = "1.0.0"


def can_approve_gate(role: str) -> bool:
    caps = ROLE_CAPABILITY_MATRIX.get(role, {})
    return caps.get("can_approve_gate", False)


def can_mutate_run_state(role: str) -> bool:
    caps = ROLE_CAPABILITY_MATRIX.get(role, {})
    return caps.get("can_mutate_run_state", False)


def is_read_only(role: str) -> bool:
    caps = ROLE_CAPABILITY_MATRIX.get(role, {})
    return caps.get("is_read_only", False)


def get_forbidden_transitions(role: str) -> list[str]:
    caps = ROLE_CAPABILITY_MATRIX.get(role, {})
    return list(caps.get("forbidden_transitions", []))


class AuthorityError(Exception):
    def __init__(self, role: str, action: str, reason: str, extra: Optional[dict] = None):
        self.role = role
        self.action = action
        self.reason = reason
        self.extra = extra or {}
        super().__init__(f"Role '{role}' cannot {action}: {reason}")


class AuthorityGuard:
    def __init__(self):
        self._assignments: list[RoleAssignment] = []
        self._delegations: list[DelegationRecord] = []
        self._capability_matrix = ROLE_CAPABILITY_MATRIX.copy()

    def get_capabilities(self, role: str) -> dict[str, Any]:
        return self._capability_matrix.get(role, {})

    def get_capability_version(self) -> str:
        return ROLE_CAPABILITY_VERSION

    def assign_role(self, assignment: RoleAssignment) -> RoleAssignment:
        self._assignments.append(assignment)
        return assignment

    def get_assignments(self, actor_id: Optional[str] = None) -> list[RoleAssignment]:
        if actor_id:
            return [a for a in self._assignments if a.actor_id == actor_id]
        return list(self._assignments)

    def delegate(self, record: DelegationRecord) -> DelegationRecord:
        source_role = record.from_role
        if not self._capability_matrix.get(source_role, {}).get("can_delegate", False):
            raise AuthorityError(
                source_role, "delegate",
                f"Role '{source_role}' is not authorized to delegate",
            )
        self._delegations.append(record)
        return record

    def accept_delegation(self, record: DelegationRecord) -> DelegationRecord:
        record.state = "accepted"
        record.accepted_at = datetime.now(timezone.utc).isoformat()
        return record

    def return_delegation(self, record: DelegationRecord) -> DelegationRecord:
        record.state = "returned"
        record.returned_at = datetime.now(timezone.utc).isoformat()
        return record

    def can_perform(self, role: str, action: str) -> bool:
        caps = self._capability_matrix.get(role, {})
        if caps.get("is_read_only", False):
            if action in ("approve_gate", "mutate_run_state", "tag", "release", "merge"):
                return False
        if action == "approve_gate":
            return caps.get("can_approve_gate", False)
        if action == "review_gate":
            return caps.get("can_review_gate", False)
        if action == "mutate_run_state":
            return caps.get("can_mutate_run_state", False)
        if action == "tag":
            return caps.get("can_tag", False)
        if action == "release":
            return caps.get("can_release", False)
        if action == "delegate":
            return caps.get("can_delegate", False)
        return False

    def approve(
        self,
        actor: str,
        role: str,
        scope: str,
        policy_digest: str,
        decision: str = "approved",
        reason: str = "",
    ) -> HumanApproval:
        action_map = {
            "approved": "approve_gate",
            "rejected": "review_gate",
        }
        action = action_map.get(decision, "review_gate")
        if not self.can_perform(role, action):
            raise AuthorityError(role, action, f"Role '{role}' lacks authority for '{decision}' on '{scope}'")

        return HumanApproval(
            actor=actor,
            timestamp=datetime.now(timezone.utc).isoformat(),
            scope=scope,
            policy_digest=policy_digest,
            decision=decision,
            reason=reason,
        )

    def validate_approval(self, approval: HumanApproval, approving_role: str) -> bool:
        if approving_role == Role.OPS.value:
            raise AuthorityError(
                approving_role, "approve_gate",
                "Ops role cannot approve gates — separation of duties violated",
                {"scope": approval.scope, "actor": approval.actor},
            )
        return self.can_perform(approving_role, "approve_gate")
