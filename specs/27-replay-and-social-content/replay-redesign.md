# Replay Redesign — Cinematic Trade Replay for Demo & Marketing

**Created**: 2026-04-11
**Priority**: High — this is the visual proof that sells the platform

## What's Wrong with Current Replay

1. **Small chart** (320px) — feels like a widget, not a showcase
2. **No story** — candles just build with no context about what's happening
3. **No entry moment** — no visual highlight when the alert fires
4. **No target hit moment** — price hits T1 and nothing happens visually
5. **P&L in sidebar** — should be overlaid on chart, big and visible
6. **No setup context** — viewer doesn't know WHY this trade was taken
7. **No result card** — replay ends and... nothing. Should freeze with outcome

## What Good Looks Like

A 15-second cinematic replay that tells a story:

```
Phase 1: SETUP (3 seconds)
  - Full-screen dark chart, symbol + price prominent
  - Text overlay: "PDL BOUNCE — ETH-USD"
  - Key level lines visible (PDL, VWAP, PDH)
  - Few candles already on chart showing the pullback

Phase 2: APPROACH (4 seconds)  
  - Candles build toward the support level
  - Price approaching PDL line — tension builds
  - Subtle glow/pulse on the PDL line as price gets close

Phase 3: ENTRY (2 seconds)
  - Price touches level — candle bounces
  - Flash highlight: "ENTRY $2235.71 — PDL Support"
  - Entry line appears bold blue
  - Sound effect (optional): subtle click/chime

Phase 4: MOVE (4 seconds)
  - Candles build upward from entry
  - Live P&L counter overlaid on chart: "+$5.20 (+0.2%)"
  - Counter ticks up with each green candle
  - T1 line ahead — price approaching

Phase 5: TARGET HIT (2 seconds)
  - Price reaches T1 line
  - Flash: "TARGET HIT +$11.08 (+0.5%)"
  - Green confetti or glow effect
  - Freeze frame

Phase 6: RESULT CARD (hold)
  - Overlay card on frozen chart:
    ┌─────────────────────────┐
    │  ✅ TARGET 1 HIT         │
    │  ETH-USD  LONG           │
    │  Entry: $2235.71 (PDL)   │
    │  Exit:  $2246.79 (T1)    │
    │  P&L: +$11.08 (+0.5%)   │
    │  Duration: 45 min        │
    │  tradesignalwithai.com   │
    └─────────────────────────┘
```

## Technical Implementation

### Chart Changes

```tsx
// Current: 320px fixed height
height: 320

// New: full container height, minimum 500px
height: Math.max(500, containerRef.current.clientHeight)
```

### Phase System

```tsx
type ReplayPhase = "setup" | "approach" | "entry" | "move" | "target" | "result";

// Calculated from alert_bar_index and outcome_bar_index
const phases = {
  setup: { start: 0, end: alertBarIndex - 5 },        // 5 bars before entry
  approach: { start: alertBarIndex - 5, end: alertBarIndex - 1 },  // approaching level
  entry: { start: alertBarIndex - 1, end: alertBarIndex + 1 },     // entry moment
  move: { start: alertBarIndex + 1, end: outcomeBarIndex - 1 },    // price moving
  target: { start: outcomeBarIndex - 1, end: outcomeBarIndex + 1 }, // target hit
  result: { start: outcomeBarIndex + 1, end: totalBars },           // freeze
};
```

### Text Overlays

