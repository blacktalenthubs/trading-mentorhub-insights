"""Import record model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ImportRecord(Base):
    __tablename__ = "imports"
    __table_args__ = (
        UniqueConstraint("user_id", "filename", "file_type",
                         name="uq_import_user_file"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    period: Mapped[str] = mapped_column(String(50), nullable=False)
    records_imported: Mapped[int] = mapped_column(Integer, server_default="0")
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
