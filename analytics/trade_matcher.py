"""FIFO trade matching for monthly statement buy/sell pairs."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from config import categorize_symbol, classify_holding_period, detect_asset_type
from models import TradeMonthly, MatchedTrade


@dataclass
class _OpenLot:
    """An open buy lot waiting to be matched."""
    trade_date: object  # date
    quantity: float
    price: float
    amount: float  # absolute value of buy cost


def match_trades_fifo(trades: list[TradeMonthly]) -> list[MatchedTrade]:
    """Match buy/sell trades using FIFO (First In, First Out).

    Groups trades by (account, symbol) and matches buys to sells in order.
    Returns realized MatchedTrade records.
    """
    # Group by (account, symbol)
    buy_lots: dict[tuple[str, str], deque[_OpenLot]] = defaultdict(deque)
    matched: list[MatchedTrade] = []

    # Sort by date
    sorted_trades = sorted(trades, key=lambda t: t.trade_date)

    for trade in sorted_trades:
        key = (trade.account, trade.symbol)

        if trade.transaction_type in ("Buy", "BTO"):
            buy_lots[key].append(_OpenLot(
                trade_date=trade.trade_date,
                quantity=trade.quantity,
                price=trade.price,
                amount=abs(trade.amount),
            ))
        elif trade.transaction_type in ("Sell", "STC"):
            remaining_qty = trade.quantity
            sell_price = trade.price

            while remaining_qty > 0.0001 and buy_lots[key]:
                lot = buy_lots[key][0]

                match_qty = min(remaining_qty, lot.quantity)
                holding_days = (trade.trade_date - lot.trade_date).days

                # Determine asset type and category
                asset_type = trade.asset_type or detect_asset_type(
                    trade.description, trade.symbol
                )
                underlying = trade.underlying_symbol or trade.symbol
                category = trade.category or categorize_symbol(underlying)

                # An option contract controls 100 shares. Prices are quoted per share,
                # so scale option cost/proceeds to real dollars HERE — realized_pnl,
                # buy_amount and sell_amount are the dollar figures every consumer reads.
                # buy_price/sell_price stay per-share (that's how a premium is quoted).
                contract_mult = 100.0 if (asset_type or "").lower() == "option" else 1.0
                buy_cost = match_qty * lot.price * contract_mult
                sell_proceeds = match_qty * sell_price * contract_mult

                matched.append(MatchedTrade(
                    account=trade.account,
                    symbol=trade.symbol,
                    buy_date=lot.trade_date,
                    sell_date=trade.trade_date,
                    quantity=match_qty,
                    buy_price=lot.price,
                    sell_price=sell_price,
                    buy_amount=buy_cost,
                    sell_amount=sell_proceeds,
                    realized_pnl=sell_proceeds - buy_cost,
                    holding_days=holding_days,
                    asset_type=asset_type,
                    category=category,
                    holding_period_type=classify_holding_period(holding_days),
                    underlying_symbol=trade.underlying_symbol,
                ))

                lot.quantity -= match_qty
                remaining_qty -= match_qty

                if lot.quantity < 0.0001:
                    buy_lots[key].popleft()

    return matched
