import uuid


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_missing_app_key_401(client):
    r = client.post("/v1/sync", json={"changes": {}}, headers={"X-User-Id": str(uuid.uuid4())})
    assert r.status_code == 401


def test_wrong_app_key_401(client, make_user):
    u = make_user()
    r = client.post("/v1/sync", json={"changes": {}}, headers={"X-App-Key": "nope", "X-User-Id": u.user_id})
    assert r.status_code == 401


def test_unregistered_user_401(client):
    r = client.post("/v1/sync", json={"changes": {}}, headers={"X-App-Key": "test-app-key", "X-User-Id": str(uuid.uuid4())})
    assert r.status_code == 401


def test_invalid_user_id_401(client):
    r = client.get("/v1/me", headers={"X-App-Key": "test-app-key", "X-User-Id": "not-a-uuid"})
    assert r.status_code == 401


def test_register_requires_matching_id(client):
    uid = str(uuid.uuid4())
    r = client.post("/v1/users", json={"id": str(uuid.uuid4())}, headers={"X-App-Key": "test-app-key", "X-User-Id": uid})
    assert r.status_code == 403


def test_register_and_me(make_user):
    u = make_user("Alex")
    me = u.get("/v1/me").json()
    assert me["display_name"] == "Alex" and me["is_pro"] is False
