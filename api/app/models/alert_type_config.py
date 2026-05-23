"""Per-alert-type enablement — the on/off switch for TradingView alert delivery.

The Pine scripts fire every alert they can. This table decides which types
are actually delivered, so each alert type can be enabled/disabled and tested
independently from the Settings UI — no code change, no redeploy.
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


# Legacy prefix families (pre per-MA split) — still used by the webhook's
# static DB-down fallback only.
PREFIX_FAMILIES = (
    "ma_bounce_long_v3",
    "ma_rejection_short_v3",
    "ma_proximity_long_v3",
    "ma_proximity_short_v3",
)

# MA families split per moving average — one toggle per EMA + one grouped SMA
# toggle, so each MA can be enabled/tested on its own. (family, label, category)
MA_SPLIT_FAMILIES = (
    ("ma_bounce_long_v3", "MA bounce long", "MA / EMA · Bounce Long"),
    ("ma_proximity_long_v3", "MA proximity long (NOTICE)", "MA / EMA · Proximity Long"),
    ("ma_rejection_short_v3", "MA rejection short", "MA / EMA · Rejection Short"),
)
# (suffix key, label). "sma" is the grouped SMA 50/100/200 toggle.
_MA_TOGGLES = (
    ("ema8", "EMA 8"),
    ("ema21", "EMA 21"),
    ("ema50", "EMA 50"),
    ("ema100", "EMA 100"),
    ("ema200", "EMA 200"),
    ("sma", "SMA 50/100/200"),
)

# Bare MA family keys obsoleted by the per-MA split — deleted on seed so the
# Settings UI doesn't show dead toggles.
OBSOLETE_ALERT_TYPES = (
    "ma_bounce_long_v3",
    "ma_proximity_long_v3",
    "ma_rejection_short_v3",
)

# Canonical catalogue. (alert_type, label, category, default_enabled).
# default_enabled only applies on first insert — `enabled` is never overwritten.
# Spec 58 (2026-05-22): retired LONG entries marked "(retired — spec 58)";
# their default_enabled is False here AND the startup migration in main.py
# soft-disables existing rows so the change takes effect on first deploy.
_BASE_CATALOG: list[tuple[str, str, str, bool]] = [
    ("open_reclaimed", "Open reclaimed (retired — spec 58, visual-only)", "Open Line", False),
    ("open_held", "Open held (retired — spec 58, visual-only)", "Open Line", False),
    ("open_wick_reclaim", "Open wick reclaim (retired — spec 58)", "Open Line", False),
    ("open_lost", "Open lost (retired — spec 58)", "Open Line", False),
    ("staged_pdh_break", "PDH break (retired — spec 58 FR-005, breakout-into-resistance)", "Daily PDH/PDL", False),
    ("staged_pdh_rejection", "PDH rejection", "Daily PDH/PDL", False),
    ("staged_pdh_failed_short", "PDH failed short", "Daily PDH/PDL", False),
    ("staged_pdl_break", "PDL break", "Daily PDH/PDL", False),
    ("staged_pdl_reclaim", "PDL reclaim", "Daily PDH/PDL", False),
    # Spec 58 NEW (FR-004) — Buy 2 prior-high support hold.
    ("staged_pdh_held", "PDH held as support (Buy 2 — spec 58)", "Daily PDH/PDL", False),
    ("staged_pwh_held", "PWH held as support (Buy 2 — spec 58)", "Weekly / Monthly", False),
    ("staged_pmh_held", "PMH held as support (Buy 2 — spec 58)", "Weekly / Monthly", False),
    # Spec 58 NEW (2026-05-23) — symmetric "low held from above" types. Fires
    # when a wick tests a prior low and price closes back above it without
    # ever closing below. The wick-and-hold pattern (ETH wicking PML on
    # 2026-05-23 — bounced hard, but no _reclaim fired because no close
    # below PML). Trusts the low levels to hold; if they fail, we know
    # structurally where the floor broke.
    ("staged_pdl_held", "PDL held as support — wick test (spec 58)", "Daily PDH/PDL", False),
    ("staged_pwl_held", "PWL held as support — wick test (spec 58)", "Weekly / Monthly", False),
    ("staged_pml_held", "PML held as support — wick test (spec 58)", "Weekly / Monthly", False),
    # Spec 58 NEW (2026-05-23 evening) — monthly anchored-VWAP defense alerts.
    # Fires when an AVWAP is defended either by a wick-and-hold OR a
    # lost-and-reclaim cycle (combined trigger). The AVWAP is the dynamic
    # breakeven of that month's buyers — defending it = bullish institutional
    # signal. Validated live on ETH 2026-05-23: PDL trade ran through PWL
    # and tagged MTD Apr AVWAP at $2,246 exactly, where price stalled —
    # the AVWAP wall held as predicted.
    ("staged_mtd_avwap_held", "MTD AVWAP defended (Buy 2 — spec 58)", "Anchored VWAP", False),
    ("staged_pm_avwap_held", "Prior-month AVWAP defended (spec 58)", "Anchored VWAP", False),
    ("staged_p2m_avwap_held", "2-months-prior AVWAP defended (spec 58)", "Anchored VWAP", False),
    ("staged_pwh_break", "Weekly high break (retired — spec 58)", "Weekly / Monthly", False),
    ("staged_pwh_rejection", "Weekly high rejection", "Weekly / Monthly", False),
    ("staged_pwh_failed_short", "Weekly high failed short", "Weekly / Monthly", False),
    ("staged_pwl_break", "Weekly low break", "Weekly / Monthly", False),
    ("staged_pwl_reclaim", "Weekly low reclaim", "Weekly / Monthly", False),
    ("staged_pmh_break", "Monthly high break (retired — spec 58)", "Weekly / Monthly", False),
    ("staged_pmh_rejection", "Monthly high rejection", "Weekly / Monthly", False),
    ("staged_pmh_failed_short", "Monthly high failed short", "Weekly / Monthly", False),
    ("staged_pml_break", "Monthly low break", "Weekly / Monthly", False),
    ("staged_pml_reclaim", "Monthly low reclaim", "Weekly / Monthly", False),
    ("htf_support_held", "HTF support held", "HTF Levels", False),
    ("htf_proximity", "HTF proximity (NOTICE)", "HTF Levels", False),
    ("pullback_long", "Uptrend pullback continuation (retired — spec 58, replaced by Buy 1)", "Pullback", False),
]

# Spec 58 — alert types soft-disabled at startup by the migration in main.py.
# Soft-disable rather than DELETE so existing `alerts` rows keep resolvable
# types for audit. Listed without the `tv_` prefix; the migration prepends it.
SPEC_58_RETIRED_ENTRY_TYPES: tuple[str, ...] = (
    "open_reclaimed",
    "open_held",
    "open_wick_reclaim",
    "open_lost",
    "staged_pdh_break",
    "staged_pwh_break",
    "staged_pmh_break",
    "pullback_long",
    "ma_proximity_long_v3_ema8",
    "ma_proximity_long_v3_ema21",
    "ma_proximity_long_v3_ema50",
    "ma_proximity_long_v3_ema100",
    "ma_proximity_long_v3_ema200",
    "ma_proximity_long_v3_sma",
    # Spec 58 — htf_support_held superseded by granular per-level types
    # (staged_pdh_held / staged_pwh_held / staged_pmh_held). The new types
    # carry the uptrend gate + chop gate; htf_support_held is pre-spec-58
    # logic without them, so it's retired to avoid duplicate alerts on the
    # same setup.
    "htf_support_held",
)

# Per-MA toggles for the three split families.
_MA_CATALOG: list[tuple[str, str, str, bool]] = [
    (f"{fam}_{suffix}", f"{flabel} · {malabel}", fcat, False)
    for fam, flabel, fcat in MA_SPLIT_FAMILIES
    for suffix, malabel in _MA_TOGGLES
]

# Swing scanner (spec 56) — one toggle per defended MA, plus the RSI-recovery
# and exit types. All default OFF; enable a type in Settings to route it.
_SWING_CATALOG: list[tuple[str, str, str, bool]] = [
    ("swing_bounce_ema21", "Swing bounce · EMA 21", "Swing · Bounce", False),
    ("swing_bounce_ema50", "Swing bounce · EMA 50", "Swing · Bounce", False),
    ("swing_bounce_sma50", "Swing bounce · SMA 50", "Swing · Bounce", False),
    ("swing_bounce_ema100", "Swing bounce · EMA 100", "Swing · Bounce", False),
    ("swing_bounce_sma100", "Swing bounce · SMA 100", "Swing · Bounce", False),
    ("swing_bounce_ema200", "Swing bounce · EMA 200", "Swing · Bounce", False),
    ("swing_bounce_sma200", "Swing bounce · SMA 200", "Swing · Bounce", False),
    ("swing_rsi_30", "Swing RSI-30 recovery (SPY-weak regime)", "Swing", False),
    ("swing_exit", "Swing exit — daily close below the stop", "Swing", False),
]

ALERT_TYPE_CATALOG: list[tuple[str, str, str, bool]] = (
    _BASE_CATALOG
    + _MA_CATALOG
    + _SWING_CATALOG
    + [("ma_proximity_short_v3", "MA proximity short (NOTICE)", "MA / EMA · Proximity Short", False)]
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
