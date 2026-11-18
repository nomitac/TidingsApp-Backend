"""Public wishlist page /w/{slug}: no app, no account. Guests can claim; claims are hidden from the
owner in the app (Sec. 8). A guest token cookie lets a guest release their own claim."""
from __future__ import annotations

import html
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import claims
from ..auth import get_app_settings, get_repo
from ..config import Settings
from ..repo import Repository
from ..schemas import norm_uuid

router = APIRouter(tags=["public"])

COOKIE = "tidings_guest"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def _wishlist(repo: Repository, slug: str) -> dict:
    found = [w for w in repo.select("wishlists", eq={"slug": slug})
             if not w.get("deleted_at") and w.get("is_public_link_enabled", True)]
    if not found:
        raise HTTPException(404, "This wishlist doesn't exist or is no longer shared.")
    return found[0]


def _money(cents: int | None, currency: str) -> str:
    if cents is None:
        return ""
    symbols = {"USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥", "MXN": "MX$"}
    if currency == "JPY":
        return f"¥{cents // 100:,}"
    return f"{symbols.get(currency, currency + ' ')}{cents // 100:,}.{cents % 100:02d}"


def _guest_token(request: Request) -> tuple[str, bool]:
    tok = request.cookies.get(COOKIE)
    if tok and 16 <= len(tok) <= 64:
        return tok, False
    return secrets.token_urlsafe(24), True


# Whimsy Addendum palette — "Sugar Cookie Morning" (light) / "Midnight at the North Pole" (dark).
CSS = """
:root{--bg:#FFFBF2;--surface:#FFFFFF;--surface-alt:#FDF0DC;--surface-festive:#FDECEA;--primary:#17603A;--primary-soft:#E3F2E4;
--accent:#BE2A30;--accent-text:#BE2A30;--gold:#F2C14E;--gold-text:#8A5A00;--ginger:#9A5B13;--link:#17603A;--text:#2E2118;--text-2:#6F5F4D;--border:#EAD9C2}
@media (prefers-color-scheme:dark){:root{--bg:#0D2018;--surface:#173529;--surface-alt:#1F4433;--surface-festive:#3A2320;--primary:#23804F;--primary-soft:#173F2A;
--accent:#C93A3E;--accent-text:#FF8A80;--gold-text:#F2C14E;--ginger:#E8A861;--link:#8FD6AE;--text:#FFF6E5;--text-2:#B9C6BB;--border:#2A4A3A}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:17px/1.45 -apple-system,BlinkMacSystemFont,"Inter","Segoe UI",sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:0 16px 64px}
header{position:relative;margin:0 -16px 18px;padding:26px 20px 22px;background:linear-gradient(135deg,#17603A,#23804F);color:#fff;border-radius:0 0 24px 24px;display:flex;align-items:center;gap:14px;overflow:hidden}
@media (prefers-color-scheme:dark){header{background:linear-gradient(135deg,#0D2018,#173529)}}
header .lights{position:absolute;left:0;right:0;top:0;height:16px;opacity:.9}
header svg.pip{flex:none;width:84px;height:100px}
header h1{font-size:26px;margin:4px 0 2px;color:#fff}header p{color:#FFF6E5;margin:0}
.brand{font-weight:700;letter-spacing:.06em;font-size:13px;text-transform:uppercase;color:#F2C14E}
.item{background:var(--surface);border:1px solid var(--border);border-radius:18px;padding:16px;margin:12px 0;display:flex;gap:14px}
.item img{width:84px;height:84px;object-fit:cover;border-radius:12px;background:var(--surface-alt);flex:none}
.body{flex:1;min-width:0}.title{font-weight:650;font-size:18px;margin:0 0 4px;overflow-wrap:anywhere}
.meta{color:var(--text-2);font-size:15px;margin:2px 0}.variant{display:inline-block;background:var(--surface-alt);border-radius:8px;padding:2px 8px;font-size:14px;margin:4px 0;font-weight:600}
.hearts{color:var(--accent-text)}a{color:var(--link)}
form{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}input{flex:1 1 140px;min-width:0;padding:10px 12px;border-radius:10px;border:1px solid var(--border);background:var(--bg);color:var(--text);font-size:16px}
button{padding:10px 16px;border-radius:10px;border:0;background:var(--primary);color:#fff;font-weight:600;font-size:16px;cursor:pointer}
button.secondary{background:transparent;color:var(--accent-text);border:1px solid var(--accent-text)}
.state{display:inline-flex;align-items:center;gap:6px;font-weight:600;margin-top:10px;color:var(--text-2)}
.state.mine{color:var(--link)}.note{background:var(--surface-alt);border-radius:14px;padding:12px 14px;color:var(--text);font-size:15px}
.msg{background:var(--surface-festive);border-left:4px solid var(--accent);padding:10px 14px;border-radius:8px;margin-bottom:12px}
footer{color:var(--text-2);font-size:13px;margin-top:28px;text-align:center}
"""

