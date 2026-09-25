from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime

class ProvenanceType(Enum):
    DECLARED = "declared"
    DETECTED = "detected"
    PROCESS_ATTESTED = "process-attested"

@dataclass
class ProvenanceClaim:
    claim_type: ProvenanceType
    source: str
    value: Any
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ProvenanceContradiction:
    attribute: str
    declared_value: Any
    actual_value: Any
    actual_type: ProvenanceType
    description: str

class HarnessProvenance:
    def __init__(self, harness_id: str):
        self.harness_id = harness_id
        # Store claims by attribute (e.g., "environment", "version", "author")
        self._claims: Dict[str, List[ProvenanceClaim]] = {}
        
    def add_claim(self, attribute: str, claim_type: ProvenanceType, source: str, value: Any, metadata: Optional[Dict[str, Any]] = None):
        if attribute not in self._claims:
            self._claims[attribute] = []
            
        claim = ProvenanceClaim(
            claim_type=claim_type,
            source=source,
            value=value,
            metadata=metadata or {}
        )
        self._claims[attribute].append(claim)
        
    def declare(self, attribute: str, source: str, value: Any, metadata: Optional[Dict[str, Any]] = None):
        """Add a declared provenance claim (what the user or system claims)."""
        self.add_claim(attribute, ProvenanceType.DECLARED, source, value, metadata)
        
    def detect(self, attribute: str, source: str, value: Any, metadata: Optional[Dict[str, Any]] = None):
        """Add a detected provenance claim (what the system observes/infers)."""
        self.add_claim(attribute, ProvenanceType.DETECTED, source, value, metadata)
        
    def attest(self, attribute: str, source: str, value: Any, metadata: Optional[Dict[str, Any]] = None):
        """Add a process-attested provenance claim (what the system provably asserts via a process)."""
        self.add_claim(attribute, ProvenanceType.PROCESS_ATTESTED, source, value, metadata)
        
    def get_claims(self, attribute: str) -> List[ProvenanceClaim]:
        return self._claims.get(attribute, [])
        
    def analyze_contradictions(self) -> List[ProvenanceContradiction]:
        """
        Analyzes claims and finds contradictions where declared values
        differ from detected or process-attested values.
        Intentionally false declarations remain visible here as contradictions,
        fulfilling the requirement to retain false declarations but expose them.
        """
        contradictions = []
        for attribute, claims in self._claims.items():
            # Find the most recent declared claim
            declared = None
            for claim in claims:
                if claim.claim_type == ProvenanceType.DECLARED:
                    declared = claim
                    break
            
            if not declared:
                continue
                
            # Compare other claims against the declared claim
            for claim in claims:
                if claim.claim_type in (ProvenanceType.DETECTED, ProvenanceType.PROCESS_ATTESTED):
                    if claim.value != declared.value:
                        contradictions.append(ProvenanceContradiction(
                            attribute=attribute,
                            declared_value=declared.value,
                            actual_value=claim.value,
                            actual_type=claim.claim_type,
                            description=f"Contradiction on '{attribute}': declared '{declared.value}' but {claim.claim_type.value} '{claim.value}' from {claim.source}."
                        ))
        return contradictions

    def summarize(self) -> Dict[str, Any]:
        """
        Returns a summary of the provenance including contradictions.
        """
        return {
            "harness_id": self.harness_id,
            "claims": {
                attr: [
                    {
                        "type": c.claim_type.value,
                        "source": c.source,
                        "value": c.value,
                        "timestamp": c.timestamp.isoformat()
                    } for c in claims
                ] for attr, claims in self._claims.items()
            },
            "contradictions": [
                {
                    "attribute": c.attribute,
                    "declared_value": c.declared_value,
                    "actual_value": c.actual_value,
                    "actual_type": c.actual_type.value,
                    "description": c.description
                } for c in self.analyze_contradictions()
            ]
        }
