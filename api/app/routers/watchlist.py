"""Watchlist + WatchlistGroup CRUD endpoints.

Groups are pure presentation — they let the user organize their watchlist by
category (Mega Tech, Chips, etc.). Alert routing (`_users_watching` in
tv_webhook.py) is unchanged: it only checks WatchlistItem.symbol == X, so
adding/removing groups never affects which alerts a user receives.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, get_user_tier, is_admin_user
from app.tier import get_limits
from app.models.user import User
from app.models.watchlist import WatchlistGroup, WatchlistItem
from app.schemas.watchlist import (
    AddSymbolRequest,
    BulkSetRequest,
    CreateGroupRequest,
    MoveItemRequest,
    UpdateGroupRequest,
    WatchlistGroupResponse,
    WatchlistItemResponse,
)
from app.services.symbol_resolver import resolve_symbol

router = APIRouter()


# ---------------------------------------------------------------------------
# Default groups + tickers — used by POST /groups/seed-defaults.
# Curated list focused on strong earnings growth + AI/data-center tailwinds.
# ---------------------------------------------------------------------------
DEFAULT_GROUPS: list[dict] = [
    {
        "name": "Mega Tech",
        "color": "#1f6feb",
        # Expanded 2026-05-24: added AAPL/NFLX/TSLA — all $500B+ caps the
        # user actually trades. TSLA folded here rather than its own EV-Auto
        # bucket because single-symbol "sectors" have no peer-analysis value.
        "symbols": ["NVDA", "MSFT", "GOOGL", "META", "AMZN", "AAPL", "NFLX", "TSLA"],
    },
    {
        "name": "Chips",
        "color": "#a371f7",
        # Expanded 2026-05-24: added ARM/QCOM/INTC/ALAB/CRDO/SMH — the
        # broader semi peer set in the user's watchlist. SMH is the ETF
        # but trades like a stock and is a useful sector breadth gauge.
        "symbols": ["AVGO", "AMD", "TSM", "ASML", "MRVL", "ARM", "QCOM", "INTC", "ALAB", "CRDO", "SMH"],
    },
    {
        "name": "Memory",
        "color": "#bf8700",
        # Expanded 2026-05-24: added WDC/STX — storage cousins of MU/SNDK.
        # Strictly speaking DRAM/NAND vs HDD, but the cycle drivers (data
        # center demand, hyperscaler capex) are the same → real peer flow.
        "symbols": ["MU", "SNDK", "WDC", "STX"],
    },
    {
        "name": "Optics",
        "color": "#1f883d",
        "symbols": ["AAOI", "COHR", "LITE"],
    },
    {
        "name": "Cloud",
        "color": "#218bff",
        # CRWV (CoreWeave) added 2026-05-24 — AI-infra cloud, fits naturally.
        "symbols": ["ORCL", "CRWD", "CRWV", "NOW", "DDOG", "SNOW"],
    },
    {
        # Renamed from "BTC" → "Crypto" 2026-05-24 to reflect that the group
        # now spans both proxies (MSTR / IREN miner) AND spot pairs that
        # trade on the user's TV watchlist. BTCUSD/ETHUSD give the actual
        # underlying for peer-flow comparison against the equity proxies.
        "name": "Crypto",
        "color": "#f78166",
        "symbols": ["BTCUSD", "ETHUSD", "MSTR", "COIN", "IREN"],
    },
    {
        # New 2026-05-24 — payments + brokerage + crypto-fintech cluster.
        # Real peer group: V's flow + HOOD's volume + SHOP's print all
        # reflect the consumer/risk-on cycle differently than Mega Tech.
        "name": "Fintech",
        "color": "#8957e5",
        "symbols": ["V", "SHOP", "HOOD", "COIN"],
    },
    {
        # New 2026-05-24 — small but cohesive. Both names are
        # high-beta speculative aerospace; they often move together on
        # NASA/DoD contract news or broader risk-on rotations.
        "name": "Space",
        "color": "#0969da",
        "symbols": ["RKLB", "SPCE"],
    },
    {
        # New 2026-05-24 — AI infrastructure / data layer plays.
        # PLTR and SWMR (and CRWV when wearing that hat) move on the
        # "AI buildout" narrative independently of Mega Tech earnings.
        "name": "AI Data",
        "color": "#fb8500",
        "symbols": ["PLTR", "SWMR"],
    },
    {
        "name": "Power",
        "color": "#cf222e",
        "symbols": ["VST", "CEG", "TLN", "POWL", "OKLO"],
    },
    {
        # 2026-05-25 — thematic bet on the nuclear renaissance / AI power
        # demand cycle. One pick per layer of the value chain, weighted to
        # names with actual earnings + EPS + growth (skips pre-revenue
        # SMR story stocks like OKLO/SMR/NNE).
        #   Layer 1 (miners):       CCJ — Cameco, only profitable uranium
        #                                  producer with utility contracts
        #                                  repricing higher
        #   Layer 2 (fuel cycle):   LEU — Centrus, US HALEU monopoly,
        #                                  DOE contracts, EPS inflecting
        #   Layer 3 (SMR + adv):    GEV — GE Vernova, BWRX-300 SMR with
        #                                  real industrial cash flow base
        #   Layer 4 (utilities):    CEG — Constellation, largest US
        #                                  nuclear fleet + AI PPA momentum
        # Named "Speculation" because while individual names are real
        # businesses, the thematic exposure is concentrated and theme-
        # dependent — treat as a basket bet, not a portfolio diversifier.
        "name": "Speculation",
        "color": "#f59e0b",
        "symbols": ["CCJ", "LEU", "GEV", "CEG"],
    },
    {
        "name": "Macro",
        "color": "#6e7681",
        "symbols": ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLE", "XLF", "XLV"],
    },
]


# ---------------------------------------------------------------------------
# Watchlist items — same surface as before, plus group_id support.
# ---------------------------------------------------------------------------


@router.get("", response_model=List[WatchlistItemResponse])
async def get_watchlist(
    group_id: Optional[int] = Query(default=None, description="Filter by group; -1 for ungrouped"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WatchlistItem).where(WatchlistItem.user_id == user.id)
    if group_id is not None:
        if group_id == -1:
            stmt = stmt.where(WatchlistItem.group_id.is_(None))
        else:
            stmt = stmt.where(WatchlistItem.group_id == group_id)
    stmt = stmt.order_by(WatchlistItem.id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=WatchlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_symbol(
    body: AddSymbolRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tier = get_user_tier(user)
    limits = get_limits(tier)
    max_symbols = limits["watchlist_max"]
    raw_symbol = body.symbol.upper().strip()

    count_result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.user_id == user.id)
    )
    if not is_admin_user(user) and len(count_result.scalars().all()) >= max_symbols:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "upgrade_required",
                "current_tier": tier,
                "limit": max_symbols,
                "message": f"{tier.title()} tier limited to {max_symbols} symbols. Upgrade for more.",
            },
        )

    resolved = resolve_symbol(raw_symbol)

    if resolved.kind == "unknown":
        raise HTTPException(
            status_code=404,
            detail={
                "error": "symbol_not_found",
                "input": raw_symbol,
                "message": f"No data found for '{raw_symbol}'. Check spelling or try the full form (e.g. BCH-USD for crypto).",
            },
        )

    if resolved.kind == "ambiguous":
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ambiguous_symbol",
                "input": raw_symbol,
                "message": f"'{raw_symbol}' matches both an equity and a crypto. Pick one.",
                "options": [
                    {
                        "symbol": opt.symbol,
                        "kind": opt.kind,
                        "display_name": opt.display_name,
                        "last_price": opt.last_price,
                    }
                    for opt in resolved.options
                ],
            },
        )

    symbol = resolved.canonical or raw_symbol

    existing = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.symbol == symbol,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Symbol already in watchlist")

    if body.group_id is not None:
        group = await _get_user_group_or_404(db, user.id, body.group_id)
        item = WatchlistItem(user_id=user.id, symbol=symbol, group_id=group.id)
    else:
        item = WatchlistItem(user_id=user.id, symbol=symbol)
    db.add(item)
    await db.flush()
    return item


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_symbol(
    symbol: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.symbol == symbol.upper(),
        )
    )


@router.put("", response_model=List[WatchlistItemResponse])
async def bulk_set(
    body: BulkSetRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    tier = get_user_tier(user)
    symbols = [s.upper().strip() for s in body.symbols]

    limits = get_limits(tier)
    max_symbols = limits["watchlist_max"]
    if not is_admin_user(user) and len(symbols) > max_symbols:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "upgrade_required",
                "current_tier": tier,
                "limit": max_symbols,
                "message": f"{tier.title()} tier limited to {max_symbols} symbols. Upgrade for more.",
            },
        )

    await db.execute(delete(WatchlistItem).where(WatchlistItem.user_id == user.id))
    items = [WatchlistItem(user_id=user.id, symbol=s) for s in symbols]
    db.add_all(items)
    await db.flush()
    return items


@router.patch("/{item_id}", response_model=WatchlistItemResponse)
async def move_item(
    item_id: int,
    body: MoveItemRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Move a watchlist item to a different group (or ungroup with null)."""
    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.id == item_id,
            WatchlistItem.user_id == user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Watchlist item not found")

    if body.group_id is not None:
        await _get_user_group_or_404(db, user.id, body.group_id)

    item.group_id = body.group_id
    await db.flush()
    return item


