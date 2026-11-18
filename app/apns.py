"""APNs sender: token-based auth (ES256 JWT via PyJWT) over HTTP/2 (httpx). No-op when unconfigured."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt

from .config import Settings

log = logging.getLogger("tidings.apns")

_token_cache: dict[str, tuple[str, float]] = {}


def is_configured(s: Settings) -> bool:
    return bool(s.apns_key_id and s.apns_team_id and s.apns_private_key)


def provider_token(s: Settings) -> str:
    cached = _token_cache.get(s.apns_key_id)
    if cached and time.time() - cached[1] < 50 * 60:  # Apple: refresh between 20 and 60 min
        return cached[0]
    key = s.apns_private_key.replace("\\n", "\n")
    token = jwt.encode({"iss": s.apns_team_id, "iat": int(time.time())}, key, algorithm="ES256", headers={"kid": s.apns_key_id})
    _token_cache[s.apns_key_id] = (token, time.time())
    return token


async def send(s: Settings, device_token: str, title: str, body: str, sandbox: bool | None = None, extra: dict[str, Any] | None = None) -> bool:
    if not is_configured(s):
        log.info("APNs not configured; skipping push %r", title)
        return False
    use_sandbox = s.apns_use_sandbox if sandbox is None else sandbox
    host = "https://api.sandbox.push.apple.com" if use_sandbox else "https://api.push.apple.com"
    payload = {"aps": {"alert": {"title": title, "body": body}, "sound": "default"}, **(extra or {})}
    headers = {
        "authorization": f"bearer {provider_token(s)}",
        "apns-topic": s.apns_bundle_id,
        "apns-push-type": "alert",
    }
    try:
        async with httpx.AsyncClient(http2=True, timeout=10) as client:
            r = await client.post(f"{host}/3/device/{device_token}", json=payload, headers=headers)
        if r.status_code != 200:
            log.warning("APNs %s: %s", r.status_code, r.text)
        return r.status_code == 200
    except httpx.HTTPError as e:
        log.warning("APNs error: %s", e)
        return False


async def send_to_user(s: Settings, repo, user_id: str, title: str, body: str) -> int:
    sent = 0
    for t in repo.select("push_tokens", eq={"user_id": user_id, "deleted_at": None}):
        if await send(s, t["token"], title, body, sandbox=t.get("environment") != "production"):
            sent += 1
    return sent
