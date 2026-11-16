#!/usr/bin/env bash
# Push the auth email templates in supabase/templates/ to the hosted Supabase project and set the
# OTP length to 6. The templates link to <site>/auth/callback?token_hash=…&type=email, which the web
# app verifies server-side (no PKCE code verifier, so the link works in any browser), and include the
# one-time code as a fallback. Re-run after editing a template.
#
#   SUPABASE_ACCESS_TOKEN=sbp_… RESEND_API_KEY=re_… supabase/push-auth-templates.sh [project-ref]
#
# Without SUPABASE_ACCESS_TOKEN the script reads the token the Supabase CLI stored in the macOS keychain.
# Free-tier projects can only customise templates once a custom SMTP sender is configured, so when
# RESEND_API_KEY is set the script first points Supabase Auth at Resend's SMTP relay (sender
# AUTH_FROM_EMAIL, required, which must be on a domain verified in Resend).
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
ref="${1:-${SUPABASE_PROJECT_REF:-$(cat "$here/.temp/project-ref" 2>/dev/null || true)}}"
[ -n "$ref" ] || { echo "pass the project ref as the first argument or set SUPABASE_PROJECT_REF" >&2; exit 1; }
token="${SUPABASE_ACCESS_TOKEN:-$(security find-generic-password -s 'Supabase CLI' -w 2>/dev/null || true)}"
[ -n "$token" ] || { echo "set SUPABASE_ACCESS_TOKEN (or run 'supabase login')" >&2; exit 1; }

if [ -n "${RESEND_API_KEY:-}" ]; then
  [ -n "${AUTH_FROM_EMAIL:-}" ] || { echo "set AUTH_FROM_EMAIL (a sender on a Resend-verified domain)" >&2; exit 1; }
  smtp="$(python3 - <<PY
import json, os
print(json.dumps({
    "smtp_host": os.environ.get("SMTP_HOST", "smtp.resend.com"),
    "smtp_port": int(os.environ.get("SMTP_PORT", "465")),
    "smtp_user": os.environ.get("SMTP_USER", "resend"),
    "smtp_pass": os.environ["RESEND_API_KEY"],
    "smtp_admin_email": os.environ["AUTH_FROM_EMAIL"],
    "smtp_sender_name": os.environ.get("AUTH_FROM_NAME", "Permit Memo"),
    "smtp_max_frequency": 1,
    "rate_limit_email_sent": 100,
}))
PY
)"
  curl -sS -f -X PATCH "https://api.supabase.com/v1/projects/$ref/config/auth" \
    -H "Authorization: Bearer $token" -H 'Content-Type: application/json' -d "$smtp" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print("smtp:", d.get("smtp_host"), "sender", d.get("smtp_admin_email"))'
fi

body="$(python3 - "$here/templates/magic_link.html" "$here/templates/confirm_signup.html" <<'PY'
import json, sys
magic, confirm = (open(p).read() for p in sys.argv[1:3])
print(json.dumps({
    "mailer_otp_length": 6,
    "mailer_subjects_magic_link": "Your Permit Memo sign-in link and code",
    "mailer_templates_magic_link_content": magic,
    "mailer_subjects_confirmation": "Confirm your email for Permit Memo",
    "mailer_templates_confirmation_content": confirm,
}))
PY
)"
curl -sS -f -X PATCH "https://api.supabase.com/v1/projects/$ref/config/auth" \
  -H "Authorization: Bearer $token" -H 'Content-Type: application/json' -d "$body" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print("otp_length", d["mailer_otp_length"]); print("magic_link:", d["mailer_templates_magic_link_content"][:160].replace("\n"," "), "…")'
