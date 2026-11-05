"""Core data models and the pricing model.

All money is USD. Rates are configurable constants that stand in for a
warehouse vendor's price list; they are deliberately simple and public.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rates:
    """Unit prices used to turn usage into dollars."""

    compute_per_second: float = 0.0012
    scan_per_gb: float = 0.005
    storage_per_gb_month: float = 0.023
    egress_per_gb: float = 0.09


DEFAULT_RATES = Rates()


def cost_of(record: "CostRecord", rates: Rates = DEFAULT_RATES) -> float:
    """Total USD cost of one usage record under the given rates."""
    return (
        record.compute_seconds * rates.compute_per_second
        + record.bytes_scanned_gb * rates.scan_per_gb
        + record.storage_gb_months * rates.storage_per_gb_month
        + record.egress_gb * rates.egress_per_gb
    )


@dataclass(frozen=True)
class CostRecord:
    """One unit of billable warehouse usage (query, ETL run, or job run)."""

    record_id: str
    date: str  # YYYY-MM-DD
    warehouse: str
    team: str  # "" means unattributed / shared pool
    project: str
    user: str
    query_id: str
    table: str
    compute_seconds: float
    bytes_scanned_gb: float
    storage_gb_months: float
    egress_gb: float
    job_type: str = "query"  # query | etl | scheduled
    schedule_id: str = ""
    shared: bool = False

    def cost(self, rates: Rates = DEFAULT_RATES) -> float:
        return cost_of(self, rates)


@dataclass(frozen=True)
class TableStat:
    name: str
    team: str
    size_gb: float
    reads_30d: int
    last_read_days_ago: int
    partitioned: bool
    scan_gb_30d: float
    query_count_30d: int


@dataclass(frozen=True)
class ClusterStat:
    name: str
    team: str
    provisioned_units: int
    avg_utilization: float  # 0.0 - 1.0
    hourly_cost_usd: float

    @property
    def monthly_cost_usd(self) -> float:
        return self.hourly_cost_usd * 730.0


@dataclass(frozen=True)
class JobStat:
    schedule_id: str
    team: str
    runs_30d: int
    avg_compute_seconds: float
    downstream_reads_30d: int
    last_run_days_ago: int


@dataclass(frozen=True)
class ViewStat:
    name: str
    team: str
    reads_30d: int
    last_refresh_days_ago: int
    refresh_cost_monthly_usd: float


@dataclass(frozen=True)
class WasteFinding:
    finding_id: str
    kind: str  # idle_table | over_provisioned | repeated_full_scan |
    # unpartitioned_hot | zombie_job | stale_mv
    team: str
    target: str
    monthly_savings_usd: float
    confidence: float  # 0.0 - 1.0
    detail: str


@dataclass
class Recommendation:
    rec_id: str
    kind: str  # partitioning | clustering | caching | schedule_consolidation |
    # tiering | rightsizing | drop
    team: str
    target: str
    projected_monthly_savings_usd: float
    risk: str  # low | medium | high
    description: str
    finding_id: str = ""
    status: str = "proposed"  # proposed | applied | rolled_back | blocked
    dry_run: bool = True


@dataclass(frozen=True)
class Budget:
    team: str
    monthly_cap_usd: float
    soft_pct: float = 0.8
    hard_pct: float = 1.0

    def __post_init__(self) -> None:
        if self.monthly_cap_usd <= 0:
            raise ValueError("monthly_cap_usd must be positive")
        if not 0 < self.soft_pct <= self.hard_pct:
            raise ValueError("require 0 < soft_pct <= hard_pct")


@dataclass
class LedgerEntry:
    entry_id: str
    rec_id: str
    team: str
    projected_monthly_savings_usd: float
    realized_monthly_savings_usd: float | None = None
    status: str = "applied"  # applied | rolled_back

    @property
    def variance_usd(self) -> float | None:
        if self.realized_monthly_savings_usd is None:
            return None
        return self.realized_monthly_savings_usd - self.projected_monthly_savings_usd
