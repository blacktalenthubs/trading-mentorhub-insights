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
_BASE_CATALOG: list[tuple[str, str, str, bool]] = [
    ("open_reclaimed", "Open reclaimed — close flipped back above the day open", "Open Line", True),
    ("open_held", "Open held — day open defended as support", "Open Line", True),
    ("open_wick_reclaim", "Open wick reclaim — wick crossed below, body held", "Open Line", False),
    ("open_lost", "Open lost — closed below the day open (NOTICE)", "Open Line", False),
    ("staged_pdh_break", "PDH break", "Daily PDH/PDL", False),
    ("staged_pdh_rejection", "PDH rejection", "Daily PDH/PDL", False),
    ("staged_pdh_failed_short", "PDH failed short", "Daily PDH/PDL", False),
    ("staged_pdl_break", "PDL break", "Daily PDH/PDL", False),
    ("staged_pdl_reclaim", "PDL reclaim", "Daily PDH/PDL", False),
    ("staged_pwh_break", "Weekly high break", "Weekly / Monthly", False),
    ("staged_pwh_rejection", "Weekly high rejection", "Weekly / Monthly", False),
    ("staged_pwh_failed_short", "Weekly high failed short", "Weekly / Monthly", False),
    ("staged_pwl_break", "Weekly low break", "Weekly / Monthly", False),
    ("staged_pwl_reclaim", "Weekly low reclaim", "Weekly / Monthly", False),
    ("staged_pmh_break", "Monthly high break", "Weekly / Monthly", False),
    ("staged_pmh_rejection", "Monthly high rejection", "Weekly / Monthly", False),
    ("staged_pmh_failed_short", "Monthly high failed short", "Weekly / Monthly", False),
    ("staged_pml_break", "Monthly low break", "Weekly / Monthly", False),
    ("staged_pml_reclaim", "Monthly low reclaim", "Weekly / Monthly", False),
    ("htf_support_held", "HTF support held", "HTF Levels", False),
    ("htf_proximity", "HTF proximity (NOTICE)", "HTF Levels", False),
    ("pullback_long", "Uptrend pullback continuation — long", "Pullback", False),
]

# Per-MA toggles for the three split families.
_MA_CATALOG: list[tuple[str, str, str, bool]] = [
    (f"{fam}_{suffix}", f"{flabel} · {malabel}", fcat, False)
    for fam, flabel, fcat in MA_SPLIT_FAMILIES
    for suffix, malabel in _MA_TOGGLES
]

ALERT_TYPE_CATALOG: list[tuple[str, str, str, bool]] = (
    _BASE_CATALOG
    + _MA_CATALOG
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
