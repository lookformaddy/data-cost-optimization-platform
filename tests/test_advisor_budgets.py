"""Tests: advisor dry-run/apply/rollback semantics and budget guards."""

from __future__ import annotations

import datetime as _dt

import pytest

from dcop.advisor import (
    SimulatedPlan,
    apply_recommendation,
    build_recommendations,
    rollback_recommendation,
)
from dcop.budgets import check_budget, guard_for, guards_for_all
from dcop.models import Budget
from dcop.waste import detect_all


@pytest.fixture()
def findings(records, tables, clusters, jobs, views):
    return detect_all(records, tables, clusters, jobs, views)


def test_recommendations_ranked_by_savings(findings):
    recs = build_recommendations(findings)
    assert len(recs) == len(findings)
    savings = [r.projected_monthly_savings_usd for r in recs]
    assert savings == sorted(savings, reverse=True)
    assert all(r.risk in {"low", "medium", "high"} for r in recs)
    assert all(r.status == "proposed" for r in recs)


def test_dry_run_does_not_mutate(findings):
    recs = build_recommendations(findings)
    plan = SimulatedPlan()
    result = apply_recommendation(recs[0], plan, dry_run=True)
    assert result["applied"] is False
    assert plan.monthly_savings_usd == 0.0
    assert recs[0].status == "proposed"


def test_apply_then_rollback_round_trip(findings):
    recs = build_recommendations(findings)
    plan = SimulatedPlan()
    result = apply_recommendation(recs[0], plan, dry_run=False)
    assert result["applied"] is True
    assert plan.monthly_savings_usd == pytest.approx(
        recs[0].projected_monthly_savings_usd)
    assert apply_recommendation(recs[0], plan, dry_run=False)["applied"] is False
    out = rollback_recommendation(recs[0], plan)
    assert out["rolled_back"] is True
    assert plan.monthly_savings_usd == 0.0
    assert recs[0].status == "rolled_back"


def test_budget_forecast_scales_linearly():
    budget = Budget("analytics", 3000.0)
    guard = guard_for(budget, 1000.0, _dt.date(2026, 11, 10))
    assert guard.forecast_usd == pytest.approx(1000.0 / 10 * 30)
    assert guard.utilization == pytest.approx(1 / 3)


def test_budget_statuses():
    ok = check_budget(guard_for(Budget("t", 1000.0), 100.0, _dt.date(2026, 11, 5)))
    assert ok["status"] == "ok"
    warn = check_budget(guard_for(Budget("t", 1000.0), 850.0, _dt.date(2026, 11, 28)))
    assert warn["status"] == "warning"  # util 85%, forecast 910 < cap
    over = check_budget(guard_for(Budget("t", 1000.0), 1000.0, _dt.date(2026, 11, 5)))
    assert over["status"] == "over"
    assert "spend crossed 100% of monthly cap" in over["alerts"]
    critical = check_budget(guard_for(Budget("t", 1000.0), 400.0, _dt.date(2026, 11, 5)))
    assert critical["status"] == "critical"  # 400/5*30 = 2400 forecast


def test_over_budget_blocks_apply_fail_closed(findings, budgets, on_date):
    recs = build_recommendations(findings)
    rec = next(r for r in recs if r.team == "analytics")
    spend = {"analytics": 99999.0}
    guards = guards_for_all(budgets, spend, on_date)
    plan = SimulatedPlan()
    result = apply_recommendation(rec, plan, guards, dry_run=False)
    assert result["applied"] is False
    assert rec.status == "blocked"
    assert plan.monthly_savings_usd == 0.0


def test_budget_validation():
    with pytest.raises(ValueError):
        Budget("t", 0)
    with pytest.raises(ValueError):
        Budget("t", 100, soft_pct=1.2, hard_pct=1.0)
