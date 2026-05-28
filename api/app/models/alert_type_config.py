"""Per-alert-type enablement — the on/off switch for TradingView alert delivery.

The Pine scripts fire every alert they can. This table decides which types
are actually delivered, so each alert type can be enabled/disabled and tested
independently from the Settings UI — no code change, no redeploy.

Spec 58 final state (2026-05-23) — Pine is long-only. The catalog below
mirrors that: only the 19 BUY alert types the Pine actively emits. Every
historical/retired type lives in OBSOLETE_ALERT_TYPES below and is DELETED
from the catalog table on each startup, so the Settings UI never shows
dead toggles.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AlertTypeConfig(Base):
    __tablename__ = "alert_type_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_type: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(140), nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Active MA family — only ma_bounce_long_v3 survives spec 58 ───────────
# Generates 6 per-MA toggles: ma_bounce_long_v3_{ema8,ema21,ema50,ema100,ema200,sma}.
# The SHORT (rejection) and NOTICE (proximity) families were removed from
# Pine — they get cleaned out of the catalog via OBSOLETE_ALERT_TYPES below.
MA_SPLIT_FAMILIES = (
    ("ma_bounce_long_v3", "MA bounce long", "MA / EMA · Bounce Long"),
)
_MA_TOGGLES = (
    ("ema8",   "EMA 8"),
    ("ema21",  "EMA 21"),
    ("ema50",  "EMA 50"),
    ("ema100", "EMA 100"),
    ("ema200", "EMA 200"),
    ("sma",    "SMA 50/100/200"),
)


# ── The canonical 19 (active alert types only) ──────────────────────────
# (alert_type, label, category, default_enabled)
# default_enabled only applies on FIRST insert — `enabled` is never
# overwritten by seeding, so user toggles persist across deploys.
_BASE_CATALOG: list[tuple[str, str, str, bool]] = [
    # Pullback continuation (uptrend-gated long entry — companion to MA bounce)
    ("pullback_long", "Uptrend pullback continuation (Buy 1)", "Pullback", False),

    # Buy 2 — Prior-high held as support (spec 58 FR-004)
    ("staged_pdh_held", "PDH held as support (Buy 2)", "Daily PDH/PDL", False),
    ("staged_pwh_held", "PWH held as support (Buy 2)", "Weekly / Monthly", False),
    ("staged_pmh_held", "PMH held as support (Buy 2)", "Weekly / Monthly", False),

    # Buy 2 — Prior-low held / wick test (spec 58, 2026-05-23)
    ("staged_pdl_held", "PDL held — wick test (Buy 2)", "Daily PDH/PDL", False),
    ("staged_pwl_held", "PWL held — wick test (Buy 2)", "Weekly / Monthly", False),
    ("staged_pml_held", "PML held — wick test (Buy 2)", "Weekly / Monthly", False),

    # Buy 2 — Prior-low reclaim (existing — lost-and-recovered)
    ("staged_pdl_reclaim", "PDL reclaim", "Daily PDH/PDL", False),
    ("staged_pwl_reclaim", "PWL reclaim", "Weekly / Monthly", False),
    ("staged_pml_reclaim", "PML reclaim", "Weekly / Monthly", False),

    # Buy 2 — Monthly anchored-VWAP defended (spec 58, 2026-05-23 evening)
    ("staged_mtd_avwap_held", "MTD AVWAP defended (Buy 2)", "Anchored VWAP", False),
    ("staged_pm_avwap_held",  "Prior-month AVWAP defended", "Anchored VWAP", False),
    ("staged_p2m_avwap_held", "2-months-prior AVWAP defended", "Anchored VWAP", False),

    # Swing scanner — daily-bar entries from analytics/swing_scanner.py
    # (un-retired 2026-05-28 — scheduled scan + push delivery added).
    # All default-disabled; user toggles per-pattern in Settings.
    ("swing_bounce_ema21",  "Swing · 21 EMA bounce", "Swing · Bounce", False),
    ("swing_bounce_ema50",  "Swing · 50 EMA bounce", "Swing · Bounce", False),
    ("swing_bounce_sma50",  "Swing · 50 SMA bounce", "Swing · Bounce", False),
    ("swing_bounce_ema200", "Swing · 200 EMA bounce", "Swing · Bounce", False),
    ("swing_bounce_sma200", "Swing · 200 SMA bounce", "Swing · Bounce", False),
    ("swing_8_21_cross",         "Swing · EMA 8/21 bullish crossover", "Swing", False),
    ("swing_golden_cross_retest","Swing · Golden-cross retest (50 EMA)", "Swing", False),
    ("swing_52w_high_retest",    "Swing · 52-week-high retest",        "Swing", False),
    ("swing_5day_low_reclaim",   "Swing · 5-day-low reclaim",          "Swing", False),
    ("swing_rsi_30",             "Swing · RSI 30 recovery",            "Swing", False),
]

# Per-MA toggles for the surviving MA-bounce family.
_MA_CATALOG: list[tuple[str, str, str, bool]] = [
    (f"{fam}_{suffix}", f"{flabel} · {malabel}", fcat, False)
    for fam, flabel, fcat in MA_SPLIT_FAMILIES
    for suffix, malabel in _MA_TOGGLES
]

ALERT_TYPE_CATALOG: list[tuple[str, str, str, bool]] = _BASE_CATALOG + _MA_CATALOG


# ── Cleanup — every retired/obsoleted alert type ────────────────────────
# These types are DELETED from the alert_type_config table on every startup
# (see seed_alert_type_config below). Soft-disable was tried first but the
# user wanted them GONE from the Settings UI dropdown, not just hidden.
#
# Historical alerts in the `alerts` table that reference these types stay
# intact — alert_type is just a String column with no FK, so deleting from
# the catalog doesn't orphan anything. The EOD scorecard can still surface
# historical alerts by name; they just won't have a toggle anymore.
OBSOLETE_ALERT_TYPES: tuple[str, ...] = (
    # Bare prefixes (pre per-MA split)
    "ma_bounce_long_v3",
    "ma_proximity_long_v3",
    "ma_rejection_short_v3",

    # Open-line entries — retired spec 58 FR-007 (open line stays visual)
    "open_reclaimed", "open_held", "open_wick_reclaim", "open_lost",

    # Breakout-into-resistance LONG — retired spec 58 FR-005
    "staged_pdh_break", "staged_pwh_break", "staged_pmh_break",

    # All SHORT alerts — removed from Pine 2026-05-23 (long-only Pine)
    "staged_pdh_rejection", "staged_pdh_failed_short", "staged_pdl_break",
    "staged_pwh_rejection", "staged_pwh_failed_short", "staged_pwl_break",
    "staged_pmh_rejection", "staged_pmh_failed_short", "staged_pml_break",

    # MA SHORT (per-MA) — Pine no longer emits
    "ma_rejection_short_v3_ema8", "ma_rejection_short_v3_ema21",
    "ma_rejection_short_v3_ema50", "ma_rejection_short_v3_ema100",
    "ma_rejection_short_v3_ema200", "ma_rejection_short_v3_sma",

    # MA proximity NOTICEs (long + short, per-MA) — Pine no longer emits
    "ma_proximity_long_v3_ema8", "ma_proximity_long_v3_ema21",
    "ma_proximity_long_v3_ema50", "ma_proximity_long_v3_ema100",
    "ma_proximity_long_v3_ema200", "ma_proximity_long_v3_sma",
    "ma_proximity_short_v3",
    "ma_proximity_short_v3_ema8", "ma_proximity_short_v3_ema21",
    "ma_proximity_short_v3_ema50", "ma_proximity_short_v3_ema100",
    "ma_proximity_short_v3_ema200", "ma_proximity_short_v3_sma",

    # HTF NOTICEs / superseded held — spec 58
    "htf_support_held",  # superseded by granular staged_p[dwm]h_held
    "htf_proximity",     # NOTICE — removed Pine, long-only

    # VWAP NOTICEs — Pine no longer emits
    "vwap_reclaim_long", "vwap_reject_short", "vwap_support_hold",

    # Spec 56 swing scanner — `swing_bounce_ema100`/`sma100` stay retired
    # (per-rule trim 2026-05-28). The rest were un-retired and re-added
    # to ALERT_TYPE_CATALOG with default-disabled for opt-in delivery.
    "swing_bounce_ema100", "swing_bounce_sma100",
    "swing_exit",
)


async def seed_alert_type_config(conn) -> None:
    """Idempotently sync the catalogue into the table.

    Inserts missing rows; refreshes label/category on existing rows; never
    touches `enabled`, so user toggles persist. Deletes obsoleted keys so
    the Settings UI never shows dead toggles.
    """
    for alert_type, label, category, default_enabled in ALERT_TYPE_CATALOG:
        await conn.execute(
            text(
                "INSERT INTO alert_type_config (alert_type, label, category, enabled) "
                "VALUES (:at, :label, :cat, :en) "
                "ON CONFLICT (alert_type) DO UPDATE SET "
                "label = EXCLUDED.label, category = EXCLUDED.category"
            ),
            {"at": alert_type, "label": label, "cat": category, "en": default_enabled},
        )
    for obsolete in OBSOLETE_ALERT_TYPES:
        await conn.execute(
            text("DELETE FROM alert_type_config WHERE alert_type = :at"),
            {"at": obsolete},
        )
