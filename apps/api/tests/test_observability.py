import json

from app.core.observability import hash_user_id, local_doctor, mask_pii, redact_text


def test_redacts_emails_and_phones_everywhere() -> None:
    span = {
        "name": "plan.generate",
        "attributes": {
            "input.value": json.dumps(
                {"description": "Call me at (415) 555-0123 or jo@example.com about the bar"}
            ),
            "nested": {"list": ["+1 415 555 0123", {"deep": "mail: a.b+c@d.io"}]},
            "neatlogs.api_key": "nl_secret",
            "Authorization": "Bearer abc",
            "count": 3,
        },
        "events": [{"name": "log", "attributes": {"msg": "owner jo@example.com"}}],
    }
    out = mask_pii(span)
    assert out is not None
    attrs = out["attributes"]
    assert (
        "example.com" not in attrs["input.value"]
        and "[email]" in attrs["input.value"]
        and "[phone]" in attrs["input.value"]
    )
    assert attrs["nested"]["list"][0] == "[phone]" and attrs["nested"]["list"][1]["deep"] == "mail: [email]"
    assert attrs["neatlogs.api_key"] == "[redacted]" and attrs["Authorization"] == "[redacted]"
    assert attrs["count"] == 3
    assert out["events"][0]["attributes"]["msg"] == "owner [email]"


def test_redact_keeps_ordinary_numbers() -> None:
    assert redact_text("fee $1,500 over 60-120 days, 40 seats") == "fee $1,500 over 60-120 days, 40 seats"


def test_hash_user_id_is_stable_and_salted() -> None:
    a = hash_user_id("user-1", "s1")
    assert (
        a == hash_user_id("user-1", "s1")
        and a != hash_user_id("user-1", "s2")
        and len(a) == 24
        and "user-1" not in a
    )


def test_local_doctor_passes_offline() -> None:
    result = local_doctor()
    assert result["status"] == "pass", result
    assert result["mode"] == "local" and result["span_count"] == 4
