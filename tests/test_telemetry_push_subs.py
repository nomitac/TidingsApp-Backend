import base64
import json


def test_events_and_errors_written(make_user, repo):
    u = make_user()
    r = u.post("/v1/events", {"events": [{"name": "first_gift_added", "properties": {"source": "manual"}},
                                         {"name": "wishlist_shared", "occurred_at": "2026-11-15T10:00:00Z"}]})
    assert r.json() == {"accepted": 2}
    rows = repo.select("analytics_events", eq={"user_id": u.user_id})
    assert {x["name"] for x in rows} == {"first_gift_added", "wishlist_shared"}
    r = u.post("/v1/errors", {"errors": [{"message": "boom", "context": {"screen": "Dashboard"}, "app_version": "1.0"}]})
    assert r.json() == {"accepted": 1}
    assert repo.select("error_logs")[0]["message"] == "boom"


def test_push_token_upsert(make_user, repo):
    a, b = make_user(), make_user()
    tok = "ab" * 32
    assert a.post("/v1/push-tokens", {"token": tok, "environment": "sandbox"}).status_code == 200
    assert b.post("/v1/push-tokens", {"token": tok.upper()}).status_code == 200
    rows = repo.select("push_tokens")
    assert len(rows) == 1 and rows[0]["user_id"] == b.user_id
    assert a.post("/v1/push-tokens", {"token": "not hex!"}).status_code == 422


def _fake_jws(payload):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'ES256'})}.{enc(payload)}.sig"


def test_subscription_sets_pro(make_user):
    u = make_user()
    jws = _fake_jws({"productId": "tidings.pro.yearly", "expiresDate": 4102444800000})  # 2100-01-01
    r = u.post("/v1/subscriptions", {"product_id": "tidings.pro.yearly", "transaction_id": "1", "signed_transaction": jws})
    assert r.status_code == 200 and r.json()["is_pro"] is True
    assert r.json()["pro_expires_at"].startswith("2100-01-01")
    assert u.get("/v1/me").json()["is_pro"] is True
    assert u.post("/v1/subscriptions", {"product_id": "evil", "transaction_id": "2"}).status_code == 422


def test_expired_subscription_not_pro(make_user):
    u = make_user()
    r = u.post("/v1/subscriptions", {"product_id": "tidings.pro.monthly", "transaction_id": "1", "expires_at": "2020-01-01T00:00:00Z"})
    assert r.json()["is_pro"] is False
