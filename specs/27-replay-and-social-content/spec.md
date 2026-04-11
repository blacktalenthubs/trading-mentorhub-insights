# Feature Specification: Trade Replay & Social Content Engine

**Status**: Draft
**Created**: 2026-04-11
**Author**: Claude (via /speckit.specify)
**Priority**: High — replay is the proof, social content is the marketing

## Vision

> "Show, don't tell. Every good trade becomes a shareable proof point."

Users trust platforms that show results. Not just win rate numbers — animated replays of real trades hitting targets, AI scan predictions that came true, and visual scorecards that prove the system works. This content serves two purposes: user confidence and viral marketing.

## Problem Statement

The system fires alerts, tracks wins/losses, and has a replay mechanism — but:

1. **Replay is hidden**: Chart replay exists (`/replay/:alertId`) but users rarely find it. No automatic replay generation for good trades.
2. **No visual proof**: Win rate is a number (75%). A 10-second video of price bouncing off PDL and hitting T1 is proof.
3. **No shareable content**: Users can copy a replay link, but there's no stats card, no GIF, no image optimized for Twitter/Instagram.
4. **No automated content**: After a great week (80% win rate), nobody generates a "This Week's Results" card automatically.
5. **AI scan has no track record yet**: We need to build proof that AI scans catch setups rules miss.

## Current State

| Feature | Status | Gap |
|---------|--------|-----|
| Chart replay (animated candles) | Built | Hidden, no auto-generation |
| Win rate tracking | Built | Numbers only, no visual cards |
| Public track record API | Built | Used on landing page, not shareable |
| Trade journal | Built | Text-only, not visual |
| AI trade review | Built | Text in Telegram, not shareable |
| EOD/weekly review | Built | Telegram text, not visual |
| Share link | Built | Just a URL, no preview card |
| Social media posting | Not built | — |
| GIF/video export | Not built | — |
| Stats card generation | Not built | — |

## Functional Requirements

### FR-1: Auto-Generate Replay for Every Winning Trade
- When a trade hits T1 or T2, automatically generate a replay
- Store replay metadata: alert_id, symbol, entry, exit, P&L, duration, outcome
- Make replay accessible at `/replay/:alertId` (already exists)
- Acceptance: Every winning trade has a replay ready to view within 5 min of T1/T2 hit

### FR-2: Visual Stats Card (Image)
- Generate shareable image cards for:
  - **Daily scorecard**: "Today: 6W/2L, 75% win rate, +$420 P&L" with mini chart thumbnails
  - **Weekly edge report**: "This Week: 80% WR, Best setup: PDL Bounce (5/5), AI scan accuracy: 85%"
  - **Single trade**: "LONG ETH-USD at $2235 PDL → T1 hit at $2246 (+0.5%)" with entry/exit on chart
  - **AI vs Rules comparison**: "AI Scan caught META bounce, Rules missed it"
- Card dimensions: 1200x675 (Twitter/LinkedIn) + 1080x1080 (Instagram)
- Dark theme matching platform branding
- Acceptance: Cards generated on-demand via API and automatically after EOD/weekly review

### FR-3: Animated Replay GIF/Video
- Convert chart replay into 10-15 second GIF or MP4
- Shows: candles building, entry line, price hitting target, P&L counter
- Watermark with platform logo + URL
- Acceptance: GIF generated for top 3 trades each day (highest R:R)

### FR-4: Social Content Templates
- Pre-built templates that auto-fill with real data:

**Template 1: Win Streak**
```
🔥 5 wins in a row
PDL bounce → T1 hit (+0.4%)
VWAP reclaim → T2 hit (+0.8%)
Session low bounce → T1 hit (+0.3%)
...
Track record: tradesignalwithai.com/track-record
```

**Template 2: AI vs Rules**
```
📊 AI Scan caught what rules missed
META dropped to $595 support — AI said BUY at $595
Rules: 0 alerts (gates suppressed)
AI Scan: LONG at $595, T1 $615 ✅ HIT
See the replay: [link]
```

**Template 3: Weekly Stats Card**
```
📈 Week of April 7-11
Signals: 45 fired, 34 won (76% WR)
Best setup: Session Low Bounce (8/8, 100%)
AI Scan accuracy: 85%
Top winner: ETH +3.5% from PDL
```

**Template 4: Live Alert Proof**
```
🎯 Called it.
AI SCAN at 10:05 AM: "LONG SPY at $673 — 50MA support"
Result: T1 hit at $677 (+0.6%)
Replay: [link]
```

### FR-5: Automated Content Pipeline
- **After each trading day**: Generate daily scorecard image + top 3 trade replays
- **After each week (Friday EOD)**: Generate weekly edge report card
- **On every T1/T2 hit**: Generate single trade card
- **Store generated content**: In DB or file storage, ready for manual posting
- Acceptance: Content queue with ready-to-post items available in dashboard

### FR-6: Content Gallery Page
- New page: `/content` or section in dashboard
- Shows all generated content (cards, replays, stats)
- One-click copy for text templates
- Download button for images
- Share buttons (copy link, open in Twitter)
- Filter by: date, type (scorecard, trade, weekly), symbol
- Acceptance: Users/admins can browse and download all marketing content

### FR-7: Public Track Record Page (Enhanced)
- Enhanced `/track-record` page showing:
  - Rolling 30-day win rate with trend chart
  - Best performing setups (table)
  - AI Scan vs Rules comparison
  - Recent winning trades with mini replay previews
  - Animated counter: "X signals, Y wins, Z% accuracy"
