from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import access
from ..auth import current_user, get_repo
from ..budget import compute_totals
from ..redaction import split_gifts
from ..repo import Repository
from ..schemas import norm_uuid

router = APIRouter(prefix="/v1", tags=["totals"])


@router.get("/years/{year_id}/totals")
def totals(year_id: str, user: dict = Depends(current_user), repo: Repository = Depends(get_repo)) -> dict:
    try:
        year_id = norm_uuid(year_id)
    except ValueError:
        raise HTTPException(404, "year not found") from None
    if access.role_in_year(repo, user["id"], year_id) is None:
        raise HTTPException(403, "no access to this year")
    year = repo.get("occasion_years", year_id)
    recipients = repo.select("recipients", eq={"occasion_year_id": year_id})
    gifts, redacted = split_gifts(repo.select("gifts", eq={"occasion_year_id": year_id}), user["id"])
    return compute_totals(year, recipients, gifts, redacted)