# Pip the Elf, waving — same shapes as the app's CrewArt, as inline SVG (no external assets).
PIP_WAVING_SVG = """<svg class="pip" viewBox="0 0 100 120" role="img" aria-label="Pip the Elf waving">
<g stroke="#2E2118" stroke-opacity="0.6" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round">
  <rect x="41" y="96" width="7" height="13" rx="2" fill="#0F4A2C"/>
  <rect x="52" y="96" width="7" height="13" rx="2" fill="#0F4A2C"/>
  <ellipse cx="43" cy="109.5" rx="7" ry="3.4" fill="#7A4A1E"/>
  <ellipse cx="57" cy="109.5" rx="7" ry="3.4" fill="#7A4A1E"/>
  <path d="M38 76 L31 88" fill="none" stroke-width="10.8"/>
  <path d="M38 76 L31 88" fill="none" stroke="#17603A" stroke-opacity="1" stroke-width="7"/>
  <path d="M62 76 Q79 74 84 62" fill="none" stroke-width="10.8"/>
  <path d="M62 76 Q79 74 84 62" fill="none" stroke="#17603A" stroke-opacity="1" stroke-width="7"/>
  <circle cx="84.5" cy="60.5" r="4.5" fill="#F6D3B3"/>
  <path d="M36 71 L64 71 Q67 85 70 100 Q50 103 30 100 Q33 85 36 71 Z" fill="#17603A"/>
  <rect x="32" y="87" width="36" height="5" rx="1" fill="#2E2118"/>
  <rect x="46.5" y="86" width="7" height="7" rx="1.5" fill="#F2C14E"/>
  <rect x="48.6" y="88.1" width="2.8" height="2.8" rx="0.5" fill="#2E2118" stroke="none"/>
  <rect x="56" y="70" width="6" height="15" rx="2" fill="#BE2A30"/>
  <rect x="35" y="65" width="30" height="8" rx="4" fill="#BE2A30"/>
  <polygon points="35,46 23,39 35,55" fill="#F6D3B3"/>
  <polygon points="65,46 77,39 65,55" fill="#F6D3B3"/>
  <circle cx="50" cy="50" r="17" fill="#F6D3B3"/>
  <polygon points="69,27 72.5,25.5 81.6,44.2 78.1,45.8" fill="#F2C14E"/>
  <polygon points="69,27 72.5,25.5 71.6,23.5 68.1,25.1" fill="#F6A6B2"/>
  <polygon points="78.1,45.8 81.6,44.2 81.5,51.5" fill="#F6D3B3"/>
  <path d="M32 42 Q47 15 80 9 Q67 23 68 42 Z" fill="#17603A"/>
  <rect x="30" y="37" width="40" height="8" rx="4" fill="#FFFBF2"/>
  <circle cx="81" cy="9" r="4.5" fill="#F2C14E"/>
  <line x1="81" y1="10" x2="81" y2="12.5" stroke-width="1.2"/>
  <rect x="19.5" y="83.5" width="15" height="19" rx="2" fill="#9A5B13"/>
  <rect x="21.5" y="86.5" width="11" height="14" rx="1" fill="#FFFBF2" stroke="none"/>
  <line x1="23.5" y1="91" x2="30.5" y2="91" stroke-width="1.1"/>
  <line x1="23.5" y1="94.5" x2="29.5" y2="94.5" stroke-width="1.1"/>
  <line x1="23.5" y1="98" x2="28" y2="98" stroke-width="1.1"/>
  <rect x="24" y="82" width="6" height="3.5" rx="1" fill="#F2C14E"/>
  <circle cx="32.5" cy="90" r="4.2" fill="#F6D3B3"/>
  <path d="M89.5 52.5 Q92.5 56 91.5 60.5" fill="none" stroke-width="1.4"/>
  <path d="M86 50 Q89 50.5 90.5 52" fill="none" stroke-width="1.4"/>
</g>
<ellipse cx="40.5" cy="56.4" rx="3" ry="1.8" fill="#F6A6B2" fill-opacity="0.7"/>
<ellipse cx="59.5" cy="56.4" rx="3" ry="1.8" fill="#F6A6B2" fill-opacity="0.7"/>
<circle cx="44" cy="52" r="2.2" fill="#2E2118"/>
<circle cx="44.8" cy="51.2" r="0.8" fill="#FFFFFF"/>
<circle cx="56" cy="52" r="2.2" fill="#2E2118"/>
<circle cx="56.8" cy="51.2" r="0.8" fill="#FFFFFF"/>
<path d="M45.5 58 Q50 62.8 54.5 58" fill="none" stroke="#2E2118" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

STRING_LIGHTS_SVG = """<svg class="lights" viewBox="0 0 360 16" preserveAspectRatio="none" aria-hidden="true">
<path d="M0 3 Q20 12 40 3 T80 3 T120 3 T160 3 T200 3 T240 3 T280 3 T320 3 T360 3" fill="none" stroke="rgba(255,246,229,.35)" stroke-width="1"/>
<g opacity=".2"><circle cx="20" cy="9" r="3" fill="#F2C14E"/><circle cx="60" cy="9" r="3" fill="#BE2A30"/><circle cx="100" cy="9" r="3" fill="#7FB069"/>
<circle cx="140" cy="9" r="3" fill="#F6A6B2"/><circle cx="180" cy="9" r="3" fill="#F2C14E"/><circle cx="220" cy="9" r="3" fill="#BE2A30"/>
<circle cx="260" cy="9" r="3" fill="#7FB069"/><circle cx="300" cy="9" r="3" fill="#F6A6B2"/><circle cx="340" cy="9" r="3" fill="#F2C14E"/></g></svg>"""



def render(wl: dict, items: list[dict], claim_state: dict[str, str], base_url: str, msg: str = "") -> str:
    e = html.escape
    title = wl.get("title") or "Wishlist"
    owner = wl.get("owner_name") or "Someone"
    page_url = f"{base_url.rstrip('/')}/w/{quote(wl['slug'])}"
    og_image = next((i["image_url"] for i in items if i.get("image_url")), "")
    cards = []
    for it in items:
        iid = it["id"]
        img = f'<img src="{e(it["image_url"])}" alt="" loading="lazy">' if it.get("image_url") else '<img alt="" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">'
        price = _money(it.get("price_cents"), it.get("currency", "USD"))
        link = f'<a href="{e(it["product_url"])}" rel="noopener nofollow" target="_blank">View in store</a>' if it.get("product_url") else ""
        state = claim_state.get(iid, "open")
        action_base = f"/w/{quote(wl['slug'])}/items/{iid}"
        if state == "mine":
            action = (f'<div class="state mine">✓ You claimed this</div>'
                      f'<form method="post" action="{action_base}/release"><button class="secondary" type="submit">Release</button></form>')
        elif state == "taken":
            action = '<div class="state">🦉🔒 Claimed — but by whom? My lips are sealed.</div>'
        elif wl.get("allow_guest_claims", True):
            action = (f'<form method="post" action="{action_base}/claim">'
                      f'<input name="claimer_name" placeholder="Your name" required maxlength="80" aria-label="Your name">'
                      f'<input name="claimer_email" type="email" placeholder="Email (optional)" maxlength="200" aria-label="Email (optional)">'
                      f'<button type="submit">Claim</button></form>')
        else:
            action = ""
        cards.append(f"""<div class="item">{img}<div class="body">
