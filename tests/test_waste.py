"""Tests: waste detectors — each planted waste case must be found,
and clean objects must not be flagged."""

from __future__ import annotations

import pytest

from dcop.waste import detect_all


def test_idle_tables_found(tables):
    from dcop.waste import detect_idle_tables
    found = {f.target for f in detect_idle_tables(tables)}
    assert "legacy_import_2019" in found
    assert "archive_logs" in found
    assert "orders" not in found  # actively read


def test_idle_table_savings_are_storage_cost(tables):
    from dcop.waste import detect_idle_tables
    f = next(x for x in detect_idle_tables(tables) if x.target == "legacy_import_2019")
    assert f.monthly_savings_usd == pytest.approx(1800 * 0.023)
    assert f.confidence == 0.9


def test_over_provisioned_cluster_found(clusters):
    from dcop.waste import detect_over_provisioned
    found = detect_over_provisioned(clusters)
    assert [f.target for f in found] == ["wh-analytics-xl"]
    assert found[0].monthly_savings_usd > 0


def test_repeated_full_scan_found(records, tables):
    from dcop.waste import detect_repeated_full_scans
    found = detect_repeated_full_scans(records, tables)
    assert any(f.target == "q-analytics-fullscan" for f in found)


def test_unpartitioned_hot_table_found(tables):
    from dcop.waste import detect_unpartitioned_hot_tables
    found = {f.target for f in detect_unpartitioned_hot_tables(tables)}
    assert "events" in found
    assert "orders" not in found  # partitioned


def test_zombie_job_found(jobs):
    from dcop.waste import detect_zombie_jobs
    found = detect_zombie_jobs(jobs)
    assert [f.target for f in found] == ["sched-legacy-weekly-rollup"]


def test_stale_view_found(views):
    from dcop.waste import detect_stale_views
    found = detect_stale_views(views)
    assert [f.target for f in found] == ["mv_legacy_kpis"]


def test_detect_all_covers_every_kind(records, tables, clusters, jobs, views):
    findings = detect_all(records, tables, clusters, jobs, views)
    kinds = {f.kind for f in findings}
    assert kinds == {
        "idle_table", "over_provisioned", "repeated_full_scan",
        "unpartitioned_hot", "zombie_job", "stale_mv",
    }
    savings = [f.monthly_savings_usd for f in findings]
    assert savings == sorted(savings, reverse=True)
    assert all(f.monthly_savings_usd > 0 for f in findings)