```tsx
// Setup phase overlay
{phase === "setup" && (
  <div className="absolute top-8 left-8 z-10">
    <div className="text-3xl font-bold text-white">
      {alert.alert_type.replace(/_/g, " ").toUpperCase()}
    </div>
    <div className="text-xl text-accent mt-1">
      {alert.symbol} — ${alert.price.toFixed(2)}
    </div>
  </div>
)}

// Entry moment overlay
{phase === "entry" && (
  <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10
                  animate-pulse">
    <div className="bg-accent/20 border border-accent rounded-xl px-6 py-3">
      <div className="text-lg font-bold text-accent">
        ENTRY ${alert.entry?.toFixed(2)}
      </div>
      <div className="text-sm text-accent/80">
        {setupLabel}
      </div>
    </div>
  </div>
)}

// Live P&L overlay (during move phase)
{phase === "move" && (
  <div className="absolute top-4 right-4 z-10">
    <div className={`text-2xl font-mono font-bold ${livePnl >= 0 ? "text-bullish" : "text-bearish"}`}>
      {livePnl >= 0 ? "+" : ""}${livePnl.toFixed(2)} ({livePnlPct >= 0 ? "+" : ""}{livePnlPct.toFixed(2)}%)
    </div>
  </div>
)}

// Target hit celebration
{phase === "target" && (
  <div className="absolute inset-0 z-10 flex items-center justify-center
                  bg-bullish/10 animate-in fade-in">
    <div className="text-center">
      <div className="text-4xl font-bold text-bullish">
        TARGET HIT
      </div>
      <div className="text-2xl font-mono text-bullish mt-2">
        +${Math.abs(pnl).toFixed(2)} (+{Math.abs(pnlPct).toFixed(2)}%)
      </div>
    </div>
  </div>
)}

// Result card overlay
{phase === "result" && (
  <div className="absolute inset-0 z-10 flex items-center justify-center
                  bg-surface-0/60 backdrop-blur-sm">
    <div className="bg-surface-1 border border-border-subtle rounded-2xl p-8 
                    max-w-sm shadow-2xl">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-2xl">✅</span>
        <span className="text-xl font-bold text-bullish">TARGET 1 HIT</span>
      </div>
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-text-muted">Symbol</span>
          <span className="text-text-primary font-bold">{alert.symbol}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-muted">Direction</span>
          <span className="text-accent font-bold">{alert.direction}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-muted">Entry</span>
          <span className="font-mono">${alert.entry?.toFixed(2)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-muted">Exit</span>
          <span className="font-mono">${outcomePrice?.toFixed(2)}</span>
        </div>
        <div className="flex justify-between border-t border-border-subtle pt-2">
          <span className="text-text-muted">P&L</span>
          <span className="text-bullish font-bold font-mono">
            +${pnl.toFixed(2)} (+{pnlPct.toFixed(2)}%)
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-text-muted">Duration</span>
          <span className="font-mono">{durationStr}</span>
        </div>
      </div>
      <div className="mt-4 pt-3 border-t border-border-subtle text-center">
        <span className="text-xs text-text-faint">tradesignalwithai.com</span>
      </div>
    </div>
  </div>
)}
```

### Controls Bar Redesign

```
┌─────────────────────────────────────────────────┐
│ ⏮  ▶️  ⏭  ──────────────●──── 1x 2x 5x  🔗 ⛶ │
│ ETH-USD  PDL Bounce  Score: 85  45 min ago      │
└─────────────────────────────────────────────────┘
```

- Centered play controls
- Progress bar with scrubbing
- Speed controls (1x, 2x, 5x)
- Share link + fullscreen buttons
- Alert metadata below controls

### Setup Label Mapping

```tsx
const SETUP_LABELS: Record<string, string> = {
  session_low_double_bottom: "Session Low Double Bottom",
  prior_day_low_bounce: "Prior Day Low Bounce",
  prior_day_low_reclaim: "Prior Day Low Reclaim",
  vwap_reclaim: "VWAP Reclaim",
  vwap_bounce: "VWAP Bounce",
  ma_bounce_50: "50 MA Bounce",
  ma_bounce_200: "200 MA Bounce",
  prior_day_high_breakout: "PDH Breakout",
  session_high_double_top: "Session High Double Top",
  pdh_failed_breakout: "PDH Failed Breakout",
  ai_scan_long: "AI Scan — Long",
  ai_scan_short: "AI Scan — Short",
};
```

### Stopped Out Variant

Same phases but:
- Phase 5: "STOPPED OUT" in red instead of "TARGET HIT" in green
- Result card shows red styling with loss amount
- Still valuable content: "Even stops are managed — $1.35 risk vs $4 target"

## Files to Modify

| File | Changes |
|------|---------|
| `web/src/components/ChartReplay.tsx` | Full rewrite — phases, overlays, larger chart, result card |
| `web/src/pages/ReplayPage.tsx` | Update to use new ChartReplay |
| `api/app/services/replay.py` | Add setup_label to replay data response |

## What NOT to Change

- Backend replay data API — works fine
- Alert outcome matching logic — works fine
- AI replay analysis — works fine
- URL structure (`/replay/:alertId`) — keep same

## Success Criteria

- [ ] Replay fills available space (min 500px height)
- [ ] Setup name shown prominently at start
- [ ] Entry moment has visual highlight
- [ ] Target hit has celebration effect
- [ ] Result card overlay with full trade details
- [ ] Live P&L counter visible during candle animation
- [ ] Stopped out variant works with red styling
- [ ] Share link copies URL
- [ ] Works on mobile (responsive)
- [ ] Someone seeing the replay for 15 seconds understands: what, where, when, result
