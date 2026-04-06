# Spec 15 — Real-Time Price Feed via WebSocket

## Problem Statement

**What:** Watchlist prices are stale — update only every 3 minutes when the scanner polls. TradingView shows live prices; our platform shows prices from the last scan. Creates a perception of a "dead" platform.

**Why:** Real-time prices are table stakes for a trading platform. Users compare us to TradingView and see stale data. This erodes trust — if prices are old, are alerts old too?

**What success looks like:**
- Watchlist sidebar prices update every 1-2 seconds
- Chart auto-refreshes with new candles
- Price changes animate (green flash up, red flash down)
- No page refresh needed

---

## Current State

| Component | Update Frequency | Source |
|-----------|-----------------|--------|
| Watchlist prices | Every 3 min (scanner poll) | yfinance via `/api/v1/scanner/scan` |
| Chart candles | On symbol click (one-time fetch) | yfinance via `/api/v1/charts/intraday` |
| Alert feed | Real-time via SSE | Monitor push via alert_bus |

## Options Evaluated

### Option A: yfinance Polling (Faster)
- Reduce scanner interval from 3 min to 30 sec
- **Pros:** No new infrastructure, just faster polling
- **Cons:** yfinance rate limits (20 req/min), CPU-heavy, still not real-time
- **Verdict:** Marginal improvement, doesn't solve the perception issue

### Option B: WebSocket Data Provider
- Use a real-time market data WebSocket (Polygon.io, Alpaca, Finnhub)
- Server receives live ticks, pushes to frontend via SSE/WebSocket
- **Pros:** True real-time, sub-second updates, professional feel
- **Cons:** Monthly cost ($29-299/mo), new dependency
- **Verdict:** Best long-term solution, adds real cost

### Option C: Frontend Polling (Quick Win)
- Frontend polls a lightweight `/api/v1/market/prices` endpoint every 5 sec
- Endpoint returns latest prices from a cache (updated by scanner)
- **Pros:** Fast to implement, no new infrastructure
- **Cons:** Still 3-min data, just fetched more often. Marginal improvement.
- **Verdict:** Quick band-aid, not a real fix

### Option D: Hybrid — yfinance WebSocket + SSE Push
- Backend uses `yfinance` rapid quotes (not full OHLCV) every 10 sec
- Push price updates to frontend via existing SSE infrastructure
- **Pros:** No new provider cost, near-real-time (10 sec delay)
- **Cons:** yfinance rate limits, may get throttled with many symbols
- **Verdict:** Best cost-effective middle ground

---

## Recommended: Option D (Hybrid) → Option B (Scale)

### Phase 1: Quick Win — Rapid Quote Polling (This Week)

**Backend: New price feed service**
```python
# api/app/background/price_feed.py
# Runs every 10 seconds via APScheduler
# Fetches latest quotes for all watchlist symbols via yfinance .fast_info
# Pushes price updates through SSE to connected frontends
```

**How yfinance rapid quotes work:**
```python
import yfinance as yf
# Fast quote — no OHLCV history, just current price
ticker = yf.Ticker("SPY")
price = ticker.fast_info.last_price  # ~200ms per symbol
```

**Flow:**
```
Every 10 sec:
  1. Get union of all user watchlist symbols (cached)
  2. Batch fetch fast_info for all symbols
  3. Push price dict via SSE to all connected frontends
  4. Frontend updates watchlist sidebar + chart last price
```

**New SSE endpoint:**
```
GET /api/v1/market/price-stream
→ SSE events: {"event": "prices", "data": {"SPY": 655.90, "NVDA": 177.50, ...}}
```

**Frontend changes:**
- Connect to price-stream SSE on app load
- Update watchlist prices on each event
- Flash green/red on price change
- Update chart's last price marker

### Phase 2: Professional Data Feed (When Revenue Supports)

**Provider options:**

| Provider | Cost | Features |
|----------|------|----------|
| **Polygon.io** | $29/mo (Starter) | REST + WebSocket, 15-min delayed free tier |
| **Alpaca** | Free (paper), $99/mo (live) | WebSocket, real-time equities |
| **Finnhub** | Free (limited), $49/mo | WebSocket, US stocks + crypto |
| **Twelve Data** | $29/mo (Basic) | WebSocket, 8 symbols real-time |

**Recommended:** Alpaca (free for paper trading data, $99/mo for live)
- Already in our tech stack (Alpaca paper trade sync planned)
- WebSocket API well-documented
- Real-time equities + crypto

---

## Phase 1 Implementation Plan

### Files to Create
| File | Purpose |
|------|---------|
| `api/app/background/price_feed.py` | 10-sec price polling + SSE push |
| `web/src/hooks/usePriceStream.ts` | SSE client hook for live prices |

### Files to Modify
| File | Change |
|------|--------|
| `api/app/main.py` | Add price_feed scheduler job (10 sec) |
| `api/app/routers/market.py` | Add `/price-stream` SSE endpoint |
| `web/src/components/WatchlistBar.tsx` | Consume live prices, flash animation |
| `web/src/components/CandlestickChart.tsx` | Update last price marker |

### Backend: Price Feed Service
```python
# api/app/background/price_feed.py

import yfinance as yf
from app.background.alert_bus import broadcast_prices

_price_cache: dict[str, float] = {}

def poll_prices(symbols: list[str]) -> dict[str, float]:
    """Fetch latest prices for all symbols. ~200ms per symbol."""
    prices = {}
    for sym in symbols:
        try:
            t = yf.Ticker(sym)
            prices[sym] = round(t.fast_info.last_price, 2)
        except Exception:
            pass
    _price_cache.update(prices)
    return prices

def get_cached_prices() -> dict[str, float]:
    return dict(_price_cache)
```

### Frontend: Price Stream Hook
```typescript
// web/src/hooks/usePriceStream.ts
export function usePriceStream() {
  const [prices, setPrices] = useState<Record<string, number>>({});
  
  useEffect(() => {
    const es = new EventSource("/api/v1/market/price-stream");
    es.addEventListener("prices", (e) => {
      setPrices(JSON.parse(e.data));
    });
    return () => es.close();
  }, []);
  
  return prices;
}
```

### Watchlist Price Animation
```css
/* Flash green on price up, red on price down */
.price-up { animation: flash-green 0.3s; }
.price-down { animation: flash-red 0.3s; }

@keyframes flash-green {
  0% { background: rgba(34, 197, 94, 0.3); }
  100% { background: transparent; }
}
```

---

## Rate Limit Considerations

**yfinance fast_info:**
- ~200ms per symbol
- 10 symbols × every 10 sec = 1 req/sec (well within limits)
- 25 symbols × every 10 sec = 2.5 req/sec (still OK)
- 50+ symbols = need batching or slower interval (15-20 sec)

**At scale (100+ users):**
- Symbols are deduped (same symbol across users = one fetch)
- Typical: 30-50 unique symbols across all users
- 50 symbols × 200ms = 10 sec total fetch time (matches interval)
- Beyond 50 unique symbols: increase interval to 15-20 sec

---

## Success Metrics

| Metric | Before | After |
|--------|--------|-------|
| Price staleness | 3 min | 10 sec |
| User perception | "Prices are old" | "Prices are live" |
| Price change visibility | None (static numbers) | Green/red flash |
| Infra cost | $0 | $0 (Phase 1) / $99/mo (Phase 2) |

---

## Out of Scope (Phase 1)
- WebSocket provider integration (Phase 2)
- Real-time candle updates on chart (requires streaming OHLCV)
- Options chain live data
- Pre/post market price feed
- Level 2 / order book data
