"""Thin async data layer over Supabase's PostgREST API (service role), plus an in-memory twin for tests/dev.

The API always scopes queries by `user_id`; RLS on the tables is defense-in-depth for the web client.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import ApiError

Filters = dict[str, Any]  # {"col": value} → eq ; {"col": ("in", [..])}


class DuplicateKeyError(ApiError):
    """An insert refused because a row with the same primary key (or another unique key) already exists. The
    same 502 `database_error` as any other refused write, so callers that do not expect it behave as before;
    a caller that uses a unique key as a claim catches this type."""

    def __init__(self, message: str) -> None:
        super().__init__(502, "database_error", message)


def utcnow() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Database(Protocol):
    async def select(
        self,
        table: str,
        *,
        filters: Filters | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]: ...
    async def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]: ...
    async def upsert(
        self, table: str, rows: list[dict[str, Any]], *, on_conflict: str
    ) -> list[dict[str, Any]]: ...
    async def update(self, table: str, filters: Filters, values: dict[str, Any]) -> list[dict[str, Any]]: ...
    async def delete(self, table: str, filters: Filters) -> None: ...


def service_headers(key: str) -> dict[str, str]:
    """The headers the API sends to Supabase's REST API with its server key.

    A legacy service_role key is a JWT: it goes in `apikey` and, as before, as the Bearer token. A new secret key
    (its value starts with `sb_`) is not a JWT: it goes in `apikey` only, and Supabase's gateway gives the request the
    service role itself. Either key works, so the key can be rotated to a new secret key with no code change.
    """
    headers = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


class SupabaseDatabase:
    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_configured:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")
        assert settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY
        self._client = httpx.AsyncClient(
            base_url=settings.SUPABASE_URL.rstrip("/") + "/rest/v1",
            headers=service_headers(settings.SUPABASE_SERVICE_ROLE_KEY),
            timeout=15.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _params(filters: Filters | None) -> dict[str, str]:
        params: dict[str, str] = {}
        for col, val in (filters or {}).items():
            if isinstance(val, tuple) and val and val[0] == "in":
                params[col] = (
                    "in.(" + ",".join(json.dumps(v) if not isinstance(v, str) else v for v in val[1]) + ")"
                )
            elif val is None:
                params[col] = "is.null"
            else:
                params[col] = f"eq.{val}"
        return params

    async def _req(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json_body: Any = None,
        prefer: str | None = None,
    ) -> Any:
        headers = {"Prefer": prefer} if prefer else {}
        resp = await self._client.request(method, f"/{table}", params=params, json=json_body, headers=headers)
        if resp.status_code == 409 and '"23505"' in resp.text:  # PostgreSQL unique_violation
            raise DuplicateKeyError(f"Supabase {method} {table} failed: {resp.status_code} {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ApiError(
                502,
                "database_error",
                f"Supabase {method} {table} failed: {resp.status_code} {resp.text[:200]}",
            )
        if resp.status_code == 204 or not resp.content:
            return []
        return resp.json()

    async def select(
        self,
        table: str,
        *,
        filters: Filters | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params = self._params(filters)
        params["select"] = "*"
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        return list(await self._req("GET", table, params=params))

    async def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        rows = await self._req("POST", table, json_body=row, prefer="return=representation")
        return dict(rows[0])

    async def upsert(
        self, table: str, rows: list[dict[str, Any]], *, on_conflict: str
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        out = await self._req(
            "POST",
            table,
            params={"on_conflict": on_conflict},
            json_body=rows,
            prefer="return=representation,resolution=merge-duplicates",
        )
        return list(out)

    async def update(self, table: str, filters: Filters, values: dict[str, Any]) -> list[dict[str, Any]]:
        out = await self._req(
            "PATCH", table, params=self._params(filters), json_body=values, prefer="return=representation"
        )
        return list(out)

    async def delete(self, table: str, filters: Filters) -> None:
        await self._req("DELETE", table, params=self._params(filters))


class MemoryDatabase:
    """Dict-backed stand-in with the same surface. Used by tests and by `make dev` without Supabase."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def _rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables.setdefault(table, [])

    @staticmethod
    def _match(row: dict[str, Any], filters: Filters | None) -> bool:
        for col, val in (filters or {}).items():
            if isinstance(val, tuple) and val and val[0] == "in":
                if row.get(col) not in val[1]:
                    return False
            elif row.get(col) != val:
                return False
        return True

    async def select(
        self,
        table: str,
        *,
        filters: Filters | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        rows = [dict(r) for r in self._rows(table) if self._match(r, filters)]
        if order:
            col, _, direction = order.partition(".")
            rows.sort(key=lambda r: (r.get(col) is None, r.get(col)), reverse=direction == "desc")
        return rows[:limit] if limit else rows

    async def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        new = dict(row)
        if "id" in new and any(r.get("id") == new["id"] for r in self._rows(table)):
            raise DuplicateKeyError(f"duplicate key: {table}.id {new['id']}")
        new.setdefault("id", str(uuid.uuid4()))
        new.setdefault("created_at", utcnow())
        if table in {"plans", "profiles", "plan_steps"}:
            new.setdefault("updated_at", new["created_at"])
        self._rows(table).append(new)
        return dict(new)

    async def upsert(
        self, table: str, rows: list[dict[str, Any]], *, on_conflict: str
    ) -> list[dict[str, Any]]:
        keys = [k.strip() for k in on_conflict.split(",")]
        out = []
        for row in rows:
            existing = next((r for r in self._rows(table) if all(r.get(k) == row.get(k) for k in keys)), None)
            if existing is None:
                out.append(await self.insert(table, row))
            else:
                existing.update(row)
                existing["updated_at"] = utcnow()
                out.append(dict(existing))
        return out

    async def update(self, table: str, filters: Filters, values: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for r in self._rows(table):
            if self._match(r, filters):
                r.update(values)
                if "updated_at" in r:
                    r["updated_at"] = utcnow()
                out.append(dict(r))
        return out

    async def delete(self, table: str, filters: Filters) -> None:
        self.tables[table] = [r for r in self._rows(table) if not self._match(r, filters)]
