from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import claims, timeutil
from ..auth import current_user, get_repo
from ..repo import Repository
from ..schemas import norm_uuid, public_row

router = APIRouter(prefix="/v1", tags=["wishlists"])


def _uuid_or_404(v: str) -> str:
    try:
        return norm_uuid(v)
    except ValueError:
        raise HTTPException(404, "not found") from None


def _items(repo: Repository, wishlist_id: str) -> list[dict]:
    items = [i for i in repo.select("wishlist_items", eq={"wishlist_id": wishlist_id}) if not i.get("deleted_at")]
    return sorted(items, key=lambda i: (i.get("sort_order", 0), -i.get("priority", 2), i.get("title", "")))


@router.get("/wishlists/by-slug/{slug}")
def by_slug(slug: str, user: dict = Depends(current_user), repo: Repository = Depends(get_repo)) -> dict:
    found = [w for w in repo.select("wishlists", eq={"slug": slug}) if not w.get("deleted_at")]
    if not found:
        raise HTTPException(404, "wishlist not found")
    wl = found[0]
    is_owner = wl["owner_user_id"] == user["id"]
    out = []
    for item in _items(repo, wl["id"]):
        row = public_row(item)
        if is_owner:
            # Owner never learns claim state — not even "claimed: false".
            row["claimed"] = None
            row["claimed_by_me"] = None
        else:
            active = claims.active_claims(repo, item["id"])
            row["claimed"] = bool(active)
            row["claimed_by_me"] = any(c.get("claimer_user_id") == user["id"] for c in active)
        out.append(row)
    return {"wishlist": public_row(wl), "is_owner": is_owner, "items": out}


class ClaimIn(BaseModel):
    claimer_name: str = ""
    status: Literal["claimed", "purchased"] = "claimed"


@router.post("/wishlist-items/{item_id}/claim")
def claim_item(item_id: str, body: ClaimIn, user: dict = Depends(current_user), repo: Repository = Depends(get_repo)) -> dict:
    try:
        c = claims.claim(repo, _uuid_or_404(item_id), user_id=user["id"],
                         name=body.claimer_name or user.get("display_name", ""), status=body.status)
    except claims.ClaimError as e:
        raise HTTPException(e.status, e.detail) from None
    return {"claim_id": c["id"]}


@router.post("/wishlist-items/{item_id}/release")
def release_item(item_id: str, user: dict = Depends(current_user), repo: Repository = Depends(get_repo)) -> dict:
    try:
        ok = claims.release(repo, _uuid_or_404(item_id), user_id=user["id"])
    except claims.ClaimError as e:
        raise HTTPException(e.status, e.detail) from None
    if not ok:
        raise HTTPException(404, "you have no claim on this item")
    return {"released": True}


@router.get("/wishlists/{wishlist_id}/reveal")
def reveal(wishlist_id: str, user: dict = Depends(current_user), repo: Repository = Depends(get_repo)) -> dict:
    wl = repo.get("wishlists", _uuid_or_404(wishlist_id))
    if not wl or wl.get("deleted_at"):
        raise HTTPException(404, "wishlist not found")
    if wl["owner_user_id"] != user["id"]:
        raise HTTPException(403, "only the owner can reveal claims")
    after = wl.get("reveal_claims_after")
    if not after or timeutil.parse(after) > timeutil.now():
        raise HTTPException(403, "claims stay hidden until after the occasion")
    items = []
    for item in _items(repo, wl["id"]):
        active = claims.active_claims(repo, item["id"])
        items.append({"item_id": item["id"], "claimed": bool(active),
                      "claimer_name": active[0].get("claimer_name", "") if active else None})
    return {"items": items}
