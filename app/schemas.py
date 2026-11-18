"""Row shapes for synced tables (see API_CONTRACT.md) and normalisation of incoming rows.

Rows travel as plain dicts. `normalize_row` keeps only known columns, fills defaults,
lower-cases UUIDs, canonicalises timestamps and validates enums. It raises ValueError
for rows that cannot be stored; the sync endpoint turns that into a `rejected` entry.
"""
from __future__ import annotations

import uuid
from typing import Any, Callable

from . import timeutil

REQUIRED = object()


def _now() -> str:
    return timeutil.now_str()


# kind, default (value or callable or REQUIRED), extra (enum values)
Field = tuple[str, Any] | tuple[str, Any, tuple[str, ...]]

COMMON: dict[str, Field] = {
    "id": ("uuid", REQUIRED),
    "created_at": ("ts", _now),
    "updated_at": ("ts", _now),
    "deleted_at": ("ts?", None),
}

GIFT_STATUSES = ("idea", "to_buy", "ordered", "shipped", "received", "wrapped", "given")
GIFT_TYPES = ("regular", "stocking_stuffer", "card", "gift_card", "experience", "cash")

TABLES: dict[str, dict[str, Field]] = {
    "occasion_years": {
        "owner_id": ("uuid", REQUIRED),
        "name": ("str", ""),
        "occasion_type": ("enum", "christmas", ("christmas", "hanukkah", "birthday", "holiday")),
        "year": ("int", REQUIRED),
        "total_budget_cents": ("int?", None),
        "currency": ("currency", "USD"),
        "occasion_date": ("ts", REQUIRED),
        "is_archived": ("bool", False),
    },
    "year_members": {
        "occasion_year_id": ("uuid", REQUIRED),
        "user_id": ("uuid?", None),
        "role": ("enum", "co_shopper", ("owner", "co_shopper")),
        "invited_email": ("str", ""),
        "display_name": ("str", ""),
        "status": ("enum", "invited", ("invited", "accepted")),
    },
    "groups": {
        "occasion_year_id": ("uuid", REQUIRED),
        "name": ("str", ""),
        "sort_order": ("int", 0),
    },
    "recipients": {
        "person_id": ("uuid", REQUIRED),
        "occasion_year_id": ("uuid", REQUIRED),
        "name": ("str", ""),
        "avatar_emoji": ("str", "🎁"),
        "relationship": ("str", ""),
        "group_ids": ("uuids", list),
        "budget_cents": ("int?", None),
        "notes_private": ("str", ""),
        "sizes_notes": ("str", ""),
        "shipping_address": ("str", ""),
        "linked_user_id": ("uuid?", None),
        "wishlist_id": ("uuid?", None),
        "external_wishlist_url": ("str", ""),
        "sort_order": ("int", 0),
    },
    "gifts": {
        "occasion_year_id": ("uuid", REQUIRED),
        "recipient_id": ("uuid", REQUIRED),
        "title": ("str", ""),
        "status": ("enum", "idea", GIFT_STATUSES),
        "gift_type": ("enum", "regular", GIFT_TYPES),
        "price_paid_cents": ("int?", None),
        "price_estimate_cents": ("int?", None),
        "currency": ("currency", "USD"),
        "fx_rate_to_year": ("float", 1.0),
        "store": ("str", ""),
        "product_url": ("str", ""),
        "image_url": ("str", ""),
        "variant": ("str", ""),
        "quantity": ("int", 1),
        "notes_private": ("str", ""),
        "notes_public": ("str", ""),
        "visibility": ("enum", "co_shopper", ("private", "co_shopper")),
        "is_surprise_for_user_id": ("uuid?", None),
        "purchased_at": ("ts?", None),
        "shipped_at": ("ts?", None),
        "tracking_number": ("str", ""),
        "carrier": ("str", ""),
        "source_wishlist_item_id": ("uuid?", None),
        "photos": ("json", list),
        "price_at_import_cents": ("int?", None),
        "created_by": ("uuid?", None),
        "updated_by": ("uuid?", None),
    },
    "wishlists": {
        "owner_user_id": ("uuid", REQUIRED),
        "owner_name": ("str", ""),
        "occasion_year_id": ("uuid?", None),
        "title": ("str", ""),
        "slug": ("str", REQUIRED),
        "is_public_link_enabled": ("bool", True),
        "allow_guest_claims": ("bool", True),
        "reveal_claims_after": ("ts?", None),
    },
    "wishlist_items": {
        "wishlist_id": ("uuid", REQUIRED),
        "title": ("str", ""),
        "product_url": ("str", ""),
        "image_url": ("str", ""),
        "price_cents": ("int?", None),
        "currency": ("currency", "USD"),
        "variant": ("str", ""),
        "priority": ("int", 2),
        "notes_public": ("str", ""),
        "sort_order": ("int", 0),
    },
    "secret_santa_exchanges": {
        "occasion_year_id": ("uuid", REQUIRED),
        "name": ("str", ""),
        "budget_cents": ("int?", None),
        "currency": ("currency", "USD"),
        "draw_date": ("ts", _now),
        "organizer_id": ("uuid", REQUIRED),
        "participants": ("json", list),
        "exclusions": ("json", list),
        "matches": ("json", list),
        "organizer_can_see_matches": ("bool", False),
        "status": ("enum", "draft", ("draft", "drawn")),
    },
    "activity_log": {
        "occasion_year_id": ("uuid", REQUIRED),
        "actor_user_id": ("uuid", REQUIRED),
        "actor_name": ("str", ""),
        "entity_type": ("str", ""),
        "entity_id": ("uuid", REQUIRED),
        "action": ("str", ""),
        "summary_redacted": ("str", ""),
        "summary_full": ("str", ""),
        "surprise_for_user_id": ("uuid?", None),
    },
}

