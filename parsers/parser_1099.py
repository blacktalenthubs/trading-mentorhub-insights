"""Parser for Robinhood Consolidated Form 1099 PDFs (1099-B and 1099-DA)."""

import re
from datetime import date
from typing import Optional

from models import Trade1099
from config import categorize_symbol, classify_holding_period, detect_asset_type, CUSIP_TO_SYMBOL
from parsers.base import (
    extract_text, parse_money, parse_date, parse_date_str,
    is_page_header, extract_symbol_from_1099_option,
)


# Regex for trade data lines:
# date_sold  quantity  proceeds  date_acquired  cost_basis  wash/disc  gain_loss  info
TRADE_LINE_RE = re.compile(
    r"^\s+"
    r"(\d{2}/\d{2}/\d{2})"            # date_sold
    r"\s+"
    r"([\d,]+\.\d+)"                   # quantity
    r"\s+"
    r"([\d,]+\.\d+)"                   # proceeds (possibly with G/N suffix after)
    r"\s+"
    r"(\d{2}/\d{2}/\d{2}|Various)"     # date_acquired
    r"\s+"
    r"([\d,]+\.\d+)"                   # cost_basis
    r"\s+"
    r"([\d,]+\.\d+\s*W|[\d,]+\.\d+\s*D|\.\.\.)" # wash_sale or market_disc or ...
    r"\s+"
    r"(-?[\d,]+\.\d+)"                 # gain_loss
    r"\s+"
    r"(.+)$"                           # trade_type info
)

# Security header: name / CUSIP: xxx / Symbol:
# Handles wrapped names like "ADVANCED MICRO DEVICES, INC. C OMMON STOCK"
SECURITY_HEADER_RE = re.compile(
    r"^([A-Z][\w\s,.\-/&'()]+?)\s*/\s*CUSIP:\s*([A-Za-z0-9]*)\s*/\s*Symbol:\s*(.*)?$"
)

# Option header: AAPL 11/14/2025 CALL $260.00 / CUSIP: / Symbol: AAPL 11/14/25 C 260.000
OPTION_HEADER_RE = re.compile(
    r"^([A-Z]+\s+\d{2}/\d{2}/\d{4}\s+(?:CALL|PUT|Call|Put)\s+\$[\d,.]+)"
    r"\s*/\s*CUSIP:\s*([A-Za-z0-9]*)\s*/\s*Symbol:\s*(.+)$"
)

# Crypto header: Bitcoin / 4H95J0R2X
CRYPTO_HEADER_RE = re.compile(
    r"^([A-Za-z][\w\s]+?)\s*/\s*([A-Za-z0-9]+)\s*$"
)

# Security total line
SECURITY_TOTAL_RE = re.compile(r"^\s*Security total:")

# Section total line
SECTION_TOTAL_RE = re.compile(r"^\s*Totals\s*:")

# Account detection
ACCOUNT_RE = re.compile(r"Account\s+(\d{9}C?)")

# Section type detection
SECTION_SHORT_COVERED_RE = re.compile(r"SHORT TERM TRANSACTIONS FOR COVERED TAX LOTS")
SECTION_SHORT_NONCOVERED_RE = re.compile(r"SHORT TERM TRANSACTIONS FOR NONCOVERED TAX LOTS")
SECTION_LONG_COVERED_RE = re.compile(r"LONG TERM TRANSACTIONS FOR COVERED TAX LOTS")
SECTION_LONG_NONCOVERED_RE = re.compile(r"LONG TERM TRANSACTIONS FOR NONCOVERED TAX LOTS")

# Continued header for same security across pages
CONTINUED_RE = re.compile(r"\(cont'd\)")

# Column header lines to skip
COLUMN_HEADER_RE = re.compile(r"^\s*1[a-i]-|^\s*sold or|^\s*disposed")


def _detect_form_type(line: str) -> Optional[str]:
    if "1099-DA" in line:
        return "1099-DA"
    if "1099-B" in line:
        return "1099-B"
    return None