<p class="title">{e(it.get("title", ""))}</p>
{f'<span class="variant">{e(it["variant"])}</span>' if it.get("variant") else ""}
<p class="meta"><span class="hearts" aria-label="priority {it.get('priority', 2)} of 3">{"♥" * int(it.get("priority", 2))}</span> {e(price)} {link}</p>
{f'<p class="meta">{e(it["notes_public"])}</p>' if it.get("notes_public") else ""}
{action}</div></div>""")
    body = "\n".join(cards) or '<p class="note">Nothing on this list yet — check back soon.</p>'
    msg_html = f'<div class="msg" role="status">{e(msg)}</div>' if msg else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · {e(owner)}'s wishlist</title>
<meta property="og:type" content="website"><meta property="og:title" content="{e(owner)}'s wishlist: {e(title)}">
<meta property="og:description" content="Claim a gift so nobody doubles up — {e(owner)} won't see who claimed what.">
<meta property="og:url" content="{e(page_url)}">{f'<meta property="og:image" content="{e(og_image)}">' if og_image else ""}
<meta name="twitter:card" content="summary_large_image"><meta name="robots" content="noindex">
<style>{CSS}</style></head><body><div class="wrap">
<header>{STRING_LIGHTS_SVG}{PIP_WAVING_SVG}<div><div class="brand">Tidings</div><h1>{e(title)}</h1><p>{e(owner)}'s wishlist</p></div></header>
{msg_html}
<p class="note">Claim an item so other givers don't buy the same thing. <strong>{e(owner)} won't see what's been claimed</strong> — Holly the Owl keeps every claim sealed.</p>
{body}
<footer>Made with Tidings · gift lists that keep the surprise</footer></div></body></html>"""


