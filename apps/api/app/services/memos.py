"""Persistence + entitlements for Location Risk Memos (teaser / unlock / Pro / bulk / answer rounds)."""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from typing import Any

from pydantic import ValidationError

from app.core.auth import AuthUser
from app.core.config import Settings
from app.core.errors import ApiError
from app.memo.answers import (
    ANSWER_ROUND_LIMIT,
    ANSWERS_LIMIT_MESSAGE,
    ANSWERS_NOT_READY_MESSAGE,
    ANSWERS_RUNNING_MESSAGE,
    ANSWERS_STOPPED_MESSAGE,
    ANSWERS_UNAVAILABLE_MESSAGE,
    IntakeBasis,
    basis_of,
)
from app.memo.intake import IntakeAnswers
from app.memo.stated import without_model_text
from app.models.memo import (
    STATUS_SEVERITY,
    Memo,
    MemoRecord,
    MemoRevision,
    MemoSummary,
    MemoTeaser,
)
from app.models.profile import BusinessProfile, ClarifyingQuestion
from app.services.db import Database, DuplicateKeyError, utcnow
from app.services.plans import ACTIVE_SUBSCRIPTION, PlanService

log = logging.getLogger(__name__)

# Report format 3 (2026-11-12): the rules and the evidence only. A memo stored in an earlier format is withheld.
FORMAT_VERSION = 3
LEGACY_MESSAGE = (
    "This memo was generated in an earlier report format and cannot be shown in the current one. "
    "Run the address again to get the current report."
)

# The one free re-run of a legacy memo the user unlocked (paid for, or opened with Pro or an owner account). No
# migration: two things already in the schema record it.
# - The claim is the new memo's own primary key. Attempt k at a free re-run of legacy memo L creates its memo with
#   the id uuid5(FREE_RERUN_NAMESPACE, "L:k"), so two requests that both find attempt k open race on one insert
#   and the database lets one through; the other is charged like any new memo.
# - The record is a usage event FREE_RERUN_EVENT with properties {legacy_memo_id, memo_id, attempt}, written
#   right after that insert (if it cannot be written, the new memo is removed and the request fails). It outlives
#   the memo, so a deleted free re-run still counts as used.
# An attempt gives the free re-run back when its memo failed, was deleted before it was ready, or has not
# finished (still generating, or waiting for a clarification answer) FREE_RERUN_RELEASE_AFTER after it last
# changed: a run takes minutes, so such a memo was abandoned (the page was closed mid-run, or the server
# restarted). Once a later attempt exists, an earlier one is no longer free if it ever finishes.
FREE_RERUN_EVENT = "memo_rerun_free"
FREE_RERUN_NAMESPACE = uuid.UUID("5b0f6c7e-2f0e-4c55-9a43-8d2b1f3e7a10")
FREE_RERUN_RELEASE_AFTER = dt.timedelta(minutes=30)
# A memo still "generating" this long after it last changed counts as failed, wherever it is read (the memo, the
# list, a batch, the free re-run rules). A run takes about a minute; one that has not finished in this time was cut
# off (the page that started it was closed or navigated away, or the API restarted), and nothing else would ever
# mark it. Nothing is charged for it: a free preview is counted only when a memo is ready, and a credit only when one
# is unlocked. The stored row is left as it is; only what the API reports changes. A bulk upload refreshes the rows
# still waiting in its queue each time it starts the next one (`touch_batch`), so a queued row is not taken for a
# stalled one.
GENERATING_TIMEOUT = dt.timedelta(minutes=15)
STALLED_MESSAGE = "This memo stopped before it was finished. Nothing was charged for it. Run it again."
RERUN_NOT_LEGACY_MESSAGE = (
    "Only a memo in an earlier report format is re-run this way. Start a new memo for this address instead."
)

# Answer rounds (owner decision of 2026-11-16, app.memo.answers): a memo is run again with more intake answers, free,
# on the same memo, up to ANSWER_ROUND_LIMIT times. What is stored (supabase/migrations/20261116000000_memo_answers.sql):
# - memos.intake_basis: what the intake of the memo's first run left (`IntakeBasis`), written right after the memo is
#   saved (`save_basis`). A round puts its answers on it, with no model call.
# - memos.answers_run: the claim of the round running now, a fresh uuid each round. A round starts only by changing
#   the claim the row had (`start_answers`), so of two requests at once one starts and the other is refused; and a
#   round saves (or ends) only while its claim is still the row's, so a round left behind by a restart never
#   overwrites a later one. A round that stalled saves nothing even when its claim is still the row's: it was
#   reported stopped and not counted, so its late result ends the row as stopped (`save_answers_result`).
# - memos.answers_round: the rounds that finished and were saved; memos.answered_at: when the last one was.
# - memo_revisions: one row per finished round, holding the version it replaced (round, intake, profile, memo,
#   teaser), with the id uuid5(REVISION_NAMESPACE, "memo:round").
# A round never changes `access` or `unlocked_at`, and never counts a free preview or uses a credit. While it runs the
# memo is "generating" and still holds the report from before it, which can be unlocked as a ready memo's can; a round that fails, or stops (still generating
# GENERATING_TIMEOUT after its claim), leaves that report as it was, reads "ready" with the error line
# ANSWERS_FAILED_MESSAGE / ANSWERS_STOPPED_MESSAGE, and is not counted.
REVISION_NAMESPACE = uuid.UUID("0d7c2b9e-5a41-4f0e-8c3b-6e9f1a2d4b70")


