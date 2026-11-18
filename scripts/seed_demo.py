"""Seed a local backend with a family member's wishlist (slug: linda-wishlist) for the iOS `-demo` mode.

Usage: python scripts/seed_demo.py [base_url] [app_key]
"""
import datetime
import json
import sys
import urllib.request
import uuid

B = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
K = sys.argv[2] if len(sys.argv) > 2 else "dev-app-key"


def call(method, path, uid, body=None):
    req = urllib.request.Request(B + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-App-Key": K, "X-User-Id": uid, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read() or b"{}")


now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
linda, jess = str(uuid.uuid4()), str(uuid.uuid4())
call("POST", "/v1/users", linda, {"id": linda, "display_name": "Linda", "default_currency": "USD"})
call("POST", "/v1/users", jess, {"id": jess, "display_name": "Jess", "default_currency": "USD"})
wid = str(uuid.uuid4())
items = [("Cashmere throw blanket", "Oatmeal", 12900, 3, "https://images.unsplash.com/photo-1580301762395-21ce84d00bc6?w=400"),
         ("Herb garden kit", "", 3999, 2, "https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=400"),
         ("Le Creuset mug set", "Set of 2 · Sea Salt", 6000, 2, ""),
         ("Mystery novel boxed set", "", 4500, 1, "")]
rows = [{"id": str(uuid.uuid4()), "wishlist_id": wid, "title": t, "variant": v, "price_cents": p, "currency": "USD",
         "priority": pr, "image_url": img, "product_url": "", "notes_public": "", "sort_order": i,
         "created_at": now, "updated_at": now} for i, (t, v, p, pr, img) in enumerate(items)]
r = call("POST", "/v1/sync", linda, {"since": None, "changes": {
    "wishlists": [{"id": wid, "owner_user_id": linda, "owner_name": "Linda", "title": "Linda's Wishlist", "slug": "linda-wishlist",
                   "is_public_link_enabled": True, "allow_guest_claims": True, "created_at": now, "updated_at": now}],
    "wishlist_items": rows}})
call("POST", f"/v1/wishlist-items/{rows[1]['id']}/claim", jess, {"claimer_name": "Jess", "status": "claimed"})
print("seeded linda-wishlist; rejected:", r.get("rejected"))
