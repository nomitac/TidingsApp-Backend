from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from .. import access, apns, timeutil
from ..auth import current_user, get_app_settings, get_repo
from ..config import Settings
from ..repo import Repository
from ..schemas import norm_uuid

router = APIRouter(prefix="/v1", tags=["invites"])

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(8))


@router.post("/years/{year_id}/invites")
def create_invite(year_id: str, user: dict = Depends(current_user), repo: Repository = Depends(get_repo),
                  settings: Settings = Depends(get_app_settings)) -> dict:
    try:
        year_id = norm_uuid(year_id)
    except ValueError:
        raise HTTPException(404, "year not found") from None
    if access.role_in_year(repo, user["id"], year_id) != "owner":
        raise HTTPException(403, "only the owner can invite co-shoppers")
    now = timeutil.now()
    row = {
        "id": str(uuid.uuid4()),
        "code": new_code(),
        "occasion_year_id": year_id,
        "created_by": user["id"],
        "expires_at": timeutil.fmt(now + timedelta(days=settings.invite_ttl_days)),
        "accepted_by": None,
        "created_at": timeutil.fmt(now),
        "updated_at": timeutil.fmt(now),
        "deleted_at": None,
        "server_updated_at": timeutil.fmt(now),
    }
    repo.upsert("invites", row)
    return {"code": row["code"], "expires_at": row["expires_at"]}


class AcceptIn(BaseModel):
    display_name: str = ""


@router.post("/invites/{code}/accept")
def accept_invite(code: str, body: AcceptIn, background: BackgroundTasks, user: dict = Depends(current_user),
                  repo: Repository = Depends(get_repo), settings: Settings = Depends(get_app_settings)) -> dict:
    invites = [i for i in repo.select("invites", eq={"code": code.strip().upper()}) if not i.get("deleted_at")]
    if not invites:
        raise HTTPException(404, "invite not found")
    inv = invites[0]
    if timeutil.parse(inv["expires_at"]) < timeutil.now():
        raise HTTPException(410, "invite expired")
    year = repo.get("occasion_years", inv["occasion_year_id"])
    if not year or year.get("deleted_at"):
        raise HTTPException(404, "year not found")
    if year["owner_id"] == user["id"]:
        raise HTTPException(400, "you already own this list")

    now = timeutil.now_str()
    existing = repo.select("year_members", eq={"occasion_year_id": year["id"], "user_id": user["id"]})
    name = body.display_name.strip() or user.get("display_name", "")
    member = {
        "id": existing[0]["id"] if existing else str(uuid.uuid4()),
        "occasion_year_id": year["id"],
        "user_id": user["id"],
        "role": "co_shopper",
        "invited_email": existing[0].get("invited_email", "") if existing else "",
        "display_name": name,
        "status": "accepted",
        "created_at": existing[0]["created_at"] if existing else now,
        "updated_at": now,
        "deleted_at": None,
        "server_updated_at": now,
    }
    repo.upsert("year_members", member)
    repo.upsert("invites", {**inv, "accepted_by": user["id"], "updated_at": now, "server_updated_at": now})
    background.add_task(apns.send_to_user, settings, repo, year["owner_id"], "Co-shopper joined",
                        f"{name or 'Your co-shopper'} joined {year.get('name', 'your list')}")
    return {"occasion_year_id": year["id"]}
