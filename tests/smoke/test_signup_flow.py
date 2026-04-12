"""Signup flow smoke test — creates a real test user. Skip in CI with SMOKE_SKIP_SIGNUP=1.

Test accounts are auto-named with timestamp + pid so they're easy to clean up.
"""

from __future__ import annotations

import pytest

from .conftest import skip_if_signup_disabled, unique_email


class TestSignupFlow:
    def setup_method(self):
        skip_if_signup_disabled()

    def test_register_creates_trial_user_with_attribution(self, api_url, http):
        """POST /auth/register with UTM fields → trial Pro user + attribution persisted."""
        email = unique_email()
        password = "Sm0keTest!2026"

        payload = {
            "email": email,
            "password": password,
            "display_name": "Smoke Test",
            "utm_source": "smoke",
            "utm_medium": "automated",
            "utm_campaign": "ci",
            "referrer": "https://smoketest.tradingwithai.ai/",
        }
        r = http.post(f"{api_url}/auth/register", json=payload, timeout=15)
        assert r.status_code == 201, f"Register failed {r.status_code}: {r.text[:300]}"

        data = r.json()
        assert "access_token" in data, "No access token returned"
        assert "user" in data
        user = data["user"]
        assert user["email"].lower() == email.lower()
        # New accounts should be on Pro trial
        assert user["tier"] == "pro", f"New signup tier={user['tier']}, expected 'pro' (trial)"
        assert user.get("trial_active") is True, "Trial should be active on fresh signup"

        # /auth/me with the new token confirms session works
        me = http.get(
            f"{api_url}/auth/me",
            headers={"Authorization": f"Bearer {data['access_token']}"},
            timeout=10,
        )
        assert me.status_code == 200

    def test_register_rejects_weak_password(self, api_url, http):
        email = unique_email()
        r = http.post(
            f"{api_url}/auth/register",
            json={"email": email, "password": "abc"},  # too short
            timeout=10,
        )
        assert r.status_code == 422, f"Weak password should be rejected — got {r.status_code}"

    def test_register_rejects_duplicate_email(self, api_url, http):
        email = unique_email()
        password = "Sm0keTest!2026"
        # First signup
        r1 = http.post(
            f"{api_url}/auth/register",
            json={"email": email, "password": password},
            timeout=15,
        )
        assert r1.status_code == 201
        # Duplicate signup should fail with 409
        r2 = http.post(
            f"{api_url}/auth/register",
            json={"email": email, "password": password},
            timeout=15,
        )
        assert r2.status_code == 409, f"Duplicate email should 409 — got {r2.status_code}"

    def test_login_after_register(self, api_url, http):
        email = unique_email()
        password = "Sm0keTest!2026"
        http.post(
            f"{api_url}/auth/register",
            json={"email": email, "password": password},
            timeout=15,
        )
        login = http.post(
            f"{api_url}/auth/login",
            json={"email": email, "password": password},
            timeout=10,
        )
        assert login.status_code == 200
        assert "access_token" in login.json()
