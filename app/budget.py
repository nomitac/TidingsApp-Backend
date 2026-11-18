"""Budget / dashboard math (spec 5.4, F12). Pure functions, integer cents only.

Per gift, amount in year currency = round_half_away_from_zero(cents * fx_rate_to_year) * quantity.
spent     = Σ price_paid (fallback estimate) for status ≥ ordered
projected = spent + Σ estimate (fallback paid) for idea / to_buy
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .schemas import GIFT_STATUSES

PURCHASED = set(GIFT_STATUSES[GIFT_STATUSES.index("ordered"):])
DONE = set(GIFT_STATUSES[GIFT_STATUSES.index("received"):])


def convert(cents: int, rate: float) -> int:
    # Decimal(str(rate)) keeps the snapshot rate exactly as the client wrote it.
    return int((Decimal(cents) * Decimal(str(rate))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def gift_amounts(g: dict[str, Any]) -> tuple[int, int]:
    """Returns (spent_cents, pending_projected_cents) in year currency for one gift."""
    qty = int(g.get("quantity") or 1)
    rate = float(g.get("fx_rate_to_year") or 1.0)
    paid, est = g.get("price_paid_cents"), g.get("price_estimate_cents")
    if g.get("status") in PURCHASED:
        base = paid if paid is not None else est
        return (convert(base, rate) * qty if base is not None else 0), 0
    base = est if est is not None else paid
    return 0, (convert(base, rate) * qty if base is not None else 0)


def compute_totals(
    year: dict[str, Any],
    recipients: list[dict[str, Any]],
    gifts: list[dict[str, Any]],
    redacted_gifts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """`gifts` are fully visible to the viewer; `redacted_gifts` count but carry no money."""
    redacted_gifts = redacted_gifts or []
    live_recipients = [r for r in recipients if not r.get("deleted_at")]
    rec_ids = {r["id"] for r in live_recipients}
    live = [g for g in gifts if not g.get("deleted_at") and g["recipient_id"] in rec_ids]
    live_red = [g for g in redacted_gifts if not g.get("deleted_at") and g["recipient_id"] in rec_ids]

    by_status = {s: 0 for s in GIFT_STATUSES}
    per: dict[str, dict[str, Any]] = {}
    for r in sorted(live_recipients, key=lambda r: (r.get("sort_order", 0), r.get("name", ""))):
        per[r["id"]] = {
            "recipient_id": r["id"],
            "name": r.get("name", ""),
            "budget_cents": r.get("budget_cents"),
            "spent_cents": 0,
            "projected_cents": 0,
            "gift_count": 0,
            "done_count": 0,
            "over_budget": False,
        }

    spent = pending = 0
    for g in live:
        s, p = gift_amounts(g)
        spent += s
        pending += p
        row = per[g["recipient_id"]]
        row["spent_cents"] += s
        row["projected_cents"] += s + p
        row["gift_count"] += 1
        row["done_count"] += 1 if g["status"] in DONE else 0
        by_status[g["status"]] += 1
    for g in live_red:
        row = per[g["recipient_id"]]
        row["gift_count"] += 1
        row["done_count"] += 1 if g["status"] in DONE else 0
        by_status[g["status"]] += 1

    for row in per.values():
        b = row["budget_cents"]
        row["over_budget"] = b is not None and row["spent_cents"] > b

    budget = year.get("total_budget_cents")
    return {
        "currency": year.get("currency", "USD"),
        "budget_cents": budget,
        "spent_cents": spent,
        "projected_cents": spent + pending,
        "remaining_cents": None if budget is None else budget - spent,
        "people_total": len(per),
        "people_done": sum(1 for r in per.values() if r["gift_count"] > 0 and r["done_count"] == r["gift_count"]),
        "gifts_by_status": by_status,
        "per_recipient": list(per.values()),
    }
