"""Hidden claiming (spec Sec. 8). Claims are never returned to the wishlist owner."""
from __future__ import annotations

import uuid

from . import timeutil
from .repo import Repository

ACTIVE = ("claimed", "purchased")


class ClaimError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status, self.detail = status, detail


def active_claims(repo: Repository, item_id: str) -> list[dict]:
    return [c for c in repo.select("claims", eq={"wishlist_item_id": item_id})
            if c["status"] in ACTIVE and not c.get("deleted_at")]


def load_item(repo: Repository, item_id: str) -> tuple[dict, dict]:
    item = repo.get("wishlist_items", item_id)
    if not item or item.get("deleted_at"):
        raise ClaimError(404, "item not found")
    wl = repo.get("wishlists", item["wishlist_id"])
    if not wl or wl.get("deleted_at"):
        raise ClaimError(404, "wishlist not found")
    return item, wl


def _is_mine(c: dict, user_id: str | None, guest_token: str | None) -> bool:
    return bool((user_id and c.get("claimer_user_id") == user_id) or (guest_token and c.get("guest_token") == guest_token))


def claim(repo: Repository, item_id: str, *, user_id: str | None = None, guest_token: str | None = None,
          name: str = "", email: str = "", status: str = "claimed") -> dict:
    if status not in ACTIVE:
        raise ClaimError(422, "status must be claimed or purchased")
    item, wl = load_item(repo, item_id)
    if user_id and wl["owner_user_id"] == user_id:
        raise ClaimError(403, "you can't claim items on your own wishlist")
    if not user_id and not wl.get("allow_guest_claims", True):
        raise ClaimError(403, "guest claims are disabled for this wishlist")
    now = timeutil.now_str()
    for c in active_claims(repo, item["id"]):
        if _is_mine(c, user_id, guest_token):
            return repo.upsert("claims", {**c, "status": status, "updated_at": now, "server_updated_at": now})
        raise ClaimError(409, "already claimed")
    row = {
        "id": str(uuid.uuid4()),
        "wishlist_item_id": item["id"],
        "claimer_user_id": user_id,
        "guest_token": guest_token,
        "claimer_name": name.strip()[:80],
        "claimer_email": email.strip()[:200],
        "status": status,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "server_updated_at": now,
    }
    return repo.upsert("claims", row)


def release(repo: Repository, item_id: str, *, user_id: str | None = None, guest_token: str | None = None) -> bool:
    item, _ = load_item(repo, item_id)
    now = timeutil.now_str()
    released = False
    for c in active_claims(repo, item["id"]):
        if _is_mine(c, user_id, guest_token):
            repo.upsert("claims", {**c, "status": "released", "updated_at": now, "server_updated_at": now})
            released = True
    return released
