"""Smoke test fixtures — shared config for all live-environment tests."""

from __future__ import annotations

import os
import time
import pytest
import requests


def _base_url() -> str:
    return os.environ.get("SMOKE_BASE_URL", "https://www.tradingwithai.ai").rstrip("/")


@pytest.fixture(scope="session")
def base_url() -> str:
    return _base_url()


@pytest.fixture(scope="session")
def api_url(base_url: str) -> str:
    return f"{base_url}/api/v1"


@pytest.fixture(scope="session")
def http() -> requests.Session:
    """Shared session with sensible defaults."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": "TradeCoPilot-SmokeTest/1.0",
    })
    return s


@pytest.fixture(scope="session", autouse=True)
def _sanity_check(base_url: str, http: requests.Session):
    """Fail fast if the target is totally unreachable."""
    try:
        r = http.get(base_url, timeout=10)
    except Exception as e:
        pytest.exit(f"SMOKE: target {base_url} unreachable: {e}", returncode=2)
    if r.status_code >= 500:
        pytest.exit(f"SMOKE: target {base_url} returned {r.status_code}", returncode=2)


def unique_email() -> str:
    """Generate a test email with timestamp for signup tests."""
    return f"smoke-{int(time.time())}-{os.getpid()}@smoketest.tradingwithai.ai"


def skip_if_signup_disabled():
    if os.environ.get("SMOKE_SKIP_SIGNUP") in ("1", "true", "yes"):
        pytest.skip("Signup tests disabled via SMOKE_SKIP_SIGNUP")