def _changed_at(row: dict[str, Any]) -> dt.datetime | None:
    stamp = row.get("updated_at") or row.get("created_at")
    try:
        changed = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return changed if changed.tzinfo is not None else changed.replace(tzinfo=dt.UTC)


def is_stalled(row: dict[str, Any], now: dt.datetime | None = None) -> bool:
    """True when the row is still "generating" GENERATING_TIMEOUT or more after it last changed."""
    if row.get("status") != "generating":
        return False
    changed = _changed_at(row)
    return changed is not None and (now or dt.datetime.now(dt.UTC)) - changed >= GENERATING_TIMEOUT


def is_answer_round(row: dict[str, Any]) -> bool:
    """True when the row's run is an answer round (`answers_run` holds the round's claim). The row then still holds
    the report from before the round, which stays as it is unless the round finishes."""
    return row.get("status") == "generating" and bool(row.get("answers_run")) and bool(row.get("memo"))


def effective_status(row: dict[str, Any], now: dt.datetime | None = None) -> str:
    """The status the API reports for a row: its stored status, except that a stalled run is "failed". A stalled
    answer round is "ready": the report from before it is still there, as it was (ANSWERS_STOPPED_MESSAGE)."""
    if is_stalled(row, now):
        return "ready" if is_answer_round(row) else "failed"
    return str(row["status"])


def is_legacy(row: dict[str, Any]) -> bool:
    """True when the row holds a memo stored before report format 3 (no `format_version`, or another one).
    Such a memo is never parsed: the API withholds it and its teaser and says `legacy_format`."""
    stored = row.get("memo")
    if not stored:
        return False
    return not (isinstance(stored, dict) and stored.get("format_version") == FORMAT_VERSION)


def _parse_stored(row: dict[str, Any]) -> tuple[Memo | None, MemoTeaser | None, bool]:
    """(memo, teaser, legacy_format) for a stored row, without ever raising on what is in the database."""
    if is_legacy(row):
        return None, None, True
    try:
        memo = Memo.model_validate(row["memo"]) if row.get("memo") else None
        teaser = MemoTeaser.model_validate(row["teaser"]) if row.get("teaser") else None
    except ValidationError:
        # marked format 3 but does not fit today's schema: withhold it rather than fail the request. That
        # includes every memo stored before the rules set the statuses (it has no `pathway` and no rule lines
        # on its rows): a report whose statuses a model chose is not shown as if a rule had set them.
        log.warning("memo %s does not validate as report format %s", row.get("id"), FORMAT_VERSION)
        return None, None, True
    return memo, teaser, False


