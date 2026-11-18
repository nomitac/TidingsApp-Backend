import json

import httpx

from app.repo import SupabaseRepo


def test_postgrest_requests():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        if req.method == "GET":
            return httpx.Response(200, json=[{"id": "a", "updated_at": "2026-11-15T10:00:00.123456+00:00"}])
        return httpx.Response(201, json=[json.loads(req.content)])

    client = httpx.Client(base_url="https://x.supabase.co/rest/v1", transport=httpx.MockTransport(handler),
                          headers={"apikey": "k", "Authorization": "Bearer k"})
    repo = SupabaseRepo("https://x.supabase.co", "k", client=client)
    rows = repo.select("gifts", eq={"owner_id": "u1", "deleted_at": None}, in_={"occasion_year_id": ["y1", "y2"]},
                       gt={"server_updated_at": "2026-11-15T10:00:00.000Z"})
    assert rows[0]["updated_at"] == "2026-11-15T10:00:00.123Z"
    q = seen[0].url.params
    assert q["owner_id"] == "eq.u1" and q["deleted_at"] == "is.null"
    assert q["occasion_year_id"] == "in.(y1,y2)"
    assert q["server_updated_at"] == "gt.2026-11-15T10:00:00.000Z"
    assert repo.select("gifts", in_={"id": []}) == []

    repo.upsert("gifts", {"id": "g1", "title": "x"})
    post = seen[-1]
    assert post.url.params["on_conflict"] == "id"
    assert "merge-duplicates" in post.headers["Prefer"]
