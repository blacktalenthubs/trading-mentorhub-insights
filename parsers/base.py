"""Common PDF extraction and parsing utilities."""

import re
import subprocess
from datetime import date, datetime
from typing import Optional


def extract_text(pdf_path: str) -> str:
    """Extract text from PDF using pdftotext with layout preservation."""
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def parse_money(s: str) -> float:
    """Parse a money string like '11,296,308.78' or '-10,246.70' to float."""
    if not s or s.strip() in ("...", ""):
        return 0.0
    s = s.strip().replace("$", "").replace(",", "")
    # Handle parenthetical negatives: (1,234.56) -> -1234.56
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return float(s)


def parse_date(s: str) -> Optional[date]:
    """Parse a date string like '08/29/25' or '01/02/2026'."""
    s = s.strip()
    if not s or s.lower() == "various":
        return None
    for fmt in ("%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_date_str(s: str) -> str:
    """Return the raw date string, cleaned."""
    return s.strip()


def is_page_header(line: str) -> bool:
    """Check if line is a page header/footer to skip."""
    line_stripped = line.strip()
    if not line_stripped:
        return True
    if re.match(r"^\s*Page\s+\d+\s+of\s+\d+\s*$", line_stripped):
        return True
    if "This is important tax information" in line_stripped:
        return True
    if "this income is taxable and the IRS determines" in line_stripped:
        return True
    if "Remember, taxpayers are ultimately responsible" in line_stripped:
        return True
    return False


def extract_symbol_from_option_desc(desc: str) -> str:
    """Extract underlying symbol from option description.

    Example: 'AAPL 11/14/2025 CALL $260.00' -> 'AAPL'
    Example: 'SPY 01/29/2026 Call $696.00' -> 'SPY'
    """
    m = re.match(r"^([A-Z]+)\s+\d{2}/\d{2}/\d{4}", desc.strip())
    if m:
        return m.group(1)
    return ""


def extract_symbol_from_1099_option(desc: str) -> str:
    """Extract underlying from 1099 option description line.

    Example: 'AAPL 11/14/2025 CALL $260.00 / CUSIP: / Symbol: AAPL 11/14/25 C 260.000'
    -> 'AAPL'
    """
    m = re.match(r"^([A-Z]+)\s+\d{2}/\d{2}/\d{4}\s+(CALL|PUT|Call|Put)", desc.strip())
    if m:
        return m.group(1)
    return ""
