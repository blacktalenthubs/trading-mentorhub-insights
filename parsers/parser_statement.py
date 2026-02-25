"""Parser for Robinhood monthly account statement PDFs."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from models import TradeMonthly, AccountSummary
from config import (
    categorize_symbol, detect_asset_type, RECURRING_ACCOUNT,
)
from parsers.base import extract_text, parse_money, extract_symbol_from_option_desc


# Account header
ACCOUNT_RE = re.compile(r"Individual Account #:(\d+)")

# Period from header
PERIOD_RE = re.compile(r"(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})")

# Account summary: Portfolio Value  opening  closing
SUMMARY_BALANCE_RE = re.compile(
    r"Portfolio Value\s+\$([\d,.]+)\s+\$([\d,.]+)"
)

# Generic trade data pattern: extract SYMBOL ACCTTYPE TRANSACTION DATE QTY $PRICE $AMOUNT
# This matches anywhere in the line (handles CUSIP prefix, Recurring prefix, indentation)
TRADE_DATA_PATTERN = re.compile(
    r"([A-Z]{1,5})"                    # symbol
    r"\s+"
    r"(Cash|Margin)"                   # acct_type
    r"\s+"
    r"(Buy|Sell|BTO|STC)"             # transaction
    r"\s+"
    r"(\d{2}/\d{2}/\d{4})"           # date
    r"\s+"
    r"([\d,.]+)"                       # quantity
    r"\s+"
    r"\$([\d,.]+)"                     # price
    r"\s+"
    r"\$([\d,.]+)"                     # amount
)

# Non-trade transactions to skip
SKIP_TRANSACTIONS = {"INT", "ACH", "GOLD", "MINT"}

# Option description pattern: "SPY 01/29/2026 Call $696.00"
OPTION_DESC_RE = re.compile(
    r"([A-Z]+)\s+(\d{2}/\d{2}/\d{4})\s+(Call|Put)\s+\$([\d,.]+)"
)

# CUSIP line (without trade data)
CUSIP_RE = re.compile(r"CUSIP:\s*([A-Za-z0-9]+)")


def _parse_statement_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%m/%d/%Y").date()


def _is_section_header(stripped: str) -> bool:
    """Check if line is a section header that ends activity parsing."""
    return stripped in (
        "Executed Trades Pending Settlement",
        "Portfolio Summary",
        "Portfolio Allocation",
        "Stock Lending - Loaned Securities",
        "Stock Lending - Loan Activity",
        "Stock Lending - Collateral Activity",
        "Deposit Sweep Program Banks",
        "Deposit Sweep Activity",
        "Income and Expense Summary",
    )


def _is_skip_transaction(line: str) -> bool:
    """Check if line contains a non-trade transaction."""
    for st in SKIP_TRANSACTIONS:
        if re.search(rf"\b{st}\b", line):
            # But make sure it's not also a trade line
            if not re.search(r"\b(Buy|Sell|BTO|STC)\b", line):
                return True
    return False


def parse_statement(pdf_path: str) -> tuple[list[TradeMonthly], list[AccountSummary]]:
    """Parse a Robinhood monthly statement PDF."""
    text = extract_text(pdf_path)
    lines = text.split("\n")

    trades: list[TradeMonthly] = []
    summaries: list[AccountSummary] = []

    # Extract period from first few lines
    period_start = None
    period_end = None
    for line in lines[:10]:
        pm = PERIOD_RE.search(line)
        if pm:
            period_start = _parse_statement_date(pm.group(1))
            period_end = _parse_statement_date(pm.group(2))
            break

    current_account = ""
    current_description = ""
    current_cusip = ""
    current_is_option = False
    current_option_detail = ""
    is_recurring_next = False
    in_activity_section = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty and page lines
        if not stripped or (stripped.startswith("Page ") and " of " in stripped):
            i += 1
            continue

        # Account detection
        acct_match = ACCOUNT_RE.search(stripped)
        if acct_match:
            current_account = acct_match.group(1)
            in_activity_section = False
            i += 1
            continue

        # Account summary
        if current_account and period_start and period_end:
            bal_match = SUMMARY_BALANCE_RE.search(stripped)
            if bal_match:
                summaries.append(AccountSummary(
                    account=current_account,
                    period_start=period_start,
                    period_end=period_end,
                    opening_balance=parse_money(bal_match.group(1)),
                    closing_balance=parse_money(bal_match.group(2)),
                ))
                i += 1
                continue

        # Activity section toggle
        if stripped == "Account Activity":
            in_activity_section = True
            i += 1
            continue

        if _is_section_header(stripped):
            in_activity_section = False
            i += 1
            continue

        if not in_activity_section or not current_account:
            i += 1
            continue

        # Skip header row
        if stripped.startswith("Description") and "Symbol" in stripped:
            i += 1
            continue

        # Skip non-trade lines
        if _is_skip_transaction(stripped):
            i += 1
            continue

        # Skip boilerplate
        if any(kw in stripped for kw in [
            "Securities Investor", "Total Funds", "FDIC",
            "Stock Lending", "Deposit Sweep", "closing date",
            "Collateral", "collateral", "Robinhood Gold is",
            "Robinhood Securities", "when \"Managed\"",
            "provisions of", "Robinhood Financial",
            "Please note that", "This statement shall",
        ]):
            i += 1
            continue

        # Recurring marker
        if stripped == "Recurring":
            is_recurring_next = True
            i += 1
            continue

        # Try to find trade data in this line
        trade_match = TRADE_DATA_PATTERN.search(stripped)
        if trade_match:
            symbol = trade_match.group(1)
            acct_type = trade_match.group(2)
            txn_type = trade_match.group(3)
            trade_date_str = trade_match.group(4)
            qty_str = trade_match.group(5)
            price_str = trade_match.group(6)
            amount_str = trade_match.group(7)

            trade_date = _parse_statement_date(trade_date_str)
            qty = parse_money(qty_str)
            price = parse_money(price_str)
            raw_amount = parse_money(amount_str)

            # Determine sign from transaction type
            if txn_type in ("Buy", "BTO"):
                amount = -raw_amount  # money out
            else:
                amount = raw_amount   # money in (Sell, STC)

            # Check if option description is embedded in this line
            # e.g. "SPY 01/29/2026 Call $696.00   SPY  Margin  BTO  ..."
            inline_opt = OPTION_DESC_RE.search(stripped)
            if inline_opt or txn_type in ("BTO", "STC"):
                current_is_option = True
                if inline_opt:
                    current_option_detail = inline_opt.group(0)
                    current_description = current_option_detail

            # Check if this line had "Recurring" prefix or we saw Recurring tag
            is_recurring = (
                is_recurring_next
                or "Recurring" in stripped
                or current_account == RECURRING_ACCOUNT
            )

            # Determine underlying for options
            underlying = ""
            if current_is_option:
                underlying = extract_symbol_from_option_desc(current_option_detail)
                cat_sym = underlying if underlying else symbol
            else:
                cat_sym = symbol

            asset_type = "option" if current_is_option else detect_asset_type(
                current_description, symbol
            )
            category = categorize_symbol(cat_sym)

            # Extract CUSIP if on same line
            cusip_match = CUSIP_RE.search(stripped)
            if cusip_match:
                current_cusip = cusip_match.group(1)

            trade = TradeMonthly(
                account=current_account,
                description=current_description,
                symbol=symbol,
                cusip=current_cusip,
                acct_type=acct_type,
                transaction_type=txn_type,
                trade_date=trade_date,
                quantity=qty,
                price=price,
                amount=amount,
                is_option=current_is_option,
                option_detail=current_option_detail if current_is_option else "",
                is_recurring=is_recurring,
                asset_type=asset_type,
                category=category,
                underlying_symbol=underlying,
            )
            trades.append(trade)
            is_recurring_next = False
            i += 1
            continue

        # Try option description
        opt_match = OPTION_DESC_RE.match(stripped)
        if opt_match:
            current_description = stripped
            current_is_option = True
            current_option_detail = stripped
            is_recurring_next = False
            i += 1
            continue

        # CUSIP line (standalone, without trade data)
        cusip_match = CUSIP_RE.match(stripped)
        if cusip_match and not TRADE_DATA_PATTERN.search(stripped):
            current_cusip = cusip_match.group(1)
            i += 1
            continue

        # Stock/ETF description line (just text, no numbers or special chars)
        if re.match(r"^[A-Za-z][\w\s&.,\'\-]+$", stripped) and len(stripped) < 80:
            if stripped not in ("Cash", "Margin", "Recurring", "Account Activity"):
                current_description = stripped
                current_is_option = False
                current_option_detail = ""
                i += 1
                continue

        i += 1

    return trades, summaries
