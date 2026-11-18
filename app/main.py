from __future__ import annotations

import logging

from fastapi import FastAPI

from .config import Settings, get_settings
from .repo import MemoryRepo, Repository, SupabaseRepo
from .routers import import_link, invites, public_web, push, subscriptions, sync, telemetry, totals, users, wishlists


def build_repo(settings: Settings) -> Repository:
    if settings.resolved_backend == "supabase":
        if not (settings.supabase_url and settings.supabase_service_role_key):
            raise RuntimeError("STORAGE_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        return SupabaseRepo(settings.supabase_url, settings.supabase_service_role_key, schema=settings.supabase_schema, table_prefix=settings.supabase_table_prefix)
    return MemoryRepo()


def create_app(settings: Settings | None = None, repo: Repository | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Tidings API", version="1.0.0")
    app.state.settings = settings
    app.state.repo = repo or build_repo(settings)
    app.state.http_transport = None
    logging.getLogger("tidings").info("storage backend: %s", type(app.state.repo).__name__)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    for r in (users, sync, invites, totals, import_link, wishlists, telemetry, push, subscriptions, public_web):
        app.include_router(r.router)
    return app


app = create_app()