# ---------------------------------------------------------------------------
# Watchlist groups CRUD.
# ---------------------------------------------------------------------------


@router.get("/groups", response_model=List[WatchlistGroupResponse])
async def list_groups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WatchlistGroup)
        .where(WatchlistGroup.user_id == user.id)
        .order_by(WatchlistGroup.sort_order, WatchlistGroup.id)
    )
    return result.scalars().all()


@router.post(
    "/groups",
    response_model=WatchlistGroupResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    body: CreateGroupRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = body.name.strip()
    existing = await db.execute(
        select(WatchlistGroup).where(
            WatchlistGroup.user_id == user.id,
            WatchlistGroup.name == name,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Group with that name already exists")

    group = WatchlistGroup(
        user_id=user.id,
        name=name,
        sort_order=body.sort_order,
        color=body.color or "",
    )
    db.add(group)
    await db.flush()
    return group


@router.patch("/groups/{group_id}", response_model=WatchlistGroupResponse)
async def update_group(
    group_id: int,
    body: UpdateGroupRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    group = await _get_user_group_or_404(db, user.id, group_id)

    if body.name is not None:
        new_name = body.name.strip()
        if new_name != group.name:
            collision = await db.execute(
                select(WatchlistGroup).where(
                    WatchlistGroup.user_id == user.id,
                    WatchlistGroup.name == new_name,
                    WatchlistGroup.id != group.id,
                )
            )
            if collision.scalar_one_or_none():
                raise HTTPException(
                    status_code=409, detail="Group with that name already exists",
                )
            group.name = new_name
    if body.sort_order is not None:
        group.sort_order = body.sort_order
    if body.color is not None:
        group.color = body.color
    await db.flush()
    return group


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a group. Items in the group demote to ungrouped (group_id = NULL)."""
    group = await _get_user_group_or_404(db, user.id, group_id)

    # Demote items to ungrouped before deleting the group (FK has ON DELETE SET NULL
    # on the SQLA side, but we set explicitly so it's portable across DB engines).
    await db.execute(
        update(WatchlistItem)
        .where(
            WatchlistItem.user_id == user.id,
            WatchlistItem.group_id == group.id,
        )
        .values(group_id=None)
    )
    await db.delete(group)


@router.post("/groups/seed-defaults", response_model=List[WatchlistGroupResponse])
async def seed_default_groups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """One-click seed of curated default groups + symbols.

    Idempotent: groups with the same name are reused; duplicate symbols on the
    user's watchlist are left alone. Existing watchlist items keep their current
    group assignment (no overwrite).
    """
    tier = get_user_tier(user)
    limits = get_limits(tier)
    max_symbols = float("inf") if is_admin_user(user) else limits["watchlist_max"]

    # Existing items by symbol — for skip + later assignment if ungrouped.
    existing_items_result = await db.execute(
        select(WatchlistItem).where(WatchlistItem.user_id == user.id)
    )
    existing_items = list(existing_items_result.scalars().all())
    existing_by_symbol = {it.symbol: it for it in existing_items}
    current_count = len(existing_items)

    groups_out: list[WatchlistGroup] = []
    for sort_idx, group_def in enumerate(DEFAULT_GROUPS):
        # Reuse existing group with same name if present (idempotency).
        existing_group_result = await db.execute(
            select(WatchlistGroup).where(
                WatchlistGroup.user_id == user.id,
                WatchlistGroup.name == group_def["name"],
            )
        )
        group = existing_group_result.scalar_one_or_none()
        if group is None:
            group = WatchlistGroup(
                user_id=user.id,
                name=group_def["name"],
                sort_order=sort_idx,
                color=group_def.get("color", ""),
            )
            db.add(group)
            await db.flush()
        groups_out.append(group)

        for symbol in group_def["symbols"]:
            sym_norm = symbol.upper().strip()
            existing_item = existing_by_symbol.get(sym_norm)
            if existing_item is not None:
                # Symbol already on watchlist — assign to this group only if
                # currently ungrouped, so we never clobber a deliberate placement.
                if existing_item.group_id is None:
                    existing_item.group_id = group.id
                continue

            if current_count >= max_symbols:
                # Tier cap hit — stop adding new symbols (groups still created).
                continue

            item = WatchlistItem(
                user_id=user.id,
                symbol=sym_norm,
                group_id=group.id,
            )
            db.add(item)
            existing_by_symbol[sym_norm] = item
            current_count += 1

    await db.flush()
    return groups_out


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


async def _get_user_group_or_404(db: AsyncSession, user_id: int, group_id: int) -> WatchlistGroup:
    result = await db.execute(
        select(WatchlistGroup).where(
            WatchlistGroup.id == group_id,
            WatchlistGroup.user_id == user_id,
        )
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group
