# Quickstart: In-Play Volume Screener

## Prerequisites
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` set (already in `.env`).
- `yfinance` + `alpaca-py` installed (already in requirements).
- Local API + web running per the project runbook.

## Local dev loop
```bash
# 1. Backend (FastAPI)
cd trade-analytics/api && python -m uvicorn app.main:app --reload --port 8000

# 2. Frontend
cd trade-analytics/web && npm run dev          # localhost:5173

# 3. Tests (TDD — write/run these first)
cd trade-analytics && python3 -m pytest tests/test_screener.py -v
```

## Manual one-shot (no scheduler) — verify the pipeline
```python
# python3 from trade-analytics/
from analytics.screener import build_universe, rank_in_play, scan_setups, apply_refine_filters

uni = build_universe(market_cap_floor=2_000_000_000, price_floor=5, dollar_vol_floor=20_000_000)
shortlist = rank_in_play(uni, top_n=30)          # uses compute_rvol
shortlist = scan_setups(shortlist)               # reuses signal_engine (read-only)
view = apply_refine_filters(shortlist, preset="momentum_long")
print(len(uni), "universe →", len(view), "in-play")
```

## API smoke test
```bash
TOKEN=...   # a Pro+ user's bearer token
curl -s "localhost:8000/api/v1/screener/in-play?preset=momentum_long&has_setup=true" \
  -H "Authorization: Bearer $TOKEN" | jq '.entries[:3]'
# expect ≤30 entries, ordered by rvol desc, each with rvol/dollar_vol/market_cap and setup|null
```

## E2E checklist
1. Open `localhost:5173` → **Trade Ideas** → **In Play** pill.
2. During RTH: ~30 rows, RVOL chips, setup badges where a pattern fired; timestamp advances.
3. Toggle **Momentum Long** → list narrows to above-50-EMA longs; switch to **Short** → short setups appear.
4. Toggle **Has setup** → only rows with a detected pattern remain.
5. After close: list frozen + "market closed" label.
6. Force the data source to fail → last snapshot shown with a "stale/delayed" indicator (no crash).
7. Free-tier account → locked teaser, no data.

## Implementation findings (recorded during build)

- **`compute_rvol` was a stub** — the shared `analytics/intraday_data.py::compute_rvol`
  resolves to ~1.0 for every symbol. The screener computes its **own** time-of-day RVOL
  (`relative_volume` + `session_fraction`) to avoid touching alert-adjacent code. The shared
  stub is a separate future cleanup.
- **Setup entry:** `signal_engine.analyze_symbol(hist, symbol)` (read-only, no DB writes) —
  `scan_watchlist` also persists daily plans, so do NOT use it here.
- **None-safe presets:** the live service sets `rs_vs_spy`/`atr_pct` to `None`; preset
  predicates must coerce via `_num()` or the default Momentum Long preset raises `TypeError`.
- **Validated against live data (2026-05-30):** crypto run proved fetch → RVOL → ranking →
  read-only setup scan → serialization; a seeded-DB browser E2E proved auth → Pro gate →
  persisted snapshot → rendered In-Play tab. Pending Monday: the **equities-only** adapters
  (yfinance `EquityQuery` field names, Alpaca most-actives entitlement).
- **Repo baseline note:** `pytest tests/` has ~63 pre-existing failures (swing/tier/premarket
  + a broken `test_score_v2.py`) unrelated to this feature. Screener: 17/17 green.

## Guardrails (Constitution)
- Do **not** modify `analytics/signal_engine.py` or any protected file — reuse read-only.
- Run the full suite (`pytest tests/ -v`) before push; keep the 648+ baseline green.
- Verify on localhost, kill local processes before evaluating production.
- New tables must work on SQLite **and** Postgres (async SQLAlchemy + idempotent migrations).
