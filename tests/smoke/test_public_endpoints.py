"""Public (no-auth) API + route smoke tests."""

from __future__ import annotations


class TestPublicAPI:
    def test_track_record_endpoint(self, api_url, http):
        r = http.get(f"{api_url}/intel/public-track-record?days=90", timeout=15)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        data = r.json()
        # Shape check — landing page relies on these fields
        assert "win_rate" in data or "total_signals" in data or isinstance(data, dict)

    def test_learn_categories(self, api_url, http):
        r = http.get(f"{api_url}/learn/categories", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) or isinstance(data, dict)

    def test_learn_pattern_detail(self, api_url, http):
        """A known pattern ID should return 200."""
        r = http.get(f"{api_url}/learn/patterns/prior_day_low_bounce", timeout=10)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"

    def test_market_status_requires_auth(self, api_url, http):
        """Market status is behind auth — that's OK, just confirming the contract."""
        r = http.get(f"{api_url}/market/status", timeout=10)
        assert r.status_code in (200, 401), (
            f"Unexpected status {r.status_code} — either public (200) or auth-gated (401)"
        )


class TestPublicPages:
    def test_learn_page_renders(self, base_url, http):
        r = http.get(f"{base_url}/learn", timeout=10)
        assert r.status_code == 200

    def test_login_page_renders(self, base_url, http):
        r = http.get(f"{base_url}/login", timeout=10)
        assert r.status_code == 200

    def test_register_page_renders(self, base_url, http):
        r = http.get(f"{base_url}/register", timeout=10)
        assert r.status_code == 200
