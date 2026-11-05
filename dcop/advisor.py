"""Optimization advisor.

Turns waste findings into ranked recommendations with a risk rating.
Dry-run is the default: ``apply`` only mutates the simulated plan when
``dry_run=False``, and only after the budget guard passes. Nothing here
touches real infrastructure — the plan is a simulation of what an apply
would do, so recommendations can be reviewed, rolled back, and audited.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dcop.budgets import BudgetGuard, check_budget
from dcop.models import Recommendation, WasteFinding

KIND_FOR_FINDING = {
    "idle_table": ("tiering", "low"),
    "over_provisioned": ("rightsizing", "medium"),
    "repeated_full_scan": ("caching", "low"),
    "unpartitioned_hot": ("partitioning", "medium"),
    "zombie_job": ("schedule_consolidation", "low"),
    "stale_mv": ("drop", "low"),
}

DESCRIPTIONS = {
    "tiering": "Move cold data to cold storage tier; restore on demand.",
    "rightsizing": "Reduce provisioned units to match observed utilization.",
    "caching": "Cache repeated query results; serve repeats from cache.",
    "partitioning": "Partition the hot table on its dominant filter key.",
    "schedule_consolidation": "Pause the schedule; re-enable only if a consumer appears.",
    "drop": "Drop the unused object after a 7-day soft-delete hold.",
}


@dataclass
class SimulatedPlan:
    """The simulated state of the platform after applying recommendations."""

    applied_rec_ids: list[str] = field(default_factory=list)
    monthly_savings_usd: float = 0.0
    notes: list[str] = field(default_factory=list)


def build_recommendations(findings: list[WasteFinding]) -> list[Recommendation]:
    recs: list[Recommendation] = []
    for i, f in enumerate(findings):
        kind, risk = KIND_FOR_FINDING.get(f.kind, ("tiering", "medium"))
        recs.append(Recommendation(
            rec_id=f"rec-{i + 1:03d}",
            kind=kind,
            team=f.team,
            target=f.target,
            projected_monthly_savings_usd=f.monthly_savings_usd,
            risk=risk,
            description=DESCRIPTIONS[kind],
            finding_id=f.finding_id,
        ))
    return sorted(recs, key=lambda r: r.projected_monthly_savings_usd, reverse=True)


def apply_recommendation(
    rec: Recommendation,
    plan: SimulatedPlan,
    budgets: dict[str, BudgetGuard] | None = None,
    dry_run: bool = True,
) -> dict:
    """Apply (or preview) a recommendation against the simulated plan.

    Fail-closed: if the team's budget guard reports over the hard cap,
    the recommendation is blocked and nothing mutates.
    """
    if rec.status == "applied":
        return {"rec_id": rec.rec_id, "applied": False, "reason": "already applied"}
    if budgets and rec.team in budgets:
        verdict = check_budget(budgets[rec.team])
        if verdict["status"] == "over":
            rec.status = "blocked"
            return {
                "rec_id": rec.rec_id, "applied": False,
                "reason": "blocked: team over hard budget cap",
                "budget": verdict,
            }
    preview = {
        "rec_id": rec.rec_id,
        "kind": rec.kind,
        "target": rec.target,
        "projected_monthly_savings_usd": rec.projected_monthly_savings_usd,
        "risk": rec.risk,
    }
    if dry_run:
        return {**preview, "applied": False, "dry_run": True}
    rec.status = "applied"
    rec.dry_run = False
    plan.applied_rec_ids.append(rec.rec_id)
    plan.monthly_savings_usd = round(
        plan.monthly_savings_usd + rec.projected_monthly_savings_usd, 2)
    plan.notes.append(f"Applied {rec.rec_id} ({rec.kind}) on {rec.target}")
    return {**preview, "applied": True, "dry_run": False}


def rollback_recommendation(rec: Recommendation, plan: SimulatedPlan) -> dict:
    """Undo an applied recommendation in the simulated plan."""
    if rec.status != "applied":
        return {"rec_id": rec.rec_id, "rolled_back": False,
                "reason": "not applied"}
    rec.status = "rolled_back"
    plan.applied_rec_ids = [r for r in plan.applied_rec_ids if r != rec.rec_id]
    plan.monthly_savings_usd = round(
        max(0.0, plan.monthly_savings_usd - rec.projected_monthly_savings_usd), 2)
    plan.notes.append(f"Rolled back {rec.rec_id} ({rec.kind}) on {rec.target}")
    return {"rec_id": rec.rec_id, "rolled_back": True}
