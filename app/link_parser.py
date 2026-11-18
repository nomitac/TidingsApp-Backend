"""Product page parsing (spec Sec. 9). Pure: HTML string in, product dict out.

Priority: JSON-LD Product > OpenGraph / Twitter meta > <title>.
"""
from __future__ import annotations

import html as htmllib
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urljoin, urlparse

STORE_NAMES = {
    "amazon": "Amazon",
    "target": "Target",
    "etsy": "Etsy",
    "walmart": "Walmart",
    "bestbuy": "Best Buy",
    "sephora": "Sephora",
    "nordstrom": "Nordstrom",
    "apple": "Apple",
}

_LD_RE = re.compile(r"<script[^>]*type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.S | re.I)
_META_RE = re.compile(r"<meta\b[^>]*>", re.I)
_ATTR_RE = re.compile(r"([a-zA-Z_:\-]+)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def store_for_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""
    labels = host.split(".")
    for key, name in STORE_NAMES.items():
        if key in labels:
            return name
    return host


def parse_price_cents(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        d = Decimal(str(value))
    else:
        s = str(value).strip()
        s = re.sub(r"[^\d.,]", "", s)
        if not s:
            return None
        # "1.299,99" (EU) vs "1,299.99" (US): last separator is the decimal one if followed by 2 digits.
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            head, _, tail = s.rpartition(",")
            s = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else s.replace(",", "")
        try:
            d = Decimal(s)
        except InvalidOperation:
            return None
    if d < 0:
        return None
    return int((d * 100).quantize(Decimal(1)))


def _clean(s: Any) -> str:
    if s is None:
        return ""
    return re.sub(r"\s+", " ", htmllib.unescape(str(s))).strip()


def _iter_ld_nodes(data: Any):
    if isinstance(data, list):
        for x in data:
            yield from _iter_ld_nodes(x)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_ld_nodes(data["@graph"])


def _is_product(node: dict) -> bool:
    t = node.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(isinstance(x, str) and x.lower() in ("product", "productgroup") for x in types)


def _image(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _image(value[0])
    if isinstance(value, dict):
        return value.get("url") or value.get("contentUrl") or ""
    return ""


def _offer(offers: Any) -> tuple[Any, Any]:
    """Returns (price, currency) from Offer / AggregateOffer / list of offers."""
    if isinstance(offers, list):
        for o in offers:
            p, c = _offer(o)
            if p not in (None, ""):
                return p, c
        return None, None
    if isinstance(offers, dict):
        price = offers.get("price", offers.get("lowPrice"))
        currency = offers.get("priceCurrency")
        if price is None and isinstance(offers.get("priceSpecification"), dict):
            spec = offers["priceSpecification"]
            price, currency = spec.get("price"), spec.get("priceCurrency", currency)
        return (None if price == "" else price), currency
    return None, None


def _variant(node: dict) -> str:
    parts = []
    for key, label in (("color", "Color"), ("size", "Size"), ("style", "Style"), ("material", "Material")):
        v = node.get(key)
        if isinstance(v, dict):
            v = v.get("name")
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        if v:
            parts.append(f"{label}: {_clean(v)}")
    return " · ".join(parts)


def _meta(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tag in _META_RE.findall(html):
        attrs = {k.lower(): v.strip("\"'") for k, v in _ATTR_RE.findall(tag)}
        key = (attrs.get("property") or attrs.get("name") or attrs.get("itemprop") or "").lower()
        if key and "content" in attrs and key not in out:
            out[key] = _clean(attrs["content"])
    return out


def parse_product(html: str, url: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": False,
        "url": url,
        "title": "",
        "image_url": "",
        "price_cents": None,
        "currency": None,
        "store": store_for_url(url),
        "variant": "",
        "error": None,
    }
    html = html or ""

    for block in _LD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _iter_ld_nodes(data):
            if not _is_product(node):
                continue
            result["title"] = result["title"] or _clean(node.get("name"))
            result["image_url"] = result["image_url"] or _image(node.get("image"))
            price, currency = _offer(node.get("offers"))
            if result["price_cents"] is None:
                result["price_cents"] = parse_price_cents(price)
                result["currency"] = (str(currency).upper() if currency else None) if result["price_cents"] is not None else None
            result["variant"] = result["variant"] or _variant(node)
            if isinstance(node.get("brand"), dict) and not result["store"]:
                result["store"] = _clean(node["brand"].get("name"))

    meta = _meta(html)
    if not result["title"]:
        result["title"] = meta.get("og:title") or meta.get("twitter:title") or ""
    if not result["image_url"]:
        result["image_url"] = (
            meta.get("og:image:secure_url") or meta.get("og:image") or meta.get("twitter:image") or ""
        )
    if result["price_cents"] is None:
        amount = meta.get("product:price:amount") or meta.get("og:price:amount")
        cents = parse_price_cents(amount)
        if cents is not None:
            result["price_cents"] = cents
            cur = meta.get("product:price:currency") or meta.get("og:price:currency")
            result["currency"] = cur.upper() if cur else None
    if not result["title"]:
        m = _TITLE_RE.search(html)
        if m:
            result["title"] = _clean(m.group(1))

    if result["image_url"]:
        result["image_url"] = urljoin(url, result["image_url"])
    result["ok"] = bool(result["title"])
    if not result["ok"]:
        result["error"] = "Could not read product details. You can still save it manually."
    return result
