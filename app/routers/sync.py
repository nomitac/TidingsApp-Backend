"""Offline-first sync: push local changes, pull everything changed since the last server_time."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import access, timeutil
from ..auth import current_user, get_repo
from ..redaction import activity_for_viewer, recipient_for_viewer, split_gifts
from ..repo import Repository
from ..schemas import SYNC_TABLES, YEAR_SCOPED, normalize_row, norm_uuid, public_row

router = APIRouter(prefix="/v1", tags=["sync"])


class SyncRequest(BaseModel):
    since: str | None = None
    changes: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class Rejected(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _check_write(repo: Repository, user_id: str, table: str, row: dict, existing: dict | None) -> None:
    if table == "occasion_years":
        if existing:
            if existing["owner_id"] != user_id:
                raise Rejected("forbidden")
            if row["owner_id"] != existing["owner_id"]:
                raise Rejected("owner_change")
        elif row["owner_id"] != user_id:
            raise Rejected("forbidden")
        return

    if table in YEAR_SCOPED or table == "secret_santa_exchanges":
        if existing and existing["occasion_year_id"] != row["occasion_year_id"]:
            raise Rejected("year_change")
        role = access.role_in_year(repo, user_id, row["occasion_year_id"])
        if role is None:
            raise Rejected("forbidden")
        if table == "year_members" and role != "owner":
            raise Rejected("forbidden")
        if table == "gifts":
            if row.get("is_surprise_for_user_id") == user_id or (
                existing and existing.get("is_surprise_for_user_id") == user_id
            ):
                raise Rejected("surprise")
        if table == "secret_santa_exchanges":
            if row["organizer_id"] != user_id or (existing and existing["organizer_id"] != user_id):
                raise Rejected("forbidden")
        return

    if table == "wishlists":
        if row["owner_user_id"] != user_id or (existing and existing["owner_user_id"] != user_id):
            raise Rejected("forbidden")
        if not existing:
            clash = [w for w in repo.select("wishlists", eq={"slug": row["slug"]}) if w["id"] != row["id"]]
            if clash:
                raise Rejected("slug_taken")
        return

    if table == "wishlist_items":
        wl_ids = {row["wishlist_id"]} | ({existing["wishlist_id"]} if existing else set())
        for wid in wl_ids:
            wl = repo.get("wishlists", wid)
            if not wl or wl["owner_user_id"] != user_id:
                raise Rejected("forbidden")
        return

    raise Rejected("unknown_table")


def apply_changes(repo: Repository, user: dict, changes: dict[str, list[dict]]) -> list[dict]:
    user_id = user["id"]
    rejected: list[dict] = []
    for table in [t for t in changes if t not in SYNC_TABLES]:
        for raw in changes[table]:
            rejected.append({"table": table, "id": str(raw.get("id", "")) if isinstance(raw, dict) else "", "reason": "unknown_table"})

    for table in SYNC_TABLES:
        for raw in changes.get(table, []):
            rid = str(raw.get("id", "")) if isinstance(raw, dict) else ""
            try:
                try:
                    row = normalize_row(table, raw)
                except ValueError as e:
                    raise Rejected(f"invalid: {e}") from None
                rid = row["id"]
                existing = repo.get(table, rid)
                _check_write(repo, user_id, table, row, existing)
                if existing and timeutil.parse(row["updated_at"]) < timeutil.parse(existing["updated_at"]):
                    raise Rejected("stale")
                if table == "gifts":
                    row["created_by"] = existing.get("created_by") if existing else user_id
                    row["created_by"] = row["created_by"] or user_id
                    row["updated_by"] = user_id
                if table == "activity_log":
                    row["actor_user_id"] = user_id
                if existing:
                    row["created_at"] = existing.get("created_at", row["created_at"])
                row["server_updated_at"] = timeutil.now_str()
                repo.upsert(table, row)
            except Rejected as r:
                rejected.append({"table": table, "id": rid, "reason": r.reason})
    return rejected


def pull(repo: Repository, user_id: str, since: str | None) -> tuple[dict[str, list[dict]], list[dict]]:
    years = access.accessible_year_ids(repo, user_id)
    gt = {"server_updated_at": since} if since else None

    # Years the user only just gained access to (membership changed since last sync) get a full pull.
    fresh: set[str] = set()
    if since:
        for m in repo.select("year_members", eq={"user_id": user_id, "status": "accepted"}, gt=gt):
            fresh.add(m["occasion_year_id"])
    fresh &= years

    def year_rows(table: str, key: str) -> list[dict]:
        rows = repo.select(table, in_={key: years}, gt=gt) if years else []
        if fresh:
            seen = {r["id"] for r in rows}
            rows += [r for r in repo.select(table, in_={key: fresh}) if r["id"] not in seen]
        return rows

    out: dict[str, list[dict]] = {}
    out["occasion_years"] = [public_row(r) for r in year_rows("occasion_years", "id")]
    out["year_members"] = [public_row(r) for r in year_rows("year_members", "occasion_year_id")]
    out["groups"] = [public_row(r) for r in year_rows("groups", "occasion_year_id")]
    out["recipients"] = [recipient_for_viewer(r, user_id) for r in year_rows("recipients", "occasion_year_id")]
    gifts, redacted = split_gifts(year_rows("gifts", "occasion_year_id"), user_id)
    out["gifts"] = gifts
    out["activity_log"] = [activity_for_viewer(r, user_id) for r in year_rows("activity_log", "occasion_year_id")]
    out["secret_santa_exchanges"] = [
        public_row(r) for r in repo.select("secret_santa_exchanges", eq={"organizer_id": user_id}, gt=gt)
    ]
    my_wishlists = repo.select("wishlists", eq={"owner_user_id": user_id})
    out["wishlists"] = [public_row(r) for r in my_wishlists if not since or timeutil.parse(r["server_updated_at"]) > timeutil.parse(since)]
    wl_ids = {w["id"] for w in my_wishlists}
    out["wishlist_items"] = [public_row(r) for r in repo.select("wishlist_items", in_={"wishlist_id": wl_ids}, gt=gt)] if wl_ids else []
    return out, redacted


@router.post("/sync")
def sync(body: SyncRequest, user: dict = Depends(current_user), repo: Repository = Depends(get_repo)) -> dict:
    # Taken before writes so nothing written concurrently can fall between two syncs.
    server_time = timeutil.now_str()
    since = timeutil.normalize(body.since) if body.since else None
    rejected = apply_changes(repo, user, body.changes)
    changes, redacted = pull(repo, user["id"], since)
    return {"server_time": server_time, "changes": changes, "redacted_gifts": redacted, "rejected": rejected}


__all__ = ["router", "apply_changes", "pull", "norm_uuid"]
