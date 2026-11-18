"""Spec acceptance test 3 + invites."""
from tests.conftest import gift_row, recipient_row, year_row


def _setup_shared_year(a, b):
    y = year_row(a.user_id)
    a.sync({"occasion_years": [y]})
    code = a.post(f"/v1/years/{y['id']}/invites").json()["code"]
    r = b.post(f"/v1/invites/{code}/accept", {"display_name": "Bea"})
    assert r.status_code == 200 and r.json()["occasion_year_id"] == y["id"]
    return y


def test_invite_accept_then_sync_returns_year(make_user):
    a, b = make_user("Alex"), make_user("Bea")
    before = b.sync().json()["server_time"]
    y = year_row(a.user_id)
    r = recipient_row(y["id"], "Grandpa")
    a.sync({"occasion_years": [y], "recipients": [r]})
    code = a.post(f"/v1/years/{y['id']}/invites").json()["code"]
    assert len(code) == 8
    assert b.post(f"/v1/invites/{code}/accept", {"display_name": "Bea"}).status_code == 200
    # Even with an old `since`, the newly shared year is fully pulled.
    ch = b.sync(since=before).json()["changes"]
    assert [x["id"] for x in ch["occasion_years"]] == [y["id"]]
    assert [x["name"] for x in ch["recipients"]] == ["Grandpa"]
    members = ch["year_members"]
    assert members[0]["user_id"] == b.user_id and members[0]["status"] == "accepted"


def test_non_owner_cannot_invite_and_owner_cannot_accept(make_user):
    a, b = make_user(), make_user()
    y = year_row(a.user_id)
    a.sync({"occasion_years": [y]})
    assert b.post(f"/v1/years/{y['id']}/invites").status_code == 403
    code = a.post(f"/v1/years/{y['id']}/invites").json()["code"]
    assert a.post(f"/v1/invites/{code}/accept", {}).status_code == 400
    assert b.post("/v1/invites/NOPE1234/accept", {}).status_code == 404


def test_surprise_redacted_for_target(make_user):
    a, b = make_user("Alex"), make_user("Bea")
    y = _setup_shared_year(a, b)
    rec_b = recipient_row(y["id"], "Bea", linked_user_id=b.user_id, notes_private="loves jade", budget_cents=30000,
                          sizes_notes="Size M", shipping_address="1 Secret Lane")
    rec_mom = recipient_row(y["id"], "Mom")
    surprise = gift_row(y["id"], rec_b["id"], title="Tiffany Bracelet", status="ordered", price_paid_cents=45000,
                        store="Tiffany", image_url="https://img.example/bracelet.jpg", product_url="https://tiffany.example/b",
                        variant="Rose gold", notes_private="engrave B", is_surprise_for_user_id=b.user_id)
    normal = gift_row(y["id"], rec_mom["id"], title="Diptyque Candle", price_paid_cents=5800, status="ordered")
    log = {"id": surprise["id"].replace(surprise["id"][:8], "aaaaaaaa"), "occasion_year_id": y["id"], "actor_user_id": a.user_id,
           "actor_name": "Alex", "entity_type": "gift", "entity_id": surprise["id"], "action": "purchased",
           "summary_redacted": "Alex bought a surprise", "summary_full": "Alex bought Tiffany Bracelet for Bea — $450",
           "surprise_for_user_id": b.user_id}
    assert a.sync({"recipients": [rec_b, rec_mom], "gifts": [surprise, normal], "activity_log": [log]}).json()["rejected"] == []

    resp = b.sync()
    raw = resp.text
    for secret in ("Tiffany", "Bracelet", "45000", "bracelet.jpg", "tiffany.example", "Rose gold", "engrave", "loves jade",
                   "Secret Lane", "30000", "Size M"):
        assert secret not in raw, secret
    body = resp.json()
    assert [g["id"] for g in body["changes"]["gifts"]] == [normal["id"]]
    assert body["redacted_gifts"] == [{"id": surprise["id"], "occasion_year_id": y["id"], "recipient_id": rec_b["id"],
                                       "status": "ordered", "created_at": surprise["created_at"],
                                       "updated_at": surprise["updated_at"], "deleted_at": None}]
    assert body["changes"]["activity_log"][0]["summary_full"] == "Alex bought a surprise"

    # Totals for B: counts include the surprise, money does not.
    t = b.get(f"/v1/years/{y['id']}/totals").json()
    assert t["spent_cents"] == 5800 and t["gifts_by_status"]["ordered"] == 2
    assert "Tiffany" not in b.get(f"/v1/years/{y['id']}/totals").text

    # B cannot overwrite the surprise, nor create one for themself.
    over = {**surprise, "title": "peek", "is_surprise_for_user_id": None, "updated_at": "2030-01-01T00:00:00.000Z"}
    mine = gift_row(y["id"], rec_b["id"], is_surprise_for_user_id=b.user_id)
    rej = b.sync({"gifts": [over, mine]}).json()["rejected"]
    assert [x["reason"] for x in rej] == ["surprise", "surprise"]
    assert "Tiffany Bracelet" in a.sync().text  # owner still sees it intact