MESSAGES = {
    "claimed": "You claimed it — thanks! Other givers will see it as taken.",
    "released": "Released — the item is open again.",
    "taken": "Sorry, someone else just claimed that one.",
    "name": "Please enter your name to claim.",
    "closed": "Guest claiming is turned off for this list.",
}


@router.get("/w/{slug}", response_class=HTMLResponse)
def public_wishlist(slug: str, request: Request, msg: str = "", repo: Repository = Depends(get_repo),
                    settings: Settings = Depends(get_app_settings)) -> HTMLResponse:
    wl = _wishlist(repo, slug)
    token, is_new = _guest_token(request)
    items = sorted([i for i in repo.select("wishlist_items", eq={"wishlist_id": wl["id"]}) if not i.get("deleted_at")],
                   key=lambda i: (i.get("sort_order", 0), -i.get("priority", 2), i.get("title", "")))
    state: dict[str, str] = {}
    for it in items:
        active = claims.active_claims(repo, it["id"])
        if active:
            state[it["id"]] = "mine" if any(c.get("guest_token") == token for c in active) else "taken"
    resp = HTMLResponse(render(wl, items, state, settings.public_base_url, MESSAGES.get(msg, "")))
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if is_new:
        resp.set_cookie(COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https")
    return resp


def _redirect(request: Request, slug: str, msg: str, token: str) -> RedirectResponse:
    r = RedirectResponse(f"/w/{quote(slug)}?msg={msg}", status_code=303)
    r.set_cookie(COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
                 secure=request.url.scheme == "https")
    return r


def _item_in(repo: Repository, wl: dict, item_id: str) -> str:
    try:
        iid = norm_uuid(item_id)
    except ValueError:
        raise HTTPException(404, "item not found") from None
    item = repo.get("wishlist_items", iid)
    if not item or item["wishlist_id"] != wl["id"] or item.get("deleted_at"):
        raise HTTPException(404, "item not found")
    return iid


@router.post("/w/{slug}/items/{item_id}/claim")
def guest_claim(slug: str, item_id: str, request: Request, claimer_name: str = Form(""), claimer_email: str = Form(""),
                repo: Repository = Depends(get_repo), settings: Settings = Depends(get_app_settings)) -> RedirectResponse:
    wl = _wishlist(repo, slug)
    iid = _item_in(repo, wl, item_id)
    token, _ = _guest_token(request)
    if not claimer_name.strip():
        return _redirect(request, slug, "name", token)
    try:
        claims.claim(repo, iid, guest_token=token, name=claimer_name, email=claimer_email)
    except claims.ClaimError as e:
        return _redirect(request, slug, "taken" if e.status == 409 else "closed", token)
    return _redirect(request, slug, "claimed", token)


@router.post("/w/{slug}/items/{item_id}/release")
def guest_release(slug: str, item_id: str, request: Request, repo: Repository = Depends(get_repo),
                  settings: Settings = Depends(get_app_settings)) -> RedirectResponse:
    wl = _wishlist(repo, slug)
    iid = _item_in(repo, wl, item_id)
    token, _ = _guest_token(request)
    claims.release(repo, iid, guest_token=token)
    return _redirect(request, slug, "released", token)
