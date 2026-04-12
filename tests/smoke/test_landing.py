"""Landing page smoke tests — checks the public marketing page."""

from __future__ import annotations


class TestLandingPage:
    def test_loads_with_200(self, base_url, http):
        r = http.get(base_url, timeout=10)
        assert r.status_code == 200, f"Got {r.status_code}: {r.text[:200]}"

    def test_has_expected_title(self, base_url, http):
        r = http.get(base_url, timeout=10)
        assert "TradeCoPilot" in r.text
        assert "AI Trading" in r.text

    def test_og_meta_tags_present(self, base_url, http):
        r = http.get(base_url, timeout=10)
        assert 'property="og:title"' in r.text
        assert 'property="og:description"' in r.text
        assert 'property="og:url"' in r.text
        assert "tradingwithai.ai" in r.text  # URL in og:url

    def test_no_reference_to_removed_features(self, base_url, http):
        """Spec 28 cleanup — these shouldn't be marketed."""
        r = http.get(base_url, timeout=10)
        # Only check the HTML head + SPA shell (the removed features shouldn't appear
        # in meta tags or structured data)
        head = r.text.split("</head>")[0] if "</head>" in r.text else r.text
        # Case-insensitive check
        head_lower = head.lower()
        assert "options flow" not in head_lower, "Options Flow leaking in head"
        assert "sector rotation" not in head_lower, "Sector Rotation leaking in head"
        assert "catalyst calendar" not in head_lower, "Catalyst Calendar leaking in head"

    def test_ga4_script_present(self, base_url, http):
        r = http.get(base_url, timeout=10)
        assert "googletagmanager.com" in r.text, "GA4 script tag missing"

    def test_ga4_has_real_measurement_id(self, base_url, http):
        """MUST pass before running paid ads — otherwise attribution is blind.
        Fails while the placeholder GA_MEASUREMENT_ID is still in web/index.html."""
        r = http.get(base_url, timeout=10)
        if "GA_MEASUREMENT_ID" in r.text:
            import pytest
            pytest.fail(
                "GA4 placeholder not replaced. Go to analytics.google.com, create a "
                "property for www.tradingwithai.ai, copy the Measurement ID (G-XXXXXXXXXX), "
                "and replace both occurrences of GA_MEASUREMENT_ID in web/index.html "
                "before running paid traffic."
            )

    def test_assets_load(self, base_url, http):
        """At least one CSS and JS bundle reachable."""
        r = http.get(base_url, timeout=10)
        # index.html references /assets/index-*.js and /assets/index-*.css
        import re
        js_refs = re.findall(r'/assets/index-[\w-]+\.js', r.text)
        css_refs = re.findall(r'/assets/index-[\w-]+\.css', r.text)
        assert js_refs, "No JS bundle referenced in index.html"
        assert css_refs, "No CSS bundle referenced in index.html"
        # Spot-check first JS asset is reachable
        js_url = f"{base_url}{js_refs[0]}"
        js_resp = http.get(js_url, timeout=10)
        assert js_resp.status_code == 200, f"JS asset {js_url} returned {js_resp.status_code}"
