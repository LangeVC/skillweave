"""Integrated Langlauf & Soak Test (SW-SOAK-001).

Comprehensive multi-phase soak test orchestrating load, resource bounds, context limits,
zero-transcript crash recovery, degradation resilience, and double-start exclusion.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
import pytest

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from tests.soak.config import SoakConfig, SoakLimits
from tests.soak.engine import SoakEngine, SoakReport
from tests.soak.guard import DoubleStartGuard, DoubleStartPreventedError


class TestSoakLanglauf:
    """Integrated Langlauf and multi-hour soak test suite."""

    def test_full_langlauf_pipeline_execution(self):
        """Run complete Langlauf soak engine pipeline with measurable limits verification."""
        config = SoakConfig(
            name="langlauf-full-test",
            duration_seconds=3.0,
            iterations=150,
            concurrency=4,
            enable_chaos=True,
            chaos_interval_iterations=10,
            enable_degradation_testing=True,
            enable_recovery_testing=True,
            limits=SoakLimits(
                max_rss_memory_mb=350.0,
                max_memory_growth_mb=60.0,
                max_error_rate_pct=0.01,
            ),
        )

        engine = SoakEngine(config)
        report: SoakReport = engine.run()

        # Assertions on soak report
        assert report.success is True, f"Soak test failed with limit violations: {report.limit_violations}"
        assert report.iterations_completed > 0
        assert report.duration_seconds > 0
        assert report.recovery_events_verified > 0
        assert report.context_limits_verified > 0
        assert report.degradation_events_verified > 0
        assert report.double_start_prevented_verified is True
        assert len(report.limit_violations) == 0

        # Assert metrics structure
        metrics = report.summary_metrics
        assert metrics["operations_total"] == report.iterations_completed
        assert metrics["errors_total"] == 0
        assert metrics["memory_growth_mb"] < config.limits.max_memory_growth_mb

    def test_double_start_protection_during_active_langlauf(self):
        """Verify that launching a secondary Langlauf test while one is running is strictly rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = os.path.join(tmp, "langlauf_active.lock")
            primary_config = SoakConfig(
                name="langlauf-primary",
                duration_seconds=1.0,
                iterations=50,
                lock_file_path=lock_path,
            )
            competing_config = SoakConfig(
                name="langlauf-competing",
                duration_seconds=1.0,
                iterations=50,
                lock_file_path=lock_path,
            )

            # Hold primary lock
            with DoubleStartGuard(lock_path=lock_path, tag="primary"):
                # Competing engine must raise DoubleStartPreventedError
                competing_engine = SoakEngine(competing_config)
                with pytest.raises(DoubleStartPreventedError):
                    competing_engine.run()
