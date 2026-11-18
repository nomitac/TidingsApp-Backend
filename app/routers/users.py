from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import timeutil
from ..auth import current_user, get_repo, header_user_id
from ..repo import Repository
from ..schemas import norm_uuid

router = APIRouter(prefix="/v1", tags=["users"])


class UserIn(BaseModel):
    id: str
    display_name: str = ""
    default_currency: str = "USD"


def is_pro(user: dict) -> bool:
    if not user.get("is_pro"):
        return False
    exp = user.get("pro_expires_at")
    return exp is None or timeutil.parse(exp) > timeutil.now()


def me_payload(user: dict) -> dict:
    return {
        "id": user["id"],
        "display_name": user.get("display_name", ""),
        "default_currency": user.get("default_currency", "USD"),
        "is_pro": is_pro(user),
        "pro_expires_at": user.get("pro_expires_at"),
    }


@router.post("/users")
def register(body: UserIn, user_id: str = Depends(header_user_id), repo: Repository = Depends(get_repo)) -> dict:
    try:
        body_id = norm_uuid(body.id)
    except ValueError:
        raise HTTPException(400, "invalid id") from None
    if body_id != user_id:
        raise HTTPException(403, "id must match X-User-Id")
    cur = (body.default_currency or "USD").upper()
    if len(cur) != 3 or not cur.isalpha():
        raise HTTPException(422, "invalid currency")
    now = timeutil.now_str()
    existing = repo.get("users", user_id) or {}
    row = {
        "id": user_id,
        "display_name": body.display_name.strip()[:80],
        "default_currency": cur,
        "is_pro": existing.get("is_pro", False),
        "pro_expires_at": existing.get("pro_expires_at"),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
        "deleted_at": None,
        "server_updated_at": now,
    }
    return me_payload(repo.upsert("users", row))


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    return me_payload(user)
