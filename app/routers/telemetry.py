"""Analytics and error logging into our own tables (no third-party SDK)."""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import timeutil
from ..auth import current_user, get_repo
from ..repo import Repository

router = APIRouter(prefix="/v1", tags=["telemetry"])
MAX_BATCH = 500


class EventIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    properties: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str | None = None


class EventsIn(BaseModel):
    events: list[EventIn] = Field(max_length=MAX_BATCH)


class ErrorIn(BaseModel):
    message: str = Field(max_length=4000)
    context: dict[str, Any] = Field(default_factory=dict)
    occurred_at: str | None = None
    app_version: str = ""


class ErrorsIn(BaseModel):
    errors: list[ErrorIn] = Field(max_length=MAX_BATCH)


def _ts(v: str | None, fallback: str) -> str:
    try:
        return timeutil.normalize(v) if v else fallback
    except ValueError:
        return fallback


@router.post("/events")
def events(body: EventsIn, user: dict = Depends(current_user), repo: Repository = Depends(get_repo)) -> dict:
    now = timeutil.now_str()
    rows = [{"id": str(uuid.uuid4()), "user_id": user["id"], "name": e.name, "properties": e.properties,
             "occurred_at": _ts(e.occurred_at, now), "received_at": now} for e in body.events]
    return {"accepted": repo.insert_many("analytics_events", rows)}


@router.post("/errors")
def errors(body: ErrorsIn, user: dict = Depends(current_user), repo: Repository = Depends(get_repo)) -> dict:
    now = timeutil.now_str()
    rows = [{"id": str(uuid.uuid4()), "user_id": user["id"], "message": e.message, "context": e.context,
             "occurred_at": _ts(e.occurred_at, now), "app_version": e.app_version[:40], "received_at": now} for e in body.errors]
    return {"accepted": repo.insert_many("error_logs", rows)}
