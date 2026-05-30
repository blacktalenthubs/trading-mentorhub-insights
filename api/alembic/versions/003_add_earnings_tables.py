"""Add earnings calendar + history + notifications-sent tables.

Spec 61 — Earnings Tracker. Three tables:

  earnings                       — one row per symbol, the upcoming earnings event
  earnings_history               — append-only, one row per (symbol, quarter_label)
  earnings_notifications_sent    — once-per-(user, symbol, earnings_date) marker
                                   so T-7 notifications never fire twice

Revision ID: 003_earnings_tables
Revises: 002_notification_prefs
Create Date: 2026-05-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "003_earnings_tables"
down_revision = "002_notification_prefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "earnings",
        sa.Column("symbol", sa.String(length=20), primary_key=True),
        sa.Column("next_earnings_date", sa.Date(), nullable=True, index=True),
        sa.Column("time_of_day", sa.String(length=8), nullable=True),  # BMO / AMC / DMH / null
        sa.Column("eps_estimate", sa.Float(), nullable=True),
        sa.Column("revenue_estimate", sa.Float(), nullable=True),
        sa.Column("confirmed", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "earnings_history",
        sa.Column("symbol", sa.String(length=20), primary_key=True),
        sa.Column("quarter_label", sa.String(length=12), primary_key=True),  # e.g. "2026Q1"
        sa.Column("eps_actual", sa.Float(), nullable=True),
        sa.Column("eps_estimate", sa.Float(), nullable=True),
        sa.Column("surprise_pct", sa.Float(), nullable=True),
        sa.Column("reported_at", sa.Date(), nullable=True, index=True),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "earnings_notifications_sent",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("earnings_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="t7"),  # t7, t14, t1, ...
        sa.Column("sent_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "symbol", "earnings_date", "kind",
                            name="uq_earnings_notif_user_sym_date_kind"),
    )


def downgrade() -> None:
    op.drop_table("earnings_notifications_sent")
    op.drop_table("earnings_history")
    op.drop_table("earnings")
