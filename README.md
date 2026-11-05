# Data Cost Optimization Platform

Warehouse / data-platform cost observability and optimization — help a data
platform team see where the money goes and cut waste safely.

## The enterprise problem

Cloud warehouses make spend invisible: one shared bill, hundreds of queries,
jobs, tables, and clusters, and no clear owner for any dollar. Teams
over-provision "just in case", idle tables accumulate storage charges,
scheduled jobs keep running long after their consumers left, and the same
full-table scan runs hundreds of times a day. Finance asks "why is the bill
up 30%?" and nobody can answer with a number.

This platform answers that question with four capabilities:

1. **Attribution** — every dollar is allocated to a team (direct, tagged, or
   proportional split of the shared pool). Whatever cannot be allocated is
   reported as an explicit unallocated remainder, never silently absorbed.
2. **Waste detection** — six detectors (idle tables, over-provisioned
   clusters, repeated full scans, unpartitioned hot tables, zombie scheduled
   jobs, stale materialized views), each with a conservative estimated saving
   and a confidence score.
3. **Optimization advisor** — ranked recommendations (partitioning,
   clustering/caching, schedule consolidation, tiering, rightsizing, drop)
   with projected savings and a risk rating. Dry-run is the default;
   applying only mutates a **simulated plan**, never real infrastructure.
4. **Budgets + savings ledger** — monthly per-team budgets with burn-rate
   forecasting and alert thresholds; advisor actions are **fail-closed**
   (blocked when a team is over its hard cap). Applied recommendations are
   tracked projected-vs-realized in a ledger with rollback.

Plus trend reporting: cost per query, cost per TB scanned, cost per active
user / per report, and rolling z-score anomaly detection on daily spend.

## Architecture

```
dcop/
  models.py      dataclasses + pricing model (compute/scan/storage/egress rates)
  synthetic.py   deterministic synthetic usage data (seeded PRNG)
  ingestion.py   validation + aggregation (rejects bad/duplicate rows)
  attribution.py direct / tagged / proportional allocation rules
  waste.py       six waste detectors, conservative savings estimates
  advisor.py     ranked recommendations, dry-run vs apply, rollback
  budgets.py     monthly caps, burn-rate forecast, alert thresholds
  ledger.py      projected vs realized savings, rollback-aware totals
  trends.py      daily spend, unit economics, z-score anomaly detection
  api.py         FastAPI service (read-only except simulated apply/rollback)
  cli.py         generate / report / recommend / budgets
  demo.py        end-to-end run
```

See [docs/architecture.md](docs/architecture.md) for the full design,
including the data model, the fail-closed budget guard, and trade-offs.

## How to run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m pytest -q            # run the test suite
python -m dcop.demo            # end-to-end demo
python -m dcop.cli report      # cost summary, attribution, waste
python -m dcop.cli recommend   # ranked recommendations
python -m dcop.cli recommend --apply   # apply to the simulated plan
python -m dcop.cli budgets     # budget status and burn-rate forecast
uvicorn dcop.api:app --port 8000       # API: /summary /attribution /waste
                                       # /recommendations /budgets /ledger /trends
```

All data is deterministic and synthetic (`dcop/synthetic.py`, seed 42).
No real cloud credentials, no network calls, no real infrastructure.

## Key design decisions and trade-offs

- **Conservative savings estimates.** Each detector claims only a fraction
  of the naive saving (e.g. 40% of a repeated scan's cost, 50% of the
  rightsizing gap), so the advisor never promises money that is not there.
- **Attribution never hides spend.** Unallocatable cost is an explicit
  `unallocated_usd` figure, which makes the shared pool visible and
  auditable instead of quietly spreading it.
- **Fail-closed budgets.** An over-cap team gets its advisor actions
  blocked rather than letting optimizations proceed against a blown budget.
- **Dry-run by default.** `apply` previews unless `dry_run=False`, and even
  then only a simulated plan changes — the platform is an advisor, not an
  operator, so a bad recommendation is cheap to undo.
- **Ledger separates projection from realization.** A recommendation is only
  "realized" once a measurement window reports an actual delta, and the
  realization rate keeps the advisor honest over time.
- **Anomaly detection needs a baseline.** The first 7 days never flag, and a
  zero-variance window never flags — avoiding false alarms on flat spend.

## What it demonstrates

Cost modeling and unit economics for a data platform; rule-based
attribution with an explicit remainder; heuristic waste detection with
confidence-scored estimates; risk-rated recommendations with dry-run/apply
semantics; fail-closed budget guardrails; projected-vs-realized savings
accounting with rollback; time-series anomaly detection; a FastAPI service
and CLI over a clean, typed Python package.
