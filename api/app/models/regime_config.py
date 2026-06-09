"""Alert-symbol config — admin-editable key/value table (no redeploy).

Holds the Alert-symbols settings the webhook reads per dispatch (same session
as the alert_type_config read). The SPY/BTC regime-gate exempt lists
(index_exempt / crypto_exempt) were REMOVED 2026-06-08 with the gates
themselves (#169/#173) — only the alert-delivery keys remain.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RegimeConfig(Base):
    __tablename__ = "regime_config"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


REGIME_CONFIG_DEFAULTS: dict[str, str] = {
    # Symbols allowed to fire the INFORMATIONAL multi-touch / gap alerts
    # (multitouch_level, gap_zone). The Pine fires broadly; the webhook keeps
    # only these. Edited live from Settings → so adding a stock needs no Pine edit.
    "alert_symbols": "SPY,NBIS",
    # Master alert switch. "true" (DEFAULT) = every symbol alerts, for every type
    # (non-breaking). "false" = alerts are OFF except for the EXCEPTION symbols in
    # alert_watchlist below. Lets the user turn alerts off broadly while keeping a
    # few names live, without clearing the list.
    "alerts_all_symbols": "true",
    # Exception symbols — when alerts_all_symbols is "false", ONLY these still
    # alert (across every alert type). Ignored when alerts_all_symbols is "true".
    "alert_watchlist": "",
    # SPY-trend long gate (2026-06-09). When ON and SPY is below BOTH its daily
    # 8-EMA and 21-EMA (broad tape rolled over), equity BUY alerts are suppressed
    # EXCEPT for spy_trend_exempt. Non-trending market = most longs are traps.
    "spy_trend_gate_enabled": "true",
    "spy_trend_exempt": "SPY,QQQ,DRAM,NVDA",
}


async def seed_regime_config(conn) -> None:
    """Insert default alert-symbol rows ONLY if missing — never overwrites edits.
    (Stale index_exempt / crypto_exempt rows may linger in old DBs; harmless —
    nothing reads them. Not worth a migration.)"""
    for k, v in REGIME_CONFIG_DEFAULTS.items():
        await conn.execute(
            text(
                "INSERT INTO regime_config (key, value) VALUES (:k, :v) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"k": k, "v": v},
        )
