"""STUB — Spec 49 cleanup deleted the original _cache.py.

The original module provided a `cache_data` decorator used by
`analytics/intraday_data.py` to cache yfinance/DB query results.
`intraday_data.py` imports it eagerly at module load, so deletion
broke the import chain.

This stub provides a pass-through decorator (no caching) so V2 paths
that touch intraday_data continue to load. The performance impact is
"every query goes to source" — acceptable for the V2 read paths that
hit Postgres, slower for any V1 paths that still use yfinance.

ACTION REQUIRED: restore the original file from git history if you
want caching back. Until then, intraday_data calls run uncached.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

logger = logging.getLogger("cache_stub")
_warned = False


def cache_data(*decorator_args, **decorator_kwargs) -> Callable[..., Any]:
    """Pass-through decorator (no caching).

    Supports both `@cache_data` and `@cache_data(ttl=60)` call patterns.
    """
    # Called as @cache_data (no args) — first positional is the function
    if len(decorator_args) == 1 and callable(decorator_args[0]) and not decorator_kwargs:
        fn = decorator_args[0]

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper

    # Called as @cache_data(ttl=60) — return a decorator
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)
        return wrapper

    global _warned
    if not _warned:
        logger.warning(
            "analytics._cache is a STUB (Spec 49 cleanup). "
            "Caching is disabled; calls pass through."
        )
        _warned = True

    return decorator
