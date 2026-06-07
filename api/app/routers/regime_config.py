"""Regime-gate exempt allow-lists API — view/edit the symbols that the SPY and
BTC gates never block. Backs Settings → Market gate. The TradingView webhook
reads the same table per dispatch (with env fallback), so edits take effect on
the next fired alert — no redeploy.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.regime_config import REGIME_CONFIG_DEFAULTS, RegimeConfig
from app.models.user import User

router = APIRouter()


class RegimeConfigUpdate(BaseModel):
    index_exempt: Optional[str] = None   # comma-separated stock symbols
    crypto_exempt: Optional[str] = None  # comma-separated crypto symbols
    alert_symbols: Optional[str] = None  # symbols allowed to fire info alerts


def _norm(s: str) -> str:
    """Normalize a comma list — trim, upper-case, drop blanks/dupes (stable)."""
    seen: list[str] = []
    for x in s.split(","):
        t = x.strip().upper()
        if t and t not in seen:
            seen.append(t)
    return ",".join(seen)


async def _current(db: AsyncSession) -> dict:
    rows = (await db.execute(select(RegimeConfig.key, RegimeConfig.value))).all()
    cfg = {k: v for k, v in rows}
    return {k: cfg.get(k, REGIME_CONFIG_DEFAULTS.get(k, "")) for k in REGIME_CONFIG_DEFAULTS}


@router.get("")
async def get_regime_config(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The current exempt allow-lists (falls back to defaults if unseeded)."""
    return await _current(db)


@router.put("")
async def set_regime_config(
    body: RegimeConfigUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update one or both exempt lists. Takes effect on the next fired alert."""
    updates = {
        "index_exempt": body.index_exempt,
        "crypto_exempt": body.crypto_exempt,
        "alert_symbols": body.alert_symbols,
    }
    for key, raw in updates.items():
        if raw is None:
            continue
        value = _norm(raw)
        row = (await db.execute(
            select(RegimeConfig).where(RegimeConfig.key == key)
        )).scalar_one_or_none()
        if row is None:
            db.add(RegimeConfig(key=key, value=value))
        else:
            row.value = value
    await db.commit()
    return await _current(db)
