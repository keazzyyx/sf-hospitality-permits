"""Persistence + entitlement logic for plans, steps, profiles, previews and usage events."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from app.core.auth import AuthUser
from app.core.config import Settings
from app.core.errors import ApiError
from app.models.plan import (
    Clarification,
    Entitlement,
    Me,
    Plan,
    PlanRecord,
    PlanStepRecord,
    PlanSummary,
)
from app.models.profile import BusinessProfile, ClarifyingQuestion
from app.services.db import Database, utcnow

log = logging.getLogger(__name__)
ACTIVE_SUBSCRIPTION = {"active", "trialing"}


def business_title(profile: BusinessProfile | None, description: str) -> str:
    if profile is None:
        return description.strip()[:60] or "New plan"
    kind = profile.business_type.replace("_", " ").title()
    where = profile.city_name or profile.state or "Unknown location"
    if profile.state and profile.city_name and profile.state.lower() not in profile.city_name.lower():
        where = f"{profile.city_name}, {profile.state}"
    return f"{kind} · {where}"


class PlanService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    # ---- profiles / entitlements ---------------------------------------------------------
    async def ensure_profile(self, user: AuthUser) -> dict[str, Any]:
        rows = await self.db.select("profiles", filters={"id": user.id})
        if rows:
            if user.email and rows[0].get("email") != user.email:
                await self.db.update("profiles", {"id": user.id}, {"email": user.email})
                rows[0]["email"] = user.email
            return rows[0]
        return await self.db.insert(
            "profiles",
            {
                "id": user.id,
                "email": user.email,
                "plans_created": 0,
                "plan_credits": 0,
                "subscription_status": None,
                "stripe_customer_id": None,
                "current_period_end": None,
            },
        )

    def entitlement_for(self, profile: dict[str, Any]) -> Me:
        created = int(profile.get("plans_created") or 0)
        credits = int(profile.get("plan_credits") or 0)
        status = profile.get("subscription_status")
        limit = self.settings.FREE_PLAN_LIMIT
        if status in ACTIVE_SUBSCRIPTION:
            kind = "subscription"
        elif credits > 0:
            kind = "credits"
        else:
            kind = "free"
        remaining = max(0, limit - created)
        can_create = kind == "subscription" or remaining > 0 or credits > 0 or self.is_admin(profile)
        return Me(
            id=str(profile["id"]),
            email=profile.get("email"),
            plans_created=created,
            free_limit=limit,
            free_plans_remaining=remaining,
            entitlement=Entitlement(
                kind=kind,
                plan_credits=credits,
                subscription_status=status,  # type: ignore[arg-type,unused-ignore]
                current_period_end=profile.get("current_period_end"),
            ),
            can_create_plan=can_create,
        )

    def is_admin(self, profile: dict[str, Any]) -> bool:
        """An owner account: its email is in ADMIN_EMAILS (case and spaces ignored). Owners get unlimited
        checklists and memos, with no paywall and no credit used."""
        email = (profile.get("email") or "").strip().lower()
        return bool(email) and email in {e.strip().lower() for e in self.settings.ADMIN_EMAILS if e.strip()}

    async def assert_can_create(self, user: AuthUser) -> dict[str, Any]:
        profile = await self.ensure_profile(user)
        me = self.entitlement_for(profile)
        if not me.can_create_plan:
            await self.record_event(user.id, "paywall_hit", {"plans_created": me.plans_created})
            raise ApiError(
                402,
                "paywall",
                "You have used your free plans.",
                plans_created=me.plans_created,
                free_limit=me.free_limit,
            )
        return profile

    async def consume_plan(self, user: AuthUser) -> None:
        profile = await self.ensure_profile(user)
        me = self.entitlement_for(profile)
        values: dict[str, Any] = {"plans_created": me.plans_created + 1}
        if me.entitlement.kind == "credits" and me.free_plans_remaining == 0 and not self.is_admin(profile):
            values["plan_credits"] = max(0, me.entitlement.plan_credits - 1)
        await self.db.update("profiles", {"id": user.id}, values)

    async def record_event(
        self, user_id: str | None, event: str, properties: dict[str, Any] | None = None
    ) -> None:
        try:
            await self.db.insert(
                "usage_events", {"user_id": user_id, "event": event, "properties": properties or {}}
            )
        except ApiError:
            log.warning("usage event %s not recorded", event)

    # ---- plans --------------------------------------------------------------------------
    async def create_plan(
        self, user: AuthUser, description: str, target_open_date: str | None
    ) -> dict[str, Any]:
        return await self.db.insert(
            "plans",
            {
                "user_id": user.id,
                "title": business_title(None, description),
                "description": description,
                "target_open_date": target_open_date,
                "status": "generating",
                "version": 1,
                "profile": None,
                "clarification": None,
                "plan": None,
                "error": None,
            },
        )

    async def get_plan_row(self, user: AuthUser, plan_id: str) -> dict[str, Any]:
        rows = await self.db.select("plans", filters={"id": plan_id, "user_id": user.id})
        if not rows:
            raise ApiError(404, "not_found", "Plan not found")
        return rows[0]

    async def set_clarification(
        self, plan_id: str, questions: list[ClarifyingQuestion], profile: BusinessProfile
    ) -> None:
        await self.db.update(
            "plans",
            {"id": plan_id},
            {
                "status": "pending_clarification",
                "profile": profile.model_dump(),
                "clarification": {"questions": [q.model_dump() for q in questions], "answers": {}},
                "title": business_title(profile, ""),
            },
        )

    async def set_generating(
        self,
        plan_id: str,
        *,
        description: str | None = None,
        target_open_date: str | None = None,
        bump_version: bool = False,
        current_version: int = 1,
    ) -> None:
        values: dict[str, Any] = {"status": "generating", "error": None}
        if description is not None:
            values["description"] = description
        if target_open_date is not None:
            values["target_open_date"] = target_open_date
        if bump_version:
            values["version"] = current_version + 1
        await self.db.update("plans", {"id": plan_id}, values)

    async def save_clarification_answers(
        self, plan_id: str, row: dict[str, Any], answers: dict[str, Any]
    ) -> None:
        clar = row.get("clarification") or {"questions": [], "answers": {}}
        clar["answers"] = answers
        await self.db.update("plans", {"id": plan_id}, {"clarification": clar})

    async def save_result(self, plan_id: str, profile: BusinessProfile, plan: Plan) -> None:
        await self.db.update(
            "plans",
            {"id": plan_id},
            {
                "status": "ready",
                "profile": profile.model_dump(),
                "plan": plan.model_dump(),
                "title": business_title(profile, ""),
                "error": None,
            },
        )
        await self._sync_steps(plan_id, plan)

    async def mark_failed(self, plan_id: str, message: str) -> None:
        await self.db.update("plans", {"id": plan_id}, {"status": "failed", "error": message[:500]})

    async def _sync_steps(self, plan_id: str, plan: Plan) -> None:
        existing = {
            r["step_key"]: r for r in await self.db.select("plan_steps", filters={"plan_id": plan_id})
        }
        keep = {s.id for s in plan.steps}
        gone = [k for k in existing if k not in keep]
        if gone:
            await self.db.delete("plan_steps", {"plan_id": plan_id, "step_key": ("in", gone)})
        rows = []
        for s in plan.steps:
            prev = existing.get(s.id)
            rows.append(
                {
                    "plan_id": plan_id,
                    "step_key": s.id,
                    "position": s.order,
                    "name": s.name,
                    "done": bool(prev["done"]) if prev else False,
                    "done_at": prev.get("done_at") if prev else None,
                    "notes": prev.get("notes") if prev else None,
                }
            )
        await self.db.upsert("plan_steps", rows, on_conflict="plan_id,step_key")

    async def record(self, user: AuthUser, plan_id: str) -> PlanRecord:
        row = await self.get_plan_row(user, plan_id)
        steps = await self.db.select("plan_steps", filters={"plan_id": plan_id}, order="position.asc")
        return self._to_record(row, steps)

    @staticmethod
    def _to_record(row: dict[str, Any], steps: list[dict[str, Any]]) -> PlanRecord:
        return PlanRecord(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            title=row["title"],
            description=row["description"],
            target_open_date=row.get("target_open_date"),
            status=row["status"],
            version=int(row.get("version") or 1),
            created_at=str(row["created_at"]),
            updated_at=str(row.get("updated_at") or row["created_at"]),
            profile=BusinessProfile.model_validate(row["profile"]) if row.get("profile") else None,
            clarification=Clarification.model_validate(row["clarification"])
            if row.get("clarification")
            else None,
            plan=Plan.model_validate(row["plan"]) if row.get("plan") else None,
            steps=[
                PlanStepRecord(
                    id=str(s["id"]),
                    plan_id=str(s["plan_id"]),
                    step_key=s["step_key"],
                    position=int(s["position"]),
                    name=s["name"],
                    done=bool(s["done"]),
                    done_at=s.get("done_at"),
                    notes=s.get("notes"),
                )
                for s in sorted(steps, key=lambda s: int(s["position"]))
            ],
            error=row.get("error"),
        )

    async def list_summaries(self, user: AuthUser) -> list[PlanSummary]:
        rows = await self.db.select("plans", filters={"user_id": user.id}, order="created_at.desc")
        if not rows:
            return []
        steps = await self.db.select("plan_steps", filters={"plan_id": ("in", [r["id"] for r in rows])})
        counts: dict[str, list[int]] = {}
        for s in steps:
            c = counts.setdefault(str(s["plan_id"]), [0, 0])
            c[0] += 1
            c[1] += 1 if s.get("done") else 0
        out = []
        for r in rows:
            plan = r.get("plan") or {}
            prof = r.get("profile") or {}
            total, done = counts.get(str(r["id"]), [0, 0])
            out.append(
                PlanSummary(
                    id=str(r["id"]),
                    title=r["title"],
                    status=r["status"],
                    version=int(r.get("version") or 1),
                    city_name=(plan.get("jurisdiction") or {}).get("city_name") or prof.get("city_name"),
                    business_type=prof.get("business_type"),
                    target_open_date=r.get("target_open_date"),
                    projected_open_date=(plan.get("timeline") or {}).get("projected_open_date"),
                    steps_total=total,
                    steps_done=done,
                    created_at=str(r["created_at"]),
                    updated_at=str(r.get("updated_at") or r["created_at"]),
                )
            )
        return out

    async def patch_step(
        self, user: AuthUser, plan_id: str, step_id: str, *, done: bool | None, notes: str | None
    ) -> PlanStepRecord:
        await self.get_plan_row(user, plan_id)
        rows = await self.db.select("plan_steps", filters={"id": step_id, "plan_id": plan_id})
        if not rows:
            raise ApiError(404, "not_found", "Step not found")
        values: dict[str, Any] = {}
        if done is not None:
            values["done"] = done
            values["done_at"] = utcnow() if done else None
        if notes is not None:
            values["notes"] = notes[:2000]
        updated = (await self.db.update("plan_steps", {"id": step_id}, values))[0] if values else rows[0]
        s = updated
        return PlanStepRecord(
            id=str(s["id"]),
            plan_id=str(s["plan_id"]),
            step_key=s["step_key"],
            position=int(s["position"]),
            name=s["name"],
            done=bool(s["done"]),
            done_at=s.get("done_at"),
            notes=s.get("notes"),
        )

    async def delete_plan(self, user: AuthUser, plan_id: str) -> None:
        await self.get_plan_row(user, plan_id)
        await self.db.delete("plan_steps", {"plan_id": plan_id})
        await self.db.delete("plans", {"id": plan_id, "user_id": user.id})

    # ---- previews (pre-auth) ---------------------------------------------------------------
    async def create_preview(self, description: str, target_open_date: str | None, ip: str) -> dict[str, Any]:
        return await self.db.insert(
            "previews",
            {
                "description": description,
                "target_open_date": target_open_date,
                "status": "generating",
                "ip_hash": hashlib.sha256(ip.encode()).hexdigest()[:32],
                "profile": None,
                "result": None,
                "clarification": None,
            },
        )

    async def get_preview(self, preview_id: str) -> dict[str, Any]:
        rows = await self.db.select("previews", filters={"id": preview_id})
        if not rows:
            raise ApiError(404, "not_found", "Preview not found or expired")
        return rows[0]

    async def update_preview(self, preview_id: str, values: dict[str, Any]) -> None:
        await self.db.update("previews", {"id": preview_id}, values)

    async def capture_lead(
        self, email: str, city: str | None, state: str | None, description: str | None
    ) -> None:
        await self.db.insert(
            "leads", {"email": email, "city": city, "state": state, "description": description}
        )
