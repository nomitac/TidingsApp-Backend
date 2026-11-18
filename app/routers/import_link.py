from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth import current_user
from ..link_parser import parse_product, store_for_url

router = APIRouter(prefix="/v1", tags=["import"])

UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)
MAX_BYTES = 3_000_000


async def is_public_host(host: str) -> bool:
    """Basic SSRF guard: refuse hosts resolving to private, loopback or link-local addresses."""
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False
    return True


class ImportIn(BaseModel):
    url: str


async def fetch_html(url: str, transport: httpx.AsyncBaseTransport | None = None) -> str:
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=8.0, transport=transport,
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-US,en;q=0.9"},
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text[:MAX_BYTES]


@router.post("/import-link")
async def import_link(body: ImportIn, request: Request, _: dict = Depends(current_user)) -> dict:
    url = body.url.strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise HTTPException(422, "url must be http(s)")
    failure = {"ok": False, "url": url, "title": "", "image_url": "", "price_cents": None, "currency": None,
               "store": store_for_url(url), "variant": ""}
    transport = getattr(request.app.state, "http_transport", None)
    if transport is None and not await is_public_host(p.hostname):
        return {**failure, "error": "That address can't be reached. You can still save it manually."}
    try:
        html = await fetch_html(url, transport)
    except (httpx.HTTPError, UnicodeDecodeError) as e:
        return {**failure, "error": f"Couldn't load the page ({type(e).__name__}). You can still save it manually."}
    return parse_product(html, url)
