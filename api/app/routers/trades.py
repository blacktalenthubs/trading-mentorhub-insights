"""Trade history, annotations, and import endpoints."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.rate_limit import limiter
from app.models.import_record import ImportRecord
from app.models.trade import (
    AccountSummary,
    MatchedTrade,
    Trade1099,
    TradeAnnotation,
    TradeMonthly,
)
from app.models.user import User
from app.schemas.trade import (
    AnnotationRequest,
    AnnotationResponse,
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportParseResponse,
    ImportRecordResponse,
    MonthlyStats,
    TradeHistoryItem,
)
from app.services.trade_import import get_pending_parse, parse_pdf, remove_pending_parse

router = APIRouter()


# ---------------------------------------------------------------------------
# Trade history
# ---------------------------------------------------------------------------

@router.get("/history", response_model=List[TradeHistoryItem])
async def trade_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get combined 1099 + matched trades for the user."""
    # 1099 trades
    result_1099 = await db.execute(
        select(Trade1099).where(Trade1099.user_id == user.id).order_by(Trade1099.date_sold.desc())
    )
    trades = []
    for t in result_1099.scalars().all():
        trades.append(TradeHistoryItem(
            symbol=t.symbol,
            trade_date=t.date_sold,
            proceeds=t.proceeds,
            cost_basis=t.cost_basis,
            realized_pnl=t.gain_loss,
            wash_sale_disallowed=t.wash_sale_disallowed,
            asset_type=t.asset_type,
            category=t.category,
            holding_days=t.holding_days,
            holding_period_type=t.holding_period_type,
            account=t.account,
            source="1099",
        ))

    # Matched trades
    result_matched = await db.execute(
        select(MatchedTrade).where(MatchedTrade.user_id == user.id)
        .order_by(MatchedTrade.sell_date.desc())
    )
    for t in result_matched.scalars().all():
        trades.append(TradeHistoryItem(
            symbol=t.symbol,
            trade_date=t.sell_date,
            proceeds=t.sell_amount,
            cost_basis=t.buy_amount,
            realized_pnl=t.realized_pnl,
            wash_sale_disallowed=0,
            asset_type=t.asset_type,
            category=t.category,
            holding_days=t.holding_days,
            holding_period_type=t.holding_period_type,
            account=t.account,
            source="monthly",
        ))

    trades.sort(key=lambda t: t.trade_date or "", reverse=True)
    return trades


@router.get("/monthly-stats", response_model=List[MonthlyStats])
async def monthly_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get P&L aggregated by month."""
    # Fetch all trades (lightweight approach: use Python aggregation)
    history = await trade_history(user=user, db=db)
    months: dict[str, dict] = {}
    for t in history:
        if not t.trade_date:
            continue
        month_key = t.trade_date[:7]  # "YYYY-MM"
        if month_key not in months:
            months[month_key] = {"total": 0, "pnl": 0.0, "wins": 0, "losses": 0}
        months[month_key]["total"] += 1
        months[month_key]["pnl"] += t.realized_pnl
        if t.realized_pnl >= 0:
            months[month_key]["wins"] += 1
        else:
            months[month_key]["losses"] += 1

    result = []
    for month, data in sorted(months.items(), reverse=True):
        total = data["total"]
        result.append(MonthlyStats(
            month=month,
            total_trades=total,
            total_pnl=round(data["pnl"], 2),
            win_count=data["wins"],
            loss_count=data["losses"],
            win_rate=round(data["wins"] / total * 100, 1) if total else 0.0,
        ))
    return result


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------

@router.post("/annotations", response_model=AnnotationResponse, status_code=status.HTTP_201_CREATED)
async def upsert_annotation(
    body: AnnotationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a trade annotation."""
    # Check for existing annotation
    result = await db.execute(
        select(TradeAnnotation).where(
            TradeAnnotation.user_id == user.id,
            TradeAnnotation.source == body.source,
            TradeAnnotation.symbol == body.symbol,
            TradeAnnotation.trade_date == body.trade_date,
            TradeAnnotation.quantity == body.quantity,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.strategy_tag = body.strategy_tag
        existing.notes = body.notes
        await db.flush()
        return existing

    annotation = TradeAnnotation(
        user_id=user.id,
        source=body.source,
        symbol=body.symbol,
        trade_date=body.trade_date,
        quantity=body.quantity,
        strategy_tag=body.strategy_tag,
        notes=body.notes,
    )
    db.add(annotation)
    await db.flush()
    return annotation


@router.get("/annotations", response_model=List[AnnotationResponse])
async def get_annotations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TradeAnnotation).where(TradeAnnotation.user_id == user.id)
    )
    return result.scalars().all()


