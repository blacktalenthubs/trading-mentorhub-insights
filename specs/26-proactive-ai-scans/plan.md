# Implementation Plan: AI-Powered Alert Engine (Spec 26)

**Spec**: [spec.md](spec.md)
**Created**: 2026-04-10
**Approach**: Incremental — ship MVP in Phase 1, iterate from live data

## Problem → Solution Flow

```
User's watchlist symbols
        │
        ▼
┌──────────────────┐
│ ai_scan_cycle()  │  ← APScheduler job, every 30 min
│                  │
│ For each symbol: │
│  1. Fetch bars   │  ← yfinance 5m + 1H (reuse existing fetch)
│  2. Fetch levels │  ← fetch_prior_day() (PDH/PDL/MAs/VWAP)
│  3. Build prompt │  ← same as Coach, minus user-specific data
│  4. Call Claude   │  ← Haiku (fast, cheap, cached)
│  5. Parse output │  ← CHART READ + ACTION block
│  6. Record alert │  ← alerts table, type = ai_scan_*
│  7. Notify       │  ← Telegram + Signal Feed
└──────────────────┘
```

## Codebase Analysis

### What Exists (Reuse)
| Component | File | What It Does | Reuse How |
|-----------|------|-------------|-----------|
| Coach prompt | `analytics/trade_coach.py:format_system_prompt()` | Builds context with MAs, RSI, key levels | Strip user-specific sections, use market data only |
| Coach API call | `analytics/trade_coach.py:ask_coach()` | Streams Claude response | Use non-streaming version for batch scans |
| OHLCV fetch | `analytics/intraday_data.py:fetch_intraday()` | Gets bars from yfinance | Call directly per symbol |
| Prior day data | `analytics/intraday_data.py:fetch_prior_day()` | PDH, PDL, MAs, VWAP | Call directly per symbol |
| Symbol technicals | `analytics/trade_coach.py:_get_symbol_technicals()` | Bulk MA + RSI fetch | Call once for all watchlist symbols |
| Alert recording | `api/app/background/monitor.py` | Writes to alerts table | Use same Alert model |
| Telegram delivery | `alerting/notifier.py` | Formats and sends Telegram | Add AI scan format |
| APScheduler | `api/app/main.py` | Job scheduling in worker | Add new scheduled job |
| Watchlist query | `api/app/background/monitor.py` | Gets per-user watchlists | Reuse, dedup symbols |

### What's New (Build)
| Component | File | Purpose |
|-----------|------|---------|
| AI scan engine | `analytics/ai_scanner.py` | Core scan logic: fetch → prompt → parse → record |
| AI scan prompt | `analytics/ai_scanner.py` | Stripped-down Coach prompt for batch scanning |
| Output parser | `analytics/ai_scanner.py` | Parse CHART READ + ACTION into structured data |
| Scan scheduler | `api/app/main.py` | APScheduler job for ai_scan_cycle |
| Telegram format | `alerting/notifier.py` | AI SCAN message format |
| Signal Feed badge | `web/src/pages/TradingPageV2.tsx` | Purple "AI SCAN" badge |

## Implementation Phases

### Phase 1: Core Engine (MVP) — Ship First

**Goal**: AI scans run every 30 min, produce alerts, send to Telegram. Minimum viable.

```
┌─────────────────┐     ┌──────────────┐     ┌──────────┐
│ ai_scan_cycle() │────>│ Claude Haiku │────>│ alerts DB│
│ (APScheduler)   │     │ (parse)      │     │ + Telegram│
└─────────────────┘     └──────────────┘     └──────────┘
```

**Files to modify/create**:

| File | Action | Changes |
|------|--------|---------|
| `analytics/ai_scanner.py` | **CREATE** | Core engine: `scan_symbol()`, `parse_ai_response()`, `ai_scan_cycle()` |
| `api/app/main.py` | MODIFY | Add APScheduler job for `ai_scan_cycle` |
| `alerting/notifier.py` | MODIFY | Add AI scan Telegram format |
| `alert_config.py` | MODIFY | Add `AI_SCAN_ENABLED`, `AI_SCAN_INTERVAL_MINUTES` config |

**Key decisions**:
- Non-streaming Claude call (batch, not SSE) — faster for batch processing
- One scan per unique symbol across all users (dedup at symbol level)
- Alert recorded per user (each user who watches the symbol gets the alert)
- Haiku only for MVP — Sonnet upgrade in Phase 2

**ai_scanner.py structure**:
```python
def build_scan_prompt(symbol, bars_5m, bars_1h, prior_day, technicals):
    """Build Coach-style prompt without user-specific data."""
    # Reuse format_system_prompt() structure but stripped down
    pass

def parse_ai_response(response_text):
    """Parse CHART READ + ACTION block into structured dict."""
    # Returns: {direction, entry, stop, t1, t2, conviction, chart_read}
    pass

def scan_symbol(symbol, api_key, model="claude-haiku-4-5-20251001"):
    """Fetch data, call Claude, parse response, return AIScanResult."""
    pass

def ai_scan_cycle(sync_session_factory):
    """Main cycle: get all watchlist symbols, scan each, record alerts."""
    # 1. Query all unique symbols across user watchlists
    # 2. Fetch bars + prior_day for each (batch where possible)
    # 3. For each symbol: scan_symbol() → parse → dedup → record alert
    # 4. Send Telegram notifications
    pass
```

