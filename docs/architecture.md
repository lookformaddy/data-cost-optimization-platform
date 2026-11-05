# Architecture — Data Cost Optimization Platform

## Overview

The platform is a pure-Python cost-observability layer that sits on top of
warehouse usage records. It never connects to a warehouse: ingestion takes
validated usage records (here, deterministic synthetic data), prices them
with a configurable rate card, and derives attribution, waste, advice,
budgets, ledger, and trends from that single priced dataset.

```
usage records ──► ingestion (validate, price) ──► attribution (team costs)
                                              ├──► waste detectors
                                              ├──► advisor (recommendations)
                                              ├──► budgets (guards)
                                              ├──► ledger (savings)
                                              └──► trends (daily spend, anomalies)
```

## Components

| Module | Responsibility |
|---|---|
| `models.py` | Dataclasses (`CostRecord`, `TableStat`, `ClusterStat`, `JobStat`, `ViewStat`, `WasteFinding`, `Recommendation`, `Budget`, `LedgerEntry`) and the `Rates` price card. `cost_of()` is the single pricing function — every dollar in the system flows through it. |
| `synthetic.py` | Seeded generator: 30 days of query/ETL records across 5 teams and 2 warehouses, plus a planted repeated full-scan query, a shared-pool slice, idle tables, an over-provisioned cluster, a zombie job, and a stale materialized view. Deterministic (seed 42) so tests and demos are reproducible. |
| `ingestion.py` | `parse_record` / `ingest` validate required fields, reject negative usage and duplicate IDs, and `summarize` aggregates by team, warehouse, and job type. A bad feed fails loudly instead of under-reporting spend. |
| `attribution.py` | Three rules in order: **direct** (record has a team), **tagged** (project matches a team's explicit tag list), **proportional** (shared-pool records split by each team's direct compute share). Anything unmatched is the unallocated remainder. |
| `waste.py` | Six pure detectors, each returning `WasteFinding`s with a conservative monthly-saving estimate and confidence. Ranked by savings descending. |
| `advisor.py` | Maps findings to recommendation kinds (`partitioning`, `caching`, `tiering`, `rightsizing`, `schedule_consolidation`, `drop`) with a risk rating. `apply_recommendation` is dry-run by default, checks the budget guard, and only then mutates the `SimulatedPlan`. `rollback_recommendation` undoes it. |
| `budgets.py` | `BudgetGuard` computes utilization and a linear burn-rate forecast (`spend/day × days in month`). `check_budget` returns `ok / warning / critical / over` plus threshold alerts. |
| `ledger.py` | `SavingsLedger` records applied recommendations (projected), accepts realized savings after a measurement window, and supports rollback. Totals exclude rolled-back entries; `realization_rate` measures advisor accuracy. |
| `trends.py` | `daily_spend` series, `unit_economics` (cost/query, cost/TB, cost/active user, cost/report), and rolling 7-day z-score anomaly detection (`|z| >= 2.5`). |
| `api.py` | FastAPI service exposing the above as JSON. `POST /recommendations/{id}/apply` and `/rollback` are the only mutating endpoints, and they only touch the in-memory simulated plan. |
| `cli.py` / `demo.py` | CLI (`generate`, `report`, `recommend`, `budgets`) and a scripted end-to-end demo. |

## Data flow (worked example)

1. A query record (600 compute-seconds, 2500 GB scanned) is priced:
   `600 × $0.0012 + 2500 × $0.005 = $13.22`.
2. Attribution charges it to the `analytics` team (direct rule).
3. The repeated-full-scan detector sees the same `query_id` 30× against
   unpartitioned table `events` and estimates 40% of its scan cost as
   recoverable by partitioning + caching.
4. The advisor emits a `caching` recommendation (risk: low) ranked by
   projected saving; a dry-run previews it; an apply (if the team's
   budget guard is not `over`) adds the saving to the simulated plan and
   creates a ledger entry.
5. The ledger later records the realized saving (e.g. 90% of projection),
   and the realization rate feeds back into how much the next round of
   recommendations is trusted.

## Design decisions and trade-offs

- **One pricing function.** All cost math goes through `cost_of()` so a
  rate change is a one-line edit and every module agrees on the numbers.
- **Conservative estimates over maximal ones.** Detectors claim 30–50% of
  the naive saving. This understates upside but keeps the advisor credible
  with finance; the ledger's realization rate is the feedback loop that
  justifies (or corrects) the fractions over time.
- **Proportional allocation needs a denominator.** The shared pool is split
  by direct compute share. If no team has direct usage, the shared pool
  stays unallocated rather than being divided arbitrarily.
- **Fail-closed, not fail-open.** Budget overruns block advisor actions.
  The alternative (warn and proceed) would let an automated advisor keep
  spending against a blown budget.
- **Simulated plan, not an operator.** The platform never executes DDL,
  cluster resizes, or schedule changes. Applying a recommendation records
  intent and projected saving; a real deployment would hand the approved
  recommendation to the platform's change-management path.
- **Linear burn-rate forecast.** Simple and explainable; it over-forecasts
  for bursty teams. A seasonal/weekly model is a natural v2, gated behind
  the same `BudgetGuard` interface.
- **Z-score anomalies need variance.** A deviation from a perfectly flat
  baseline flags (a flat week followed by a jump is a real signal); the
  first 7 days are baseline-only. This trades a slower time-to-first
  alert for far fewer false positives.

## CI

`docs/github-actions-ci.yml` runs the test suite on Python 3.10–3.12.
It ships under `docs/` because the GitHub App integration used to publish
this repo cannot write `.github/workflows/`; moving the file there activates
it unchanged.
