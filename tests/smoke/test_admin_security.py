"""Admin endpoint security — must NOT be accessible without auth."""

from __future__ import annotations

import pytest


ADMIN_ENDPOINTS = [
    ("GET", "/admin/stats"),
    ("GET", "/admin/users"),
    ("GET", "/admin/attribution"),
    ("GET", "/admin/user-debug?email=foo@bar.com"),
    ("POST", "/admin/backfill-ai-alerts"),
]


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_admin_endpoint_rejects_anonymous(api_url, http, method, path):
    """Anonymous request to any /admin endpoint must return 401/403."""
    url = f"{api_url}{path}"
    r = http.request(method, url, timeout=10)
    assert r.status_code in (401, 403), (
        f"{method} {path} should require auth — got {r.status_code}: {r.text[:200]}"
    )


@pytest.mark.parametrize("method,path", ADMIN_ENDPOINTS)
def test_admin_endpoint_rejects_bad_token(api_url, http, method, path):
    """Request with a garbage JWT must still be rejected."""
    url = f"{api_url}{path}"
    r = http.request(
        method, url, timeout=10,
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code in (401, 403), (
        f"{method} {path} with bad token should reject — got {r.status_code}"
    )
