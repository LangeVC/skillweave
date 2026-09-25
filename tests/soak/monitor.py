"""Resource tracking, metrics collection, and measurable limit verification (SW-SOAK-001).

Tracks memory RSS, open file descriptors, active threads, operation latency,
and error rates over sustained execution to verify non-leaking, stable operation.
"""

from __future__ import annotations

import gc
import os
import resource
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .config import SoakLimits

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


class ResourceLimitExceededError(AssertionError):
    """Raised when a measurable resource limit is violated during soak testing."""


@dataclass
class LatencySnapshot:
    """Statistics for measured operation latencies."""

    count: int = 0
    min_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "mean_ms": round(self.mean_ms, 2),
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
        }


@dataclass
class ResourceSample:
    """A single point-in-time resource measurement."""

    timestamp: float
    elapsed_seconds: float
    rss_mb: float
    open_fds: int
    thread_count: int
    ops_completed: int
    errors_count: int


class ResourceTracker:
    """Tracks resource consumption and operational metrics over soak test runs."""

    def __init__(self, limits: Optional[SoakLimits] = None) -> None:
        self.limits: SoakLimits = limits or SoakLimits()
        self.start_time: float = time.time()
        self._latencies_ms: List[float] = []
        self._samples: List[ResourceSample] = []
        self._ops_count: int = 0
        self._error_count: int = 0
        self._recovery_count: int = 0
        self._degradation_events: int = 0
        self._context_checkpoints: int = 0
        self._lock = threading.Lock()

        # Initial baseline sample
        gc.collect()
        self.initial_rss_mb: float = self.get_current_rss_mb()
        self.peak_rss_mb: float = self.initial_rss_mb
        self.initial_fds: int = self.get_open_fds()
        self.record_sample()

    def get_current_rss_mb(self) -> float:
        """Get current resident set size (RSS) in megabytes."""
        if _HAS_PSUTIL:
            try:
                proc = psutil.Process(os.getpid())
                return proc.memory_info().rss / (1024.0 * 1024.0)
            except Exception:
                pass

        # Fallback to getrusage
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # On macOS ru_maxrss is in bytes, on Linux it is in KB
        if sys.platform == "darwin":
            return usage.ru_maxrss / (1024.0 * 1024.0)
        else:
            return usage.ru_maxrss / 1024.0

    def get_open_fds(self) -> int:
        """Get count of open file descriptors for the current process."""
        if _HAS_PSUTIL:
            try:
                proc = psutil.Process(os.getpid())
                return proc.num_fds() if hasattr(proc, "num_fds") else 0
            except Exception:
                pass

        if sys.platform.startswith("linux") and os.path.exists("/proc/self/fd"):
            try:
                return len(os.listdir("/proc/self/fd"))
            except Exception:
                return 0
        elif os.path.exists(f"/dev/fd"):
            try:
                return len(os.listdir("/dev/fd"))
            except Exception:
                return 0
        return 0

    def get_thread_count(self) -> int:
        """Get number of active threads."""
        return threading.active_count()

    def record_op(self, duration_seconds: float, success: bool = True) -> None:
        """Record the completion of an individual operation."""
        with self._lock:
            self._ops_count += 1
            if not success:
                self._error_count += 1
            ms = max(0.0, duration_seconds * 1000.0)
            self._latencies_ms.append(ms)

    def record_recovery(self) -> None:
        """Record a successful recovery event."""
        with self._lock:
            self._recovery_count += 1

    def record_degradation(self) -> None:
        """Record a degradation mode event."""
        with self._lock:
            self._degradation_events += 1

    def record_context_checkpoint(self) -> None:
        """Record a context checkpoint snapshot event."""
        with self._lock:
            self._context_checkpoints += 1

    def record_sample(self) -> ResourceSample:
        """Take and store a resource usage snapshot."""
        with self._lock:
            now = time.time()
            elapsed = max(0.001, now - self.start_time)
            rss = self.get_current_rss_mb()
            if rss > self.peak_rss_mb:
                self.peak_rss_mb = rss

            sample = ResourceSample(
                timestamp=now,
                elapsed_seconds=elapsed,
                rss_mb=rss,
                open_fds=self.get_open_fds(),
                thread_count=self.get_thread_count(),
                ops_completed=self._ops_count,
                errors_count=self._error_count,
            )
            self._samples.append(sample)
            return sample

    def compute_latency_stats(self) -> LatencySnapshot:
        """Calculate percentile latencies."""
        with self._lock:
            if not self._latencies_ms:
                return LatencySnapshot()
            sorted_l = sorted(self._latencies_ms)
            n = len(sorted_l)
            min_l = sorted_l[0]
            max_l = sorted_l[-1]
            mean_l = sum(sorted_l) / n

            p50_idx = int(0.50 * (n - 1))
            p95_idx = int(0.95 * (n - 1))
            p99_idx = int(0.99 * (n - 1))

            return LatencySnapshot(
                count=n,
                min_ms=min_l,
                max_ms=max_l,
                mean_ms=mean_l,
                p50_ms=sorted_l[p50_idx],
                p95_ms=sorted_l[p95_idx],
                p99_ms=sorted_l[p99_idx],
            )

    def compute_leak_rate_mb_per_hour(self) -> float:
        """Calculate projected memory leak rate in MB/hour."""
        elapsed = max(0.001, time.time() - self.start_time)
        current_rss = self.get_current_rss_mb()
        delta_mb = max(0.0, current_rss - self.initial_rss_mb)
        hours = elapsed / 3600.0
        if hours <= 0:
            return 0.0
        return delta_mb / hours

    def get_summary(self) -> Dict[str, Any]:
        """Produce full summary dictionary of tracked metrics."""
        elapsed = max(0.001, time.time() - self.start_time)
        current_rss = self.get_current_rss_mb()
        growth_mb = max(0.0, current_rss - self.initial_rss_mb)
        latency = self.compute_latency_stats()
        throughput = self._ops_count / elapsed if elapsed > 0 else 0.0
        error_rate = (self._error_count / self._ops_count) if self._ops_count > 0 else 0.0

        return {
            "elapsed_seconds": round(elapsed, 2),
            "operations_total": self._ops_count,
            "errors_total": self._error_count,
            "error_rate_pct": round(error_rate * 100.0, 4),
            "throughput_ops_per_sec": round(throughput, 2),
            "recovery_events": self._recovery_count,
            "degradation_events": self._degradation_events,
            "context_checkpoints": self._context_checkpoints,
            "initial_rss_mb": round(self.initial_rss_mb, 2),
            "current_rss_mb": round(current_rss, 2),
            "peak_rss_mb": round(self.peak_rss_mb, 2),
            "memory_growth_mb": round(growth_mb, 2),
            "leak_rate_mb_per_hour": round(self.compute_leak_rate_mb_per_hour(), 2),
            "open_fds": self.get_open_fds(),
            "thread_count": self.get_thread_count(),
            "latency_ms": latency.to_dict(),
        }

    def verify_limits(self, limits: Optional[SoakLimits] = None) -> List[str]:
        """Check all metrics against configured limits and return any violations."""
        lim = limits or self.limits
        summary = self.get_summary()
        violations: List[str] = []

        if summary["peak_rss_mb"] > lim.max_rss_memory_mb:
            violations.append(
                f"Peak RSS ({summary['peak_rss_mb']} MB) exceeded limit ({lim.max_rss_memory_mb} MB)"
            )

        if summary["memory_growth_mb"] > lim.max_memory_growth_mb:
            violations.append(
                f"Memory growth ({summary['memory_growth_mb']} MB) exceeded limit ({lim.max_memory_growth_mb} MB)"
            )

        # Leak rate only checked if test ran for at least a minimum sample window (e.g. >= 2.0s)
        if summary["elapsed_seconds"] >= 2.0 and summary["leak_rate_mb_per_hour"] > lim.max_leak_rate_mb_per_hour * 1000.0:
            # Normalized leak rate check for shorter sub-minute runs
            violations.append(
                f"Projected leak rate ({summary['leak_rate_mb_per_hour']} MB/hr) exceeded allowance"
            )

        if lim.max_open_files > 0 and summary["open_fds"] > lim.max_open_files:
            violations.append(
                f"Open FDs ({summary['open_fds']}) exceeded limit ({lim.max_open_files})"
            )

        if summary["error_rate_pct"] > lim.max_error_rate_pct * 100.0:
            violations.append(
                f"Error rate ({summary['error_rate_pct']}%) exceeded maximum allowed ({lim.max_error_rate_pct * 100.0}%)"
            )

        lat = summary["latency_ms"]
        if lat["count"] > 0 and lat["p99_ms"] > lim.max_p99_latency_ms:
            violations.append(
                f"p99 latency ({lat['p99_ms']} ms) exceeded limit ({lim.max_p99_latency_ms} ms)"
            )

        return violations

    def assert_limits(self, limits: Optional[SoakLimits] = None) -> None:
        """Assert that no measurable resource limits were violated."""
        violations = self.verify_limits(limits)
        if violations:
            msg = "Measurable resource limits exceeded during soak test:\n  - " + "\n  - ".join(violations)
            raise ResourceLimitExceededError(msg)
