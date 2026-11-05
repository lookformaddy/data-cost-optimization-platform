"""Savings ledger: projected vs realized savings, with rollback.

An applied recommendation creates a ledger entry with a projection.
Once a measurement window has passed, the realized saving is recorded
(simulated here from a post-apply cost delta supplied by the caller).
Rolling back marks the entry rolled back and removes it from the
realized total, keeping the audit trail intact.
"""

from __future__ import annotations

from dcop.models import LedgerEntry, Recommendation


class SavingsLedger:
    def __init__(self) -> None:
        self.entries: list[LedgerEntry] = []

    def record_applied(self, rec: Recommendation) -> LedgerEntry:
        entry = LedgerEntry(
            entry_id=f"led-{len(self.entries) + 1:03d}",
            rec_id=rec.rec_id,
            team=rec.team,
            projected_monthly_savings_usd=rec.projected_monthly_savings_usd,
        )
        self.entries.append(entry)
        return entry

    def record_realized(self, entry_id: str, realized_usd: float) -> LedgerEntry:
        entry = self._get(entry_id)
        if entry.status == "rolled_back":
            raise ValueError(f"entry {entry_id} was rolled back; cannot realize savings")
        if realized_usd < 0:
            raise ValueError("realized savings must be >= 0")
        entry.realized_monthly_savings_usd = round(realized_usd, 2)
        return entry

    def rollback(self, entry_id: str) -> LedgerEntry:
        entry = self._get(entry_id)
        entry.status = "rolled_back"
        return entry

    def _get(self, entry_id: str) -> LedgerEntry:
        for e in self.entries:
            if e.entry_id == entry_id:
                return e
        raise KeyError(f"unknown ledger entry: {entry_id}")

    @property
    def total_projected_usd(self) -> float:
        return round(sum(
            e.projected_monthly_savings_usd for e in self.entries
            if e.status == "applied"), 2)

    @property
    def total_realized_usd(self) -> float:
        return round(sum(
            e.realized_monthly_savings_usd or 0.0 for e in self.entries
            if e.status == "applied"), 2)

    @property
    def realization_rate(self) -> float | None:
        projected = self.total_projected_usd
        if projected == 0:
            return None
        return round(self.total_realized_usd / projected, 4)

    def summary(self) -> dict:
        return {
            "entries": len(self.entries),
            "active": sum(1 for e in self.entries if e.status == "applied"),
            "rolled_back": sum(1 for e in self.entries if e.status == "rolled_back"),
            "total_projected_usd": self.total_projected_usd,
            "total_realized_usd": self.total_realized_usd,
            "realization_rate": self.realization_rate,
        }
