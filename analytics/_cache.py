"""Cache adapter — uses st.cache_data when Streamlit is available, no-op otherwise.

This allows analytics modules to be imported by both Streamlit pages and
the FastAPI backend without requiring Streamlit as a dependency.
"""

from __future__ import annotations

import functools


def _noop_cache(ttl: int = 0, show_spinner: bool = True):
    """No-op decorator matching st.cache_data signature."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


try:
    import streamlit as st

    cache_data = st.cache_data
except Exception:
    cache_data = _noop_cache
