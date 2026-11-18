"""App-facing auth: shared app key header + per-user ID check."""
from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, Request

from .config import Settings
from .repo import Repository
from .schemas import norm_uuid


def get_repo(request: Request) -> Repository:
    return request.app.state.repo


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def require_app_key(
    x_app_key: str | None = Header(default=None),
    settings: Settings = Depends(get_app_settings),
) -> None:
    if not x_app_key or not hmac.compare_digest(x_app_key.encode(), settings.app_key.encode()):
        raise HTTPException(status_code=401, detail="invalid app key")


def header_user_id(x_user_id: str | None = Header(default=None), _: None = Depends(require_app_key)) -> str:
    """User id from header, validated as a UUID but not required to be registered."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="missing user id")
    try:
        return norm_uuid(x_user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid user id") from None


def current_user(user_id: str = Depends(header_user_id), repo: Repository = Depends(get_repo)) -> dict:
    user = repo.get("users", user_id)
    if not user or user.get("deleted_at"):
        raise HTTPException(status_code=401, detail="unknown user")
    return user
