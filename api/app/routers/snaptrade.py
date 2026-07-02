"""SnapTrade broker-connect + fill-sync endpoints.

Flow for a user:
  1. POST /register        → create their SnapTrade identity (once).
  2. GET  /connect         → get a Connection Portal URL; user links Robinhood.
  3. GET  /connections     → confirm the broker is linked.
  4. POST /sync            → pull fills now (also runs nightly via scheduler).
  5. GET  /status          → connection + last-sync summary for the settings UI.
  6. DELETE /disconnect    → unlink brokers, stop syncing.

Blocking SnapTrade SDK calls run in a worker thread so the event loop stays free.
When SnapTrade isn't configured every endpoint returns 503 (feature disabled).
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.snaptrade import (
    STATUS_CONNECTED,
    STATUS_DISABLED,
    STATUS_REGISTERED,
    SnapTradeConnection,
)
from app.models.user import User
from app.schemas.snaptrade import (
    BrokerAccountResponse,
    ConnectionsListResponse,
    ConnectionStatusResponse,
    ConnectPortalResponse,
    SyncResultResponse,
)
from app.services import snaptrade_service as svc

router = APIRouter()


def _require_configured():
    settings = get_settings()
    if not svc.is_configured(settings):
        raise HTTPException(
            status_code=503,
            detail="Broker sync is not available — SnapTrade is not configured.",
        )
    return settings


async def _get_connection(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(SnapTradeConnection).where(SnapTradeConnection.user_id == user_id)
    )
    return result.scalar_one_or_none()


@router.get("/status", response_model=ConnectionStatusResponse)
async def get_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conn = await _get_connection(db, user.id)
    if conn is None:
        return ConnectionStatusResponse(connected=False, status="none")
    return ConnectionStatusResponse(
        connected=conn.status == STATUS_CONNECTED,
        status=conn.status,
        broker_slug=conn.broker_slug,
        last_synced_at=conn.last_synced_at,
        last_sync_count=conn.last_sync_count,
    )


@router.post("/register", response_model=ConnectionStatusResponse)
async def register(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create the user's SnapTrade identity (idempotent)."""
    settings = _require_configured()
    conn = await _get_connection(db, user.id)
    if conn is not None:
        # Already registered — reactivate if previously disabled.
        if conn.status == STATUS_DISABLED:
            conn.status = STATUS_REGISTERED
        return ConnectionStatusResponse(
            connected=conn.status == STATUS_CONNECTED,
            status=conn.status,
            broker_slug=conn.broker_slug,
            last_synced_at=conn.last_synced_at,
            last_sync_count=conn.last_sync_count,
        )

    st_user_id = svc.snaptrade_user_id_for(user.id)
    client = svc.get_client(settings)
    try:
        user_secret = await asyncio.to_thread(svc.register_user, client, st_user_id)
    except Exception as exc:  # network / already-exists
        raise HTTPException(status_code=502, detail=f"SnapTrade registration failed: {exc}")

    conn = SnapTradeConnection(
        user_id=user.id,
        snaptrade_user_id=st_user_id,
        user_secret=user_secret,
        status=STATUS_REGISTERED,
    )
    db.add(conn)
    await db.flush()
    return ConnectionStatusResponse(connected=False, status=STATUS_REGISTERED)


@router.get("/connect", response_model=ConnectPortalResponse)
async def connect(
    request: Request,
    broker: str | None = Query(None, description="Broker slug, e.g. ROBINHOOD"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return a one-time Connection Portal URL to link a brokerage."""
    settings = _require_configured()
    conn = await _get_connection(db, user.id)
    if conn is None:
        # Auto-register so the UI can offer "Connect" in a single click.
        st_user_id = svc.snaptrade_user_id_for(user.id)
        client = svc.get_client(settings)
        try:
            user_secret = await asyncio.to_thread(svc.register_user, client, st_user_id)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"SnapTrade registration failed: {exc}")
        conn = SnapTradeConnection(
            user_id=user.id,
            snaptrade_user_id=st_user_id,
            user_secret=user_secret,
            status=STATUS_REGISTERED,
        )
        db.add(conn)
        await db.flush()

    client = svc.get_client(settings)
    try:
        url = await asyncio.to_thread(
            svc.connection_portal_url,
            client,
            conn.snaptrade_user_id,
            conn.user_secret,
            broker=broker,
            redirect_uri=settings.SNAPTRADE_REDIRECT_URI,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SnapTrade portal error: {exc}")
    return ConnectPortalResponse(redirect_uri=url)


@router.get("/connections", response_model=ConnectionsListResponse)
async def list_connections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List linked brokerage accounts; flips status to 'connected' when live."""
    settings = _require_configured()
    conn = await _get_connection(db, user.id)
    if conn is None:
        return ConnectionsListResponse(status="none", accounts=[])

    client = svc.get_client(settings)
    try:
        raw = await asyncio.to_thread(
            svc.list_accounts, client, conn.snaptrade_user_id, conn.user_secret
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SnapTrade accounts error: {exc}")

    accounts = [
        BrokerAccountResponse(
            account_id=str(svc._pluck(a, "id", default="")),
            institution_name=svc._pluck(a, "institution_name", "institutionName"),
            name=svc._pluck(a, "name"),
            number=svc._pluck(a, "number"),
        )
        for a in raw
    ]

    if accounts:
        conn.status = STATUS_CONNECTED
        inst = accounts[0].institution_name
        if inst:
            conn.broker_slug = inst.upper().replace(" ", "_")
    return ConnectionsListResponse(status=conn.status, accounts=accounts)


@router.post("/sync", response_model=SyncResultResponse)
async def sync_now(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pull the last N days of fills into the journal right now."""
    settings = _require_configured()
    conn = await _get_connection(db, user.id)
    if conn is None or conn.status == STATUS_DISABLED:
        raise HTTPException(status_code=400, detail="No active broker connection.")

    sync_session_factory = getattr(request.app.state, "sync_session_factory", None)
    if sync_session_factory is None:
        raise HTTPException(status_code=503, detail="Sync backend unavailable.")

    try:
        summary = await asyncio.to_thread(
            svc.sync_user_fills, sync_session_factory, settings, user.id
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SnapTrade sync failed: {exc}")
    return SyncResultResponse(**summary)


@router.delete("/disconnect", response_model=ConnectionStatusResponse)
async def disconnect(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove all brokerage authorizations and stop syncing."""
    settings = _require_configured()
    conn = await _get_connection(db, user.id)
    if conn is None:
        return ConnectionStatusResponse(connected=False, status="none")

    client = svc.get_client(settings)
    try:
        await asyncio.to_thread(
            svc.remove_all_connections, client, conn.snaptrade_user_id, conn.user_secret
        )
    except Exception:
        # Best-effort: even if the remote removal fails, disable locally so we
        # stop pulling. The user can retry; SnapTrade cleanup is idempotent.
        pass

    conn.status = STATUS_DISABLED
    conn.broker_slug = None
    return ConnectionStatusResponse(connected=False, status=STATUS_DISABLED)
