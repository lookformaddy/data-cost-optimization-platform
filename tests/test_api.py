"""API tests — skipped automatically when FastAPI is not installed."""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from dcop.api import app  # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["records"] > 0


def test_summary_shape():
    body = client.get("/summary").json()
    assert body["total_usd"] > 0
    assert body["record_count"] > 0
    assert "analytics" in body["by_team"]


def test_attribution_conserves_total():
    body = client.get("/attribution").json()
    assert body["total_usd"] == pytest.approx(
        sum(body["team_costs"].values()) + body["unallocated_usd"], abs=0.05)


def test_waste_and_recommendations():
    waste = client.get("/waste").json()
    assert len(waste["findings"]) >= 6
    assert waste["total_monthly_savings_usd"] > 0
    recs = client.get("/recommendations").json()["recommendations"]
    assert len(recs) == len(waste["findings"])
    assert recs[0]["projected_monthly_savings_usd"] >= recs[-1]["projected_monthly_savings_usd"]


def test_apply_dry_run_then_real_then_rollback():
    recs = client.get("/recommendations").json()["recommendations"]
    rec_id = next(r["rec_id"] for r in recs if r["status"] == "proposed")
    dry = client.post(f"/recommendations/{rec_id}/apply", params={"dry_run": True})
    assert dry.json()["applied"] is False
    real = client.post(f"/recommendations/{rec_id}/apply", params={"dry_run": False})
    assert real.json()["applied"] is True
    again = client.post(f"/recommendations/{rec_id}/apply", params={"dry_run": False})
    assert again.json()["applied"] is False
    rb = client.post(f"/recommendations/{rec_id}/rollback")
    assert rb.json()["rolled_back"] is True
    ledger = client.get("/ledger").json()
    assert ledger["entries"] >= 1


def test_apply_unknown_rec_404():
    assert client.post("/recommendations/rec-999/apply").status_code == 404


def test_budgets_and_trends():
    budgets = client.get("/budgets").json()["budgets"]
    assert len(budgets) == 5
    assert all("forecast_usd" in b for b in budgets)
    trends = client.get("/trends").json()
    assert len(trends["daily_spend"]) == 30
    assert trends["unit_economics"]["cost_per_query_usd"] > 0
