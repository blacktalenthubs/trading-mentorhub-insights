"""Rumi signal ingest (2026-11-27) — Victor's agent-run lanes log their
DELIVERED signals to the desk so he can review them in the "Rumi signals"
feed tab.

Accepts POST `/api/v1/rumi/signals` from the lane runner (the 4H / VP / SMA
engines on Victor's machine). These signals are already gated and deduped
by the lanes themselves, so — unlike the TV webhook — there is NO pipeline
here: no HTF gate, no confluence merge, no notifier. The rows land in the
alerts table for the owner account only, with channel="app" (recorded,
never re-pushed — the lanes already delivered them to Telegram/chat).

Auth: shared secret in the `X-Rumi-Secret` header, compared against the
`RUMI_INGEST_SECRET` env var. When the env var is unset the endpoint
returns 503 — a forgotten caller can never write rows.

Owner: the user whose email matches `RUMI_OWNER_EMAIL`; when unset,
DEFAULT_OWNER_EMAIL (Victor's login); last resort the earliest account.
Visibility does NOT depend on the owner — the feed's read endpoints serve
rumi_* rows to every logged-in user (see alerts.py `_feed_scope_clause`).

Idempotent: a signal whose (user, alert_type, symbol, session_date,
created_at) already exists is skipped, so the poster can retry / re-run a
whole day safely. alert_type is `rumi_4h` / `rumi_vp` / `rumi_sma`.
"""
from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alert import Alert
from app.models.user import User

logger = logging.getLogger("rumi_signals")
router = APIRouter()

_LANES = {"4h", "vp", "sma"}


class RumiSignal(BaseModel):
    symbol: str
    direction: str  # LONG | SHORT
    lane: str  # 4h | vp | sma
    entry: float
    stop: Optional[float] = None
    target: Optional[float] = None
    price: Optional[float] = None  # fire price; defaults to entry
    reason: Optional[str] = None
    card: Optional[str] = None  # full delivered card text, kept as narrative
    fired_at: str  # ISO 8601 with offset
    session_date: str  # YYYY-MM-DD — the ET trading day


class RumiBatch(BaseModel):
    signals: List[RumiSignal]


def _check_secret(header_value: Optional[str]) -> None:
    secret = os.environ.get("RUMI_INGEST_SECRET", "")
    if not secret:
        raise HTTPException(503, "rumi ingest not configured")
    if not header_value or not hmac.compare_digest(header_value, secret):
        raise HTTPException(401, "bad rumi secret")


# Victor's desk login — the canonical owner of the Rumi log (Victor,
# 2026-11-28: "always only vbolofidne@gmail.com"). Visibility no longer
# depends on this (the feed serves rumi_* rows to every logged-in user);
# the owner is bookkeeping for the rows themselves.
DEFAULT_OWNER_EMAIL = "vbolofidne@gmail.com"


async def _owner(db: AsyncSession) -> User:
    email = os.environ.get("RUMI_OWNER_EMAIL", "").strip() \
        or DEFAULT_OWNER_EMAIL
    user = (await db.execute(
        select(User).where(User.email == email)
    )).scalars().first()
    if user is not None:
        return user
    logger.warning("rumi ingest: owner email %s not found, "
                   "falling back to earliest account", email)
    user = (await db.execute(
        select(User).order_by(User.id).limit(1)
    )).scalars().first()
    if user is None:
        raise HTTPException(500, "no user account to own rumi signals")
    return user


@router.post("/signals")
async def ingest_signals(
    batch: RumiBatch,
    db: AsyncSession = Depends(get_db),
    x_rumi_secret: Optional[str] = Header(default=None),
):
    _check_secret(x_rumi_secret)
    owner = await _owner(db)
    inserted = 0
    skipped = 0
    for sig in batch.signals:
        lane = sig.lane.strip().lower()
        if lane not in _LANES:
            skipped += 1
            continue
        direction = sig.direction.strip().upper()
        if direction not in ("LONG", "SHORT"):
            skipped += 1
            continue
        try:
            fired = datetime.fromisoformat(
                sig.fired_at.replace("Z", "+00:00"))
        except ValueError:
            skipped += 1
            continue
        if fired.tzinfo is None:
            fired = fired.replace(tzinfo=timezone.utc)
        fired_naive = fired.astimezone(timezone.utc).replace(tzinfo=None)
        alert_type = f"rumi_{lane}"
        symbol = sig.symbol.strip().upper()
        existing = (await db.execute(
            select(Alert.id).where(
                Alert.user_id == owner.id,
                Alert.alert_type == alert_type,
                Alert.symbol == symbol,
                Alert.session_date == sig.session_date,
                Alert.created_at == fired_naive,
            )
        )).scalars().first()
        if existing is not None:
            skipped += 1
            continue
        db.add(Alert(
            user_id=owner.id,
            symbol=symbol,
            alert_type=alert_type,
            direction=direction,
            price=sig.price if sig.price is not None else sig.entry,
            entry=sig.entry,
            stop=sig.stop,
            target_1=sig.target,
            message=sig.reason,
            narrative=sig.card,
            session_date=sig.session_date,
            created_at=fired_naive,
            channel="app",
            trade_type="day",
        ))
        inserted += 1
    if inserted:
        await db.commit()
    logger.info("rumi ingest: owner=%s inserted=%d skipped=%d",
                owner.email, inserted, skipped)
    return {"inserted": inserted, "skipped": skipped, "owner": owner.email}
