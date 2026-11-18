import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.repo import MemoryRepo

APP_KEY = "test-app-key"


class Api:
    def __init__(self, client: TestClient, user_id: str):
        self.client, self.user_id = client, user_id

    @property
    def headers(self):
        return {"X-App-Key": APP_KEY, "X-User-Id": self.user_id}

    def get(self, path, **kw):
        return self.client.get(path, headers=self.headers, **kw)

    def post(self, path, json=None, **kw):
        return self.client.post(path, headers=self.headers, json=json, **kw)

    def sync(self, changes=None, since=None):
        r = self.post("/v1/sync", {"since": since, "changes": changes or {}})
        assert r.status_code == 200, r.text
        return r


@pytest.fixture
def repo():
    return MemoryRepo()


@pytest.fixture
def app(repo):
    return create_app(Settings(app_key=APP_KEY, public_base_url="https://tidings.test"), repo)


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def make_user(client):
    def _make(name="User"):
        uid = str(uuid.uuid4())
        api = Api(client, uid)
        r = api.post("/v1/users", {"id": uid, "display_name": name, "default_currency": "USD"})
        assert r.status_code == 200, r.text
        return api
    return _make


def ts(s="2026-11-15T10:00:00.000Z"):
    return s


def year_row(owner_id, **kw):
    return {"id": str(uuid.uuid4()), "owner_id": owner_id, "name": "Christmas 2026", "year": 2026,
            "currency": "USD", "occasion_date": "2026-12-25T00:00:00.000Z", "total_budget_cents": 100000,
            "created_at": ts(), "updated_at": ts(), **kw}


def recipient_row(year_id, name="Mom", **kw):
    return {"id": str(uuid.uuid4()), "person_id": str(uuid.uuid4()), "occasion_year_id": year_id, "name": name,
            "created_at": ts(), "updated_at": ts(), **kw}


def gift_row(year_id, recipient_id, title="Candle", **kw):
    return {"id": str(uuid.uuid4()), "occasion_year_id": year_id, "recipient_id": recipient_id, "title": title,
            "status": "idea", "currency": "USD", "created_at": ts(), "updated_at": ts(), **kw}
