"""
Ideation module with divergent thinking for SkillWeave.

Enforces quantity-first generation, deferred judgment, and wild idea inclusion.
Configurable via lens settings.
"""

import random
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class IdeationMode(str, Enum):
    GENERATE = "generate"
    EVALUATE = "evaluate"
    EXPAND = "expand"


@dataclass
class IdeationOption:
    id: str
    title: str
    description: str
    rationale: str
    is_wild: bool = False
    evaluation: Optional[Dict[str, Any]] = None
    parent_id: Optional[str] = None


@dataclass
class IdeationConfig:
    min_options: int = 5
    require_wild: bool = True
    require_rationale: bool = True
    separate_evaluation: bool = True
    max_options: int = 20

    @classmethod
    def from_lens_config(cls, config: Optional[Dict[str, Any]] = None) -> "IdeationConfig":
        if not config:
            return cls()
        return cls(
            min_options=config.get("min_options", 5),
            require_wild=config.get("require_wild", True),
            require_rationale=config.get("require_rationale", True),
            separate_evaluation=config.get("separate_evaluation", True),
            max_options=config.get("max_options", 20),
        )


class IdeationSession:
    def __init__(self, config: Optional[IdeationConfig] = None):
        self.config = config or IdeationConfig()
        self.options: List[IdeationOption] = []
        self.mode: IdeationMode = IdeationMode.GENERATE
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"opt-{self._counter:04d}"

    def generate(self, problem: str, provider: Optional[Callable] = None) -> List[IdeationOption]:
        if self.mode == IdeationMode.EVALUATE:
            raise ValueError("Cannot generate in EVALUATE mode. Call reset() first.")

        if provider:
            raw_options = provider(problem, self.config)
        else:
            raw_options = self._default_generate(problem)

        self.options = []
        for raw in raw_options:
            option = IdeationOption(
                id=self._next_id(),
                title=raw.get("title", "Untitled"),
                description=raw.get("description", ""),
                rationale=raw.get("rationale", ""),
                is_wild=raw.get("is_wild", False),
            )
            self.options.append(option)

        if self.config.require_wild:
            has_wild = any(o.is_wild for o in self.options)
            if not has_wild and self.options:
                self.options[-1].is_wild = True
                self.options[-1].title = f"[WILD] {self.options[-1].title}"

        return self.options

    def _default_generate(self, problem: str) -> List[Dict[str, Any]]:
        target = max(self.config.min_options, 5)
        templates = [
            {"title": "Direct Approach", "description": f"Solve {problem} head-on with a focused tool.", "rationale": "Most straightforward path; lowest complexity."},
            {"title": "Platform Play", "description": f"Build a platform that enables others to solve {problem}.", "rationale": "Scales through ecosystem effects; higher initial investment."},
            {"title": "Integration-First", "description": f"Integrate with existing tools to solve {problem} where users already work.", "rationale": "Leverages existing user behavior; lower adoption barrier."},
            {"title": "Simplification Engine", "description": f"Abstract away complexity so {problem} becomes a one-click operation.", "rationale": "Removes friction for non-expert users."},
            {"title": "Community-Powered", "description": f"Let the community solve {problem} through shared patterns and templates.", "rationale": "Self-sustaining over time; quality depends on contribution."},
        ]
        wild = {"title": "[WILD] Reverse the Frame", "description": f"Instead of solving {problem}, make the problem irrelevant by changing the paradigm.", "rationale": "Radical reframing opens new solution spaces.", "is_wild": True}
        result = templates[:target]
        if target > len(templates):
            result.extend([templates[i % len(templates)] for _ in range(target - len(templates))])
        if self.config.require_wild:
            result.append(wild)
        return result[:target + (1 if self.config.require_wild else 0)]

    def evaluate(self, criteria: Optional[Dict[str, float]] = None) -> List[IdeationOption]:
        if not self.options:
            raise ValueError("No options to evaluate. Run generate() first.")

        self.mode = IdeationMode.EVALUATE
        default_criteria = criteria or {
            "feasibility": 0.3,
            "impact": 0.3,
            "novelty": 0.2,
            "effort": 0.2,
        }

        for option in self.options:
            scores = {}
            total_weight = sum(default_criteria.values())
            for criterion, weight in default_criteria.items():
                base = random.uniform(3.0, 9.0)
                if option.is_wild and criterion == "novelty":
                    base = random.uniform(7.0, 10.0)
                elif option.is_wild and criterion == "feasibility":
                    base = random.uniform(1.0, 4.0)
                scores[criterion] = round(base, 1)

            weighted = sum(scores[c] * default_criteria[c] for c in default_criteria) / total_weight
            option.evaluation = {
                "scores": scores,
                "weighted_score": round(weighted, 2),
                "criteria_weights": default_criteria,
            }

        self.options.sort(key=lambda o: o.evaluation["weighted_score"] if o.evaluation else 0, reverse=True)
        return self.options

    def expand(self, option_id: str, provider: Optional[Callable] = None) -> List[IdeationOption]:
        self.mode = IdeationMode.EXPAND
        parent = next((o for o in self.options if o.id == option_id), None)
        if not parent:
            raise ValueError(f"Option {option_id} not found.")

        expansions = []
        for i in range(3):
            self._counter += 1
            child = IdeationOption(
                id=self._next_id(),
                title=f"{parent.title} — Variation {i+1}",
                description=f"A variation on {parent.title}: refined approach to address specific sub-concerns.",
                rationale="Builds on prior idea with specific refinement direction.",
                parent_id=parent.id,
            )
            expansions.append(child)

        self.options.extend(expansions)
        return expansions

    def reset(self) -> None:
        self.options = []
        self.mode = IdeationMode.GENERATE
        self._counter = 0
