"""Breakout pattern scanner — cup-and-handle, flat base, ascending triangle, bull flag.

Entry points:
    patterns.screener.run_scan(symbols, cfg)      → ScanResult
    patterns.today_writer.write_today(body, date) → market_reports (Today tab)
    python -m patterns.screener --help            → CLI
"""

from patterns.common import PatternHit  # noqa: F401
from patterns.config import DEFAULT_CONFIG, ScannerConfig  # noqa: F401
