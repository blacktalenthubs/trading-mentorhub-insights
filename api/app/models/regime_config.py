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
    # (2026-06-09 cleanup) alert_symbols / alerts_all_symbols / alert_watchlist
    # were removed — alert delivery is now controlled by Alert Types + the single
    # SPY-trend gate below. Stale rows in old DBs are harmless (nothing reads them).
    # SPY-trend long gate. When ON and SPY is below BOTH its daily
    # 8-EMA and 21-EMA (broad tape rolled over), equity BUY alerts are suppressed
    # EXCEPT for spy_trend_exempt. Non-trending market = most longs are traps.
    "spy_trend_gate_enabled": "true",
    "spy_trend_exempt": "SPY,QQQ,DRAM,NVDA",
    # 4h RC rejection-SHORT symbol allowlist (2026-06-12). The rc_4h SHORT (failed
    # break of the prior 4h high) is opt-in per symbol — it delivers ONLY for these.
    # Non-empty = allowlist; BLANK = NONE (block all — a SHORT is opt-in, the
    # opposite of the multitouch default). Default SPY,DRAM — add more live in Settings.
    "rc_4h_short_symbols": "SPY,DRAM",
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
