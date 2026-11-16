"""Scheduled job: email users 90 days after a memo asking what happened.

    python -m app.jobs.feedback_emails            # send due emails (idempotent: marks memos as sent)
    python -m app.jobs.feedback_emails --dry-run  # list what would be sent
Runs daily on Railway (cron) — see apps/api/railway.cron.toml.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import neatlogs

from app.core.config import settings

neatlogs_enabled = bool(settings.NEATLOGS_API_KEY)
if neatlogs_enabled:
    neatlogs.init(
        api_key=settings.NEATLOGS_API_KEY,
        endpoint=settings.NEATLOGS_ENDPOINT,
        workflow_name="permit-memo-jobs",
        tags=[f"env:{settings.ENV}", f"version:{settings.GIT_SHA}", "job:feedback_emails"],
    )

from app.deps import get_db  # noqa: E402
from app.services.feedback import send_feedback_email, sign_feedback_token  # noqa: E402
from app.services.memos import MemoService  # noqa: E402

log = logging.getLogger("jobs.feedback_emails")


@neatlogs.span(kind="CHAIN", name="job.feedback_emails")
async def run(*, dry_run: bool) -> int:
    svc = MemoService(get_db(), settings)
    due = await svc.memos_due_for_feedback(delay_days=settings.FEEDBACK_DELAY_DAYS)
    sent = 0
    for row in due:
        memo_id = str(row["id"])
        profile = (await svc.db.select("profiles", filters={"id": row["user_id"]}) or [{}])[0]
        email = profile.get("email")
        if not email:
            log.info("memo %s: user has no email, skipping", memo_id)
            await svc.mark_feedback_sent(memo_id)
            continue
        token = sign_feedback_token(memo_id, settings)
        link = f"{settings.WEB_URL.rstrip('/')}/feedback/{token}"
        concept = ((row.get("profile") or {}).get("business_type") or "business").replace("_", " ")
        if dry_run:
            log.info("would email %s about memo %s (%s)", email, memo_id, row["address"])
            continue
        try:
            await send_feedback_email(
                to=email, address=row["address"], concept=concept, link=link, settings=settings
            )
            await svc.mark_feedback_sent(memo_id)
            await svc.plans.record_event(str(row["user_id"]), "feedback_email_sent", {"memo_id": memo_id})
            sent += 1
        except Exception:
            log.exception("memo %s: email failed", memo_id)
    log.info("feedback emails: %d due, %d sent%s", len(due), sent, " (dry run)" if dry_run else "")
    return sent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if not (settings.RESEND_API_KEY and settings.FEEDBACK_FROM_EMAIL) and not args.dry_run:
        log.warning("RESEND_API_KEY or FEEDBACK_FROM_EMAIL not set; running as dry run")
        args.dry_run = True
    asyncio.run(run(dry_run=args.dry_run))
    if neatlogs_enabled:
        neatlogs.flush()
        neatlogs.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
