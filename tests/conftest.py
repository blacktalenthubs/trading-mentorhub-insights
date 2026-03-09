"""Shared test fixtures — mock unavailable packages for CI/sandbox environments."""

import sys
from unittest.mock import MagicMock

# yfinance requires multitasking which may not build in all environments
if "multitasking" not in sys.modules:
    sys.modules["multitasking"] = MagicMock()
