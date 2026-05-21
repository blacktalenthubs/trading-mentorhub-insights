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
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# MA/EMA alert types arrive with a variable suffix (e.g. tv_ma_bounce_long_v3_ema50).
# These base keys are matched by prefix against the incoming alert_type.
PREFIX_FAMILIES = (
    "ma_bounce_long_v3",
    "ma_rejection_short_v3",
    "ma_proximity_long_v3",
    "ma_proximity_short_v3",
)

# Canonical catalogue. (alert_type, label, category, default_enabled).
# default_enabled only applies on first seed — existing rows are never overwritten.
# Tomorrow's starting point (2026-05-21): only the two open-line alerts ON.
ALERT_TYPE_CATALOG: list[tuple[str, str, str, bool]] = [
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
    ("ma_bounce_long_v3", "MA/EMA bounce — long", "MA / EMA", False),
    ("ma_rejection_short_v3", "MA/EMA rejection — short", "MA / EMA", False),
    ("ma_proximity_long_v3", "MA/EMA proximity — long (NOTICE)", "MA / EMA", False),
    ("ma_proximity_short_v3", "MA/EMA proximity — short (NOTICE)", "MA / EMA", False),
    ("pullback_long", "Uptrend pullback continuation — long", "Pullback", False),
]


async def seed_alert_type_config(conn) -> None:
    """Idempotently insert any missing alert types. Never overwrites an
    existing row, so user toggles persist across restarts."""
    for alert_type, label, category, default_enabled in ALERT_TYPE_CATALOG:
        await conn.execute(
            text(
                "INSERT INTO alert_type_config (alert_type, label, category, enabled) "
                "VALUES (:at, :label, :cat, :en) "
                "ON CONFLICT (alert_type) DO NOTHING"
            ),
            {"at": alert_type, "label": label, "cat": category, "en": default_enabled},
        )
