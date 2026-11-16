"""Stripe Checkout + webhooks → Supabase entitlements (plan_credits / subscription_status)."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Any

import stripe

from app.core.auth import AuthUser
from app.core.config import Settings
from app.core.errors import ApiError
from app.services.db import Database

log = logging.getLogger(__name__)


class BillingService:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        if settings.STRIPE_SECRET_KEY:
            stripe.api_key = settings.STRIPE_SECRET_KEY

    def _require(self, mode: str = "plan") -> None:
        ok = (
            self.settings.memo_billing_configured
            if mode in {"memo", "pro"}
            else self.settings.stripe_configured
        )
        if not ok:
            raise ApiError(503, "stripe_error", "Billing is not configured on this server")

    def _price(self, mode: str) -> str | None:
        return {
            "plan": self.settings.STRIPE_PRICE_PLAN,
            "subscription": self.settings.STRIPE_PRICE_SUBSCRIPTION,
            "memo": self.settings.STRIPE_PRICE_MEMO,
            "pro": self.settings.STRIPE_PRICE_PRO,
        }[mode]

    async def _customer_id(self, user: AuthUser, profile: dict[str, Any]) -> str:
        if profile.get("stripe_customer_id"):
            return str(profile["stripe_customer_id"])
        customer = await asyncio.to_thread(
            stripe.Customer.create, email=user.email or None, metadata={"user_id": user.id}
        )
        await self.db.update("profiles", {"id": user.id}, {"stripe_customer_id": customer.id})
        return str(customer.id)

    async def checkout_url(
        self, user: AuthUser, profile: dict[str, Any], mode: str, success_url: str, cancel_url: str
    ) -> str:
        self._require()
        customer = await self._customer_id(user, profile)
        price = (
            self.settings.STRIPE_PRICE_SUBSCRIPTION
            if mode == "subscription"
            else self.settings.STRIPE_PRICE_PLAN
        )
        try:
            session = await asyncio.to_thread(
                stripe.checkout.Session.create,
                mode="subscription" if mode in {"subscription", "pro"} else "payment",
                customer=customer,
                client_reference_id=user.id,
                line_items=[{"price": price, "quantity": 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                allow_promotion_codes=True,
                metadata={"user_id": user.id, "purchase": mode},
            )
        except stripe.StripeError as exc:
            raise ApiError(502, "stripe_error", f"Stripe error: {exc.user_message or exc}") from exc
        return str(session.url)

    async def portal_url(self, user: AuthUser, profile: dict[str, Any], return_url: str) -> str:
        self._require()
        customer = await self._customer_id(user, profile)
        try:
            session = await asyncio.to_thread(
                stripe.billing_portal.Session.create, customer=customer, return_url=return_url
            )
        except stripe.StripeError as exc:
            raise ApiError(502, "stripe_error", f"Stripe error: {exc.user_message or exc}") from exc
        return str(session.url)

    def construct_event(self, payload: bytes, signature: str | None) -> stripe.Event:
        if not self.settings.STRIPE_WEBHOOK_SECRET:
            raise ApiError(503, "stripe_error", "STRIPE_WEBHOOK_SECRET is not set")
        try:
            return stripe.Webhook.construct_event(
                payload, signature or "", self.settings.STRIPE_WEBHOOK_SECRET
            )
        except (ValueError, stripe.SignatureVerificationError) as exc:
            raise ApiError(400, "stripe_error", "Invalid webhook signature") from exc

    async def _profile_for(self, *, user_id: str | None, customer_id: str | None) -> dict[str, Any] | None:
        if user_id:
            rows = await self.db.select("profiles", filters={"id": user_id})
            if rows:
                return rows[0]
        if customer_id:
            rows = await self.db.select("profiles", filters={"stripe_customer_id": customer_id})
            if rows:
                return rows[0]
        return None

    async def handle_event(self, event: dict[str, Any]) -> str:
        """Apply a Stripe event to entitlements. Returns a short description of what happened."""
        kind = event.get("type", "")
        obj = (event.get("data") or {}).get("object") or {}
        if kind == "checkout.session.completed":
            meta = obj.get("metadata") or {}
            profile = await self._profile_for(
                user_id=meta.get("user_id") or obj.get("client_reference_id"), customer_id=obj.get("customer")
            )
            if profile is None:
                return "ignored: unknown user"
            values: dict[str, Any] = {
                "stripe_customer_id": obj.get("customer") or profile.get("stripe_customer_id")
            }
            if obj.get("mode") == "payment":
                values["plan_credits"] = int(profile.get("plan_credits") or 0) + 1
                await self.db.update("profiles", {"id": profile["id"]}, values)
                await self.db.insert(
                    "usage_events",
                    {"user_id": profile["id"], "event": "upgrade", "properties": {"kind": "plan"}},
                )
                return "credited 1 plan"
            values["subscription_status"] = "active"
            values["stripe_subscription_id"] = obj.get("subscription")
            await self.db.update("profiles", {"id": profile["id"]}, values)
            await self.db.insert(
                "usage_events",
                {"user_id": profile["id"], "event": "upgrade", "properties": {"kind": "subscription"}},
            )
            return "subscription activated"
        if kind in {
            "customer.subscription.updated",
            "customer.subscription.created",
            "customer.subscription.deleted",
        }:
            profile = await self._profile_for(
                user_id=(obj.get("metadata") or {}).get("user_id"), customer_id=obj.get("customer")
            )
            if profile is None:
                return "ignored: unknown customer"
            status = "canceled" if kind.endswith("deleted") else str(obj.get("status") or "active")
            period_end = obj.get("current_period_end")
            if period_end is None:
                items = (obj.get("items") or {}).get("data") or [{}]
                period_end = items[0].get("current_period_end") if items else None
            values = {
                "subscription_status": status,
                "stripe_subscription_id": obj.get("id"),
                "current_period_end": dt.datetime.fromtimestamp(int(period_end), tz=dt.UTC).isoformat()
                if period_end
                else None,
            }
            await self.db.update("profiles", {"id": profile["id"]}, values)
            return f"subscription {status}"
        if kind == "invoice.payment_failed":
            profile = await self._profile_for(user_id=None, customer_id=obj.get("customer"))
            if profile is not None:
                await self.db.update("profiles", {"id": profile["id"]}, {"subscription_status": "past_due"})
                return "subscription past_due"
        return "ignored"
