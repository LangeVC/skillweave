"""
Assumption tracking module for SkillWeave.

Extracts, categorizes, and tracks assumptions with risk scoring
and validation status. Persists to .skillweave/tracking-log/assumptions.yaml.
"""

import yaml
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


ASSUMPTION_CATEGORIES = ["user", "market", "technical", "value", "business", "adoption"]


@dataclass
class Assumption:
    id: str
    category: str
    description: str
    source: str = ""
    stated_as_fact: bool = False
    impact: int = 3
    probability: int = 3
    evidence_level: str = "none"
    certainty: str = "medium"
    status: str = "unvalidated"
    validation_method: str = ""
    validation_criterion: str = ""
    validated_date: Optional[str] = None
    notes: str = ""
    contingency: str = ""
    owner: str = ""

    @property
    def risk_score(self) -> int:
        return self.impact * self.probability

    @property
    def zone(self) -> str:
        score = self.risk_score
        if score >= 15:
            return "high"
        elif score >= 6:
            return "medium"
        return "low"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "description": self.description,
            "source": self.source,
            "stated_as_fact": self.stated_as_fact,
            "impact": self.impact,
            "probability": self.probability,
            "risk_score": self.risk_score,
            "zone": self.zone,
            "evidence_level": self.evidence_level,
            "certainty": self.certainty,
            "status": self.status,
            "validation_method": self.validation_method,
            "validation_criterion": self.validation_criterion,
            "validated_date": self.validated_date,
            "notes": self.notes,
            "contingency": self.contingency,
            "owner": self.owner,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Assumption":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AssumptionTracker:
    def __init__(self, project_root: Optional[str] = None):
        base = Path(project_root or Path.cwd())
        self.tracking_dir = base / ".skillweave" / "tracking-log"
        self.log_path = self.tracking_dir / "assumptions.yaml"
        self.assumptions: List[Assumption] = []
        self._load()

    def _load(self) -> None:
        if self.log_path.exists():
            with open(self.log_path) as f:
                data = yaml.safe_load(f) or {}
            raw = data.get("assumptions", [])
            self.assumptions = [Assumption.from_dict(a) for a in raw]
        else:
            self.assumptions = []

    def _save(self) -> None:
        self.tracking_dir.mkdir(parents=True, exist_ok=True)
        serialized = {"assumptions": [a.to_dict() for a in self.assumptions], "metadata": {"updated": datetime.now().isoformat(), "total": len(self.assumptions)}}
        with open(self.log_path, "w") as f:
            yaml.dump(serialized, f, default_flow_style=False, sort_keys=False)

    def extract_from_text(self, text: str, source: str = "manual") -> List[Assumption]:
        extracted = []
        patterns = {
            "assumption_markers": [
                r"assum(?:e|ing|ption)[^.]*",
                r"believe[^.]*",
                r"expect[^.]*",
                r"presume[^.]*",
                r"take[\s\w]*for granted[^.]*",
                r"likely[^.]*",
                r"(?:should|may|could|must|can)[^.]*",
                r"(?:will|would)[^.]*",
            ],
        }

        text_lower = text.lower()
        seen = set()
        counter = 1

        for marker in patterns["assumption_markers"]:
            matches = re.finditer(marker, text_lower)
            for match in matches:
                start = max(0, match.start() - 40)
                end = match.end()
                sentence = text[start:end].strip()
                sentence = sentence.split(".")[-1].strip() if "." in sentence else sentence
                if sentence in seen or len(sentence) < 10:
                    continue
                seen.add(sentence)
                category = self._infer_category(sentence)
                assumption = Assumption(
                    id=f"assumption-{counter:03d}",
                    category=category,
                    description=sentence.capitalize(),
                    source=source,
                    stated_as_fact="will" in sentence.lower() or "is" in sentence.lower(),
                    impact=3,
                    probability=3,
                    evidence_level="none",
                    certainty="medium",
                    validation_method=self._suggest_validation(category),
                )
                extracted.append(assumption)
                counter += 1

        self.assumptions.extend(extracted)
        self._save()
        return extracted

    def _infer_category(self, text: str) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in ["user", "persona", "customer", "audience"]):
            return "user"
        if any(w in text_lower for w in ["market", "marketplace", "industry", "competitor"]):
            return "market"
        if any(w in text_lower for w in ["technolog", "database", "api", "server", "system", "scalab"]):
            return "technical"
        if any(w in text_lower for w in ["pay", "pric", "revenue", "monetiz", "cost"]):
            return "value"
        if any(w in text_lower for w in ["team", "budget", "timeline", "resource", "deliver"]):
            return "business"
        if any(w in text_lower for w in ["adopt", "onboard", "growth", "viral", "retention"]):
            return "adoption"
        return "user"

    def _suggest_validation(self, category: str) -> str:
        methods = {
            "user": "User interview or survey",
            "market": "Market data analysis or competitor review",
            "technical": "Technical prototype or proof-of-concept",
            "value": "Pricing experiment or willingness-to-pay survey",
            "business": "Resource planning workshop or stakeholder review",
            "adoption": "Usability test or beta program",
        }
        return methods.get(category, "Validation experiment")

    def get_by_zone(self, zone: str) -> List[Assumption]:
        return [a for a in self.assumptions if a.zone == zone]

    def get_by_category(self, category: str) -> List[Assumption]:
        return [a for a in self.assumptions if a.category == category]

    def get_by_status(self, status: str) -> List[Assumption]:
        return [a for a in self.assumptions if a.status == status]

    def update_assumption(self, assumption_id: str, updates: Dict[str, Any]) -> Optional[Assumption]:
        for a in self.assumptions:
            if a.id == assumption_id:
                for key, value in updates.items():
                    if hasattr(a, key):
                        setattr(a, key, value)
                if "status" in updates and updates["status"] in ("validated", "invalidated"):
                    a.validated_date = datetime.now().strftime("%Y-%m-%d")
                self._save()
                return a
        return None

    def add(self, assumption: Assumption) -> None:
        self.assumptions.append(assumption)
        self._save()

    def summary(self) -> Dict[str, Any]:
        zones = {"high": 0, "medium": 0, "low": 0}
        statuses = {"unvalidated": 0, "validated": 0, "invalidated": 0, "in_progress": 0}
        categories = {c: 0 for c in ASSUMPTION_CATEGORIES}

        for a in self.assumptions:
            zones[a.zone] = zones.get(a.zone, 0) + 1
            statuses[a.status] = statuses.get(a.status, 0) + 1
            categories[a.category] = categories.get(a.category, 0) + 1

        return {
            "total": len(self.assumptions),
            "by_zone": zones,
            "by_status": statuses,
            "by_category": categories,
        }

    def clear(self) -> None:
        self.assumptions = []
        self._save()
