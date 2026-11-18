"""Who can see / write what (Sec. 7 of the spec)."""
from __future__ import annotations

from .repo import Repository


def accepted_member_year_ids(repo: Repository, user_id: str) -> set[str]:
    rows = repo.select("year_members", eq={"user_id": user_id, "status": "accepted", "deleted_at": None})
    return {r["occasion_year_id"] for r in rows}


def owned_year_ids(repo: Repository, user_id: str) -> set[str]:
    return {r["id"] for r in repo.select("occasion_years", eq={"owner_id": user_id})}


def accessible_year_ids(repo: Repository, user_id: str) -> set[str]:
    return owned_year_ids(repo, user_id) | accepted_member_year_ids(repo, user_id)


def role_in_year(repo: Repository, user_id: str, year_id: str) -> str | None:
    year = repo.get("occasion_years", year_id)
    if not year or year.get("deleted_at"):
        return None
    if year["owner_id"] == user_id:
        return "owner"
    if year_id in accepted_member_year_ids(repo, user_id):
        return "co_shopper"
    return None
