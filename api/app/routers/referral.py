"""Referral program — refer a friend, both get 1 month free Pro."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.referral import Referral
from app.models.user import Subscription, User

logger = logging.getLogger("referral")
router = APIRouter()

REWARD_DAYS = 30  # 1 month free Pro for both referrer and referred


def _generate_code(user_id: int, email: str) -> str:
    """Generate a short, unique referral code from user data."""
    raw = f"{user_id}:{email}:tradecopilot"
    return hashlib.md5(raw.encode()).hexdigest()[:8].upper()


@router.get("/code")
async def get_referral_code(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get or generate the user's referral code + stats."""
    # Generate code if not set
    if not user.referral_code:
        code = _generate_code(user.id, user.email)
        user.referral_code = code
        await db.flush()
    else:
        code = user.referral_code

    # Count referrals
    result = await db.execute(
        select(func.count()).where(Referral.referrer_id == user.id)
    )
    total_referrals = result.scalar() or 0

    rewarded_result = await db.execute(
        select(func.count()).where(
            Referral.referrer_id == user.id,
            Referral.status == "rewarded",
        )
    )
    rewarded = rewarded_result.scalar() or 0

    return {
        "code": code,
        "share_url": f"https://www.tradingwithai.ai/register?ref={code}",
        "total_referrals": total_referrals,
        "rewarded": rewarded,
        "reward": f"{REWARD_DAYS} days free Pro",
    }


@router.post("/apply")
async def apply_referral(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a referral code. Called during or after registration."""
    code = (body.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(400, "Referral code required")

    # Can't refer yourself
    if user.referral_code == code:
        raise HTTPException(400, "Cannot use your own referral code")

    # Check if already referred
    existing = await db.execute(
        select(Referral).where(Referral.referred_id == user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "You've already used a referral code")

    # Find referrer
    referrer = await db.execute(
        select(User).where(User.referral_code == code)
    )
    referrer_user = referrer.scalar_one_or_none()
    if not referrer_user:
        raise HTTPException(404, "Invalid referral code")

    # Create referral record
    ref = Referral(
        referrer_id=referrer_user.id,
        referred_id=user.id,
        referral_code=code,
        status="rewarded",
        rewarded_at=datetime.utcnow(),
    )
    db.add(ref)

    # Reward both users: extend trial / add Pro time
    for uid in (referrer_user.id, user.id):
        sub_result = await db.execute(
            select(Subscription).where(Subscription.user_id == uid)
        )
        sub = sub_result.scalar_one_or_none()
        if sub:
            # If already Pro/Premium, extend current_period_end
            if sub.tier in ("pro", "premium"):
                base = sub.current_period_end or datetime.utcnow()
                sub.current_period_end = base + timedelta(days=REWARD_DAYS)
            else:
                # Free user: give them Pro trial extension
                base = sub.trial_ends_at or datetime.utcnow()
                sub.trial_ends_at = base + timedelta(days=REWARD_DAYS)

    logger.info(
        "REFERRAL: %s (id=%d) referred %s (id=%d) with code %s",
        referrer_user.email, referrer_user.id, user.email, user.id, code,
    )

    return {
        "success": True,
        "message": f"Referral applied! Both you and your friend get {REWARD_DAYS} days free Pro.",
    }
