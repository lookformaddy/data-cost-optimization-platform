"""Waste detectors.

Each detector is a pure function over inventory + usage stats and returns
findings with an estimated monthly saving and a confidence score.
Estimates are deliberately conservative (a fraction of the naive saving)
so the advisor never promises money that is not there.
"""

from __future__ import annotations

from collections import defaultdict

from dcop.models import (
    DEFAULT_RATES,
    ClusterStat,
    CostRecord,
    JobStat,
    Rates,
    TableStat,
    ViewStat,
    WasteFinding,
    cost_of,
)

IDLE_DAYS = 90
LOW_UTILIZATION = 0.35
HOT_SCAN_GB_30D = 5000.0
REPEAT_QUERY_MIN_RUNS = 5


def _finding(kind: str, team: str, target: str, savings: float,
             confidence: float, detail: str) -> WasteFinding:
    return WasteFinding(
        finding_id=f"{kind}:{target}",
        kind=kind,
        team=team,
        target=target,
        monthly_savings_usd=round(max(0.0, savings), 2),
        confidence=round(min(1.0, max(0.0, confidence)), 2),
        detail=detail,
    )


def detect_idle_tables(tables: list[TableStat],
                       rates: Rates = DEFAULT_RATES) -> list[WasteFinding]:
    out = []
    for t in tables:
        if t.reads_30d == 0 and t.last_read_days_ago >= IDLE_DAYS:
            savings = t.size_gb * rates.storage_per_gb_month
            out.append(_finding(
                "idle_table", t.team, t.name, savings, 0.9,
                f"No reads in {t.last_read_days_ago} days; "
                f"{t.size_gb:.0f} GB storage could be tiered or dropped.",
            ))
    return out


def detect_over_provisioned(clusters: list[ClusterStat]) -> list[WasteFinding]:
    out = []
    for c in clusters:
        if c.avg_utilization < LOW_UTILIZATION:
            # Rightsizing to roughly double the observed utilization keeps
            # headroom; only half the naive saving is claimed.
            savings = c.monthly_cost_usd * (1.0 - c.avg_utilization) * 0.5
            out.append(_finding(
                "over_provisioned", c.team, c.name, savings, 0.8,
                f"Average utilization {c.avg_utilization:.0%} on "
                f"{c.provisioned_units} units; rightsizing saves "
                f"~${savings:,.2f}/mo.",
            ))
    return out


def detect_repeated_full_scans(records: list[CostRecord],
                               tables: list[TableStat],
                               rates: Rates = DEFAULT_RATES) -> list[WasteFinding]:
    partitioned = {t.name: t.partitioned for t in tables}
    by_query: dict[str, list[CostRecord]] = defaultdict(list)
    for r in records:
        if r.job_type == "query":
            by_query[r.query_id].append(r)
    out = []
    for query_id, recs in sorted(by_query.items()):
        if len(recs) < REPEAT_QUERY_MIN_RUNS:
            continue
        avg_scan = sum(r.bytes_scanned_gb for r in recs) / len(recs)
        if avg_scan < 500:
            continue
        table = recs[0].table
        if partitioned.get(table, True):
            continue
        monthly_scan_cost = sum(cost_of(r, rates) for r in recs)
        # Partitioning + caching typically cuts repeated scans by ~40%.
        savings = monthly_scan_cost * 0.4
        out.append(_finding(
            "repeated_full_scan", recs[0].team, query_id, savings, 0.75,
            f"Ran {len(recs)}x scanning {avg_scan:,.0f} GB avg against "
            f"unpartitioned table {table}.",
        ))
    return out


def detect_unpartitioned_hot_tables(tables: list[TableStat],
                                    rates: Rates = DEFAULT_RATES) -> list[WasteFinding]:
    out = []
    for t in tables:
        if t.partitioned or t.scan_gb_30d < HOT_SCAN_GB_30D:
            continue
        savings = t.scan_gb_30d * rates.scan_per_gb * 0.3
        out.append(_finding(
            "unpartitioned_hot", t.team, t.name, savings, 0.7,
            f"Unpartitioned table scanned {t.scan_gb_30d:,.0f} GB in 30d "
            f"across {t.query_count_30d} queries.",
        ))
    return out


def detect_zombie_jobs(jobs: list[JobStat],
                       rates: Rates = DEFAULT_RATES) -> list[WasteFinding]:
    out = []
    for j in jobs:
        if j.runs_30d > 0 and j.downstream_reads_30d == 0:
            savings = j.runs_30d * j.avg_compute_seconds * rates.compute_per_second
            out.append(_finding(
                "zombie_job", j.team, j.schedule_id, savings, 0.85,
                f"Ran {j.runs_30d}x in 30d with zero downstream reads.",
            ))
    return out


def detect_stale_views(views: list[ViewStat]) -> list[WasteFinding]:
    out = []
    for v in views:
        if v.reads_30d == 0:
            out.append(_finding(
                "stale_mv", v.team, v.name, v.refresh_cost_monthly_usd, 0.9,
                f"Materialized view refreshed but never read in 30d; "
                f"refresh costs ${v.refresh_cost_monthly_usd:,.2f}/mo.",
            ))
    return out


def detect_all(records: list[CostRecord], tables: list[TableStat],
               clusters: list[ClusterStat], jobs: list[JobStat],
               views: list[ViewStat],
               rates: Rates = DEFAULT_RATES) -> list[WasteFinding]:
    """Run every detector; results ranked by estimated savings desc."""
    findings = (
        detect_idle_tables(tables, rates)
        + detect_over_provisioned(clusters)
        + detect_repeated_full_scans(records, tables, rates)
        + detect_unpartitioned_hot_tables(tables, rates)
        + detect_zombie_jobs(jobs, rates)
        + detect_stale_views(views)
    )
    return sorted(findings, key=lambda f: f.monthly_savings_usd, reverse=True)
