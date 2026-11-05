"""Budget engine: monthly caps, burn-rate forecasting, alerts.

Fail-closed by design: a team that has blown its hard cap gets its
advisor actions blocked (see advisor.apply_recommendation) instead of
letting optimizations silently proceed against a blown budget.
"""

from __future__ import annotations

import calendar
import datetime as _dt
from dataclasses import dataclass

from dcop.models import Budget

ALERT_THRESHOLDS = (0.5, 0.8, 1.0)


@dataclass
class BudgetGuard:
    budget: Budget
    spend_to_date_usd: float
    day_of_month: int
    days_in_month: int

    @property
    def forecast_usd(self) -> float:
        """Linear burn-rate forecast for the full month."""
        if self.day_of_month <= 0:
            return self.spend_to_date_usd
        daily = self.spend_to_date_usd / self.day_of_month
        return round(daily * self.days_in_month, 2)

    @property
    def utilization(self) -> float:
        return self.spend_to_date_usd / self.budget.monthly_cap_usd

    @property
    def forecast_utilization(self) -> float:
        return self.forecast_usd / self.budget.monthly_cap_usd


def guard_for(budget: Budget, spend_to_date_usd: float,
              on_date: _dt.date | None = None) -> BudgetGuard:
    on_date = on_date or _dt.date.today()
    days_in_month = calendar.monthrange(on_date.year, on_date.month)[1]
    return BudgetGuard(
        budget=budget,
        spend_to_date_usd=round(spend_to_date_usd, 2),
        day_of_month=on_date.day,
        days_in_month=days_in_month,
    )


def check_budget(guard: BudgetGuard) -> dict:
    """Status + alerts for one team's budget guard."""
    util = guard.utilization
    forecast_util = guard.forecast_utilization
    if util >= guard.budget.hard_pct:
        status = "over"
    elif forecast_util >= guard.budget.hard_pct:
        status = "critical"  # on pace to blow the cap
    elif util >= guard.budget.soft_pct or forecast_util >= guard.budget.soft_pct:
        status = "warning"
    else:
        status = "ok"
    alerts = [
        f"spend crossed {int(t * 100)}% of monthly cap"
        for t in ALERT_THRESHOLDS if util >= t
    ]
    if forecast_util >= guard.budget.hard_pct and status == "critical":
        alerts.append("burn rate forecasts exceeding the monthly cap")
    return {
        "team": guard.budget.team,
        "status": status,
        "spend_to_date_usd": guard.spend_to_date_usd,
        "monthly_cap_usd": guard.budget.monthly_cap_usd,
        "utilization": round(util, 4),
        "forecast_usd": guard.forecast_usd,
        "forecast_utilization": round(forecast_util, 4),
        "alerts": alerts,
    }


def guards_for_all(budgets: list[Budget], spend_by_team: dict[str, float],
                   on_date: _dt.date | None = None) -> dict[str, BudgetGuard]:
    return {
        b.team: guard_for(b, spend_by_team.get(b.team, 0.0), on_date)
        for b in budgets
    }