# Order matters: parents before children so a single batch can create a whole year.
SYNC_TABLES: tuple[str, ...] = (
    "occasion_years",
    "year_members",
    "groups",
    "recipients",
    "wishlists",
    "wishlist_items",
    "gifts",
    "secret_santa_exchanges",
    "activity_log",
)

YEAR_SCOPED = ("year_members", "groups", "recipients", "gifts", "activity_log")


def norm_uuid(value: Any) -> str:
    return str(uuid.UUID(str(value))).lower()


def _default(d: Any) -> Any:
    if isinstance(d, Callable):  # type: ignore[arg-type]
        return d()
    return d


def _coerce(name: str, kind: str, value: Any, enum: tuple[str, ...] = ()) -> Any:
    if kind == "uuid":
        return norm_uuid(value)
    if kind == "uuid?":
        return None if value in (None, "") else norm_uuid(value)
    if kind == "uuids":
        return [norm_uuid(v) for v in (value or [])]
    if kind == "str":
        return "" if value is None else str(value)
    if kind == "currency":
        s = str(value or "USD").upper()
        if len(s) != 3 or not s.isalpha():
            raise ValueError(f"{name}: invalid currency")
        return s
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            raise ValueError(f"{name}: expected integer")
        return int(value)
    if kind == "int?":
        return None if value is None else _coerce(name, "int", value)
    if kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name}: expected number")
        return float(value)
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{name}: expected boolean")
        return value
    if kind == "ts":
        return timeutil.normalize(value)
    if kind == "ts?":
        return None if value in (None, "") else timeutil.normalize(value)
    if kind == "json":
        if not isinstance(value, (list, dict)):
            raise ValueError(f"{name}: expected JSON array/object")
        return _normalize_json_uuids(value)
    if kind == "enum":
        if value not in enum:
            raise ValueError(f"{name}: must be one of {', '.join(enum)}")
        return value
    raise AssertionError(kind)


def _normalize_json_uuids(value: Any) -> Any:
    """Lower-case UUID-looking strings inside JSON blobs (participants, matches, photos)."""
    if isinstance(value, list):
        return [_normalize_json_uuids(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(v, str) and (k == "id" or k.endswith("_id")):
                try:
                    v = norm_uuid(v)
                except ValueError:
                    pass
            else:
                v = _normalize_json_uuids(v)
            out[k] = v
        return out
    return value


def normalize_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("row must be an object")
    fields = {**COMMON, **TABLES[table]}
    out: dict[str, Any] = {}
    for name, spec in fields.items():
        kind, default = spec[0], spec[1]
        enum = spec[2] if len(spec) > 2 else ()
        if name in row and row[name] is not None or (name in row and kind.endswith("?")):
            try:
                out[name] = _coerce(name, kind, row[name], enum)
            except (TypeError, ValueError) as e:
                raise ValueError(str(e) if str(e).startswith(name) else f"{name}: {e}") from None
        else:
            if default is REQUIRED:
                raise ValueError(f"{name}: required")
            out[name] = _default(default)
    return out


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    """Strip server-only columns before returning to clients."""
    return {k: v for k, v in row.items() if k not in ("server_updated_at",)}
