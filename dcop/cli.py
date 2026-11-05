"""CLI: generate data, report costs, list waste/recommendations, check budgets."""

from __future__ import annotations

import argparse
import datetime as _dt
import json

from dcop.advisor import SimulatedPlan, apply_recommendation, build_recommendations
from dcop.attribution import attribute
from dcop.budgets import check_budget, guards_for_all
from dcop.ingestion import summarize
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

DEFAULT_BUDGETS = [
    Budget("analytics", 2500.0), Budget("growth", 1500.0),
    Budget("risk", 1200.0), Budget("platform", 2000.0),
    Budget("marketing", 800.0),
]


def _load(seed: int = 42):
    records = generate_records(seed=seed)
    tables = generate_tables(seed)
    clusters = generate_clusters(seed)
    jobs = generate_jobs(seed)
    views = generate_views(seed)
    return records, tables, clusters, jobs, views


def cmd_generate(args) -> int:
    records, *_ = _load(args.seed)
    rows = [r.__dict__ for r in records]
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)
    print(f"Wrote {len(rows)} synthetic cost records to {args.out}")
    return 0


def cmd_report(args) -> int:
    records, tables, clusters, jobs, views = _load(args.seed)
    s = summarize(records)
    print(f"Total spend (30d, synthetic): ${s.total_usd:,.2f}")
    print(f"  compute ${s.compute_usd:,.2f} | scan ${s.scan_usd:,.2f} | "
          f"storage ${s.storage_usd:,.2f} | egress ${s.egress_usd:,.2f}")
    print("Attribution:")
    attr = attribute(records)
    for team, cost in sorted(attr.team_costs.items()):
        print(f"  {team:12s} ${cost:>10,.2f}")
    print(f"  {'unallocated':12s} ${attr.unallocated_usd:>10,.2f}")
    findings = detect_all(records, tables, clusters, jobs, views)
    print(f"Waste findings: {len(findings)} — potential "
          f"${sum(f.monthly_savings_usd for f in findings):,.2f}/mo")
    print(f"Unit economics: {unit_economics(records)}")
    series = daily_spend(records)
    print(f"Spend anomalies: {detect_spend_anomalies(series)}")
    return 0


def cmd_recommend(args) -> int:
    records, tables, clusters, jobs, views = _load(args.seed)
    findings = detect_all(records, tables, clusters, jobs, views)
    recs = build_recommendations(findings)
    plan = SimulatedPlan()
    for rec in recs:
        print(f"{rec.rec_id} [{rec.risk:6s}] {rec.kind:24s} {rec.target:32s} "
              f"${rec.projected_monthly_savings_usd:>8,.2f}/mo — {rec.description}")
        if args.apply:
            result = apply_recommendation(rec, plan, dry_run=False)
            print(f"    -> applied={result['applied']}")
    if args.apply:
        print(f"Simulated plan savings: ${plan.monthly_savings_usd:,.2f}/mo")
    return 0


def cmd_budgets(args) -> int:
    records, *_ = _load(args.seed)
    # Month-to-date slice (Nov 1-4) so the burn-rate forecast is honest.
    mtd = [r for r in records if r.date.startswith("2026-11")]
    s = summarize(mtd)
    guards = guards_for_all(DEFAULT_BUDGETS, s.by_team, _dt.date(2026, 11, 4))
    for guard in guards.values():
        v = check_budget(guard)
        print(f"{v['team']:12s} {v['status']:8s} spend ${v['spend_to_date_usd']:>9,.2f} / "
              f"${v['monthly_cap_usd']:>8,.2f} forecast ${v['forecast_usd']:>9,.2f} "
              f"alerts={v['alerts']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dcop", description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("generate", help="write synthetic cost records as JSON")
    p.add_argument("--out", default="examples/synthetic_cost_records.json")
    p.set_defaults(func=cmd_generate)
    p = sub.add_parser("report", help="print cost summary, attribution, waste")
    p.set_defaults(func=cmd_report)
    p = sub.add_parser("recommend", help="list ranked recommendations")
    p.add_argument("--apply", action="store_true",
                   help="apply to the simulated plan (never real infra)")
    p.set_defaults(func=cmd_recommend)
    p = sub.add_parser("budgets", help="check team budgets and burn rate")
    p.set_defaults(func=cmd_budgets)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
