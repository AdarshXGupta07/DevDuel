import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.services.billing_service import (
    BillingDisabled,
    BillingError,
    billing_status,
    cancel_subscription,
    create_subscription,
    handle_webhook,
    sync_subscription,
    verify_webhook_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


class SyncRequest(BaseModel):
    subscription_id: str


@router.get("/status")
async def status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await billing_status(db, current_user)


@router.post("/subscribe")
async def subscribe(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a subscription and return what Razorpay Checkout needs.

    Nothing here grants access — the user has not paid yet.
    """
    try:
        return await create_subscription(db, current_user)
    except BillingDisabled as e:
        raise HTTPException(status_code=503, detail=str(e))
    except BillingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sync")
async def sync(
    payload: SyncRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-check a subscription with Razorpay after the browser reports success.

    The request body is only a *pointer* to what to re-check — the answer comes from
    Razorpay's API, never from the client.
    """
    try:
        return await sync_subscription(db, current_user, payload.subscription_id)
    except BillingDisabled as e:
        raise HTTPException(status_code=503, detail=str(e))
    except BillingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cancel")
async def cancel(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel at the end of the paid period — never a mid-period cut-off."""
    try:
        return await cancel_subscription(db, current_user, at_cycle_end=True)
    except BillingDisabled as e:
        raise HTTPException(status_code=503, detail=str(e))
    except BillingError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook", include_in_schema=False)
async def webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None),
    x_razorpay_event_id: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Razorpay → us. Unauthenticated by design; the signature *is* the authentication.

    Always returns 200 once the signature verifies, even on an internal error: a non-2xx
    makes Razorpay retry, and retrying will not fix a bug in our handler. Failures are
    logged with the event id so they can be replayed deliberately.
    """
    raw = await request.body()

    if not verify_webhook_signature(raw, x_razorpay_signature):
        logger.warning("rejected webhook with bad signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    if not x_razorpay_event_id:
        raise HTTPException(status_code=400, detail="Missing event id")

    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Malformed payload")

    try:
        return await handle_webhook(db, x_razorpay_event_id, body)
    except Exception:  # noqa: BLE001
        logger.exception("webhook %s failed to process", x_razorpay_event_id)
        return {"status": "error_logged"}


@router.get("/config", include_in_schema=False)
async def billing_config():
    """What the frontend needs to know before showing an upgrade button."""
    return {
        "enabled": settings.billing_enabled,
        "test_mode": settings.billing_is_test_mode,
        "amount_paise": settings.subscription_amount_paise,
        "currency": "INR",
    }