class MemoService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.plans = PlanService(db, settings)

    # ---- entitlements ----------------------------------------------------------------------
    @staticmethod
    def is_pro(profile: dict[str, Any]) -> bool:
        return profile.get("pro_status") in ACTIVE_SUBSCRIPTION

    def is_unlimited(self, profile: dict[str, Any]) -> bool:
        """Pro, or an owner account in ADMIN_EMAILS: every memo is created unlocked, no credit is used, and the
        Pro features (bulk upload) are open."""
        return self.is_pro(profile) or self.plans.is_admin(profile)

    def memo_entitlement(self, profile: dict[str, Any]) -> dict[str, Any]:
        credits = int(profile.get("memo_credits") or 0)
        teasers = int(profile.get("teasers_generated") or 0)
        pro = self.is_unlimited(profile)
        remaining = max(0, self.settings.FREE_TEASER_LIMIT - teasers)
        return {
            "memo_credits": credits,
            "pro_status": profile.get("pro_status"),
            "pro_current_period_end": profile.get("pro_current_period_end"),
            "free_teasers_remaining": remaining,
            "can_create_memo": pro or credits > 0 or remaining > 0,
            "can_unlock": pro or credits > 0,
            "is_admin": self.plans.is_admin(profile),
        }

    def _unlock_via(self, profile: dict[str, Any]) -> str:
        if self.is_pro(profile):
            return "pro"
        return "admin" if self.plans.is_admin(profile) else "credit"

    async def assert_can_create(self, user: AuthUser) -> dict[str, Any]:
        profile = await self.plans.ensure_profile(user)
        ent = self.memo_entitlement(profile)
        # a run left behind by a closed page still finishes and counts its preview, so previews still running are
        # spoken for (with no credit and not unlimited)
        if (
            ent["can_create_memo"]
            and not self.is_unlimited(profile)
            and not ent["memo_credits"]
            and ent["free_teasers_remaining"] - await self.running_count(user) <= 0
        ):
            ent["can_create_memo"] = False
        if not ent["can_create_memo"]:
            await self.plans.record_event(
                user.id, "memo_paywall_hit", {"teasers_generated": profile.get("teasers_generated")}
            )
            raise ApiError(
                402,
                "paywall_memo",
                "You have used your free memo previews.",
                free_teaser_limit=self.settings.FREE_TEASER_LIMIT,
            )
        return profile

    async def assert_pro(self, user: AuthUser) -> dict[str, Any]:
        profile = await self.plans.ensure_profile(user)
        if not self.is_unlimited(profile):
            raise ApiError(403, "pro_required", "Bulk address upload is a Pro feature ($299/month).")
        return profile

    async def count_teaser(self, user: AuthUser) -> None:
        profile = await self.plans.ensure_profile(user)
        if self.is_unlimited(profile):
            return
        await self.db.update(
            "profiles", {"id": user.id}, {"teasers_generated": int(profile.get("teasers_generated") or 0) + 1}
        )

    # ---- rows --------------------------------------------------------------------------------
    async def create(
        self,
        user: AuthUser,
        *,
        address: str,
        description: str,
        lat: float | None,
        lng: float | None,
        batch_id: str | None = None,
        intake: IntakeAnswers | None = None,
        memo_id: str | None = None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "user_id": user.id,
            "address": address,
            "lat": lat,
            "lng": lng,
            "description": description,
            "profile": None,
            "status": "generating",
            "access": "teaser",
            "teaser": None,
            "memo": None,
            "clarification": None,
            "batch_id": batch_id,
            "error": None,
            "unlocked_at": None,
            "feedback_email_sent_at": None,
        }
        # The answers are stored only when one was given, so a row without them never needs the column
        # (supabase/migrations/20261111000000_memo_intake.sql adds it).
        if intake is not None and not intake.empty:
            row["intake"] = intake.model_dump(exclude_none=True)
        if memo_id is not None:  # a free re-run's claim (FREE_RERUN_EVENT); otherwise the database picks it
            row["id"] = memo_id
        return await self.db.insert("memos", row)

    @staticmethod
    def intake_of(row: dict[str, Any]) -> IntakeAnswers:
        """The intake answers stored with a memo row. A stored row never fails a request: a key this version does
        not know (one a later version wrote, read here after a rollback) is dropped, and so is a known key whose
        value no longer validates, so the other answers are kept. Empty when there are none, or when what is left
        still does not validate (two answers that contradict each other)."""
        stored = row.get("intake")
        if not isinstance(stored, dict) or not stored:
            return IntakeAnswers()
        known = {k: v for k, v in stored.items() if k in IntakeAnswers.model_fields}
        if len(known) != len(stored):
            log.warning("memo %s has intake keys this version does not know: dropped", row.get("id"))
        try:
            return IntakeAnswers.model_validate(known)
        except ValidationError as exc:
            bad = {str(e["loc"][0]) for e in exc.errors() if e["loc"]}
            log.warning("memo %s has intake answers that do not validate: %s", row.get("id"), sorted(bad))
            try:
                return IntakeAnswers.model_validate({k: v for k, v in known.items() if k not in bad})
            except ValidationError:
                return IntakeAnswers()

    async def row(self, user: AuthUser, memo_id: str) -> dict[str, Any]:
        rows = await self.db.select("memos", filters={"id": memo_id, "user_id": user.id})
        if not rows:
            raise ApiError(404, "not_found", "Memo not found")
        return rows[0]

    async def set_clarification(
        self, memo_id: str, questions: list[ClarifyingQuestion], profile: BusinessProfile
    ) -> None:
        await self.db.update(
            "memos",
            {"id": memo_id},
            {
                "status": "pending_clarification",
                "profile": profile.model_dump(),
                "clarification": {"questions": [q.model_dump() for q in questions], "answers": {}},
            },
        )

    async def set_generating(self, memo_id: str, row: dict[str, Any], answers: dict[str, Any]) -> None:
        clar = row.get("clarification") or {"questions": [], "answers": {}}
        clar["answers"] = answers
        await self.db.update(
            "memos", {"id": memo_id}, {"status": "generating", "clarification": clar, "error": None}
        )

    # ---- the free re-run of a legacy memo the user unlocked ------------------------------------------
    async def rerun_source(self, user: AuthUser, memo_id: str) -> dict[str, Any]:
        """The legacy memo named by `rerun_of` on a create request. Another user's memo, or one that does not
        exist, is 404 `not_found` (as on every memo route); a memo in the current format is 409
        `rerun_not_legacy` (its report is shown, so there is nothing to re-run it for)."""
        row = await self.row(user, memo_id)
        if not _parse_stored(row)[2]:
            raise ApiError(409, "rerun_not_legacy", RERUN_NOT_LEGACY_MESSAGE, memo_id=memo_id)
        return row

    @staticmethod
    def free_rerun_memo_id(legacy_memo_id: str, attempt: int) -> str:
        """The id of the memo made by attempt `attempt` (0, 1, ...) at the free re-run of `legacy_memo_id`."""
        return str(uuid.uuid5(FREE_RERUN_NAMESPACE, f"{legacy_memo_id}:{attempt}"))

    async def _free_rerun_grants(self, user: AuthUser) -> list[dict[str, Any]]:
        return await self.db.select("usage_events", filters={"user_id": user.id, "event": FREE_RERUN_EVENT})

    @staticmethod
    def _props(grant: dict[str, Any]) -> dict[str, Any]:
        props = grant.get("properties")
        return props if isinstance(props, dict) else {}

    @staticmethod
    def _abandoned(memo_row: dict[str, Any], now: dt.datetime) -> bool:
        if memo_row.get("status") not in {"generating", "pending_clarification"}:
            return False
        if memo_row.get("answers_run"):  # an answer round on a memo that was ready: it was not abandoned
            return False
        changed = _changed_at(memo_row)
        return changed is not None and now - changed >= FREE_RERUN_RELEASE_AFTER

    async def _released(self, grant: dict[str, Any], now: dt.datetime) -> bool:
        """True when the attempt `grant` records gave its free re-run back (see FREE_RERUN_EVENT)."""
        props = self._props(grant)
        if props.get("released_at"):
            return True
        new = await self.memo_by_id(str(props["memo_id"])) if props.get("memo_id") else None
        if new is None:  # deleted once it was ready (a deletion before that marks the grant released)
            return False
        # a stalled run counts as failed (GENERATING_TIMEOUT), so it gives the free re-run back as a failure does
        return effective_status(new, now) == "failed" or self._abandoned(new, now)

    async def free_rerun_attempt(self, user: AuthUser, legacy_row: dict[str, Any]) -> int | None:
        """The number of the next free attempt at re-running `legacy_row`, or None when it has no free re-run:
        it is not a legacy memo the user unlocked, or an earlier attempt is ready, deleted once ready, or still
        running."""
        if legacy_row.get("access") != "full" or not _parse_stored(legacy_row)[2]:
            return None
        legacy_id = str(legacy_row["id"])
        grants = [
            g
            for g in await self._free_rerun_grants(user)
            if self._props(g).get("legacy_memo_id") == legacy_id
        ]
        now = dt.datetime.now(dt.UTC)
        for grant in grants:
            if not await self._released(grant, now):
                return None
        return max((int(self._props(g).get("attempt") or 0) for g in grants), default=-1) + 1

    async def free_rerun_available(self, user: AuthUser, legacy_row: dict[str, Any]) -> bool:
        return await self.free_rerun_attempt(user, legacy_row) is not None

    async def create_free_rerun(
        self, user: AuthUser, legacy_row: dict[str, Any], attempt: int, *, intake: IntakeAnswers
    ) -> dict[str, Any] | None:
        """Create the memo of free attempt `attempt` at re-running `legacy_row`, with that memo's address,
        coordinates and description, and record it. None when another request took this attempt first: the
        caller then charges the re-run like any new memo. If the record cannot be written, the new memo is removed
        and the request fails, so no memo is made free without the record that stops a second free re-run."""
        legacy_id = str(legacy_row["id"])
        memo_id = self.free_rerun_memo_id(legacy_id, attempt)
        try:
            row = await self.create(
                user,
                address=legacy_row["address"],
                description=legacy_row["description"],
                lat=legacy_row.get("lat"),
                lng=legacy_row.get("lng"),
                intake=intake,
                memo_id=memo_id,
            )
        except DuplicateKeyError:
            log.info("free re-run %s of memo %s was taken by another request", attempt, legacy_id)
            return None
        try:
            await self.db.insert(
                "usage_events",
                {
                    "user_id": user.id,
                    "event": FREE_RERUN_EVENT,
                    "properties": {"legacy_memo_id": legacy_id, "memo_id": memo_id, "attempt": attempt},
                },
            )
        except ApiError:
            await self.db.delete("memos", {"id": memo_id, "user_id": user.id})
            raise
        return row

    async def free_rerun_grant(self, user: AuthUser, memo_id: str) -> dict[str, Any] | None:
        """The record of the free re-run attempt that made `memo_id`, if one did."""
        return next(
            (g for g in await self._free_rerun_grants(user) if self._props(g).get("memo_id") == memo_id), None
        )

    async def is_free_rerun(self, user: AuthUser, memo_id: str) -> bool:
        """True when `memo_id` is a free re-run attempt that is still the latest attempt for its legacy memo and
        was not given back by a deletion. An attempt abandoned and then finished after a later attempt was made
        is charged like any new memo."""
        grants = await self._free_rerun_grants(user)
        mine = next((g for g in grants if self._props(g).get("memo_id") == memo_id), None)
        if mine is None or self._props(mine).get("released_at"):
            return False
        legacy_id = self._props(mine).get("legacy_memo_id")
        attempt = int(self._props(mine).get("attempt") or 0)
        return not any(
            self._props(g).get("legacy_memo_id") == legacy_id
            and int(self._props(g).get("attempt") or 0) > attempt
            for g in grants
        )

    async def save_result(
        self,
        user: AuthUser,
        memo_id: str,
        profile: BusinessProfile,
        memo: Memo,
        teaser: MemoTeaser,
        *,
        lat: float,
        lng: float,
        address: str,
    ) -> dict[str, Any] | None:
        """Save a finished run. Only a row still "generating" is saved: None (and nothing charged) when the memo was
        deleted, or already ended, while the run went on. A run that finishes after its memo was reported stalled
        (GENERATING_TIMEOUT: the page said nothing was charged) is saved without counting a preview."""
        current = await self.memo_by_id(memo_id)
        if current is None or current.get("status") != "generating":
            log.info("memo %s ended or was deleted while its run went on; result not saved", memo_id)
            return None
        stalled = is_stalled(current)
        prof = await self.plans.ensure_profile(user)
        unlocked = self.is_unlimited(prof) or await self.is_free_rerun(user, memo_id)
        access = "full" if unlocked else "teaser"
        values: dict[str, Any] = {
            "status": "ready",
            "profile": profile.model_dump(),
            "memo": memo.model_dump(),
            "teaser": teaser.model_dump(),
            "access": access,
            "lat": lat,
            "lng": lng,
            "address": address,
            "error": None,
        }
        if access == "full":
            values["unlocked_at"] = utcnow()
        saved = await self.db.update("memos", {"id": memo_id, "status": "generating"}, values)
        if not saved:  # deleted (or ended) between the read above and this write
            return None
        if access == "teaser" and not stalled:
            await self.count_teaser(user)
        return saved[0]

    async def touch_batch(self, batch_id: str) -> None:
        """Mark the rows of a bulk upload that are still waiting as changed now, so the ones queued behind a long
        batch are not taken for stalled runs (GENERATING_TIMEOUT)."""
        await self.db.update(
            "memos",
            {"batch_id": batch_id, "status": "generating"},
            {"status": "generating", "updated_at": utcnow()},
        )

    async def mark_failed(self, memo_id: str, message: str) -> None:
        await self.db.update("memos", {"id": memo_id}, {"status": "failed", "error": message[:500]})

    async def mark_failed_if_running(self, memo_id: str, message: str) -> bool:
        """Mark the memo failed only while it is still running, and say whether it did: a run that raised after its
        memo was saved (or after it asked a clarification question) leaves the memo as it is."""
        changed = await self.db.update(
            "memos", {"id": memo_id, "status": "generating"}, {"status": "failed", "error": message[:500]}
        )
        return bool(changed)

    async def running_count(self, user: AuthUser) -> int:
        """Memos of the user still running (not stalled), outside bulk uploads: each will count a free preview when
        it is ready, so the create paywall counts them now. An answer round counts no preview, so it is not one."""
        rows = await self.db.select("memos", filters={"user_id": user.id, "status": "generating"})
        return sum(
            1 for r in rows if not r.get("batch_id") and not is_stalled(r) and not r.get("answers_run")
        )

    async def unlock(self, user: AuthUser, memo_id: str) -> MemoRecord:
        row = await self.row(user, memo_id)
        if row.get("access") == "full":
            return self.to_record(row)
        # a memo in an answer round, running or stopped, holds the report from before the round, and a round never
        # changes `access` or `unlocked_at`: it is unlocked as a ready memo is
        if effective_status(row) != "ready" and not is_answer_round(row):
            raise ApiError(409, "not_ready", "The memo is not ready yet")
        # never spend a credit on a memo that would be withheld: an earlier format, or a row marked format 3
        # that no longer validates (the same test `to_record` applies)
        if _parse_stored(row)[2]:
            raise ApiError(409, "legacy_format", LEGACY_MESSAGE, memo_id=memo_id)
        profile = await self.plans.ensure_profile(user)
        ent = self.memo_entitlement(profile)
        if not ent["can_unlock"]:
            await self.plans.record_event(user.id, "memo_paywall_hit", {"memo_id": memo_id, "at": "unlock"})
            raise ApiError(
                402, "paywall_memo", "Unlock this memo with a $499 Operator credit or Pro.", memo_id=memo_id
            )
        if not self.is_unlimited(profile):
            await self.db.update(
                "profiles",
                {"id": user.id},
                {"memo_credits": max(0, int(profile.get("memo_credits") or 0) - 1)},
            )
        await self.db.update("memos", {"id": memo_id}, {"access": "full", "unlocked_at": utcnow()})
        await self.plans.record_event(
            user.id, "memo_unlocked", {"memo_id": memo_id, "via": self._unlock_via(profile)}
        )
        return self.to_record((await self.db.select("memos", filters={"id": memo_id}))[0])

    async def delete(self, user: AuthUser, memo_id: str) -> None:
        row = await self.row(user, memo_id)
        # a memo in an answer round is "generating" again, but it was ready: deleting it gives nothing back
        if row.get("status") != "ready" and not row.get("answers_run"):
            # a free re-run deleted before it was ready (failed, stuck, or waiting for a clarification answer)
            # gives the free re-run back; once its memo is gone that can no longer be told from the memo
            grant = await self.free_rerun_grant(user, memo_id)
            if grant is not None:
                props = {**self._props(grant), "released_at": utcnow()}
                await self.db.update("usage_events", {"id": grant["id"]}, {"properties": props})
        if row.get("answers_round") or row.get("answers_run"):
            # the table's foreign key removes them too; the in-memory twin has none
            await self.db.delete("memo_revisions", {"memo_id": memo_id, "user_id": user.id})
        await self.db.delete("memos", {"id": memo_id, "user_id": user.id})

    # ---- answer rounds (app.memo.answers; see REVISION_NAMESPACE) --------------------------------------------
    async def save_basis(self, memo_id: str, basis: IntakeBasis) -> dict[str, Any] | None:
        """Keep what the intake of the memo's run left, for answer rounds. Never fails the run: without it (the
        column is missing, the write failed) the memo is only not answered that way, and None comes back."""
        try:
            saved = await self.db.update(
                "memos", {"id": memo_id}, {"intake_basis": basis.model_dump(mode="json")}
            )
        except ApiError:
            log.warning("memo %s: intake basis not saved; it cannot be answered with a round", memo_id)
            return None
        return saved[0] if saved else None

    async def answers_source(self, user: AuthUser, memo_id: str) -> tuple[dict[str, Any], IntakeBasis]:
        """The memo an answer round is for, and its intake basis. Another user's memo, or one that does not exist,
        is 404 `not_found`; a legacy memo 409 `legacy_format`; one still being made, or in a round now, 409
        `not_ready` or `answers_running`; one made before the basis was kept 409 `answers_unavailable`; one with no
        round left 409 `answers_round_limit`."""
        row = await self.row(user, memo_id)
        if _parse_stored(row)[2]:
            raise ApiError(409, "legacy_format", LEGACY_MESSAGE, memo_id=memo_id)
        status = effective_status(row)
        if status not in {"ready", "failed"}:
            if is_answer_round(row):
                raise ApiError(409, "answers_running", ANSWERS_RUNNING_MESSAGE, memo_id=memo_id)
            raise ApiError(409, "not_ready", ANSWERS_NOT_READY_MESSAGE, memo_id=memo_id)
        basis = basis_of(row.get("intake_basis"))
        if basis is None or not row.get("memo"):
            raise ApiError(409, "answers_unavailable", ANSWERS_UNAVAILABLE_MESSAGE, memo_id=memo_id)
        if int(row.get("answers_round") or 0) >= ANSWER_ROUND_LIMIT:
            raise ApiError(
                409,
                "answers_round_limit",
                ANSWERS_LIMIT_MESSAGE,
                memo_id=memo_id,
                answers_round_limit=ANSWER_ROUND_LIMIT,
            )
        return row, basis

    async def start_answers(self, row: dict[str, Any]) -> str | None:
        """Claim an answer round on `row` as it was read: the row becomes "generating" with a new claim. None when
        the row changed since it was read (another round started first, or the memo was deleted)."""
        claim = str(uuid.uuid4())
        claimed = await self.db.update(
            "memos",
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "status": row["status"],
                "answers_run": row.get("answers_run"),
            },
            {"status": "generating", "answers_run": claim, "error": None, "updated_at": utcnow()},
        )
        return claim if claimed else None

    @staticmethod
    def revision_id(memo_id: str, round_no: int) -> str:
        return str(uuid.uuid5(REVISION_NAMESPACE, f"{memo_id}:{round_no}"))

    async def save_answers_result(
        self,
        memo_id: str,
        claim: str,
        round_no: int,
        answers: IntakeAnswers,
        profile: BusinessProfile,
        memo: Memo,
        teaser: MemoTeaser,
        *,
        lat: float,
        lng: float,
        address: str,
    ) -> dict[str, Any] | None:
        """Save a finished answer round: the version it replaces goes to memo_revisions first, then the memo takes
        the new report and the merged answers. Only while the round's claim is still the row's and the round has not
        stalled: None (and nothing saved) when the memo was deleted, a later round took it over, or the round is
        GENERATING_TIMEOUT old. The API already reports a stalled round as stopped and not counted
        (ANSWERS_STOPPED_MESSAGE), so its late result is dropped and the row is ended as the page showed it.
        `access`, `unlocked_at` and every count are left as they are."""
        current = await self.memo_by_id(memo_id)
        if current is None or current.get("status") != "generating" or current.get("answers_run") != claim:
            log.info("memo %s: answer round %s was ended or taken over; result not saved", memo_id, round_no)
            return None
        if is_stalled(current):
            log.info(
                "memo %s: answer round %s finished after it was reported stopped; not saved",
                memo_id,
                round_no,
            )
            await self.end_answers(memo_id, claim, ANSWERS_STOPPED_MESSAGE)
            return None
        rev_id = self.revision_id(memo_id, round_no)
        # an upsert: a revision left by a round whose save was cut off between these two writes is replaced
        await self.db.upsert(
            "memo_revisions",
            [
                {
                    "id": rev_id,
                    "memo_id": memo_id,
                    "user_id": current["user_id"],
                    "round": round_no,
                    "intake": current.get("intake"),
                    "profile": current.get("profile"),
                    "memo": current.get("memo"),
                    "teaser": current.get("teaser"),
                    "created_at": utcnow(),
                }
            ],
            on_conflict="id",
        )
        saved = await self.db.update(
            "memos",
            {"id": memo_id, "status": "generating", "answers_run": claim},
            {
                "status": "ready",
                "profile": profile.model_dump(),
                "memo": memo.model_dump(),
                "teaser": teaser.model_dump(),
                "intake": answers.model_dump(exclude_none=True),
                "answers_round": round_no,
                "answers_run": None,
                "answered_at": utcnow(),
                "lat": lat,
                "lng": lng,
                "address": address,
                "error": None,
            },
        )
        if not saved:  # deleted, or taken over, between the read above and this write
            await self.db.delete("memo_revisions", {"id": rev_id})
            return None
        return saved[0]

    async def end_answers(self, memo_id: str, claim: str, message: str) -> bool:
        """End an answer round that did not finish: the memo is as it was before the round, "ready", with `message`
        as its error line. Only while the round's claim is still the row's; says whether it ended it."""
        changed = await self.db.update(
            "memos",
            {"id": memo_id, "status": "generating", "answers_run": claim},
            {"status": "ready", "answers_run": None, "error": message[:500]},
        )
        return bool(changed)

    async def revisions(self, user: AuthUser, memo_id: str) -> list[MemoRevision]:
        """The versions answer rounds replaced, oldest first. Each shows what the memo shows now: the full report
        only when the memo is unlocked."""
        row = await self.row(user, memo_id)
        if not row.get("answers_round"):  # no round finished: nothing replaced (and no read of the table)
            return []
        full = row.get("access") == "full"
        rows = await self.db.select("memo_revisions", filters={"memo_id": memo_id, "user_id": user.id})
        out: list[MemoRevision] = []
        for rev in sorted(rows, key=lambda r: int(r.get("round") or 0)):
            memo, teaser, legacy = _parse_stored(rev)
            stored = rev.get("memo")
            generated = stored.get("generated_at") if isinstance(stored, dict) and not legacy else None
            out.append(
                MemoRevision(
                    round=int(rev["round"]),
                    replaced_at=str(rev["created_at"]),
                    generated_at=str(generated) if generated else None,
                    intake=self._intake_or_none(rev),
                    teaser=teaser,
                    memo=memo if full else None,
                    legacy_format=legacy,
                )
            )
        return out

    # ---- projections ---------------------------------------------------------------------------
    @staticmethod
    def to_record(row: dict[str, Any], *, force_access: str | None = None) -> MemoRecord:
        access = force_access or row.get("access") or "teaser"
        memo, teaser, legacy = _parse_stored(row)
        status = effective_status(row)
        rounds = int(row.get("answers_round") or 0)
        stalled = is_stalled(row)
        error: str | None = row.get("error")
        if stalled:
            error = ANSWERS_STOPPED_MESSAGE if is_answer_round(row) else STALLED_MESSAGE
        return MemoRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            address=row["address"],
            lat=row.get("lat"),
            lng=row.get("lng"),
            description=row["description"],
            # never the intake model's own text, whatever an older row stored (app.memo.stated)
            profile=without_model_text(BusinessProfile.model_validate(row["profile"]))
            if row.get("profile")
            else None,
            status=status,
            access=access,
            teaser=teaser,
            memo=memo if access == "full" else None,
            legacy_format=legacy,
            clarification=row.get("clarification"),
            intake=MemoService._intake_or_none(row),
            batch_id=str(row["batch_id"]) if row.get("batch_id") else None,
            created_at=str(row["created_at"]),
            updated_at=str(row.get("updated_at") or row["created_at"]),
            unlocked_at=row.get("unlocked_at"),
            error=error,
            answers_round=rounds,
            answers_rounds_left=max(0, ANSWER_ROUND_LIMIT - rounds),
            answers_running=is_answer_round(row) and not stalled,
            answers_available=(
                status == "ready"
                and not legacy
                and rounds < ANSWER_ROUND_LIMIT
                and basis_of(row.get("intake_basis")) is not None
            ),
            answered_at=str(row["answered_at"]) if row.get("answered_at") else None,
        )

    @staticmethod
    def _intake_or_none(row: dict[str, Any]) -> IntakeAnswers | None:
        answers = MemoService.intake_of(row)
        return None if answers.empty else answers

    async def record(self, user: AuthUser, memo_id: str) -> MemoRecord:
        row = await self.row(user, memo_id)
        rec = self.to_record(row)
        if rec.legacy_format and row.get("status") == "ready" and row.get("access") == "full":
            rec.rerun_free = await self.free_rerun_available(user, row)
        elif not rec.legacy_format:
            grant = await self.free_rerun_grant(user, rec.id)
            if grant is not None:
                rec.rerun_of = str(self._props(grant).get("legacy_memo_id") or "") or None
        return rec

    async def full_memo(self, user: AuthUser, memo_id: str) -> tuple[dict[str, Any], Memo]:
        row = await self.row(user, memo_id)
        if row.get("access") != "full" or not row.get("memo"):
            raise ApiError(402, "paywall_memo", "Unlock the memo to export it", memo_id=memo_id)
        memo, _teaser, legacy = _parse_stored(row)
        if legacy or memo is None:
            raise ApiError(409, "legacy_format", LEGACY_MESSAGE, memo_id=memo_id)
        return row, memo

    @staticmethod
    def summary(row: dict[str, Any]) -> MemoSummary:
        legacy = _parse_stored(row)[
            2
        ]  # as in `to_record`: a format-3 row that no longer validates is withheld
        stored = row.get("teaser")
        teaser: dict[str, Any] = stored if isinstance(stored, dict) and not legacy else {}
        status = teaser.get("overall_status")
        prof = row.get("profile") or {}
        concept = prof.get("business_type", "").replace("_", " ").title() if prof else row["description"][:60]
        return MemoSummary(
            id=str(row["id"]),
            address=row["address"],
            concept=concept or row["description"][:60],
            status=effective_status(row),
            access=row.get("access") or "teaser",
            overall_status=status if status in STATUS_SEVERITY else None,
            comparable_count=teaser.get("comparable_count"),
            legacy_format=legacy,
            created_at=str(row["created_at"]),
            batch_id=str(row["batch_id"]) if row.get("batch_id") else None,
        )

    async def list_summaries(self, user: AuthUser, *, batch_id: str | None = None) -> list[MemoSummary]:
        filters: dict[str, Any] = {"user_id": user.id}
        if batch_id:
            filters["batch_id"] = batch_id
        rows = await self.db.select("memos", filters=filters, order="created_at.desc")
        return [self.summary(r) for r in rows]

    async def create_batch(self, user: AuthUser, filename: str | None, row_count: int) -> dict[str, Any]:
        return await self.db.insert(
            "memo_batches", {"user_id": user.id, "filename": filename, "row_count": row_count}
        )

    # ---- admin / feedback ------------------------------------------------------------------------
    async def memo_stats(self) -> dict[str, Any]:
        rows = await self.db.select("memos")
        week_ago = (dt.datetime.now(dt.UTC) - dt.timedelta(days=7)).isoformat()
        by_status: dict[str, int] = {}
        legacy = 0
        for r in rows:
            # as in `to_record` and `summary`: a format-3 row that no longer validates counts as legacy
            if _parse_stored(r)[2]:
                legacy += 1
                continue
            v = (r.get("teaser") or {}).get("overall_status")
            if v:
                by_status[v] = by_status.get(v, 0) + 1
        return {
            "total": len(rows),
            "full": sum(1 for r in rows if r.get("access") == "full"),
            "teaser": sum(1 for r in rows if r.get("access") != "full"),
            "last_7_days": sum(1 for r in rows if str(r.get("created_at")) >= week_ago),
            "by_overall_status": by_status,
            "legacy_format": legacy,
            "feedback_emails_sent": sum(1 for r in rows if r.get("feedback_email_sent_at")),
        }

    async def user_stats(self) -> dict[str, Any]:
        rows = await self.db.select("profiles")
        return {"total": len(rows), "pro": sum(1 for r in rows if r.get("pro_status") in ACTIVE_SUBSCRIPTION)}

    async def memos_due_for_feedback(self, *, delay_days: int, limit: int = 200) -> list[dict[str, Any]]:
        cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(days=delay_days)).isoformat()
        rows = await self.db.select(
            "memos",
            filters={"status": "ready", "feedback_email_sent_at": None},
            order="created_at.asc",
            limit=limit,
        )
        return [r for r in rows if str(r.get("created_at")) <= cutoff]

    async def mark_feedback_sent(self, memo_id: str) -> None:
        await self.db.update("memos", {"id": memo_id}, {"feedback_email_sent_at": utcnow()})

    async def memo_by_id(self, memo_id: str) -> dict[str, Any] | None:
        rows = await self.db.select("memos", filters={"id": memo_id})
        return rows[0] if rows else None
