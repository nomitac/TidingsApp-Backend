"""Storage layer. The API never talks to Postgres directly — only via Supabase PostgREST
with the service-role key (SupabaseRepo). MemoryRepo backs tests and local development."""
from __future__ import annotations

import copy
import threading
from typing import Any, Iterable, Protocol

import httpx

from . import timeutil

Row = dict[str, Any]


class Repository(Protocol):
    def get(self, table: str, id: str) -> Row | None: ...

    def select(
        self,
        table: str,
        eq: dict[str, Any] | None = None,
        in_: dict[str, Iterable[Any]] | None = None,
        gt: dict[str, Any] | None = None,
    ) -> list[Row]: ...

    def upsert(self, table: str, row: Row) -> Row: ...

    def insert_many(self, table: str, rows: list[Row]) -> int: ...


class MemoryRepo:
    def __init__(self) -> None:
        self._tables: dict[str, dict[str, Row]] = {}
        self._lock = threading.Lock()

    def _t(self, table: str) -> dict[str, Row]:
        return self._tables.setdefault(table, {})

    def get(self, table: str, id: str) -> Row | None:
        with self._lock:
            row = self._t(table).get(id)
            return copy.deepcopy(row) if row else None

    def select(self, table, eq=None, in_=None, gt=None) -> list[Row]:
        eq, in_, gt = eq or {}, in_ or {}, gt or {}
        in_sets = {k: set(v) for k, v in in_.items()}
        out = []
        with self._lock:
            for row in self._t(table).values():
                if any(row.get(k) != v for k, v in eq.items()):
                    continue
                if any(row.get(k) not in s for k, s in in_sets.items()):
                    continue
                if any(row.get(k) is None or not _gt(row.get(k), v) for k, v in gt.items()):
                    continue
                out.append(copy.deepcopy(row))
        return out

    def upsert(self, table: str, row: Row) -> Row:
        with self._lock:
            t = self._t(table)
            merged = {**t.get(row["id"], {}), **copy.deepcopy(row)}
            t[row["id"]] = merged
            return copy.deepcopy(merged)

    def insert_many(self, table: str, rows: list[Row]) -> int:
        for r in rows:
            self.upsert(table, r)
        return len(rows)


def _gt(a: Any, b: Any) -> bool:
    if timeutil.looks_like_ts(a) and timeutil.looks_like_ts(b):
        return timeutil.parse(a) > timeutil.parse(b)
    return a > b


class SupabaseRepo:
    """PostgREST client. Uses the service-role key, which bypasses RLS — RLS is enabled on
    every table with no policies, so the anon key can read nothing."""

    def __init__(self, url: str, service_key: str, client: httpx.Client | None = None,
                 schema: str = "public", table_prefix: str = "tidings_") -> None:
        self._prefix = table_prefix
        self._client = client or httpx.Client(
            base_url=url.rstrip("/") + "/rest/v1",
            headers=self.build_headers(service_key, schema),
            timeout=10.0,
        )

    @staticmethod
    def build_headers(service_key: str, schema: str = "public") -> dict[str, str]:
        headers = {"apikey": service_key, "Content-Type": "application/json"}
        # Legacy service_role keys are JWTs and go in Authorization too. New-style secret keys
        # (sb_secret_…) are not JWTs and must only be sent as `apikey`.
        if service_key.startswith("eyJ"):
            headers["Authorization"] = f"Bearer {service_key}"
        # PostgREST schema selection: reads use Accept-Profile, writes use Content-Profile.
        if schema and schema != "public":
            headers["Accept-Profile"] = schema
            headers["Content-Profile"] = schema
        return headers

    @staticmethod
    def _out(row: Row) -> Row:
        return {k: timeutil.normalize(v) if timeutil.looks_like_ts(v) else v for k, v in row.items()}

    @staticmethod
    def _lit(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        s = str(v)
        # Quote values containing PostgREST reserved characters.
        if any(c in s for c in ',.:()"'):
            return '"' + s.replace('"', '\\"') + '"'
        return s

    def _path(self, table: str) -> str:
        """API table name → Postgres table, e.g. "gifts" → "/tidings_gifts"."""
        return f"/{self._prefix}{table}"

    def get(self, table: str, id: str) -> Row | None:
        rows = self.select(table, eq={"id": id})
        return rows[0] if rows else None

    def select(self, table, eq=None, in_=None, gt=None) -> list[Row]:
        params: list[tuple[str, str]] = [("select", "*")]
        for k, v in (eq or {}).items():
            params.append((k, "is.null" if v is None else f"eq.{v if not isinstance(v, bool) else self._lit(v)}"))
        for k, vs in (in_ or {}).items():
            vs = list(vs)
            if not vs:
                return []
            params.append((k, "in.(" + ",".join(self._lit(v) for v in vs) + ")"))
        for k, v in (gt or {}).items():
            params.append((k, f"gt.{v}"))
        r = self._client.get(self._path(table), params=params)
        r.raise_for_status()
        return [self._out(x) for x in r.json()]

    def upsert(self, table: str, row: Row) -> Row:
        r = self._client.post(
            self._path(table),
            params={"on_conflict": "id"},
            json=row,
            headers={"Prefer": "resolution=merge-duplicates,return=representation"},
        )
        r.raise_for_status()
        data = r.json()
        return self._out(data[0] if isinstance(data, list) and data else row)

    def insert_many(self, table: str, rows: list[Row]) -> int:
        if not rows:
            return 0
        r = self._client.post(self._path(table), json=rows, headers={"Prefer": "return=minimal"})
        r.raise_for_status()
        return len(rows)
