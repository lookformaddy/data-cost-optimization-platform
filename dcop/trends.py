"""Trend reporting: daily spend, unit economics, anomaly detection.

Anomalies are flagged with a rolling z-score: a day whose spend is more
than ``z_threshold`` standard deviations from the trailing 7-day mean
(ignoring the day itself) is an anomaly. At least 7 prior days are
required, so the first week never produces false alarms.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from dcop.models import DEFAULT_RATES, CostRecord, Rates, cost_of

WINDOW = 7
Z_THRESHOLD = 2.5


@dataclass
class DailySpend:
    date: str
    total_usd: float
    record_count: int


def daily_spend(records: list[CostRecord],
                rates: Rates = DEFAULT_RATES) -> list[DailySpend]:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for r in records:
        totals[r.date] = totals.get(r.date, 0.0) + cost_of(r, rates)
        counts[r.date] = counts.get(r.date, 0) + 1
    return [
        DailySpend(date=d, total_usd=round(totals[d], 2), record_count=counts[d])
        for d in sorted(totals)
    ]


def unit_economics(records: list[CostRecord],
                   rates: Rates = DEFAULT_RATES) -> dict:
    """Cost per query, per TB scanned, per active user, per scheduled report."""
    if not records:
        return {
            "total_usd": 0.0, "cost_per_query_usd": 0.0,
            "cost_per_tb_scanned_usd": 0.0, "cost_per_active_user_usd": 0.0,
            "cost_per_report_usd": 0.0, "active_users": 0, "reports": 0,
        }
    total = sum(cost_of(r, rates) for r in records)
    queries = {r.query_id for r in records}
    tb_scanned = sum(r.bytes_scanned_gb for r in records) / 1024.0
    users = {r.user for r in records}
    reports = {r.schedule_id for r in records if r.schedule_id}
    return {
        "total_usd": round(total, 2),
        "cost_per_query_usd": round(total / max(1, len(queries)), 2),
        "cost_per_tb_scanned_usd": round(total / tb_scanned, 2) if tb_scanned else 0.0,
        "cost_per_active_user_usd": round(total / max(1, len(users)), 2),
        "cost_per_report_usd": round(total / max(1, len(reports)), 2),
        "active_users": len(users),
        "reports": len(reports),
    }


def detect_spend_anomalies(series: list[DailySpend],
                           z_threshold: float = Z_THRESHOLD) -> list[dict]:
    """Flag days whose spend deviates from the trailing WINDOW-day baseline."""
    anomalies = []
    values = [d.total_usd for d in series]
    for i, day in enumerate(series):
        if i < WINDOW:
            continue
        window = values[i - WINDOW:i]
        mean = statistics.fmean(window)
        stdev = statistics.pstdev(window) if len(window) > 1 else 0.0
        if stdev == 0:
            if day.total_usd == mean:
                continue
            z = 999.0 if day.total_usd > mean else -999.0
        else:
            z = (day.total_usd - mean) / stdev
        if abs(z) >= z_threshold:
            anomalies.append({
                "date": day.date,
                "total_usd": day.total_usd,
                "baseline_mean_usd": round(mean, 2),
                "z_score": round(z, 2),
                "direction": "spike" if z > 0 else "dip",
            })
    return anomalies
