"""Tests: savings ledger and trend reporting / anomaly detection."""

from __future__ import annotations

import pytest

from dcop.advisor import build_recommendations
from dcop.ledger import SavingsLedger
from dcop.trends import (
    DailySpend,
    daily_spend,
    detect_spend_anomalies,
    unit_economics,
)
from dcop.waste import detect_all


def test_ledger_tracks_projected_vs_realized(records, tables, clusters, jobs, views):
    recs = build_recommendations(detect_all(records, tables, clusters, jobs, views))
    ledger = SavingsLedger()
    e1 = ledger.record_applied(recs[0])
    e2 = ledger.record_applied(recs[1])
    ledger.record_realized(e1.entry_id, recs[0].projected_monthly_savings_usd * 0.9)
    assert ledger.total_projected_usd == pytest.approx(
        recs[0].projected_monthly_savings_usd + recs[1].projected_monthly_savings_usd)
    assert ledger.total_realized_usd == pytest.approx(
        recs[0].projected_monthly_savings_usd * 0.9)
    assert ledger.realization_rate == pytest.approx(
        ledger.total_realized_usd / ledger.total_projected_usd, abs=1e-3)
    assert e1.variance_usd == pytest.approx(
        -0.1 * recs[0].projected_monthly_savings_usd)


def test_ledger_rollback_excludes_from_totals(records, tables, clusters, jobs, views):
    recs = build_recommendations(detect_all(records, tables, clusters, jobs, views))
    ledger = SavingsLedger()
    e = ledger.record_applied(recs[0])
    ledger.record_realized(e.entry_id, 10.0)
    ledger.rollback(e.entry_id)
    assert ledger.total_projected_usd == 0.0
    assert ledger.total_realized_usd == 0.0
    assert ledger.summary()["rolled_back"] == 1


def test_ledger_rejects_realized_on_rolled_back_entry():
    ledger = SavingsLedger()
    from dcop.models import Recommendation
    rec = Recommendation("rec-001", "drop", "risk", "x", 50.0, "low", "d")
    entry = ledger.record_applied(rec)
    ledger.rollback(entry.entry_id)
    with pytest.raises(ValueError, match="rolled back"):
        ledger.record_realized(entry.entry_id, 10.0)
    with pytest.raises(KeyError):
        ledger.record_realized("led-999", 10.0)


def test_daily_spend_covers_all_days(records):
    series = daily_spend(records)
    assert len(series) == 30
    assert series[0].date == "2026-10-06"
    assert sum(d.total_usd for d in series) > 0


def test_unit_economics(records):
    econ = unit_economics(records)
    assert econ["active_users"] == 10  # 8 named users + svc.etl + svc.shared
    assert econ["cost_per_query_usd"] > 0
    assert econ["cost_per_tb_scanned_usd"] > 0
    assert econ["reports"] == 5  # one nightly schedule per team
    assert unit_economics([])["total_usd"] == 0.0


def test_anomaly_detector_flags_planted_spike():
    base = [DailySpend(f"2026-10-{d:02d}", 100.0, 10) for d in range(1, 15)]
    spike = DailySpend("2026-10-15", 500.0, 10)
    anomalies = detect_spend_anomalies(base + [spike])
    assert len(anomalies) == 1
    assert anomalies[0]["date"] == "2026-10-15"
    assert anomalies[0]["direction"] == "spike"


def test_anomaly_detector_needs_baseline():
    series = [DailySpend(f"2026-10-{d:02d}", 100.0, 5) for d in range(1, 5)]
    assert detect_spend_anomalies(series) == []


def test_no_anomaly_on_flat_series():
    series = [DailySpend(f"2026-10-{d:02d}", 100.0, 5) for d in range(1, 20)]
    assert detect_spend_anomalies(series) == []
