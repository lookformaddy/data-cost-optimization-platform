"""Data Cost Optimization Platform (dcop).

Warehouse / data-platform cost observability and optimization.
All data is deterministic and synthetic; no real cloud credentials,
no network calls, no real infrastructure is ever touched.
"""

from dcop.models import (
    Budget,
    ClusterStat,
    CostRecord,
    JobStat,
    LedgerEntry,
    Rates,
    Recommendation,
    TableStat,
    ViewStat,
    WasteFinding,
)

__all__ = [
    "Budget",
    "ClusterStat",
    "CostRecord",
    "JobStat",
    "LedgerEntry",
    "Rates",
    "Recommendation",
    "TableStat",
    "ViewStat",
    "WasteFinding",
]
__version__ = "0.1.0"