def _parse_trade_line(line: str) -> Optional[dict]:
    """Parse a single trade data line into a dict of raw values."""
    m = TRADE_LINE_RE.match(line)
    if not m:
        return None

    date_sold_str = m.group(1)
    quantity_str = m.group(2)
    proceeds_str = m.group(3)
    date_acquired_str = m.group(4)
    cost_basis_str = m.group(5)
    wash_disc_str = m.group(6).strip()
    gain_loss_str = m.group(7)
    info_str = m.group(8).strip()

    wash_sale = 0.0
    if wash_disc_str != "..." and wash_disc_str.endswith("W"):
        wash_sale = parse_money(wash_disc_str.rstrip("W").strip())

    return {
        "date_sold": date_sold_str,
        "quantity": parse_money(quantity_str),
        "proceeds": parse_money(proceeds_str),
        "date_acquired": date_acquired_str,
        "cost_basis": parse_money(cost_basis_str),
        "wash_sale_disallowed": wash_sale,
        "gain_loss": parse_money(gain_loss_str),
        "trade_type": info_str,
    }


def _compute_holding_days(date_sold: date, date_acquired: Optional[date]) -> Optional[int]:
    if date_acquired is None:
        return None
    return (date_sold - date_acquired).days


def _extract_underlying(description: str, symbol_text: str) -> str:
    """Extract underlying symbol for options."""
    underlying = extract_symbol_from_1099_option(description)
    if not underlying and symbol_text:
        underlying = extract_symbol_from_1099_option(symbol_text)
    return underlying


