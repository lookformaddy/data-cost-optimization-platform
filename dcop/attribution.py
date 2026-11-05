"""Attribution engine.

Three allocation rules, applied in order:
1. direct — a record with a team is charged to that team in full.
2. proportional — shared-pool records (team == "" and shared=True) are
   split across teams in proportion to each team's direct compute usage.
3. tagged — a record whose project matches a team's explicit project
   tag list is charged to that team even if its team field is empty.

Anything that matches none of the rules stays in the unallocated
remainder and is reported explicitly — attribution never silently
absorbs unknown spend.
"""

from __future__ import annotations

from dataclasses import dataclass

from dcop.models import DEFAULT_RATES, CostRecord, Rates, cost_of


@dataclass
class AttributionResult:
    team_costs: dict[str, float]
    unallocated_usd: float
    total_usd: float
    shared_pool_usd: float

    def as_dict(self) -> dict:
        return {
            "team_costs": {k: round(v, 2) for k, v in sorted(self.team_costs.items())},
            "unallocated_usd": round(self.unallocated_usd, 2),
            "total_usd": round(self.total_usd, 2),
            "shared_pool_usd": round(self.shared_pool_usd, 2),
        }


def attribute(
    records: list[CostRecord],
    project_tags: dict[str, str] | None = None,
    rates: Rates = DEFAULT_RATES,
) -> AttributionResult:
    """Allocate record costs to teams; return per-team totals + remainder."""
    project_tags = project_tags or {}
    team_costs: dict[str, float] = {}
    direct_compute: dict[str, float] = {}
    shared: list[CostRecord] = []
    unallocated = 0.0
    total = 0.0

    for rec in records:
        c = cost_of(rec, rates)
        total += c
        team = rec.team
        if not team and rec.project in project_tags:
            team = project_tags[rec.project]
        if team:
            team_costs[team] = team_costs.get(team, 0.0) + c
            direct_compute[team] = direct_compute.get(team, 0.0) + rec.compute_seconds
        elif rec.shared:
            shared.append(rec)
        else:
            unallocated += c

    shared_total = sum(cost_of(r, rates) for r in shared)
    if shared and direct_compute:
        total_compute = sum(direct_compute.values())
        for team, compute in direct_compute.items():
            team_costs[team] = team_costs.get(team, 0.0) + shared_total * compute / total_compute
    elif shared:
        # No direct usage to proportion against: shared spend stays unallocated.
        unallocated += shared_total

    return AttributionResult(
        team_costs=team_costs,
        unallocated_usd=unallocated,
        total_usd=total,
        shared_pool_usd=shared_total,
    )
