from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class ReconciliationResult:
    reconciled: bool
    evidence_weight: str
    observer_verdict: str
    authority_statement: str
    gate_name: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "reconciled": self.reconciled,
            "evidence_weight": self.evidence_weight,
            "observer_verdict": self.observer_verdict,
            "authority_statement": self.authority_statement,
            "gate_name": self.gate_name,
            "timestamp": self.timestamp,
        }


def reconcile_gate(
    gate_name: str,
    evidence_registry,
    observer_runtime,
    authority_guard,
) -> ReconciliationResult:
    counts = evidence_registry.count_by_type()
    total_evidence = sum(counts.values())
    findings = evidence_registry.get_findings()
    observer_outputs = observer_runtime.state().outputs

    if total_evidence < 3:
        return ReconciliationResult(
            reconciled=False,
            evidence_weight="insufficient",
            observer_verdict="neutral",
            authority_statement=f"Gate {gate_name}: insufficient evidence ({total_evidence} artifacts)",
            gate_name=gate_name,
        )

    has_alerts = any(o.output_type == "alert" for o in observer_outputs)
    has_critical_findings = any(f.severity == "critical" for f in findings)

    if has_critical_findings:
        evidence_weight = "high_evidence_blocked"
        reconciled = False
    elif has_alerts:
        evidence_weight = "medium_evidence_warning"
        reconciled = False
    else:
        evidence_weight = "sufficient"
        reconciled = True

    observer_verdict = "blocked" if not reconciled else "clear"

    has_ops_approval = False
    for o in observer_outputs:
        if o.output_type == "recommendation" and o.authority_verified:
            has_ops_approval = True

    authority_statement = (
        f"Gate {gate_name}: {evidence_weight}, observer={observer_verdict}, "
        f"authority={'verified' if has_ops_approval else 'pending'}"
    )

    return ReconciliationResult(
        reconciled=reconciled,
        evidence_weight=evidence_weight,
        observer_verdict=observer_verdict,
        authority_statement=authority_statement,
        gate_name=gate_name,
    )
