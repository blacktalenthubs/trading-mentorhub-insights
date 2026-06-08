"""Regime-gate exempt symbols — admin-editable allow-lists (no redeploy).

A tiny key/value table holding two comma-separated lists:
  • index_exempt  — stock 'index' symbols the SPY gate never blocks
                    (relative-strength names you'd trade even on a red day).
  • crypto_exempt — crypto symbols the BTC gate never blocks.

Edited live from Settings → Market gate. The webhook reads these per dispatch
(same session as the alert_type_config read) and falls back to the env defaults
(INDEX_REGIME_ALLOWLIST / CRYPTO_REGIME_ALLOWLIST) if a row is missing or the
read fails — so the gate never goes dark.
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


# Defaults mirror the env constants in tv_webhook.py.
REGIME_CONFIG_DEFAULTS: dict[str, str] = {
    "index_exempt": "SPY,QQQ,IWM,DRAM",
    "crypto_exempt": "BTC-USD",
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
}


async def seed_regime_config(conn) -> None:
    """Insert default exempt lists ONLY if missing — never overwrites admin edits."""
    for k, v in REGIME_CONFIG_DEFAULTS.items():
        await conn.execute(
            text(
                "INSERT INTO regime_config (key, value) VALUES (:k, :v) "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"k": k, "v": v},
        )