def parse_1099(pdf_path: str) -> list[Trade1099]:
    """Parse a Robinhood 1099 PDF and return a list of Trade1099 objects."""
    text = extract_text(pdf_path)
    lines = text.split("\n")

    trades: list[Trade1099] = []
    current_account = ""
    current_term = "short"
    current_covered = True
    current_form_type = "1099-B"
    current_description = ""
    current_cusip = ""
    current_symbol = ""
    current_is_option = False
    current_underlying = ""

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines and page headers
        if is_page_header(line) or not stripped:
            i += 1
            continue

        # Skip column header lines
        if COLUMN_HEADER_RE.match(stripped):
            i += 1
            continue

        # Skip various boilerplate
        if stripped.startswith("Report on Form") or stripped.startswith('"Gain or loss'):
            i += 1
            continue
        if stripped.startswith("FATCA") or stripped.startswith("Several columns"):
            i += 1
            continue
        if "Robinhood Markets Inc" in stripped and "Account" not in stripped:
            i += 1
            continue
        if stripped.startswith("2025") and ("1099-B" in stripped or "1099-DA" in stripped):
            ft = _detect_form_type(stripped)
            if ft:
                current_form_type = ft
            i += 1
            continue
        if stripped.startswith("Sales transactions are organized"):
            i += 1
            continue
        if stripped.startswith("Closing of written options"):
            i += 1
            continue
        if "Proceeds from Broker" in stripped or "Digital Assets Proceeds" in stripped:
            i += 1
            continue
        if stripped.startswith("(continued)"):
            i += 1
            continue
        if stripped == "":
            i += 1
            continue

        # Detect account
        acct_match = ACCOUNT_RE.search(stripped)
        if acct_match and ("Robinhood" in stripped or "Account" in stripped):
            new_acct = acct_match.group(1)
            if new_acct != current_account:
                current_account = new_acct
                # Detect form type from context
                if current_account.endswith("C"):
                    current_form_type = "1099-DA"
                else:
                    current_form_type = "1099-B"
            i += 1
            continue

        # Detect section type
        if SECTION_SHORT_COVERED_RE.search(stripped):
            current_term = "short"
            current_covered = True
            i += 1
            continue
        if SECTION_SHORT_NONCOVERED_RE.search(stripped):
            current_term = "short"
            current_covered = False
            i += 1
            continue
        if SECTION_LONG_COVERED_RE.search(stripped):
            current_term = "long"
            current_covered = True
            i += 1
            continue
        if SECTION_LONG_NONCOVERED_RE.search(stripped):
            current_term = "long"
            current_covered = False
            i += 1
            continue

        # Skip security total and section total lines
        if SECURITY_TOTAL_RE.match(stripped) or SECTION_TOTAL_RE.match(stripped):
            i += 1
            continue

        # Skip continued markers
        if CONTINUED_RE.search(stripped):
            i += 1
            continue

        # Try option header (must check before security header)
        opt_match = OPTION_HEADER_RE.match(stripped)
        if opt_match:
            current_description = opt_match.group(1)
            current_cusip = opt_match.group(2) or ""
            current_symbol = opt_match.group(3).strip() if opt_match.group(3) else ""
            current_is_option = True
            current_underlying = _extract_underlying(current_description, current_symbol)
            i += 1
            continue

        # Try security header
        sec_match = SECURITY_HEADER_RE.match(stripped)
        if sec_match:
            current_description = sec_match.group(1).strip()
            current_cusip = sec_match.group(2) or ""
            raw_symbol = sec_match.group(3).strip() if sec_match.group(3) else ""
            # Symbol field is often empty for stocks; use CUSIP lookup
            if raw_symbol:
                current_symbol = raw_symbol
            elif current_cusip and current_cusip in CUSIP_TO_SYMBOL:
                current_symbol = CUSIP_TO_SYMBOL[current_cusip]
            else:
                current_symbol = ""
            current_is_option = False
            current_underlying = ""
            i += 1
            continue

        # Try crypto header (for 1099-DA)
        if current_form_type == "1099-DA":
            crypto_match = CRYPTO_HEADER_RE.match(stripped)
            if crypto_match and not stripped.startswith("Robinhood"):
                current_description = crypto_match.group(1).strip()
                current_cusip = crypto_match.group(2).strip()
                # Map crypto names to symbols
                name_to_sym = {
                    "Bitcoin": "BTC", "Ethereum": "ETH", "Dogecoin": "DOGE",
                    "Solana": "SOL", "Cardano": "ADA",
                }
                current_symbol = name_to_sym.get(current_description, current_description.upper()[:4])
                current_is_option = False
                current_underlying = ""
                i += 1
                continue

        # Try trade data line
        trade_data = _parse_trade_line(line)
        if trade_data and current_account:
            ds = parse_date(trade_data["date_sold"])
            da = parse_date(trade_data["date_acquired"])

            if ds is None:
                i += 1
                continue

            # Determine the clean symbol for categorization
            if current_is_option:
                cat_symbol = current_underlying or current_symbol.split()[0]
                asset_type = "option"
            else:
                # Use CUSIP lookup first, then current_symbol
                if current_cusip and current_cusip in CUSIP_TO_SYMBOL:
                    cat_symbol = CUSIP_TO_SYMBOL[current_cusip]
                elif current_symbol:
                    cat_symbol = current_symbol.split()[0]
                else:
                    cat_symbol = ""
                asset_type = detect_asset_type(current_description, cat_symbol)

            holding_days = _compute_holding_days(ds, da)
            category = categorize_symbol(cat_symbol)

            # Build the display symbol
            display_symbol = current_symbol if current_symbol else cat_symbol

            trade = Trade1099(
                account=current_account,
                description=current_description,
                symbol=display_symbol,
                cusip=current_cusip,
                date_sold=ds,
                date_acquired=da,
                date_acquired_raw=parse_date_str(trade_data["date_acquired"]),
                quantity=trade_data["quantity"],
                proceeds=trade_data["proceeds"],
                cost_basis=trade_data["cost_basis"],
                wash_sale_disallowed=trade_data["wash_sale_disallowed"],
                gain_loss=trade_data["gain_loss"],
                term=current_term,
                covered=current_covered,
                form_type=current_form_type,
                trade_type=trade_data["trade_type"],
                asset_type=asset_type,
                category=category,
                holding_days=holding_days,
                holding_period_type=classify_holding_period(holding_days),
                underlying_symbol=current_underlying if current_is_option else "",
            )
            trades.append(trade)
            i += 1
            continue

        i += 1

    return trades
