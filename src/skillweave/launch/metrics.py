import statistics
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


DEGRADATION_THRESHOLD_PCT = 5.0


@dataclass
class MetricSnapshot:
    response_time_ms: float
    error_rate: float
    requests_per_minute: float
    timestamp: str


def capture_metrics(endpoint: Optional[str] = None) -> MetricSnapshot:
    if endpoint:
        samples = []
        errors = 0
        for _ in range(5):
            start = time.monotonic()
            try:
                req = urllib.request.Request(endpoint, method="GET")
                resp = urllib.request.urlopen(req, timeout=10)
                elapsed = (time.monotonic() - start) * 1000
                samples.append(elapsed)
                if resp.status >= 500:
                    errors += 1
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
                elapsed = (time.monotonic() - start) * 1000
                samples.append(elapsed)
                errors += 1
            time.sleep(0.2)

        response_time_ms = statistics.mean(samples) if samples else 0.0
        error_rate = errors / len(samples) if samples else 1.0
    else:
        response_time_ms = 0.0
        error_rate = 0.0

    return MetricSnapshot(
        response_time_ms=round(response_time_ms, 2),
        error_rate=round(error_rate, 4),
        requests_per_minute=0.0,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def compare_metrics(pre: MetricSnapshot, post: MetricSnapshot) -> dict:
    def delta_pct(before: float, after: float) -> float:
        if before == 0:
            return 0.0
        return round(((after - before) / before) * 100, 2)

    rt_delta = delta_pct(pre.response_time_ms, post.response_time_ms)
    er_delta = delta_pct(pre.error_rate, post.error_rate)
    rpm_delta = delta_pct(pre.requests_per_minute, post.requests_per_minute)

    verdicts = []
    if abs(rt_delta) <= DEGRADATION_THRESHOLD_PCT:
        verdicts.append("stable")
    elif rt_delta > DEGRADATION_THRESHOLD_PCT:
        verdicts.append("degraded")
    else:
        verdicts.append("improved")

    if abs(er_delta) <= DEGRADATION_THRESHOLD_PCT:
        verdicts.append("stable")
    elif er_delta > DEGRADATION_THRESHOLD_PCT:
        verdicts.append("degraded")
    else:
        verdicts.append("improved")

    if abs(rpm_delta) <= DEGRADATION_THRESHOLD_PCT:
        verdicts.append("stable")
    elif rpm_delta < -DEGRADATION_THRESHOLD_PCT:
        verdicts.append("degraded")
    else:
        verdicts.append("improved")

    if "degraded" in verdicts:
        overall = "degraded"
    elif all(v == "improved" for v in verdicts):
        overall = "improved"
    else:
        overall = "stable"

    return {
        "deltas": {
            "response_time": {
                "before": pre.response_time_ms,
                "after": post.response_time_ms,
                "delta_pct": rt_delta,
            },
            "error_rate": {
                "before": pre.error_rate,
                "after": post.error_rate,
                "delta_pct": er_delta,
            },
            "requests_per_minute": {
                "before": pre.requests_per_minute,
                "after": post.requests_per_minute,
                "delta_pct": rpm_delta,
            },
        },
        "verdict": overall,
        "threshold_pct": DEGRADATION_THRESHOLD_PCT,
    }
