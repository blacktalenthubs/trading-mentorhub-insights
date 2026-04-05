# Feature Specification: Interactive Chart Replay

**Status**: Spec Complete — Ready for Implementation
**Created**: 2026-04-05
**Priority**: Medium — high marketing value, education differentiator

---

## Vision

> "See how every pattern plays out — before you trade it live."

Users click any past alert and watch the chart animate candle-by-candle from the alert moment through the outcome. Entry, stop, and target lines are drawn. They see the trade unfold like a sports replay.

---

## User Stories

1. **Learning trader** reads about PDL reclaim in Signal Library → clicks "Watch Example" → sees a real NVDA alert play out: price dips below PDL, reclaims, bounces to T1. Learns what the pattern looks like in motion.

2. **Active trader** reviews their daily alerts → clicks a trade they took → watches the replay to understand what happened after their exit. "I left at T1 but it went to T2 — should I hold runners?"

3. **Marketing** — record replays as GIFs for Twitter/landing page. "Watch how our system caught the SPY double bottom in real time."

---

## Technical Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Alert        │────▶│ OHLCV Fetch  │────▶│ Replay       │
│ (DB record)  │     │ (yfinance)   │     │ Component    │
│ id, symbol,  │     │ 5m bars      │     │ (Lightweight │
│ timestamp,   │     │ ±2 hours     │     │  Charts)     │
│ entry/stop/  │     │ around alert │     │              │
│ target       │     │              │     │ Animated     │
└──────────────┘     └──────────────┘     └──────────────┘
```

### Data Flow

1. User clicks "Replay" on an alert (dashboard, Signal Library, or trades page)
2. Frontend calls `GET /api/v1/charts/replay/:alert_id`
3. Backend:
   - Loads alert from DB (symbol, timestamp, entry, stop, T1, T2)
   - Fetches OHLCV bars: 1 hour before alert → 2 hours after (5-min interval)
   - Finds the outcome: did T1 hit? T2 hit? Stop hit? Or still open?
   - Returns: `{ alert, bars, outcome, outcome_bar_index }`
4. Frontend renders chart with Lightweight Charts
5. Animation loop:
   - Start with bars up to alert moment
   - Add one candle every 500ms (configurable speed)
   - Entry/stop/target lines are static from the start
   - When outcome bar is reached, flash the result
   - Pause at the end showing final P&L

---

## API Endpoint

```
GET /api/v1/charts/replay/:alert_id

Response:
{
  "alert": {
    "id": 1234,
    "symbol": "NVDA",
    "direction": "BUY",
    "alert_type": "prior_day_low_reclaim",
    "price": 177.50,
    "entry": 177.00,
    "stop": 174.50,
    "target_1": 182.00,
    "target_2": 186.00,
    "score": 85,
    "created_at": "2026-04-03T10:15:00",
    "message": "PDL reclaim with 1.8x volume..."
  },
  "bars": [
    { "timestamp": "2026-04-03T09:15:00", "open": 178.2, "high": 178.5, ... },
    { "timestamp": "2026-04-03T09:20:00", "open": 177.8, ... },
    ...  // ~36 bars (3 hours of 5-min data)
  ],
  "alert_bar_index": 12,     // which bar the alert fired on
  "outcome": "target_1_hit", // or "stop_loss_hit" or "open"
  "outcome_bar_index": 28,   // which bar the outcome occurred
  "outcome_price": 182.15,
  "pnl_per_share": 5.00,
  "pnl_pct": 2.82
}
```

### Data Requirements

- **OHLCV source**: yfinance `interval="5m"` for the alert's session date
- **Window**: 1 hour before alert → 2 hours after (or session end)
- **Caching**: Cache replay data for 24 hours (same alert won't change)
- **Outcome matching**: Look for target_1_hit / stop_loss_hit in alerts table for same symbol + session

---

## Frontend Component: `<ChartReplay />`

```tsx
interface ChartReplayProps {
  alertId: number;
  onClose: () => void;
}
```

### UI Layout

```
┌─────────────────────────────────────────────────────┐
│  NVDA — Prior Day Low Reclaim                    [X]│
│  Score 85 (A) · BUY $177.00                         │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─ - - - - - - - - - - - - - Target $182.00 - ─┐  │
│  │                                   ████         │  │
│  │                              ████ ████         │  │
│  │                         ████ ████ ████         │  │
│  │  ┌─ Entry $177.00 ─────────────────────────┐  │  │
│  │  │           ████                           │  │  │
│  │  │      ████ ████                           │  │  │
│  │  ┌─ Stop $174.50 ──────────────────────────┐  │  │
│  │                                               │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  [◀◀] [▶ Play]  [▶▶]  Speed: [1x] [2x] [5x]       │
│                                                     │
│  ┌─────────────────────────────────────────────┐    │
│  │ 🟢 TARGET 1 HIT — $182.15 (+$5.15, +2.9%)  │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### Animation Logic

