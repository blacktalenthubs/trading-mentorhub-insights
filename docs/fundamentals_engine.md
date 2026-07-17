# Fundamentals Engine (Phase 1)

Automates the deep fundamental research from value/short-selling literature
(Graham, Greenblatt, Staley) so watchlist stocks are scored for **quality** and
**risk** — with red flags surfaced — without reading a single filing.

## What it does

For every distinct watchlist symbol, nightly:

1. **Pull** — SEC EDGAR XBRL `companyfacts` → normalised multi-quarter financials.
2. **Compute** — the Section 3a (red-flag) and 3b (value/quality) metrics.
3. **Score & flag** — a 0–100 quality score, a 0–100 risk score, and scannable
   labels (`PROFITABLE ✅`, `DSO rising 3 quarters ⚠️`, `Earnings / cash-flow
   divergence 🚩`).
4. **Alert** — a genuinely *new* red flag (vs the prior run) fires a Telegram
   notification.

Every number is traceable to the source filing (accession + URL + as-of date).
Missing data stays missing — the engine never invents a value.

## Data source

**EDGAR-only** for Phase 1 (free, and the only source with the multi-quarter
line-item history the red-flag trends need). Price/market-cap for the valuation
metrics is passed in from the app's existing feed; when absent, those metrics
degrade gracefully to `None`.

## Modules

| File | Role |
|------|------|
| `fundamentals_config.py` | All thresholds + weights. Env-overridable, read per-run — tune without redeploy (same contract as the Pine/webhook gates). |
| `analytics/edgar_client.py` | ticker→CIK, throttled + cached `companyfacts` fetch, XBRL → `PeriodFinancials`. The only network module. |
| `analytics/fundamentals_metrics.py` | Pure metric engine (DSI, DSO, accruals, coverage, margins, dilution / ROC, earnings yield, FCF yield, margin of safety, Graham ratios). Modular registry. |
| `analytics/fundamentals_scoring.py` | `MetricSet` → quality score, risk score, flags. Config-driven. |
| `analytics/fundamentals_engine_refresh.py` | Nightly orchestrator: pull → upsert → compute → score → persist → alert. Idempotent. |
| `api/app/models/fundamentals_engine.py` | Tables: `fund_company`, `fund_financials`, `fund_metric`, `fund_score`, `fund_flag`. |
| `api/app/routers/fundamentals.py` | `GET /fundamentals/engine/{watchlist,report/{symbol},config}`. |
| `pages/fundamentals.py` | Streamlit dashboard: ranking table + per-stock drill-down. |

The metric/scoring/parse layers are **pure** (no network, DB, or clock) → fully
unit-tested offline with fixtures.

## Metrics

**Red flags (3a):** Days Sales of Inventory, Days Sales Outstanding, accruals
ratio, earnings/cash-flow divergence, margin compression, interest coverage,
debt/equity, share dilution.

**Value/quality (3b):** Return on Capital (Greenblatt), Earnings Yield
(Greenblatt), Free-cash-flow yield, current/quick ratio & debt/equity (Graham),
margin of safety vs a conservative Graham earnings-based intrinsic **estimate**,
and TTM GAAP profitability.

## Scoring

Equal-weight to start (tune later via config). Each score normalises to 0–100
over the sub-signals that actually had data, and reports a **coverage** fraction
so a small cap with partial data reads as low-coverage rather than falsely low.

## Operations

- **Cadence:** nightly at 03:00 ET (after the 02:00 Finnhub refresh so the two
  external feeds don't burst together). Toggle with `FUND_ENGINE_ENABLED`.
- **Idempotent:** re-running a day updates rows in place (unique keys on
  `(symbol, period_end, form)`, `(symbol, period_end, name)`,
  `(symbol, as_of_date)`, `(symbol, code, as_of_date)`) and re-notifies nothing.
- **EDGAR etiquette:** descriptive `SEC_EDGAR_USER_AGENT`, token-bucket rate
  cap, ~20h disk cache of `companyfacts`.
- **Graceful:** ETFs / ADRs / recent IPOs without XBRL are marked
  `no_edgar_data` and skipped; per-symbol failures are logged and the batch
  continues.

## Not in Phase 1

Full-market screening, special-situations parsing, peer/sector comparison, and
signal backtesting — all Phase 2. The metric registry and long-format
`fund_metric` table are built so new ratios plug in without a schema change.
