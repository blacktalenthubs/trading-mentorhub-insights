"""Coach conversation history — save/load/clear endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.models.coach import CoachMessage
from app.models.user import User
from app.dependencies import get_current_user

router = APIRouter(prefix="/coach-history", tags=["coach"])


class SaveMessageRequest(BaseModel):
    symbol: str | None = None
    role: str  # "user" or "assistant"
    content: str


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    symbol: str | None
    created_at: str


@router.get("/messages")
async def get_messages(
    symbol: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get recent coach messages for the user, optionally filtered by symbol."""
    query = select(CoachMessage).where(
        CoachMessage.user_id == user.id
    ).order_by(CoachMessage.created_at.desc()).limit(limit)

    if symbol:
        query = query.where(CoachMessage.symbol == symbol)

    result = await db.execute(query)
    rows = result.scalars().all()

    # Return in chronological order (oldest first)
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "symbol": m.symbol,
            "created_at": m.created_at.isoformat() if m.created_at else "",
        }
        for m in reversed(rows)
    ]


@router.post("/messages")
async def save_message(
    body: SaveMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a coach message."""
    msg = CoachMessage(
        user_id=user.id,
        symbol=body.symbol,
        role=body.role,
        content=body.content,
    )
    db.add(msg)
    await db.commit()
    return {"id": msg.id, "status": "saved"}


@router.delete("/messages")
async def clear_messages(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Clear all coach messages for the user."""
    await db.execute(
        delete(CoachMessage).where(CoachMessage.user_id == user.id)
    )
    await db.commit()
    return {"status": "cleared"}
