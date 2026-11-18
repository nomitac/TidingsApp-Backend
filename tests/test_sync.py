from tests.conftest import gift_row, recipient_row, year_row


def test_create_and_pull(make_user):
    a = make_user()
    y = year_row(a.user_id)
    r = recipient_row(y["id"])
    g = gift_row(y["id"], r["id"])
    body = a.sync({"occasion_years": [y], "recipients": [r], "gifts": [g]}).json()
    assert body["rejected"] == []
    assert {x["id"] for x in body["changes"]["gifts"]} == {g["id"]}
    assert "server_updated_at" not in body["changes"]["gifts"][0]
    assert body["changes"]["gifts"][0]["created_by"] == a.user_id


def test_lww_older_does_not_overwrite(make_user):
    a = make_user()
    y = year_row(a.user_id)
    r = recipient_row(y["id"])
    g = gift_row(y["id"], r["id"], title="New title", updated_at="2026-11-15T12:00:00.000Z")
    a.sync({"occasion_years": [y], "recipients": [r], "gifts": [g]})
    old = {**g, "title": "Old title", "updated_at": "2026-11-15T11:00:00.000Z"}
    body = a.sync({"gifts": [old]}).json()
    assert body["rejected"] == [{"table": "gifts", "id": g["id"], "reason": "stale"}]
    gifts = a.sync().json()["changes"]["gifts"]
    assert gifts[0]["title"] == "New title"
    newer = {**g, "title": "Newest", "updated_at": "2026-11-15T13:00:00.000Z"}
    a.sync({"gifts": [newer]})
    assert a.sync().json()["changes"]["gifts"][0]["title"] == "Newest"


def test_soft_delete_is_synced_not_removed(make_user):
    a = make_user()
    y = year_row(a.user_id)
    r = recipient_row(y["id"])
    g = gift_row(y["id"], r["id"])
    a.sync({"occasion_years": [y], "recipients": [r], "gifts": [g]})
    deleted = {**g, "deleted_at": "2026-11-15T12:00:00.000Z", "updated_at": "2026-11-15T12:00:00.000Z"}
    a.sync({"gifts": [deleted]})
    gifts = a.sync().json()["changes"]["gifts"]
    assert len(gifts) == 1 and gifts[0]["deleted_at"] == "2026-11-15T12:00:00.000Z"


def test_since_filters_on_server_updated_at(make_user):
    a = make_user()
    y = year_row(a.user_id)
    r = recipient_row(y["id"])
    first = a.sync({"occasion_years": [y], "recipients": [r]}).json()
    # Client clock is far in the past; server_updated_at still makes it visible.
    g = gift_row(y["id"], r["id"], updated_at="2001-01-01T00:00:00.000Z", created_at="2001-01-01T00:00:00.000Z")
    a.sync({"gifts": [g]})
    after = a.sync(since=first["server_time"]).json()["changes"]
    assert [x["id"] for x in after["gifts"]] == [g["id"]]
    latest = a.sync().json()["server_time"]
    assert a.sync(since=latest).json()["changes"]["gifts"] == []


def test_unauthorized_writes_rejected(make_user):
    a, b = make_user("A"), make_user("B")
    y = year_row(a.user_id)
    a.sync({"occasion_years": [y]})
    r = recipient_row(y["id"])
    body = b.sync({"recipients": [r], "occasion_years": [{**y, "name": "hijack", "updated_at": "2027-01-01T00:00:00.000Z"}],
                   "occasion_years_bogus": [{"id": "x"}]}).json()
    reasons = {(x["table"], x["reason"]) for x in body["rejected"]}
    assert ("recipients", "forbidden") in reasons
    assert ("occasion_years", "forbidden") in reasons
    assert ("occasion_years_bogus", "unknown_table") in reasons
    # Creating a year owned by someone else is also rejected.
    body = b.sync({"occasion_years": [year_row(a.user_id)]}).json()
    assert body["rejected"][0]["reason"] == "forbidden"
    assert a.sync().json()["changes"]["occasion_years"][0]["name"] == "Christmas 2026"
    assert b.sync().json()["changes"]["occasion_years"] == []


def test_invalid_rows_rejected_not_500(make_user):
    a = make_user()
    y = year_row(a.user_id)
    bad = {**gift_row(y["id"], y["id"]), "status": "teleported"}
    body = a.sync({"occasion_years": [y], "gifts": [bad, {"no_id": True}]}).json()
    assert len(body["rejected"]) == 2
    assert body["rejected"][0]["reason"].startswith("invalid: status")


def test_uuid_case_normalised(make_user, repo):
    a = make_user()
    y = year_row(a.user_id.upper())
    y["id"] = y["id"].upper()
    r = recipient_row(y["id"])
    body = a.sync({"occasion_years": [y], "recipients": [r]}).json()
    assert body["rejected"] == []
    assert repo.get("occasion_years", y["id"].lower())["owner_id"] == a.user_id
    assert body["changes"]["recipients"][0]["occasion_year_id"] == y["id"].lower()
    # Uppercase X-User-Id header also works.
    a.user_id = a.user_id.upper()
    assert a.get("/v1/me").status_code == 200


def test_wishlist_items_only_by_owner(make_user):
    a, b = make_user(), make_user()
    import uuid
    wl = {"id": str(uuid.uuid4()), "owner_user_id": a.user_id, "title": "Mine", "slug": "mine-123"}
    item = {"id": str(uuid.uuid4()), "wishlist_id": wl["id"], "title": "Scarf"}
    assert a.sync({"wishlists": [wl], "wishlist_items": [item]}).json()["rejected"] == []
    body = b.sync({"wishlist_items": [{**item, "title": "pwned", "updated_at": "2030-01-01T00:00:00.000Z"}]}).json()
    assert body["rejected"][0]["reason"] == "forbidden"
    clash = {"id": str(uuid.uuid4()), "owner_user_id": b.user_id, "title": "Clash", "slug": "mine-123"}
    assert b.sync({"wishlists": [clash]}).json()["rejected"][0]["reason"] == "slug_taken"
