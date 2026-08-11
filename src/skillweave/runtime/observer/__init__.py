from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Callable, Optional
from skillweave.runtime.journal import EventJournal, JournalEvent


class OutputType(str, Enum):
    SNAPSHOT = "snapshot"
    ALERT = "alert"
    DRIFT_FINDING = "drift_finding"
    RECOMMENDATION = "recommendation"


@dataclass
class ObserverOutput:
    output_type: str
    severity: str
    message: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evidence: dict[str, Any] = field(default_factory=dict)
    authority_verified: bool = False
    authorizing_clause: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        return {
            "output_type": self.output_type,
            "severity": self.severity,
            "message": self.message,
            "timestamp": self.timestamp,
            "evidence": self.evidence,
            "authority_verified": self.authority_verified,
            "authorizing_clause": self.authorizing_clause,
            "metadata": self.metadata,
        }


@dataclass
class ObserverState:
    offset: int = 0
    heartbeat_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    lease_id: Optional[str] = None
    outputs: list[ObserverOutput] = field(default_factory=list)

    def to_dict(self):
        return {
            "offset": self.offset,
            "heartbeat_at": self.heartbeat_at,
            "lease_id": self.lease_id,
            "outputs": [o.to_dict() for o in self.outputs],
        }


@dataclass
class ObserverLease:
    lease_id: str
    owner: str
    expires_at: str
    offset: int = 0

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc).isoformat() > self.expires_at


class Detector:
    def __init__(self, name: str, check_fn: Callable[[], list[ObserverOutput]]):
        self.name = name
        self._check = check_fn
        self.last_run: Optional[str] = None
        self.findings: list[dict] = []

    def run(self) -> list[ObserverOutput]:
        outputs = self._check()
        self.last_run = datetime.now(timezone.utc).isoformat()
        for o in outputs:
            self.findings.append(o.to_dict())
        return outputs


class ObserverRuntime:
    def __init__(self, journal: EventJournal, run_id: str):
        self._journal = journal
        self.run_id = run_id
        self._state = ObserverState()
        self._detectors: list[Detector] = []
        self._findings: list[dict[str, Any]] = []
        self._contradiction_log: list[dict[str, Any]] = []
        self._init_detectors()

    def _init_detectors(self):
        self._detectors.append(Detector(
            "mutual_wait",
            lambda: self._detect_mutual_wait(),
        ))
        self._detectors.append(Detector(
            "ops_sets_release",
            lambda: self._detect_ops_release(),
        ))

    def _detect_mutual_wait(self) -> list[ObserverOutput]:
        outputs = []
        events = self._journal.get_events(self.run_id, from_sequence=self._state.offset)
        block_events = [
            e for e in events
            if "BLOCKED" in e.payload.get("state", "")
        ]
        if len(block_events) >= 2:
            times = [datetime.fromisoformat(e.timestamp) for e in block_events]
            if times:
                delta = max(times) - min(times)
                if delta > timedelta(minutes=30):
                    outputs.append(ObserverOutput(
                        output_type=OutputType.ALERT.value,
                        severity="critical",
                        message=f"Mutual wait detected: {len(block_events)} blocked events over {delta}",
                        evidence={"blocked_event_count": len(block_events), "duration_minutes": delta.total_seconds() / 60},
                        authority_verified=False,
                    ))
        return outputs

    def _detect_ops_release(self) -> list[ObserverOutput]:
        return []

    def advance_offset(self, new_offset: int):
        self._state.offset = new_offset

    def heartbeat(self):
        self._state.heartbeat_at = datetime.now(timezone.utc).isoformat()

    def acquire_lease(self, owner: str, ttl_minutes: int = 60) -> ObserverLease:
        import uuid
        lease = ObserverLease(
            lease_id=str(uuid.uuid4())[:12],
            owner=owner,
            expires_at=(datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat(),
            offset=self._state.offset,
        )
        self._state.lease_id = lease.lease_id
        return lease

    def replay(self) -> list[ObserverOutput]:
        events = self._journal.get_events(self.run_id, from_sequence=0)
        outputs = []
        for detector in self._detectors:
            outputs.extend(detector.run())
        self._state.offset = len(events)
        return outputs

    def run_detectors(self) -> list[ObserverOutput]:
        outputs = []
        for detector in self._detectors:
            outputs.extend(detector.run())
        for o in outputs:
            self._findings.append(o.to_dict())
        return outputs

    def check_self_contradiction(self, new_recommendation: ObserverOutput) -> bool:
        open_findings = [
            f for f in self._findings
            if f.get("output_type") == OutputType.DRIFT_FINDING.value and not f.get("resolved", False)
        ]
        if not open_findings:
            return False

        for finding in open_findings:
            if new_recommendation.evidence.get("finding_id") == finding.get("finding_id"):
                alert = ObserverOutput(
                    output_type=OutputType.ALERT.value,
                    severity="critical",
                    message="Self-contradiction: new recommendation conflicts with open finding",
                    evidence={
                        "new_recommendation": new_recommendation.to_dict(),
                        "open_finding": finding,
                    },
                    authority_verified=False,
                )
                self._contradiction_log.append(alert.to_dict())
                return True
        return False

    def emit_snapshot(self, message: str, data: dict[str, Any]) -> ObserverOutput:
        output = ObserverOutput(
            output_type=OutputType.SNAPSHOT.value,
            severity="info",
            message=message,
            evidence=data,
        )
        self._state.outputs.append(output)
        return output

    def emit_alert(self, message: str, severity: str = "high", evidence: Optional[dict] = None) -> ObserverOutput:
        output = ObserverOutput(
            output_type=OutputType.ALERT.value,
            severity=severity,
            message=message,
            evidence=evidence or {},
        )
        self._state.outputs.append(output)
        return output

    def emit_recommendation(
        self,
        message: str,
        authorizing_clause: str,
        authority_verified: bool = False,
        evidence: Optional[dict] = None,
    ) -> ObserverOutput:
        output = ObserverOutput(
            output_type=OutputType.RECOMMENDATION.value,
            severity="info",
            message=message,
            authorizing_clause=authorizing_clause,
            authority_verified=authority_verified,
            evidence=evidence or {},
        )
        self._state.outputs.append(output)
        return output

    def state(self) -> ObserverState:
        return self._state

    def generate_report(self, format: str = "dict") -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "offset": self._state.offset,
            "outputs": [o.to_dict() for o in self._state.outputs],
            "detectors_run": len(self._detectors),
            "findings_count": len(self._findings),
        }

    def generate_markdown_report(self) -> str:
        lines = [
            f"# Observer Report: {self.run_id}",
            f"",
            f"**Offset:** {self._state.offset}",
            f"**Heartbeat:** {self._state.heartbeat_at}",
            f"**Outputs:** {len(self._state.outputs)}",
            f"**Findings:** {len(self._findings)}",
            f"",
            "## Outputs",
           "",
        ]
        for o in self._state.outputs:
            lines.append(f"- `[{o.output_type}/{o.severity}]` {o.message}")
        return "\n".join(lines)
