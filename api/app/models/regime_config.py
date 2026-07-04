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
    # SPY-PDL long gate. When ON and SPY is below its PDL, equity BUY alerts are
    # suppressed EXCEPT for spy_trend_exempt. OFF by default (2026-06-17): alerts
    # flow ungated and the VOLUME GRADE is the conviction filter; flip to 'true'
    # here or in Settings to re-arm once the regime read is trustworthy.
    "spy_trend_gate_enabled": "false",
    "spy_trend_exempt": "SPY,QQQ,DRAM,NVDA",
    # 4h RC rejection-SHORT symbol allowlist (2026-06-12). The rc_4h SHORT (failed
    # break of the prior 4h high) is opt-in per symbol — it delivers ONLY for these.
    # Non-empty = allowlist; BLANK = NONE (block all — a SHORT is opt-in, the
    # opposite of the multitouch default). Default SPY,DRAM — add more live in Settings.
    "rc_4h_short_symbols": "SPY,DRAM",
    # Short-alert allowlist (#278, 2026-06-17). SHORT alerts of ANY type (index PDL
    # break, rc_4h rejection, MA rejection, htf_sr reject) flow ONLY for these symbols;
    # everything else is Not-routed. Supersedes rc_4h_short_symbols. BLANK = no shorts.
    # Default SPY,QQQ — add the names you want shorts on, live in Settings.
    "short_symbols": "SPY,QQQ",
    # ORB (15m opening-range + PDH/PDL) allowlist (2026-07-03). The orb_break/held/
    # retest/exit family is being TRIALED — delivers ONLY for these names so noise stays
    # controlled. User-editable in Settings. Default the 4 index/liquid vehicles.
    "orb_symbols": "SPY,QQQ,SOXL,MU",
    # MA/EMA bounce allowlist (#282, 2026-06-17). MA bounce/rejection alerts fire ONLY
    # for these clean trending names — on a chop chart the MA tangle is pure noise.
    # Everything else Not-routed. BLANK = no MA alerts. Default SPY,QQQ,DRAM,MU,AAPL.
    "ma_alert_symbols": "SPY,QQQ,DRAM,MU,AAPL",
    # 4h RC allowlist (#286, widened #288 to the full watchlist 2026-06-17). rc_4h
    # alerts — BOTH the long reclaim AND the short rejection — fire for these symbols
    # (RC shorts are wanted, so rc_4h is exempt from the general short gate). BLANK = no
    # RC alerts. Default = the day-trade watchlist; trim live in Settings if noisy.
    "rc_symbols": "SPY,QQQ,AAPL,DRAM,MU,NVDA,IREN,NBIS,HOOD,WDC,MRVL,TSM,GOOGL,META,MSFT,TSLA,SNDK,CRWV,RKLB,ASTS,AIP,AAOI,SPCX,BTCUSD,ETHUSD",
    # Gap-and-go always-deliver allowlist (2026-06-15). These names' gap-up
    # continuation fires even when a user has muted gap-and-go — an index doesn't
    # gap without a strong macro reason. Default SPY,QQQ; managed live in Settings.
    "gap_always_symbols": "SPY,QQQ",
    # ORL-held allowlist (2026-06-27, wired). staged_orl_held (60m opening-range-low
    # held) is NOISY, so it fires ONLY for the symbols on this list — everything else
    # Not-routed. Fully user-editable in Settings (add whatever names you want).
    # Default = index ETFs; the alert type itself also defaults OFF.
    "orl_always_symbols": "SPY,QQQ,IWM",
    # Multi-period S/R alert allowlist (2026-06-17). The clustered weekly/monthly/
    # daily S/R reject+bounce (htf_sr_*) is clumpy on busy names, so it delivers
    # ONLY for these — start with indexes (where it reads cleanest), expand live in
    # Settings as it validates. BLANK = none. Default SPY,QQQ.
    "htf_sr_symbols": "SPY,QQQ",
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
