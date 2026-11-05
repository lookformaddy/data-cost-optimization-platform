"""Tests: ingestion validation, cost math, attribution rules."""

from __future__ import annotations

import pytest

from dcop.attribution import attribute
from dcop.ingestion import ingest, parse_record, summarize
from dcop.models import CostRecord, Rates, cost_of


def _raw(**over):
    base = {
        "record_id": "r1", "date": "2026-10-06", "warehouse": "wh-prod",
        "team": "analytics", "project": "analytics-dashboards",
        "user": "ana.analyst", "query_id": "q1", "table": "orders",
        "compute_seconds": 100.0, "bytes_scanned_gb": 10.0,
        "storage_gb_months": 5.0, "egress_gb": 1.0,
    }
    base.update(over)
    return base


def test_cost_of_uses_all_four_components():
    rec = CostRecord(**{**_raw(), "record_id": "x"})
    rates = Rates(0.01, 0.1, 0.2, 1.0)
    assert cost_of(rec, rates) == pytest.approx(100 * 0.01 + 10 * 0.1 + 5 * 0.2 + 1 * 1.0)


def test_parse_record_rejects_missing_field():
    raw = _raw()
    del raw["compute_seconds"]
    with pytest.raises(ValueError, match="missing fields"):
        parse_record(raw)


def test_parse_record_rejects_negative_usage():
    with pytest.raises(ValueError, match="must be >= 0"):
        parse_record(_raw(compute_seconds=-1))


def test_ingest_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="duplicate"):
        ingest([_raw(), _raw()])


def test_summarize_totals_match_record_costs(records):
    s = summarize(records)
    assert s.record_count == len(records)
    assert s.total_usd == pytest.approx(
        s.compute_usd + s.scan_usd + s.storage_usd + s.egress_usd, abs=0.05)
    assert set(s.by_team) <= {"analytics", "growth", "risk", "platform",
                              "marketing", "unattributed"}
    assert s.total_usd > 0


def test_attribution_conserves_total(records):
    result = attribute(records)
    assert result.total_usd == pytest.approx(
        sum(result.team_costs.values()) + result.unallocated_usd, abs=0.05)
    assert result.shared_pool_usd > 0  # synthetic shared slice exists
    assert result.unallocated_usd == 0.0  # shared pool fully proportioned


def test_attribution_shared_pool_goes_to_all_teams(records):
    direct = attribute([r for r in records if not r.shared])
    full = attribute(records)
    for team in direct.team_costs:
        assert full.team_costs[team] >= direct.team_costs[team]


def test_attribution_tagged_project_rescues_unattributed(records):
    shared = [r for r in records if r.shared]
    assert attribute(shared).unallocated_usd == pytest.approx(
        sum(r.cost() for r in shared), abs=0.01)
    tagged = attribute(shared, project_tags={"shared-infra": "platform"})
    assert tagged.unallocated_usd == 0.0
    assert tagged.team_costs["platform"] > 0


def test_attribution_empty_input():
    result = attribute([])
    assert result.total_usd == 0.0 and result.unallocated_usd == 0.0
