"""Deterministic synthetic cost data.

Every number comes from a seeded PRNG over generic, invented domains
(orders, events, sessions, payments, ...). Nothing here is real usage
from any employer or vendor.
"""

from __future__ import annotations

import datetime as _dt
import random

from dcop.models import ClusterStat, CostRecord, JobStat, TableStat, ViewStat

TEAMS = ["analytics", "growth", "risk", "platform", "marketing"]
WAREHOUSES = ["wh-prod", "wh-analytics"]
TABLES = [
    "orders",
    "events",
    "customers",
    "sessions",
    "payments",
    "inventory",
    "shipments",
    "campaigns",
]
USERS = {
    "analytics": ["ana.analyst", "ben.analyst"],
    "growth": ["gwen.growth", "gus.growth"],
    "risk": ["ruth.risk"],
    "platform": ["pia.platform", "pete.platform"],
    "marketing": ["mia.marketing"],
}


def _dates(start: str, days: int) -> list[str]:
    base = _dt.date.fromisoformat(start)
    return [(base + _dt.timedelta(days=i)).isoformat() for i in range(days)]


def generate_records(
    seed: int = 42, days: int = 30, start: str = "2026-10-06"
) -> list[CostRecord]:
    """Generate deterministic synthetic cost records for ``days`` days."""
    rng = random.Random(seed)
    out: list[CostRecord] = []
    dates = _dates(start, days)
    n = 0
    for day in dates:
        for team in TEAMS:
            # A few queries per team per day, plus one scheduled ETL job.
            for _ in range(rng.randint(2, 4)):
                n += 1
                table = rng.choice(TABLES)
                compute = round(rng.uniform(20, 900), 2)
                scanned = round(rng.uniform(5, 800), 2)
                out.append(
                    CostRecord(
                        record_id=f"rec-{n:05d}",
                        date=day,
                        warehouse=rng.choice(WAREHOUSES),
                        team=team,
                        project=f"{team}-dashboards",
                        user=rng.choice(USERS[team]),
                        query_id=f"q-{team}-{rng.randint(1, 12):02d}",
                        table=table,
                        compute_seconds=compute,
                        bytes_scanned_gb=scanned,
                        storage_gb_months=round(rng.uniform(0, 40), 2),
                        egress_gb=round(rng.uniform(0, 5), 2),
                        job_type="query",
                    )
                )
            n += 1
            out.append(
                CostRecord(
                    record_id=f"rec-{n:05d}",
                    date=day,
                    warehouse="wh-prod",
                    team=team,
                    project=f"{team}-etl",
                    user="svc.etl",
                    query_id=f"etl-{team}",
                    table=rng.choice(TABLES),
                    compute_seconds=round(rng.uniform(300, 1800), 2),
                    bytes_scanned_gb=round(rng.uniform(50, 1500), 2),
                    storage_gb_months=round(rng.uniform(10, 120), 2),
                    egress_gb=0.0,
                    job_type="scheduled",
                    schedule_id=f"sched-{team}-nightly",
                )
            )
    # One deliberately wasteful repeated full-scan query, every day.
    for i, day in enumerate(dates):
        n += 1
        out.append(
            CostRecord(
                record_id=f"rec-{n:05d}",
                date=day,
                warehouse="wh-prod",
                team="analytics",
                project="analytics-dashboards",
                user="ana.analyst",
                query_id="q-analytics-fullscan",
                table="events",
                compute_seconds=600.0,
                bytes_scanned_gb=2500.0,
                storage_gb_months=0.0,
                egress_gb=0.0,
                job_type="query",
            )
        )
    # A small shared-pool slice that attribution must split proportionally.
    for i, day in enumerate(dates[:5]):
        n += 1
        out.append(
            CostRecord(
                record_id=f"rec-{n:05d}",
                date=day,
                warehouse="wh-prod",
                team="",
                project="shared-infra",
                user="svc.shared",
                query_id="q-shared-monitor",
                table="events",
                compute_seconds=120.0,
                bytes_scanned_gb=10.0,
                storage_gb_months=500.0,
                egress_gb=0.0,
                job_type="etl",
                shared=True,
            )
        )
    return out


def generate_tables(seed: int = 42) -> list[TableStat]:
    rng = random.Random(seed + 1)
    tables = [
        TableStat("orders", "analytics", 420.0, 900, 0, True, 8200.0, 300),
        TableStat("events", "analytics", 2600.0, 1400, 0, False, 42000.0, 520),
        TableStat("customers", "growth", 180.0, 220, 1, True, 900.0, 80),
        TableStat("sessions", "growth", 950.0, 60, 2, False, 6100.0, 45),
        # Idle: large, untouched for 120 days.
        TableStat("legacy_import_2019", "risk", 1800.0, 0, 120, False, 0.0, 0),
        TableStat("archive_logs", "platform", 3200.0, 0, 200, False, 0.0, 0),
        TableStat("payments", "risk", 640.0, 410, 0, True, 3800.0, 150),
        TableStat("inventory", "platform", 210.0, 95, 3, True, 700.0, 40),
    ]
    # Deterministic jitter keeps the fixture stable but not hard-coded-looking.
    return [
        TableStat(
            t.name, t.team, t.size_gb, t.reads_30d, t.last_read_days_ago,
            t.partitioned, t.scan_gb_30d, t.query_count_30d,
        )
        for t in tables
    ]


def generate_clusters(seed: int = 42) -> list[ClusterStat]:
    return [
        ClusterStat("wh-prod-large", "platform", 8, 0.82, 2.0),
        # Over-provisioned: 18% average utilization.
        ClusterStat("wh-analytics-xl", "analytics", 16, 0.18, 4.0),
        ClusterStat("wh-risk-medium", "risk", 4, 0.55, 1.0),
    ]


def generate_jobs(seed: int = 42) -> list[JobStat]:
    return [
        JobStat("sched-analytics-nightly", "analytics", 30, 900.0, 120, 0),
        JobStat("sched-growth-nightly", "growth", 30, 700.0, 80, 0),
        # Zombie: runs daily, nobody reads its output.
        JobStat("sched-legacy-weekly-rollup", "risk", 30, 1500.0, 0, 0),
        JobStat("sched-platform-cleanup", "platform", 30, 200.0, 15, 1),
    ]


def generate_views(seed: int = 42) -> list[ViewStat]:
    return [
        ViewStat("mv_daily_revenue", "analytics", 260, 0, 180.0),
        # Stale: refreshed daily, never read.
        ViewStat("mv_legacy_kpis", "marketing", 0, 1, 95.0),
        ViewStat("mv_weekly_cohorts", "growth", 40, 0, 60.0),
    ]
