"""Square billing — subscription management endpoints."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import Subscription, User

logger = logging.getLogger("billing")
router = APIRouter()
settings = get_settings()


# ── Square client (lazy init) ─────────────────────────────────────────

_square_client = None


def _get_square():
    global _square_client
    if _square_client is None:
        from square import Square
        from square.environment import SquareEnvironment
        env = SquareEnvironment.SANDBOX if settings.SQUARE_ENVIRONMENT == "sandbox" else SquareEnvironment.PRODUCTION
        _square_client = Square(
            token=settings.SQUARE_ACCESS_TOKEN,
            environment=env,
        )
    return _square_client


# ── Plan → tier mapping ──────────────────────────────────────────────

def _plan_to_tier(plan_variation_id: str) -> str:
    if plan_variation_id == settings.SQUARE_PRO_PLAN_ID:
        return "pro"
    if plan_variation_id == settings.SQUARE_PREMIUM_PLAN_ID:
        return "premium"
    return "free"


# ── Request/Response schemas ──────────────────────────────────────────

class SubscribeRequest(BaseModel):
    nonce: str  # Card nonce from Square Web Payments SDK
    plan: str   # "pro" or "premium"


class BillingStatusResponse(BaseModel):
    tier: str
    status: str
    square_subscription_id: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/status", response_model=BillingStatusResponse)
async def billing_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current billing status for the user."""
    sub = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub_row = sub.scalar_one_or_none()

    return BillingStatusResponse(
        tier=sub_row.tier if sub_row else "free",
        status=sub_row.status if sub_row else "none",
        square_subscription_id=sub_row.stripe_customer_id if sub_row else None,
    )


@router.post("/subscribe")
async def subscribe(
    body: SubscribeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a Square subscription for the user.

    Flow: create/get customer → store card → create subscription → update tier.
    """
    if not settings.SQUARE_ACCESS_TOKEN:
        raise HTTPException(503, "Billing not configured")

    sq = _get_square()

    plan_id = (
        settings.SQUARE_PRO_PLAN_ID if body.plan == "pro"
        else settings.SQUARE_PREMIUM_PLAN_ID if body.plan == "premium"
        else None
    )
    if not plan_id:
        raise HTTPException(400, f"Unknown plan: {body.plan}")

    # Get or create Square customer
    sub = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub_row = sub.scalar_one_or_none()
    square_customer_id = sub_row.stripe_customer_id if sub_row else None

    if not square_customer_id:
        try:
            cust_result = sq.customers.create(
                idempotency_key=str(uuid.uuid4()),
                email_address=user.email,
                reference_id=str(user.id),
            )
            square_customer_id = cust_result.customer.id
        except Exception as e:
            logger.error("Create customer failed: %s", e)
            raise HTTPException(502, "Failed to create billing customer")

    # Store card on file
    try:
        card_result = sq.cards.create(
            idempotency_key=str(uuid.uuid4()),
            source_id=body.nonce,
            card={"customer_id": square_customer_id},
        )
        card_id = card_result.card.id
    except Exception as e:
        logger.error("Create card failed: %s", e)
        raise HTTPException(502, "Failed to store payment method")

    # Create subscription
    try:
        sub_result = sq.subscriptions.create(
            idempotency_key=str(uuid.uuid4()),
            location_id=settings.SQUARE_LOCATION_ID,
            plan_variation_id=plan_id,
            customer_id=square_customer_id,
            card_id=card_id,
        )
        sq_sub_id = sub_result.subscription.id
        sq_sub_status = sub_result.subscription.status
    except Exception as e:
        logger.error("Create subscription failed: %s", e)
        raise HTTPException(502, "Failed to create subscription")

    tier = _plan_to_tier(plan_id)

    # Update DB
    if sub_row:
        sub_row.tier = tier
        sub_row.status = "active"
        sub_row.stripe_customer_id = square_customer_id  # reusing column for square
    else:
        db.add(Subscription(
            user_id=user.id,
            tier=tier,
            status="active",
            stripe_customer_id=square_customer_id,
        ))
    await db.commit()

    logger.info("SUBSCRIBE: user=%d tier=%s sq_sub=%s", user.id, tier, sq_sub_id)
    return {
        "tier": tier,
        "subscription_id": sq_sub_id,
        "status": sq_sub_status,
    }


@router.post("/cancel")
async def cancel_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel the user's subscription. Tier reverts to free."""
    if not settings.SQUARE_ACCESS_TOKEN:
        raise HTTPException(503, "Billing not configured")

    sub = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    sub_row = sub.scalar_one_or_none()
    if not sub_row or sub_row.status != "active" or sub_row.tier == "free":
        raise HTTPException(400, "No active subscription to cancel")

    # Find and cancel the Square subscription
    sq = _get_square()
    try:
        search = sq.subscriptions.search(
            query={
                "filter": {
                    "customer_ids": [sub_row.stripe_customer_id],
                    "location_ids": [settings.SQUARE_LOCATION_ID],
                }
            }
        )
        for sq_sub in (search.subscriptions or []):
            if sq_sub.status == "ACTIVE":
                sq.subscriptions.cancel(subscription_id=sq_sub.id)
                logger.info("CANCEL: user=%d sq_sub=%s", user.id, sq_sub.id)
    except Exception as e:
        logger.error("Cancel search failed: %s", e)

    # Downgrade to free
    sub_row.tier = "free"
    sub_row.status = "canceled"
    await db.commit()

    return {"tier": "free", "status": "canceled"}


# ── Square Webhook ────────────────────────────────────────────────────

@router.post("/webhooks/square")
async def square_webhook(request: Request):
    """Handle Square subscription lifecycle events."""
    body = await request.body()
    signature = request.headers.get("x-square-hmacsha256-signature", "")

    # Verify signature in production
    if settings.SQUARE_WEBHOOK_SIGNATURE_KEY:
        webhook_url = str(request.url)
        combined = webhook_url.encode() + body
        expected = hmac.new(
            settings.SQUARE_WEBHOOK_SIGNATURE_KEY.encode(),
            combined,
            hashlib.sha256,
        ).digest()
        import base64
        expected_b64 = base64.b64encode(expected).decode()
        if not hmac.compare_digest(expected_b64, signature):
            raise HTTPException(403, "Invalid webhook signature")

    event = await request.json()
    event_type = event.get("type", "")
    logger.info("Square webhook: %s", event_type)

    if event_type in ("subscription.created", "subscription.updated"):
        sq_sub = event.get("data", {}).get("object", {}).get("subscription", {})
        customer_id = sq_sub.get("customer_id")
        status = sq_sub.get("status", "")
        plan_id = sq_sub.get("plan_variation_id", "")

        if not customer_id:
            return {"status": "ok"}

        from app.database import async_session_factory
        async with async_session_factory() as db:
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_customer_id == customer_id)
            )
            sub_row = result.scalar_one_or_none()
            if sub_row:
                if status == "ACTIVE":
                    sub_row.tier = _plan_to_tier(plan_id)
                    sub_row.status = "active"
                elif status in ("CANCELED", "DEACTIVATED"):
                    sub_row.tier = "free"
                    sub_row.status = "canceled"
                elif status == "PAUSED":
                    sub_row.status = "paused"
                await db.commit()
                logger.info("Webhook updated: customer=%s tier=%s status=%s",
                            customer_id, sub_row.tier, sub_row.status)

    return {"status": "ok"}