### Phase 2: Signal Feed + Dedup

**Goal**: AI scan alerts visible in web dashboard with purple badge. Smart dedup.

**Files to modify**:

| File | Action | Changes |
|------|--------|---------|
| `web/src/pages/TradingPageV2.tsx` | MODIFY | Purple "AI SCAN" badge for `ai_scan_*` alert types |
| `analytics/ai_scanner.py` | MODIFY | Add dedup: skip if same setup at same level already fired |
| `api/app/routers/alerts.py` | MODIFY | Include `ai_scan_*` types in today's alerts query |

### Phase 3: Cost Optimization

**Goal**: Reduce API costs with caching and skip logic.

| Optimization | Implementation |
|-------------|---------------|
| Prompt caching | `cache_control: {"type": "ephemeral"}` on system prompt |
| Skip unchanged | Track last scan price per symbol, skip if <0.3% change |
| Symbol dedup | Scan once per symbol, distribute alert to all watching users |
| Non-streaming | Use `client.messages.create()` not `.stream()` |

### Phase 4: Comparison Dashboard (Later)

**Goal**: Side-by-side AI vs rules analysis.

- New page or tab showing both alert sources per symbol per day
- Win rate comparison, false signal rate, missed setups
- This is analytics — build after 1 week of data

## Architecture Diagram

```
api/app/main.py
  │
  ├── scheduler.add_job(poll_all_users, ...)     ← existing rule engine
  │
  └── scheduler.add_job(ai_scan_cycle, ...)      ← NEW AI scan engine
                │
                ▼
      analytics/ai_scanner.py
                │
      ┌─────────┼──────────┐
      │         │          │
      ▼         ▼          ▼
  fetch_      fetch_     _get_symbol_
  intraday()  prior_day() technicals()
      │         │          │
      └─────────┼──────────┘
                │
                ▼
        build_scan_prompt()
                │
                ▼
        Claude Haiku API
        (non-streaming)
                │
                ▼
        parse_ai_response()
                │
                ▼
        ┌───────┼───────┐
        │       │       │
        ▼       ▼       ▼
    alerts    Telegram  log
    table     notify    scan
```

## Data Flow

### Input (per symbol)
```
5m bars (last 20)  ─┐
1H bars (last 20)  ─┤
PDH, PDL           ─┤──→ build_scan_prompt() ──→ Claude ──→ parse
MAs (20/50/100/200)─┤
VWAP               ─┤
RSI14              ─┘
```

### Output (per symbol)
```python
{
    "symbol": "SPY",
    "direction": "LONG",        # LONG / SHORT / WAIT
    "entry": 673.50,
    "stop": 671.80,
    "t1": 677.08,
    "t2": 681.00,
    "conviction": "HIGH",       # HIGH / MEDIUM / LOW
    "chart_read": "SPY pulling back to 50MA support at $673",
    "raw_response": "...",      # full AI text for debugging
}
```

### Alert Record
```python
Alert(
    user_id=user_id,
    symbol="SPY",
    alert_type="ai_scan_long",  # ai_scan_long / ai_scan_short / ai_scan_wait
    direction="BUY",
    price=673.50,
    entry=673.50,
    stop=671.80,
    target_1=677.08,
    target_2=681.00,
    score=85,                   # HIGH=85, MEDIUM=65, LOW=45
    confidence="high",
    message="AI: 50MA support bounce — SPY pulling back to 50MA support at $673",
    session_date="2026-04-11",
)
```

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Claude API latency spikes | Scan cycle takes >5 min, overlaps with next | Timeout per symbol (10s). Skip if cycle runs long. |
| AI returns garbage | Bad entries, wrong prices | Validate parsed output: entry > 0, stop > 0, stop < entry for LONG. Discard invalid. |
| Cost overrun | Sonnet at $2.50/day per user | Haiku-only for MVP. Track cost per scan in DB. |
| AI uses current price as entry | Same problem as CoPilot had | Prompt explicitly says "entry must be a key level, not current price" |
| Too many alerts | 10 symbols x 17 scans = 170 alerts/day | Dedup: same setup at same level skips. WAIT alerts don't notify. |
| Worker crash | Scan job dies, no alerts | try/except per symbol. Log errors. Job re-runs on schedule. |

## Testing Strategy

### Unit Tests
- `test_parse_ai_response()` — valid LONG, valid SHORT, WAIT, malformed, missing fields
- `test_build_scan_prompt()` — context includes MAs, PDH/PDL, VWAP, bars
- `test_dedup_logic()` — same setup skips, new setup fires, new level fires

### Integration Tests
- `test_scan_symbol()` — mock Claude API, verify alert record created
- `test_ai_scan_cycle()` — mock watchlists + Claude, verify correct number of alerts

### Live Validation
- Run alongside rules for 1 week
- Compare: did AI catch the META $595 bounce that rules missed?
- Compare: did AI give false signals that rules correctly filtered?

## Timeline

| Phase | Effort | Dependency |
|-------|--------|-----------|
| Phase 1 (MVP) | 1 session | None — build from scratch |
| Phase 2 (Signal Feed) | 30 min | Phase 1 deployed |
| Phase 3 (Cost optimization) | 30 min | Phase 1 running |
| Phase 4 (Comparison) | 1 session | 1 week of data |

**Phase 1 can ship tomorrow** — it's one new file (`ai_scanner.py`), one scheduler job, and one Telegram format addition. Everything else is reuse.
