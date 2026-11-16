"""Supabase JWT verification. Every /v1 route (except the documented public ones) depends on `current_user`.

Supports both signing schemes Supabase uses:
  * legacy HS256 with the project's JWT secret (`SUPABASE_JWT_SECRET`)
  * asymmetric keys (ES256/RS256) published at `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, cast

import httpx
import jwt
from fastapi import Depends, Request
from jwt import PyJWK

from app.core.config import Settings, get_settings
from app.core.errors import ApiError


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str | None
    is_anonymous: bool
    claims: dict[str, Any]


class JWKSCache:
    def __init__(self, ttl_seconds: int = 600) -> None:
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at = 0.0
        self._ttl = ttl_seconds

    async def get(self, supabase_url: str, kid: str | None) -> PyJWK | None:
        if kid and kid in self._keys and time.monotonic() - self._fetched_at < self._ttl:
            return self._keys[kid]
        url = supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        self._keys = {k["kid"]: PyJWK.from_dict(k) for k in data.get("keys", []) if "kid" in k}
        self._fetched_at = time.monotonic()
        return self._keys.get(kid or "")


_jwks = JWKSCache()


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "unauthorized", "Missing bearer token")
    return token.strip()


async def verify_supabase_jwt(token: str, settings: Settings) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise ApiError(401, "unauthorized", "Malformed token") from exc
    alg = header.get("alg", "HS256")
    options = cast(Any, {"require": ["exp", "sub"]})
    try:
        if alg == "HS256":
            if not settings.SUPABASE_JWT_SECRET:
                raise ApiError(401, "unauthorized", "Server is missing SUPABASE_JWT_SECRET")
            return jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience=settings.SUPABASE_JWT_AUDIENCE,
                options=options,
            )
        if not settings.SUPABASE_URL:
            raise ApiError(401, "unauthorized", "Server is missing SUPABASE_URL")
        key = await _jwks.get(settings.SUPABASE_URL, header.get("kid"))
        if key is None:
            raise ApiError(401, "unauthorized", "Unknown signing key")
        return jwt.decode(
            token, key.key, algorithms=[alg], audience=settings.SUPABASE_JWT_AUDIENCE, options=options
        )
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "unauthorized", "Token expired") from exc
    except jwt.PyJWTError as exc:
        raise ApiError(401, "unauthorized", "Invalid token") from exc
    except httpx.HTTPError as exc:
        raise ApiError(401, "unauthorized", "Could not fetch signing keys") from exc


async def current_user(request: Request, settings: Settings = Depends(get_settings)) -> AuthUser:
    token = _bearer(request)
    claims = await verify_supabase_jwt(token, settings)
    sub = str(claims.get("sub") or "")
    if not sub:
        raise ApiError(401, "unauthorized", "Token has no subject")
    return AuthUser(
        id=sub,
        email=claims.get("email"),
        is_anonymous=bool(claims.get("is_anonymous", False)),
        claims=claims,
    )
