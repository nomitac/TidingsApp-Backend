"""StoreKit 2 entitlement mirror.

NOTE: the signed transaction (JWS) is stored and its payload is decoded to cross-check
product/expiry, but its Apple certificate chain is NOT yet verified. Before charging real
money, verify with Apple's App Store Server API / x5c chain (marked `verified=false` until then).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import timeutil
from ..auth import current_user, get_repo
from ..repo import Repository
from .users import is_pro

router = APIRouter(prefix="/v1", tags=["subscriptions"])

PRODUCTS = {"tidings.pro.yearly", "tidings.pro.monthly", "tidings.pro.lifetime"}


class SubscriptionIn(BaseModel):
    product_id: str
    transaction_id: str
    original_transaction_id: str = ""
    expires_at: str | None = None
    signed_transaction: str = ""


@router.post("/subscriptions")
def record(body: SubscriptionIn, user: dict = Depends(current_user), repo: Repository = Depends(get_repo)) -> dict:
    if body.product_id not in PRODUCTS:
        raise HTTPException(422, "unknown product")
    expires = timeutil.normalize(body.expires_at) if body.expires_at else None
    if body.signed_transaction:
        try:
            payload = jwt.decode(body.signed_transaction, options={"verify_signature": False})
        except jwt.PyJWTError:
            raise HTTPException(422, "malformed signed transaction") from None
        if payload.get("productId") not in (None, body.product_id):
            raise HTTPException(422, "product mismatch")
        if payload.get("expiresDate"):
            expires = timeutil.fmt(datetime.fromtimestamp(payload["expiresDate"] / 1000, tz=timezone.utc))
    lifetime = body.product_id.endswith("lifetime")
    if not lifetime and not expires:
        raise HTTPException(422, "subscription needs expires_at")
    now = timeutil.now_str()
    repo.upsert("subscriptions", {
        "id": str(uuid.uuid4()), "user_id": user["id"], "product_id": body.product_id,
        "transaction_id": body.transaction_id, "original_transaction_id": body.original_transaction_id,
        "expires_at": None if lifetime else expires, "signed_transaction": body.signed_transaction,
        "verified": False, "created_at": now,
    })
    new_exp = None if lifetime else expires
    if user.get("is_pro") and user.get("pro_expires_at") is None:
        new_exp = None  # lifetime already owned
    elif not lifetime and user.get("pro_expires_at") and user.get("is_pro"):
        new_exp = max(new_exp, user["pro_expires_at"], key=timeutil.parse)
    updated = repo.upsert("users", {**user, "is_pro": True, "pro_expires_at": new_exp, "updated_at": now, "server_updated_at": now})
    return {"is_pro": is_pro(updated), "pro_expires_at": updated.get("pro_expires_at")}