```typescript
const [visibleBars, setVisibleBars] = useState(alertBarIndex); // start at alert
const [playing, setPlaying] = useState(false);
const [speed, setSpeed] = useState(1); // 1x, 2x, 5x

useEffect(() => {
  if (!playing || visibleBars >= totalBars) return;
  const timer = setInterval(() => {
    setVisibleBars(prev => {
      const next = prev + 1;
      if (next >= totalBars) { setPlaying(false); return totalBars; }
      // Flash when outcome bar reached
      if (next === outcomeBarIndex) {
        showOutcomeBanner();
      }
      return next;
    });
  }, 500 / speed);
  return () => clearInterval(timer);
}, [playing, speed, visibleBars]);

// Feed bars[0..visibleBars] to Lightweight Charts
chart.series.setData(bars.slice(0, visibleBars));
```

### Controls

| Control | Action |
|---------|--------|
| ▶ Play | Start/pause animation |
| ◀◀ | Jump to alert moment (reset) |
| ▶▶ | Jump to outcome (skip to end) |
| 1x / 2x / 5x | Animation speed |
| Scrubber bar | Drag to any point in time |

---

## Where Replay Appears

### 1. Signal Library Pattern Pages
Each pattern page shows "Watch a real example" with a curated replay:
```
/learn/patterns/prior_day_low_reclaim
  → "Watch Example" button
  → Opens replay modal with a real historical alert
```

### 2. Dashboard — Today's Activity
Each alert in the history section gets a small "▶ Replay" button:
```
ETH-USD  SHORT  consol 15m breakout  01:22 AM  TOOK  [▶]
```

### 3. Trade Analytics — Session Browser
Past session alerts get replay buttons for post-trade review.

### 4. Marketing — GIF Export
Internal tool to record replays as GIFs for:
- Landing page hero section
- Twitter/X posts
- Signal Library examples
- Email campaigns

---

## Implementation Plan

### Backend (1-2 hours)

| File | Change |
|------|--------|
| `api/app/routers/charts.py` | Add `GET /charts/replay/:alert_id` endpoint |
| `api/app/services/replay.py` | Fetch OHLCV window, compute outcome, return structured data |

### Frontend (3-4 hours)

| File | Change |
|------|--------|
| `web/src/components/ChartReplay.tsx` | New component: Lightweight Charts + animation loop + controls |
| `web/src/pages/PatternDetailPage.tsx` | Add "Watch Example" button that opens replay modal |
| `web/src/pages/DashboardPage.tsx` | Add small ▶ button on alert history items |

### Content (30 min)

| Task |
|------|
| Select 1 best example alert per pattern (11 patterns × 1 example each) |
| Store example alert IDs in pattern_content.py |

---

## Edge Cases

- **Alert has no outcome yet** → Show bars up to current time, outcome = "open"
- **Market was closed** (crypto overnight) → Bars may have gaps — handle gracefully
- **Very old alert** → yfinance may not have 5-min data older than 60 days. Cache or pre-fetch.
- **Mobile** → Smaller chart, hide scrubber, keep Play/Skip buttons
- **No OHLCV data** → Show "Replay not available" with static entry/target/stop text

---

## GIF Export (Marketing Tool)

For internal use — not user-facing initially:

```python
# Record replay as GIF using headless browser
# 1. Open replay URL in Puppeteer/Playwright
# 2. Click Play
# 3. Screenshot every 200ms
# 4. Compile frames into GIF
# 5. Upload to CDN for embedding
```

Output: 5-10 second GIF showing the trade unfold. Use in:
- Landing page hero (instead of static mockup)
- Twitter posts ("Watch how we caught the SPY bounce")
- Signal Library examples

---

## Acceptance Criteria

- [ ] User clicks Replay on a past alert → chart animates candle by candle
- [ ] Entry, stop, target lines drawn from the start
- [ ] Outcome banner flashes when target/stop bar is reached
- [ ] Play/Pause/Speed controls work
- [ ] Jump to start / jump to end buttons work
- [ ] Mobile responsive (smaller chart, touch controls)
- [ ] Works on alerts from last 30 days
- [ ] Signal Library pattern pages have "Watch Example" with curated replays
- [ ] Dashboard alert history items have ▶ Replay button

---

## Cost / Performance

- **yfinance fetch**: ~500ms per replay (5m bars for one session)
- **Cache**: 24-hour TTL on replay data — same alert won't re-fetch
- **Chart rendering**: Lightweight Charts handles 200 bars easily
- **Animation**: Pure client-side setInterval — zero server load during playback
- **Storage**: No extra storage needed — data fetched on demand from yfinance

---

## Priority

This is a **Phase 2 feature** — not needed for Monday launch but high-value for:
1. Marketing (GIF exports for social media)
2. Education (see patterns play out)
3. Retention (post-trade review)

Estimated effort: **4-6 hours** total (backend + frontend + content selection)
