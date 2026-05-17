"""STUB — Spec 49 cleanup deleted the original real_trade_store.py.

The original module persisted real-money trade records (open / closed /
stats) for `swing_scanner._auto_close_real_trade`, `trade_coach`, and
`position_advisor`. The cleanup pass removed it under the assumption it
was V1-dead, but pre-flight research missed the lazy importers in those
retained modules.

This stub keeps the import surface intact so V2 paths (`/swing/*`,
`/intel/*`) continue to load. Functions return safe no-op defaults +
log a clear warning. Real-money trade auto-close from swing_scanner is
effectively DISABLED until this is reconstructed from git history or a
backup.

ACTION REQUIRED: restore the original file from git history or a backup,
OR explicitly decide the real-trade-store functionality is deprecated
and refactor the consumers to not need it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("real_trade_store_stub")
_warned = False


def _warn_once(fn: str) -> None:
    global _warned
    if not _warned:
        logger.warning(
            "alerting.real_trade_store is a STUB (Spec 49 cleanup). "
            "Call to %s returned a safe default. Restore the real module "
            "from git history or reconstruct.", fn,
        )
        _warned = True


def get_open_trades(trade_type: str | None = None, **kwargs) -> list[dict]:
    _warn_once("get_open_trades")
    return []


def get_closed_trades(*args, **kwargs) -> list[dict]:
    _warn_once("get_closed_trades")
    return []


def get_real_trade_stats(*args, **kwargs) -> dict:
    _warn_once("get_real_trade_stats")
    return {"open": 0, "closed": 0, "total_pnl": 0.0}


def close_real_trade(trade_id: int, exit_price: float, notes: str = "") -> bool:
    _warn_once("close_real_trade")
    logger.warning(
        "close_real_trade(trade_id=%s, exit_price=%.2f) — STUB no-op",
        trade_id, exit_price,
    )
    return False


def stop_real_trade(trade_id: int, exit_price: float, notes: str = "") -> bool:
    _warn_once("stop_real_trade")
    logger.warning(
        "stop_real_trade(trade_id=%s, exit_price=%.2f) — STUB no-op",
        trade_id, exit_price,
    )
    return False
