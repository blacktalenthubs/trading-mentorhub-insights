"""Alert-symbol config API — view/edit the alert-delivery lists (info-alert
symbols + the alerts_all_symbols master switch / alert_watchlist exceptions).
The TradingView webhook reads the same table per dispatch, so edits take effect
on the next fired alert — no redeploy. (The SPY/BTC regime-gate exempt lists
were removed with the gates, #169/#173.)
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
    alert_symbols: Optional[str] = None  # symbols allowed to fire info alerts
    alerts_all_symbols: Optional[str] = None  # master switch: "true"=all, "false"=exceptions only
    alert_watchlist: Optional[str] = None  # exception symbols when the master switch is off
    spy_trend_gate_enabled: Optional[str] = None  # "true"/"false" — SPY-below-8&21 long gate
    spy_trend_exempt: Optional[str] = None  # symbols still allowed to fire longs when SPY rolled over


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
        "alert_symbols": body.alert_symbols,
        "alerts_all_symbols": body.alerts_all_symbols,
        "alert_watchlist": body.alert_watchlist,
        "spy_trend_gate_enabled": body.spy_trend_gate_enabled,
        "spy_trend_exempt": body.spy_trend_exempt,
    }
    _BOOL_KEYS = {"alerts_all_symbols", "spy_trend_gate_enabled"}
    for key, raw in updates.items():
        if raw is None:
            continue
        # bool flags store true/false; the rest are normalized symbol lists.
        if key in _BOOL_KEYS:
            value = "false" if (raw or "").strip().lower() in ("false", "0", "no", "off") else "true"
        else:
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
