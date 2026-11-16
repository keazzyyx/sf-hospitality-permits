"""The API's Supabase REST headers work with both kinds of server key, so the service key can be rotated from the
legacy service_role JWT to a new secret key (its value starts with `sb_`) without a code change. No network.
The made-up keys are built from parts so that no secret scanner mistakes them for real ones."""

from __future__ import annotations

from app.core.config import Settings
from app.services.db import SupabaseDatabase, service_headers

LEGACY = ".".join(["legacy-jwt-header", "legacy-jwt-payload", "not-a-real-signature"])
NEW = "sb_" + "secret" + "_not-a-real-key"


def test_a_legacy_service_role_key_is_sent_as_apikey_and_bearer() -> None:
    assert service_headers(LEGACY) == {
        "apikey": LEGACY,
        "Authorization": f"Bearer {LEGACY}",
        "Content-Type": "application/json",
    }


def test_a_new_secret_key_is_sent_as_apikey_only() -> None:
    headers = service_headers(NEW)
    assert headers == {"apikey": NEW, "Content-Type": "application/json"}
    assert "Authorization" not in headers


async def test_the_client_uses_those_headers() -> None:
    for key, bearer in ((LEGACY, True), (NEW, False)):
        db = SupabaseDatabase(
            Settings(SUPABASE_URL="https://example.supabase.co", SUPABASE_SERVICE_ROLE_KEY=key)
        )
        try:
            assert db._client.headers["apikey"] == key
            assert ("authorization" in db._client.headers) is bearer
            assert str(db._client.base_url) == "https://example.supabase.co/rest/v1/"
        finally:
            await db.aclose()
