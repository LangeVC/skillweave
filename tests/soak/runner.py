"""Standalone CLI runner for multi-hour SkillWeave Soak & Langlauf testing (SW-SOAK-001).

Usage:
    python -m tests.soak.runner --duration 10 --iterations 500
    python -m tests.soak.runner --hours 2 --profile standard --max-memory-mb 300
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from tests.soak.config import SoakConfig, SoakLimits
from tests.soak.engine import SoakEngine, SoakReport
from tests.soak.guard import DoubleStartPreventedError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SkillWeave Multi-Hour Soak & Langlauf Test Runner")
    parser.add_argument("--name", type=str, default="skillweave-langlauf-soak", help="Test run identifier")
    parser.add_argument("--duration", type=float, default=5.0, help="Test duration in seconds (overridden by --hours)")
    parser.add_argument("--hours", type=float, default=None, help="Target duration in hours for multi-hour soak")
    parser.add_argument("--iterations", type=int, default=200, help="Maximum number of operations to execute")
    parser.add_argument("--concurrency", type=int, default=4, help="Worker concurrency limit")
    parser.add_argument("--profile", type=str, default="standard", help="Context token limit profile (standard/strict/fast/extended)")
    parser.add_argument("--max-memory-mb", type=float, default=250.0, help="Max allowed RSS memory in MB")
    parser.add_argument("--max-growth-mb", type=float, default=75.0, help="Max allowed memory growth in MB")
    parser.add_argument("--output-json", type=str, default=None, help="Path to write JSON summary report")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    limits = SoakLimits(
        max_rss_memory_mb=args.max_memory_mb,
        max_memory_growth_mb=args.max_growth_mb,
    )

    config = SoakConfig(
        name=args.name,
        duration_seconds=args.duration,
        target_hours=args.hours,
        iterations=args.iterations,
        concurrency=args.concurrency,
        context_profile=args.profile,
        limits=limits,
    )

    print("=" * 70)
    print(f"SKILLWEAVE SOAK & LANGLAUF TEST RUNNER (SW-SOAK-001)")
    print(f"Target Duration: {config.duration_seconds:.1f}s ({config.duration_seconds/3600.0:.2f} hours)")
    print(f"Max Iterations:  {config.iterations}")
    print(f"Context Profile: {config.context_profile}")
    print(f"Max Memory Limit: {limits.max_rss_memory_mb:.1f} MB")
    print("=" * 70)

    try:
        engine = SoakEngine(config)
        report: SoakReport = engine.run()
    except DoubleStartPreventedError as dse:
        print(f"\n❌ FAILED TO START: {dse}")
        return 1
    except Exception as exc:
        print(f"\n❌ UNHANDLED ERROR DURING SOAK RUN: {exc}")
        return 1

    print("\n" + "=" * 70)
    print("SOAK TEST RESULTS SUMMARY")
    print("=" * 70)
    print(f"Status:               {'✅ PASSED' if report.success else '❌ FAILED'}")
    print(f"Duration:             {report.duration_seconds:.2f} seconds")
    print(f"Iterations Completed: {report.iterations_completed}/{report.target_iterations}")
    print(f"Initial RSS Memory:   {report.summary_metrics['initial_rss_mb']} MB")
    print(f"Peak RSS Memory:      {report.summary_metrics['peak_rss_mb']} MB")
    print(f"Memory Growth:        {report.summary_metrics['memory_growth_mb']} MB")
    print(f"Throughput:           {report.summary_metrics['throughput_ops_per_sec']} ops/sec")
    print(f"p95 Latency:          {report.summary_metrics['latency_ms']['p95_ms']} ms")
    print(f"Recovery Events:      {report.recovery_events_verified} verified")
    print(f"Context Limit Events: {report.context_limits_verified} verified")
    print(f"Degradation Events:   {report.degradation_events_verified} verified")
    print(f"Double-Start Guard:   {'✅ Verified' if report.double_start_prevented_verified else '❌ Not Verified'}")

    if report.limit_violations:
        print("\n❌ LIMIT VIOLATIONS DETECTED:")
        for v in report.limit_violations:
            print(f"  - {v}")

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report.to_json())
        print(f"\nWrote JSON report to: {out_path.resolve()}")

    return 0 if report.success else 1


if __name__ == "__main__":
    sys.exit(main())
