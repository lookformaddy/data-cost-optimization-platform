"""End-to-end demo: generate data, attribute costs, find waste, advise,
check budgets, apply one recommendation to the simulated plan, track it
in the savings ledger, roll it back, and report trends.

Run:  python -m dcop.demo
"""

from __future__ import annotations

import datetime as _dt

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

BUDGETS = [
    Budget("analytics", 2500.0), Budget("growth", 1500.0),
    Budget("risk", 1200.0), Budget("platform", 2000.0),
    Budget("marketing", 800.0),
]


def main() -> int:
    records = generate_records()
    tables, clusters = generate_tables(), generate_clusters()
    jobs, views = generate_jobs(), generate_views()

    s = summarize(records)
    print(f"Ingested {s.record_count} synthetic records; "
          f"30d spend ${s.total_usd:,.2f}")
    attr = attribute(records)
    print(f"Attribution: {len(attr.team_costs)} teams, "
          f"shared pool ${attr.shared_pool_usd:,.2f}, "
          f"unallocated ${attr.unallocated_usd:,.2f}")

    findings = detect_all(records, tables, clusters, jobs, views)
    total_waste = sum(f.monthly_savings_usd for f in findings)
    print(f"Waste: {len(findings)} findings, "
          f"potential ${total_waste:,.2f}/mo")
    for f in findings[:5]:
        print(f"  - [{f.kind}] {f.target}: ${f.monthly_savings_usd:,.2f}/mo "
              f"(confidence {f.confidence:.0%})")

    recs = build_recommendations(findings)
    print(f"Advisor: {len(recs)} recommendations; top: {recs[0].kind} on "
          f"{recs[0].target} (${recs[0].projected_monthly_savings_usd:,.2f}/mo, "
          f"risk {recs[0].risk})")

    guards = guards_for_all(
        BUDGETS,
        summarize([r for r in records if r.date.startswith("2026-11")]).by_team,
        _dt.date(2026, 11, 4))
    for g in guards.values():
        v = check_budget(g)
        print(f"Budget {v['team']:12s}: {v['status']:8s} "
              f"forecast ${v['forecast_usd']:,.2f} vs cap ${v['monthly_cap_usd']:,.2f}")

    plan, ledger = SimulatedPlan(), SavingsLedger()
    top = recs[0]
    preview = apply_recommendation(top, plan, guards, dry_run=True)
    print(f"Dry-run {top.rec_id}: applied={preview['applied']} "
          f"(plan savings still ${plan.monthly_savings_usd:,.2f})")
    result = apply_recommendation(top, plan, guards, dry_run=False)
    entry = ledger.record_applied(top)
    ledger.record_realized(entry.entry_id,
                           top.projected_monthly_savings_usd * 0.9)
    print(f"Applied {top.rec_id}: applied={result['applied']}, "
          f"plan savings ${plan.monthly_savings_usd:,.2f}/mo, "
          f"ledger realized ${ledger.total_realized_usd:,.2f} "
          f"(realization {ledger.realization_rate:.0%})")
    rollback_recommendation(top, plan)
    ledger.rollback(entry.entry_id)
    print(f"Rolled back {top.rec_id}: plan savings ${plan.monthly_savings_usd:,.2f}/mo, "
          f"ledger active entries {ledger.summary()['active']}")

    econ = unit_economics(records)
    print(f"Unit economics: ${econ['cost_per_query_usd']:.2f}/query, "
          f"${econ['cost_per_tb_scanned_usd']:.2f}/TB, "
          f"${econ['cost_per_active_user_usd']:.2f}/active user")
    series = daily_spend(records)
    print(f"Trends: {len(series)} days, "
          f"anomalies: {detect_spend_anomalies(series)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
