"""Cost ingestion: validate raw records and aggregate spend.

Accepts dicts (e.g. from JSON) or CostRecord objects. Invalid rows are
rejected with a clear error instead of silently dropped, so a bad feed
cannot quietly under-report spend.
"""

from __future__ import annotations

from dataclasses import dataclass

from dcop.models import DEFAULT_RATES, CostRecord, Rates, cost_of

_REQUIRED = (
    "record_id", "date", "warehouse", "team", "project", "user",
    "query_id", "table", "compute_seconds", "bytes_scanned_gb",
    "storage_gb_months", "egress_gb",
)


def parse_record(raw: dict) -> CostRecord:
    missing = [k for k in _REQUIRED if k not in raw]
    if missing:
        raise ValueError(f"record missing fields: {sorted(missing)}")
    numeric = ("compute_seconds", "bytes_scanned_gb", "storage_gb_months", "egress_gb")
    for key in numeric:
        if raw[key] < 0:
            raise ValueError(f"record {raw.get('record_id')}: {key} must be >= 0")
    return CostRecord(
        record_id=str(raw["record_id"]),
        date=str(raw["date"]),
        warehouse=str(raw["warehouse"]),
        team=str(raw["team"]),
        project=str(raw["project"]),
        user=str(raw["user"]),
        query_id=str(raw["query_id"]),
        table=str(raw["table"]),
        compute_seconds=float(raw["compute_seconds"]),
        bytes_scanned_gb=float(raw["bytes_scanned_gb"]),
        storage_gb_months=float(raw["storage_gb_months"]),
        egress_gb=float(raw["egress_gb"]),
        job_type=str(raw.get("job_type", "query")),
        schedule_id=str(raw.get("schedule_id", "")),
        shared=bool(raw.get("shared", False)),
    )


def ingest(raw_records: list[dict]) -> list[CostRecord]:
    """Parse and validate a batch; raises on the first bad row."""
    seen: set[str] = set()
    out: list[CostRecord] = []
    for raw in raw_records:
        rec = parse_record(raw)
        if rec.record_id in seen:
            raise ValueError(f"duplicate record_id: {rec.record_id}")
        seen.add(rec.record_id)
        out.append(rec)
    return out


@dataclass
class CostSummary:
    total_usd: float
    compute_usd: float
    scan_usd: float
    storage_usd: float
    egress_usd: float
    record_count: int
    by_team: dict[str, float]
    by_warehouse: dict[str, float]
    by_job_type: dict[str, float]


def summarize(records: list[CostRecord], rates: Rates = DEFAULT_RATES) -> CostSummary:
    total = compute = scan = storage = egress = 0.0
    by_team: dict[str, float] = {}
    by_warehouse: dict[str, float] = {}
    by_job_type: dict[str, float] = {}
    for rec in records:
        c = cost_of(rec, rates)
        total += c
        compute += rec.compute_seconds * rates.compute_per_second
        scan += rec.bytes_scanned_gb * rates.scan_per_gb
        storage += rec.storage_gb_months * rates.storage_per_gb_month
        egress += rec.egress_gb * rates.egress_per_gb
        by_team[rec.team or "unattributed"] = by_team.get(rec.team or "unattributed", 0.0) + c
        by_warehouse[rec.warehouse] = by_warehouse.get(rec.warehouse, 0.0) + c
        by_job_type[rec.job_type] = by_job_type.get(rec.job_type, 0.0) + c
    return CostSummary(
        total_usd=round(total, 2),
        compute_usd=round(compute, 2),
        scan_usd=round(scan, 2),
        storage_usd=round(storage, 2),
        egress_usd=round(egress, 2),
        record_count=len(records),
        by_team={k: round(v, 2) for k, v in sorted(by_team.items())},
        by_warehouse={k: round(v, 2) for k, v in sorted(by_warehouse.items())},
        by_job_type={k: round(v, 2) for k, v in sorted(by_job_type.items())},
    )