# ---------------------------------------------------------------------------
# PDF Import
# ---------------------------------------------------------------------------

@router.post("/import/parse", response_model=ImportParseResponse)
@limiter.limit("5/minute")
async def import_parse(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """Upload a PDF and get a preview of parsed trades."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are supported")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=422, detail="File too large (max 10MB)")

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, partial(parse_pdf, file.filename, contents)
    )

    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])

    return ImportParseResponse(**result)


@router.post("/import/confirm", response_model=ImportConfirmResponse)
async def import_confirm(
    body: ImportConfirmRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm and persist a previously parsed PDF import."""
    pending = get_pending_parse(body.parse_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Parse not found or expired")

    # Check for duplicate import
    existing = await db.execute(
        select(ImportRecord).where(
            ImportRecord.user_id == user.id,
            ImportRecord.filename == pending["filename"],
            ImportRecord.file_type == pending["file_type"],
        )
    )
    if existing.scalar_one_or_none():
        remove_pending_parse(body.parse_id)
        raise HTTPException(status_code=409, detail="This file was already imported")

    # Create import record
    import_rec = ImportRecord(
        user_id=user.id,
        filename=pending["filename"],
        file_type=pending["file_type"],
        period=pending["period"],
        records_imported=len(pending["trades"]),
    )
    db.add(import_rec)
    await db.flush()

    # Persist trades
    if pending["file_type"] == "1099":
        for t in pending["trades"]:
            db.add(Trade1099(
                import_id=import_rec.id,
                user_id=user.id,
                account=t.account,
                description=t.description,
                symbol=t.symbol,
                cusip=t.cusip,
                date_sold=t.date_sold.isoformat() if t.date_sold else None,
                date_acquired=t.date_acquired.isoformat() if t.date_acquired else None,
                date_acquired_raw=t.date_acquired_raw,
                quantity=t.quantity,
                proceeds=t.proceeds,
                cost_basis=t.cost_basis,
                wash_sale_disallowed=t.wash_sale_disallowed,
                gain_loss=t.gain_loss,
                term=t.term,
                covered=int(t.covered),
                form_type=t.form_type,
                trade_type=t.trade_type,
                asset_type=t.asset_type,
                category=t.category,
                holding_days=t.holding_days,
                holding_period_type=t.holding_period_type,
                underlying_symbol=t.underlying_symbol,
            ))
    else:
        for t in pending["trades"]:
            db.add(TradeMonthly(
                import_id=import_rec.id,
                user_id=user.id,
                account=t.account,
                description=t.description,
                symbol=t.symbol,
                cusip=t.cusip,
                acct_type=t.acct_type,
                transaction_type=t.transaction_type,
                trade_date=t.trade_date.isoformat() if t.trade_date else None,
                quantity=t.quantity,
                price=t.price,
                amount=t.amount,
                is_option=int(t.is_option),
                option_detail=t.option_detail,
                is_recurring=int(t.is_recurring),
                asset_type=t.asset_type,
                category=t.category,
                underlying_symbol=t.underlying_symbol,
            ))

        # Account summary
        if pending["account_summary"]:
            s = pending["account_summary"]
            db.add(AccountSummary(
                import_id=import_rec.id,
                user_id=user.id,
                account=s.account,
                period_start=s.period_start.isoformat(),
                period_end=s.period_end.isoformat(),
                opening_balance=s.opening_balance,
                closing_balance=s.closing_balance,
            ))

    await db.flush()
    remove_pending_parse(body.parse_id)

    return ImportConfirmResponse(
        import_id=import_rec.id,
        records_imported=len(pending["trades"]),
    )


@router.get("/equity-curve")
async def equity_curve(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cumulative P&L from imported trade history, sorted by trade date."""
    history = await trade_history(user=user, db=db)
    # Sort ascending by date for cumulative calculation
    sorted_trades = sorted(history, key=lambda t: t.trade_date or "")
    cumulative = 0.0
    curve = []
    for t in sorted_trades:
        cumulative += t.realized_pnl
        curve.append({
            "date": t.trade_date,
            "pnl": round(cumulative, 2),
        })
    return curve


@router.get("/imports", response_model=List[ImportRecordResponse])
async def list_imports(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ImportRecord)
        .where(ImportRecord.user_id == user.id)
        .order_by(ImportRecord.imported_at.desc())
    )
    return result.scalars().all()
