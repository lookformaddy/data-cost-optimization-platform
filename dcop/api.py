"""FastAPI service: cost summary, attribution, waste, recommendations,
budgets, ledger, and trends over the deterministic synthetic dataset.

Read-only except for the simulated apply/rollback endpoints, which only
mutate the in-memory simulated plan — never real infrastructure.
"""

from __future__ import annotations

import datetime as _dt

from fastapi import FastAPI, HTTPException

from dcop.advisor import (
    SimulatedPlan,
    apply_recommendation,
    build_recommendations,
    rollback_recommendation,
)
from dcop.attribution import attribute
from dcop.budgets import check_budget, guards_for_all
from dcop.ingestion import summarize
from dcop.ledger import SavingsLedger
from dcop.models import Budget
from dcop.synthetic import (
    generate_clusters,
    generate_jobs,
    generate_records,
    generate_tables,
    generate_views,
)
from dcop.trends import daily_spend, detect_spend_anomalies, unit_economics
from dcop.waste import detect_all

app = FastAPI(title="Data Cost Optimization Platform", version="0.1.0")

RECORDS = generate_records()
TABLES = generate_tables()
CLUSTERS = generate_clusters()
JOBS = generate_jobs()
VIEWS = generate_views()
BUDGETS = [Budget(team, cap) for team, cap in {
    "analytics": 2500.0, "growth": 1500.0, "risk": 1200.0,
    "platform": 2000.0, "marketing": 800.0,
}.items()]
PLAN = SimulatedPlan()
LEDGER = SavingsLedger()
RECOMMENDATIONS = build_recommendations(
    detect_all(RECORDS, TABLES, CLUSTERS, JOBS, VIEWS))


def _guards():
    # Budgets track the current month only: the synthetic window ends
    # 2026-11-04, so month-to-date is the Nov 1-4 slice, not the full 30d.
    mtd = [r for r in RECORDS if r.date.startswith("2026-11")]
    summary = summarize(mtd)
    spend = {t: v for t, v in summary.by_team.items()}
    return guards_for_all(BUDGETS, spend, _dt.date(2026, 11, 4))


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "records": len(RECORDS)}


@app.get("/summary")
def summary() -> dict:
    s = summarize(RECORDS)
    return {
        "total_usd": s.total_usd, "compute_usd": s.compute_usd,
        "scan_usd": s.scan_usd, "storage_usd": s.storage_usd,
        "egress_usd": s.egress_usd, "record_count": s.record_count,
        "by_team": s.by_team, "by_warehouse": s.by_warehouse,
        "by_job_type": s.by_job_type,
    }


@app.get("/attribution")
def attribution() -> dict:
    return attribute(RECORDS).as_dict()


@app.get("/waste")
def waste() -> dict:
    findings = detect_all(RECORDS, TABLES, CLUSTERS, JOBS, VIEWS)
    return {
        "findings": [f.__dict__ for f in findings],
        "total_monthly_savings_usd": round(sum(f.monthly_savings_usd for f in findings), 2),
    }


@app.get("/recommendations")
def recommendations() -> dict:
    return {"recommendations": [r.__dict__ for r in RECOMMENDATIONS]}


@app.post("/recommendations/{rec_id}/apply")
def apply(rec_id: str, dry_run: bool = True) -> dict:
    rec = next((r for r in RECOMMENDATIONS if r.rec_id == rec_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"unknown recommendation: {rec_id}")
    result = apply_recommendation(rec, PLAN, _guards(), dry_run=dry_run)
    if result.get("applied"):
        LEDGER.record_applied(rec)
    return result


@app.post("/recommendations/{rec_id}/rollback")
def rollback(rec_id: str) -> dict:
    rec = next((r for r in RECOMMENDATIONS if r.rec_id == rec_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"unknown recommendation: {rec_id}")
    result = rollback_recommendation(rec, PLAN)
    if result.get("rolled_back"):
        for entry in LEDGER.entries:
            if entry.rec_id == rec_id and entry.status == "applied":
                LEDGER.rollback(entry.entry_id)
    return result


@app.get("/budgets")
def budgets() -> dict:
    return {"budgets": [check_budget(g) for g in _guards().values()]}


@app.get("/ledger")
def ledger() -> dict:
    return LEDGER.summary()


@app.get("/trends")
def trends() -> dict:
    series = daily_spend(RECORDS)
    return {
        "daily_spend": [d.__dict__ for d in series],
        "unit_economics": unit_economics(RECORDS),
        "anomalies": detect_spend_anomalies(series),
    }
