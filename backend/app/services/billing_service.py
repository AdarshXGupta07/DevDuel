"""Razorpay subscriptions.

Two rules govern everything in this file:

1. **The client never decides who is paid.** The browser's "payment succeeded" callback
   is a hint to re-check, never a fact. Plan changes come from Razorpay — either a signed
   webhook, or a server-to-server fetch of the subscription.
2. **Webhooks are at-least-once.** The same event *will* arrive twice, so every one is
   recorded against a UNIQUE `provider_event_id` and replays are dropped. This is Day
   10's delivery-semantics lesson, now with money attached.

Uses the REST API directly over httpx rather than the `razorpay` SDK, which is
synchronous and would block the event loop on every call.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Payment, Subscription, User, utcnow

logger = logging.getLogger(__name__)

API_BASE = "https://api.razorpay.com/v1"

# Razorpay subscription states that mean "this person has paid and should have access".
PAID_STATES = {"active", "authenticated", "pending"}
# `pending` = a renewal charge failed and Razorpay is retrying. Access continues through
# the grace window rather than cutting off mid-duel over a bank blip.
ENDED_STATES = {"cancelled", "completed", "expired"}


class BillingDisabled(Exception):
    pass


class BillingError(Exception):
    pass


def _require_enabled() -> None:
    if not settings.billing_enabled:
        raise BillingDisabled("Billing is not configured on this server.")


def _auth() -> tuple[str, str]:
    return (settings.razorpay_key_id, settings.razorpay_key_secret)


async def _post(path: str, payload: dict) -> dict:
    _require_enabled()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(f"{API_BASE}{path}", json=payload, auth=_auth())
    if response.status_code >= 400:
        logger.error("razorpay POST %s failed: %s %s", path, response.status_code, response.text)
        raise BillingError(f"Payment provider rejected the request ({response.status_code}).")
    return response.json()


async def _get(path: str) -> dict:
    _require_enabled()
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"{API_BASE}{path}", auth=_auth())
    if response.status_code >= 400:
        logger.error("razorpay GET %s failed: %s %s", path, response.status_code, response.text)
        raise BillingError(f"Payment provider rejected the request ({response.status_code}).")
    return response.json()


def _ts(value) -> datetime | None:
    """Razorpay sends unix seconds. Everything in our schema is timezone-aware."""
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


# ------------------------------------------------------------------ create / read


async def create_subscription(db: AsyncSession, user: User) -> dict:
    """Start a subscription and hand the browser what Checkout needs.

    Nothing about the user's plan changes here — they have not paid yet. The row is
    recorded as `created` so a webhook arriving before the browser returns still finds
    something to attach to.
    """
    _require_enabled()

    existing = await active_subscription(db, user.id)
    if existing and existing.status in PAID_STATES:
        raise BillingError("You already have an active subscription.")

    entity = await _post(
        "/subscriptions",
        {
            "plan_id": settings.razorpay_plan_id,
            "total_count": settings.subscription_total_count,
            "customer_notify": 1,
            "notes": {"user_id": str(user.id), "email": user.email},
        },
    )

    subscription = Subscription(
        user_id=user.id,
        provider="razorpay",
        provider_sub_id=entity["id"],
        status=entity.get("status", "created"),
        current_period_end=_ts(entity.get("current_end")),
        amount_paise=settings.subscription_amount_paise,
        raw_payload=entity,
    )
    db.add(subscription)
    await db.commit()

    return {
        "subscription_id": entity["id"],
        "key_id": settings.razorpay_key_id,
        "amount_paise": settings.subscription_amount_paise,
        "test_mode": settings.billing_is_test_mode,
        "name": user.name,
        "email": user.email,
    }


async def active_subscription(db: AsyncSession, user_id) -> Subscription | None:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def billing_status(db: AsyncSession, user: User) -> dict:
    subscription = await active_subscription(db, user.id)
    return {
        "enabled": settings.billing_enabled,
        "test_mode": settings.billing_is_test_mode,
        "plan": user.plan,
        "is_paid": user.is_paid,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        "amount_paise": settings.subscription_amount_paise,
        "subscription": (
            {
                "id": subscription.provider_sub_id,
                "status": subscription.status,
                "current_period_end": (
                    subscription.current_period_end.isoformat()
                    if subscription.current_period_end
                    else None
                ),
            }
            if subscription
            else None
        ),
    }


# ------------------------------------------------------------------ applying state


async def _apply_entity(db: AsyncSession, entity: dict) -> Subscription | None:
    """Reconcile one Razorpay subscription entity into our tables.

    This is the only place `users.plan` is written, so there is exactly one code path
    that can make someone paid.
    """
    sub_id = entity.get("id")
    if not sub_id:
        return None

    result = await db.execute(
        select(Subscription).where(Subscription.provider_sub_id == sub_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        # A subscription we have no record of — possible if the create call succeeded at
        # Razorpay but our commit failed. Recover it from the notes we attached.
        user_id = (entity.get("notes") or {}).get("user_id")
        if not user_id:
            logger.warning("webhook for unknown subscription %s with no user note", sub_id)
            return None
        subscription = Subscription(
            user_id=user_id,
            provider="razorpay",
            provider_sub_id=sub_id,
            status=entity.get("status", "created"),
            amount_paise=settings.subscription_amount_paise,
        )
        db.add(subscription)

    subscription.status = entity.get("status", subscription.status)
    subscription.current_period_end = _ts(entity.get("current_end")) or (
        subscription.current_period_end
    )
    subscription.raw_payload = entity
    subscription.updated_at = utcnow()

    user = await db.get(User, subscription.user_id)
    if user is not None:
        if subscription.status in PAID_STATES:
            user.plan = "paid"
            # Access runs to the paid-for period end plus a grace window, so a retrying
            # renewal never locks someone out mid-match.
            end = subscription.current_period_end
            user.plan_expires_at = (
                end + timedelta(days=settings.billing_grace_days) if end else None
            )
        elif subscription.status == "halted":
            # Repeated charge failures: keep access only through the grace window.
            user.plan_expires_at = utcnow() + timedelta(days=settings.billing_grace_days)
        elif subscription.status in ENDED_STATES:
            # Cancelled mid-period still keeps what was paid for; only then does it lapse.
            end = subscription.current_period_end
            if end is None or end <= utcnow():
                user.plan = "free"
                user.plan_expires_at = None
            else:
                user.plan_expires_at = end

    await db.commit()
    return subscription


async def sync_subscription(db: AsyncSession, user: User, subscription_id: str) -> dict:
    """Server-to-server re-check, used right after the browser reports success.

    The browser is not believed — this fetches the subscription from Razorpay and applies
    whatever *they* say. It exists so a user is not stuck on "free" while waiting for a
    webhook that may take seconds to arrive.
    """
    _require_enabled()

    owned = await db.execute(
        select(Subscription).where(
            Subscription.provider_sub_id == subscription_id,
            Subscription.user_id == user.id,
        )
    )
    if owned.scalar_one_or_none() is None:
        raise BillingError("Unknown subscription.")

    entity = await _get(f"/subscriptions/{subscription_id}")
    await _apply_entity(db, entity)
    await db.refresh(user)
    return await billing_status(db, user)


async def cancel_subscription(db: AsyncSession, user: User, at_cycle_end: bool = True) -> dict:
    subscription = await active_subscription(db, user.id)
    if subscription is None or subscription.status in ENDED_STATES:
        raise BillingError("No active subscription to cancel.")

    entity = await _post(
        f"/subscriptions/{subscription.provider_sub_id}/cancel",
        {"cancel_at_cycle_end": 1 if at_cycle_end else 0},
    )
    await _apply_entity(db, entity)
    await db.refresh(user)
    return await billing_status(db, user)


# ---------------------------------------------------------------------- webhooks


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    """HMAC-SHA256 of the **raw** body with the webhook secret.

    Raw, not re-serialised JSON: any reordering or whitespace change breaks the digest.
    `compare_digest` rather than `==` so a wrong signature cannot be found byte by byte
    through timing.
    """
    if not signature or not settings.razorpay_webhook_secret:
        return False
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


HANDLED_EVENTS = {
    "subscription.authenticated",
    "subscription.activated",
    "subscription.charged",
    "subscription.updated",
    "subscription.pending",
    "subscription.halted",
    "subscription.cancelled",
    "subscription.completed",
}


async def handle_webhook(db: AsyncSession, event_id: str, body: dict) -> dict:
    """Process one webhook exactly once."""
    event_type = body.get("event", "")
    entity = (((body.get("payload") or {}).get("subscription") or {}).get("entity")) or {}
    payment = (((body.get("payload") or {}).get("payment") or {}).get("entity")) or {}

    # Idempotency gate. The UNIQUE constraint on provider_event_id is the mechanism —
    # not a prior SELECT, which would race with a simultaneous redelivery.
    ledger = Payment(
        user_id=None,
        provider="razorpay",
        provider_event_id=event_id,
        event_type=event_type,
        amount_paise=payment.get("amount"),
        status=payment.get("status") or entity.get("status"),
        raw_payload=body,
    )
    db.add(ledger)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.info("duplicate webhook %s (%s) ignored", event_id, event_type)
        return {"status": "duplicate"}

    if event_type not in HANDLED_EVENTS:
        logger.info("webhook %s ignored (not handled)", event_type)
        return {"status": "ignored"}

    subscription = await _apply_entity(db, entity)
    if subscription is not None and ledger.user_id is None:
        ledger.user_id = subscription.user_id
        await db.commit()

    logger.info("webhook %s applied for subscription %s", event_type, entity.get("id"))
    return {"status": "ok"}
