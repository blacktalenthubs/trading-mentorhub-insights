"""STUB — Spec 49 cleanup deleted the original paper_trader.py.

The original module managed paper-trading open positions for
`position_advisor` and `trade_coach`. Consumers import lazily inside
their functions, so the module deletion didn't break module-level
imports — but per-function calls would fail.

This stub returns safe defaults + logs warnings.

ACTION REQUIRED: restore the original file from git history or a backup,
OR refactor consumers to not need it. The /paper-trading React page was
deleted in Spec 49 FR-404 so paper-trading UI is gone; this stub keeps
the analytics consumers from crashing while you decide.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("paper_trader_stub")
_warned = False


def _warn_once(fn: str) -> None:
    global _warned
    if not _warned:
        logger.warning(
            "alerting.paper_trader is a STUB (Spec 49 cleanup). "
            "Call to %s returned a safe default.", fn,
        )
        _warned = True


def get_open_paper_trades_for_coach(*args, **kwargs) -> list[dict]:
    _warn_once("get_open_paper_trades_for_coach")
    return []
