"""Trade import service — wraps existing parsers for the API."""

from __future__ import annotations

import sys
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

_root = str(Path(__file__).resolve().parents[3])
if _root not in sys.path:
    sys.path.insert(0, _root)

from models import Trade1099, TradeMonthly, AccountSummary  # noqa: E402
from parsers.parser_1099 import parse_1099  # noqa: E402
from parsers.parser_statement import parse_statement  # noqa: E402

# In-memory store for pending parses (keyed by parse_id)
# In production, use Redis or a temp DB table
_pending_parses: dict[str, dict] = {}


def parse_pdf(filename: str, file_bytes: bytes) -> dict:
    """Parse a PDF and return a preview + parse_id for confirmation.

    Tries 1099 parser first, falls back to monthly statement parser.
    """
    # Write to temp file for pdftotext
    suffix = Path(filename).suffix or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(file_bytes)
        tmp_path = f.name

    try:
        # Try 1099 first
        trades_1099 = parse_1099(tmp_path)
        if trades_1099:
            parse_id = uuid.uuid4().hex
            _pending_parses[parse_id] = {
                "file_type": "1099",
                "filename": filename,
                "trades": trades_1099,
                "account_summary": None,
                "period": _infer_period_1099(trades_1099),
            }
            return {
                "file_type": "1099",
                "period": _pending_parses[parse_id]["period"],
                "trade_count": len(trades_1099),
                "preview": [_trade_1099_to_dict(t) for t in trades_1099[:10]],
                "parse_id": parse_id,
            }

        # Try monthly statement
        trades_monthly, account_summaries = parse_statement(tmp_path)
        if trades_monthly:
            parse_id = uuid.uuid4().hex
            summary = account_summaries[0] if account_summaries else None
            _pending_parses[parse_id] = {
                "file_type": "monthly",
                "filename": filename,
                "trades": trades_monthly,
                "account_summary": summary,
                "period": _infer_period_monthly(summary),
            }
            return {
                "file_type": "monthly",
                "period": _pending_parses[parse_id]["period"],
                "trade_count": len(trades_monthly),
                "preview": [_trade_monthly_to_dict(t) for t in trades_monthly[:10]],
                "parse_id": parse_id,
            }

        return {"error": "Could not parse PDF — no trades found"}

    finally:
        Path(tmp_path).unlink(missing_ok=True)


def get_pending_parse(parse_id: str) -> Optional[dict]:
    """Retrieve a pending parse by ID."""
    return _pending_parses.get(parse_id)


def remove_pending_parse(parse_id: str) -> None:
    """Remove a pending parse after confirmation."""
    _pending_parses.pop(parse_id, None)


def _infer_period_1099(trades: List[Trade1099]) -> str:
    if not trades:
        return "unknown"
    dates = [t.date_sold for t in trades if t.date_sold]
    if dates:
        years = {d.year for d in dates}
        return f"Tax Year {min(years)}" if len(years) == 1 else f"Tax Years {min(years)}-{max(years)}"
    return "unknown"


def _infer_period_monthly(summary: Optional[AccountSummary]) -> str:
    if summary and summary.period_start and summary.period_end:
        return f"{summary.period_start.isoformat()} to {summary.period_end.isoformat()}"
    return "unknown"


def _trade_1099_to_dict(t: Trade1099) -> dict:
    return {
        "symbol": t.symbol,
        "date_sold": t.date_sold.isoformat() if t.date_sold else None,
        "proceeds": t.proceeds,
        "cost_basis": t.cost_basis,
        "gain_loss": t.gain_loss,
        "asset_type": t.asset_type,
    }


def _trade_monthly_to_dict(t: TradeMonthly) -> dict:
    return {
        "symbol": t.symbol,
        "trade_date": t.trade_date.isoformat() if t.trade_date else None,
        "transaction_type": t.transaction_type,
        "quantity": t.quantity,
        "price": t.price,
        "amount": t.amount,
    }