- No auth required — this is the marketing proof page
- Acceptance: Visitors see live, impressive, verifiable performance data

## Content Generation Architecture

```
┌──────────────────┐     ┌──────────────────┐
│ Trade Outcomes    │     │ AI Scan Results  │
│ (T1 hit, T2 hit) │     │ (predictions)    │
└────────┬─────────┘     └────────┬─────────┘
         │                        │
         └──────────┬─────────────┘
                    │
         ┌──────────▼──────────┐
         │ Content Generator   │
         │                     │
         │ - Stats cards       │
         │ - Trade cards       │
         │ - Weekly reports    │
         │ - Replay GIFs      │
         │ - Social templates  │
         └──────────┬──────────┘
                    │
         ┌──────────▼──────────┐
         │ Content Queue       │
         │ (DB: content_items) │
         └──────────┬──────────┘
                    │
         ┌──────────┼──────────────┐
         │          │              │
    ┌────▼───┐ ┌───▼────┐   ┌────▼─────┐
    │Gallery │ │Download│   │Social API│
    │Page    │ │/Export │   │(future)  │
    └────────┘ └────────┘   └──────────┘
```

## Image Generation Approach

Option A: **HTML-to-Image** (recommended for MVP)
- Build card as HTML/CSS component
- Use Puppeteer or html2canvas to render as PNG
- Fast, fully customizable, matches platform theme
- No external service needed

Option B: **Canvas API** (frontend only)
- Draw cards using HTML5 Canvas in the browser
- User clicks "Generate Card" → downloads PNG
- No server-side rendering needed
- Limited styling compared to HTML

Option C: **AI Image Generation** (future)
- Use AI to generate custom chart art / infographics
- More creative but slower and expensive

**Recommendation**: Option A for server-side automated cards, Option B for on-demand user downloads.

## Data Needed per Content Type

### Daily Scorecard
```python
{
    "date": "2026-04-11",
    "wins": 6, "losses": 2,
    "win_rate": 75.0,
    "total_pnl": 420.50,
    "best_trade": {"symbol": "ETH-USD", "pnl_pct": 3.5, "setup": "PDL Bounce"},
    "worst_trade": {"symbol": "SPY", "pnl_pct": -0.3, "setup": "PDH Breakout"},
    "ai_scan_accuracy": 85.0,
    "top_setups": [{"name": "Session Low Bounce", "wins": 3, "total": 3}],
}
```

### Single Trade Card
```python
{
    "symbol": "ETH-USD",
    "direction": "LONG",
    "entry": 2235.71,
    "exit": 2246.79,
    "pnl_pct": 0.5,
    "pnl_r": 2.1,
    "setup": "Session Low Double Bottom",
    "source": "rule" | "ai_scan",
    "duration_min": 45,
    "replay_url": "/replay/12345",
}
```

### AI vs Rules Comparison
```python
{
    "period": "2026-04-11",
    "rules_fired": 12, "rules_wins": 8,
    "ai_fired": 6, "ai_wins": 5,
    "rules_only_catches": 3,  # setups only rules caught
    "ai_only_catches": 2,     # setups only AI caught
    "both_agreed": 4,         # both caught same setup
    "example": {
        "symbol": "META",
        "ai_caught": True, "rules_caught": False,
        "entry": 595, "exit": 630, "pnl_pct": 5.9,
    }
}
```

## Success Metrics

- [ ] Every winning trade has a replay generated within 5 min
- [ ] Daily scorecard generated automatically after market close
- [ ] Weekly edge report card generated every Friday
- [ ] Content gallery page with 50+ items after 2 weeks
- [ ] Public track record page shows live data with trend chart
- [ ] At least 3 shareable content items per trading day
- [ ] AI vs Rules comparison data available after 1 week

## Scope

### In Scope (Phase 1 — MVP)
- Auto-generate replay metadata on T1/T2 hit
- HTML-to-image stats card generation (daily + weekly)
- Single trade card generation
- Content gallery page in dashboard
- Enhanced public track record page
- Text templates for social media (copy-paste)

### In Scope (Phase 2)
- GIF/MP4 replay export
- AI vs Rules comparison cards
- Automated content pipeline (EOD generation)
- Instagram-optimized square cards

### Out of Scope
- Direct social media posting (API integration with Twitter/Instagram)
- AI-generated custom artwork
- Video editing / production
- Paid ad content generation
- Email newsletter content

## Edge Cases

- **No winning trades today**: Don't generate scorecard (or show "Flat day — 0 trades taken")
- **AI scan has no data yet**: Show "Coming soon — collecting data" on comparison cards
- **User didn't "Took" any alerts**: Scorecard shows system performance, not user performance
- **Replay data unavailable**: OHLCV gaps → show static chart screenshot instead of animation

## Assumptions

- Puppeteer or html2canvas available on Railway for server-side rendering
- Content stored in DB (content_items table) or Railway volume
- Public track record page is the primary marketing asset
- Users will manually post to social media initially (no auto-posting)

## Constraints

- Image generation must complete in <10 seconds
- Generated images must be <2MB (social media upload limits)
- No user PII in shareable content (no names, no account balances)
- All content labeled "Educational — not financial advice"

## Clarifications

_To be added during /speckit.clarify sessions._
