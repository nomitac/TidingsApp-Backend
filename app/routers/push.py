from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import timeutil
from ..auth import current_user, get_repo
from ..repo import Repository

router = APIRouter(prefix="/v1", tags=["push"])


class TokenIn(BaseModel):
    token: str = Field(min_length=8, max_length=200, pattern=r"^[0-9a-fA-F]+$")
    platform: Literal["ios"] = "ios"
    environment: Literal["sandbox", "production"] = "production"


@router.post("/push-tokens")
def register_token(body: TokenIn, user: dict = Depends(current_user), repo: Repository = Depends(get_repo)) -> dict:
    now = timeutil.now_str()
    token = body.token.lower()
    existing = repo.select("push_tokens", eq={"token": token})
    row = {
        "id": existing[0]["id"] if existing else str(uuid.uuid4()),
        "user_id": user["id"],  # a device token moves to whoever registers it last
        "token": token,
        "platform": body.platform,
        "environment": body.environment,
        "created_at": existing[0]["created_at"] if existing else now,
        "updated_at": now,
        "deleted_at": None,
        "server_updated_at": now,
    }
    repo.upsert("push_tokens", row)
    return {"ok": True}
