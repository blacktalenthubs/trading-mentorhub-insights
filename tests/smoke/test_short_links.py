"""Short-link redirect smoke tests — verify UTM attribution flow."""

from __future__ import annotations

import pytest


SHORT_LINK_EXPECTATIONS = [
    ("tw", "utm_source=twitter"),
    ("tt", "utm_source=tiktok"),
    ("ig", "utm_source=instagram"),
    ("dm", "utm_source=friend"),
    ("fr", "utm_source=friend"),
    ("launch", "utm_campaign=launch"),
]


@pytest.mark.parametrize("code,expected_fragment", SHORT_LINK_EXPECTATIONS)
def test_short_link_redirects_with_utm(base_url, http, code, expected_fragment):
    """Each short code should 302 → landing with the matching UTM param."""
    r = http.get(f"{base_url}/{code}", allow_redirects=False, timeout=10)
    assert r.status_code in (301, 302, 307, 308), (
        f"/{code} did not redirect — got {r.status_code}"
    )
    location = r.headers.get("Location", "")
    assert expected_fragment in location, (
        f"/{code} redirected to {location!r}, expected fragment {expected_fragment!r}"
    )


def test_unknown_short_code_falls_through_to_spa(base_url, http):
    """Unknown paths should render the SPA (index.html), not 404."""
    r = http.get(f"{base_url}/this-is-not-a-real-page-xyz", timeout=10)
    assert r.status_code == 200
    assert "<div id=\"root\">" in r.text or "TradeCoPilot" in r.text


def test_short_link_target_loads_after_redirect(base_url, http):
    """Full flow: hit short link, follow redirect, final URL has UTM and renders."""
    r = http.get(f"{base_url}/tw", timeout=10)  # follow redirects
    assert r.status_code == 200
    # Final URL should have UTM
    assert "utm_source=twitter" in r.url
