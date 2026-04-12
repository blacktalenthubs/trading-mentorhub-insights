# Smoke Tests — Run Against Live/Staging Environment

End-to-end checks that hit the deployed app. Complements manual checklist in
`tickets/pre-ad-launch-smoke-tests.md` — automates the boring parts so you can
run them on every deploy / nightly / before ad campaigns.

## Usage

```bash
# Against production (default)
python -m pytest tests/smoke/ -v

# Against custom URL
SMOKE_BASE_URL=https://staging.tradingwithai.ai python -m pytest tests/smoke/ -v

# Skip signup tests (they create real test users — cleanup needed)
SMOKE_SKIP_SIGNUP=1 python -m pytest tests/smoke/ -v

# CI mode — fail fast, no signup
SMOKE_SKIP_SIGNUP=1 python -m pytest tests/smoke/ -x --tb=short
```

## What's Covered

| File | What it tests |
|---|---|
| `test_landing.py` | Homepage loads, meta tags, no 500s |
| `test_short_links.py` | `/tw`, `/tt`, `/ig`, etc. redirect with UTM |
| `test_public_endpoints.py` | Track record, learn/patterns, replay (no auth) |
| `test_admin_security.py` | Admin endpoints return 401/403 without token |
| `test_signup_flow.py` | Register creates trial user with attribution (skippable) |

## CI Integration

See `.github/workflows/smoke.yml` — runs on push, PR, and nightly at 3am UTC.
