"""Surprise redaction (spec Sec. 7). A viewer never receives details of gifts that are a
surprise for them — only a stub that lets the client show "🎁 N surprises planned"."""
from __future__ import annotations

from typing import Any

from .schemas import public_row

REDACTED_GIFT_FIELDS = ("id", "occasion_year_id", "recipient_id", "status", "created_at", "updated_at", "deleted_at")
RECIPIENT_PRIVATE_BLANK = {"notes_private": "", "sizes_notes": "", "shipping_address": "", "budget_cents": None}


def is_surprise_for(gift: dict[str, Any], viewer_id: str) -> bool:
    return gift.get("is_surprise_for_user_id") == viewer_id


def redacted_gift(gift: dict[str, Any]) -> dict[str, Any]:
    return {k: gift.get(k) for k in REDACTED_GIFT_FIELDS}


def split_gifts(gifts: list[dict[str, Any]], viewer_id: str) -> tuple[list[dict], list[dict]]:
    visible, redacted = [], []
    for g in gifts:
        if is_surprise_for(g, viewer_id):
            redacted.append(redacted_gift(g))
        else:
            visible.append(public_row(g))
    return visible, redacted


def recipient_for_viewer(r: dict[str, Any], viewer_id: str) -> dict[str, Any]:
    r = public_row(r)
    if r.get("linked_user_id") == viewer_id:
        r.update(RECIPIENT_PRIVATE_BLANK)
    return r


def activity_for_viewer(a: dict[str, Any], viewer_id: str) -> dict[str, Any]:
    a = public_row(a)
    if a.get("surprise_for_user_id") == viewer_id:
        a["summary_full"] = a.get("summary_redacted", "")
    return a
