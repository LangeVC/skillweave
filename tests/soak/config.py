"""Soak test configuration and limit definitions (SW-SOAK-001).

Configures parameters for multi-hour soak tests, load thresholds, resource limits,
context limit profiles, recovery intervals, and degradation scenarios.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SoakLimits:
    """Measurable resource and operational limit boundaries."""

    max_rss_memory_mb: float = 250.0
    max_memory_growth_mb: float = 75.0
    max_leak_rate_mb_per_hour: float = 15.0
    max_open_files: int = 256
    max_error_rate_pct: float = 0.05
    min_throughput_ops_per_sec: float = 1.0
    max_p99_latency_ms: float = 2000.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_rss_memory_mb": self.max_rss_memory_mb,
            "max_memory_growth_mb": self.max_memory_growth_mb,
            "max_leak_rate_mb_per_hour": self.max_leak_rate_mb_per_hour,
            "max_open_files": self.max_open_files,
            "max_error_rate_pct": self.max_error_rate_pct,
            "min_throughput_ops_per_sec": self.min_throughput_ops_per_sec,
            "max_p99_latency_ms": self.max_p99_latency_ms,
        }


@dataclass
class SoakConfig:
    """Configuration for Soak, Load, Resource, and Degradation testing."""

    name: str = "skillweave-soak"
    duration_seconds: float = 5.0
    target_hours: Optional[float] = None
    iterations: int = 100
    concurrency: int = 4
    batch_size: int = 10
    limits: SoakLimits = field(default_factory=SoakLimits)
    context_profile: str = "standard"
    enable_chaos: bool = True
    chaos_interval_iterations: int = 15
    enable_degradation_testing: bool = True
    enable_recovery_testing: bool = True
    lock_file_path: Optional[str] = None
    sample_interval_seconds: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # If target_hours is specified, duration_seconds is computed from it
        if self.target_hours is not None and self.target_hours > 0:
            self.duration_seconds = self.target_hours * 3600.0

        # Allow environment overrides
        env_dur = os.environ.get("SKILLWEAVE_SOAK_DURATION")
        if env_dur is not None:
            try:
                self.duration_seconds = float(env_dur)
            except ValueError:
                pass

        env_hours = os.environ.get("SKILLWEAVE_SOAK_HOURS")
        if env_hours is not None:
            try:
                self.target_hours = float(env_hours)
                self.duration_seconds = self.target_hours * 3600.0
            except ValueError:
                pass

        env_iter = os.environ.get("SKILLWEAVE_SOAK_ITERATIONS")
        if env_iter is not None:
            try:
                self.iterations = int(env_iter)
            except ValueError:
                pass

        env_conc = os.environ.get("SKILLWEAVE_SOAK_CONCURRENCY")
        if env_conc is not None:
            try:
                self.concurrency = int(env_conc)
            except ValueError:
                pass

        env_mem = os.environ.get("SKILLWEAVE_SOAK_MAX_MEMORY_MB")
        if env_mem is not None:
            try:
                self.limits.max_rss_memory_mb = float(env_mem)
            except ValueError:
                pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "duration_seconds": self.duration_seconds,
            "target_hours": self.target_hours,
            "iterations": self.iterations,
            "concurrency": self.concurrency,
            "batch_size": self.batch_size,
            "limits": self.limits.to_dict(),
            "context_profile": self.context_profile,
            "enable_chaos": self.enable_chaos,
            "chaos_interval_iterations": self.chaos_interval_iterations,
            "enable_degradation_testing": self.enable_degradation_testing,
            "enable_recovery_testing": self.enable_recovery_testing,
            "lock_file_path": self.lock_file_path,
            "sample_interval_seconds": self.sample_interval_seconds,
            "metadata": dict(self.metadata),
        }
