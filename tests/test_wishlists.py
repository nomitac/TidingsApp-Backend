"""Spec acceptance test 4: hidden claiming."""
import re
import uuid

from fastapi.testclient import TestClient

from app import timeutil


def _wishlist(owner, slug="mom-xmas", reveal=None):
    wl = {"id": str(uuid.uuid4()), "owner_user_id": owner.user_id, "owner_name": "Mom", "title": "Christmas 2026",
          "slug": slug, "reveal_claims_after": reveal}
    items = [{"id": str(uuid.uuid4()), "wishlist_id": wl["id"], "title": t, "price_cents": p, "variant": v, "priority": 3}
             for t, p, v in (("Wool Scarf", 4500, "Color: Green"), ("Pottery Class", 12000, ""))]
    assert owner.sync({"wishlists": [wl], "wishlist_items": items}).json()["rejected"] == []
    return wl, items


def test_guest_claim_hidden_from_owner(app, make_user):
    owner = make_user("Mom")
    wl, items = _wishlist(owner)
    guest1, guest2 = TestClient(app), TestClient(app)

    page = guest1.get("/w/mom-xmas")
    assert page.status_code == 200 and "Wool Scarf" in page.text and "og:title" in page.text
    assert page.text.count(">Claim</button>") == 2
    r = guest1.post(f"/w/mom-xmas/items/{items[0]['id']}/claim",
                    data={"claimer_name": "Aunt Zelda", "claimer_email": "z@example.com"}, follow_redirects=False)
    assert r.status_code == 303
    assert "You claimed this" in guest1.get("/w/mom-xmas").text

    p2 = guest2.get("/w/mom-xmas").text
    assert "Claimed — but by whom? My lips are sealed." in p2
    assert p2.count(">Claim</button>") == 1
    assert "Aunt Zelda" not in p2
    # Second guest can't steal it.
    guest2.post(f"/w/mom-xmas/items/{items[0]['id']}/claim", data={"claimer_name": "Cousin"})
    assert "Claimed — but by whom? My lips are sealed." in guest2.get("/w/mom-xmas").text

    # Owner (logged in) sees no claim state in the API response.
    resp = owner.get("/v1/wishlists/by-slug/mom-xmas")
    assert resp.json()["is_owner"] is True
    assert all(i["claimed"] is None and i["claimed_by_me"] is None for i in resp.json()["items"])
    assert "Aunt Zelda" not in resp.text and "z@example.com" not in resp.text
    assert not re.search(r'"claimed"\s*:\s*(true|false)', resp.text)
    # ...nor via sync.
    sync_text = owner.sync().text
    assert "Aunt Zelda" not in sync_text and "\"claimed\"" not in sync_text and "claimer" not in sync_text

    # Guest releases → open again.
    guest1.post(f"/w/mom-xmas/items/{items[0]['id']}/release")
    assert "Claimed — but by whom? My lips are sealed." not in guest2.get("/w/mom-xmas").text


def test_app_user_claims(make_user):
    owner, giver, other = make_user("Mom"), make_user("Sis"), make_user("Bro")
    wl, items = _wishlist(owner)
    iid = items[1]["id"]
    assert owner.post(f"/v1/wishlist-items/{iid}/claim", {"claimer_name": "me"}).status_code == 403
    assert giver.post(f"/v1/wishlist-items/{iid}/claim", {"claimer_name": "Sis"}).status_code == 200
    assert other.post(f"/v1/wishlist-items/{iid}/claim", {}).status_code == 409
    view = {i["id"]: i for i in other.get("/v1/wishlists/by-slug/mom-xmas").json()["items"]}
    assert view[iid]["claimed"] is True and view[iid]["claimed_by_me"] is False
    mine = {i["id"]: i for i in giver.get("/v1/wishlists/by-slug/mom-xmas").json()["items"]}
    assert mine[iid]["claimed_by_me"] is True
    # Upgrade to purchased keeps the claim.
    assert giver.post(f"/v1/wishlist-items/{iid}/claim", {"status": "purchased"}).status_code == 200
    assert other.post(f"/v1/wishlist-items/{iid}/release").status_code == 404
    assert giver.post(f"/v1/wishlist-items/{iid}/release").status_code == 200
    assert other.get("/v1/wishlists/by-slug/mom-xmas").json()["items"][1]["claimed"] is False


def test_reveal_only_after_date(make_user):
    owner, giver = make_user("Mom"), make_user("Sis")
    wl, items = _wishlist(owner, reveal="2099-01-01T00:00:00.000Z")
    giver.post(f"/v1/wishlist-items/{items[0]['id']}/claim", {"claimer_name": "Sis"})
    assert owner.get(f"/v1/wishlists/{wl['id']}/reveal").status_code == 403
    assert giver.get(f"/v1/wishlists/{wl['id']}/reveal").status_code == 403

    wl2, items2 = _wishlist(owner, slug="past", reveal="2020-01-01T00:00:00.000Z")
    giver.post(f"/v1/wishlist-items/{items2[0]['id']}/claim", {"claimer_name": "Sis"})
    rev = {i["item_id"]: i for i in owner.get(f"/v1/wishlists/{wl2['id']}/reveal").json()["items"]}
    assert rev[items2[0]["id"]]["claimed"] is True and rev[items2[0]["id"]]["claimer_name"] == "Sis"
    assert rev[items2[1]["id"]]["claimed"] is False and rev[items2[1]["id"]]["claimer_name"] is None


def test_guest_claims_disabled_and_private_link(app, make_user, repo):
    owner = make_user()
    wl, items = _wishlist(owner, slug="closed")
    repo.upsert("wishlists", {**repo.get("wishlists", wl["id"]), "allow_guest_claims": False})
    g = TestClient(app)
    assert ">Claim</button>" not in g.get("/w/closed").text
    g.post(f"/w/closed/items/{items[0]['id']}/claim", data={"claimer_name": "X"})
    assert "Claimed — but by whom? My lips are sealed." not in g.get("/w/closed").text
    repo.upsert("wishlists", {**repo.get("wishlists", wl["id"]), "is_public_link_enabled": False})
    assert g.get("/w/closed").status_code == 404
    assert g.get("/w/does-not-exist").status_code == 404


def test_html_is_escaped(app, make_user):
    owner = make_user()
    wl = {"id": str(uuid.uuid4()), "owner_user_id": owner.user_id, "owner_name": "<b>x</b>", "title": "<script>alert(1)</script>", "slug": "xss"}
    owner.sync({"wishlists": [wl]})
    page = TestClient(app).get("/w/xss").text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
