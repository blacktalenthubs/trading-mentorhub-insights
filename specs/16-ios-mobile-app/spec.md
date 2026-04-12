# Feature Specification: TradeCoPilot iOS Mobile App

**Status**: Draft
**Created**: 2026-04-07
**Author**: AI-assisted

## Overview

Build a native iOS mobile app for TradeCoPilot that delivers real-time trading alerts, AI coaching, and portfolio management directly on iPhone. The app wraps the existing web platform's core features into a mobile-native experience optimized for speed — because traders need to act on alerts within seconds, not minutes.

## Problem Statement

TradeCoPilot currently delivers alerts via Telegram DMs and a web dashboard. While functional, this creates friction:

1. **Telegram is a workaround, not a product** — alerts land in a chat app mixed with personal messages. No portfolio view, no chart context, no trade management.
2. **Web dashboard requires a laptop** — traders on the go (commute, lunch, gym) can't quickly act on alerts. Mobile web is usable but not optimized for speed.
3. **No push notifications** — Telegram notifications work but look generic. Native push with rich previews (symbol, direction, price) lets traders triage alerts without opening the app.
4. **Retention and credibility** — an App Store presence signals legitimacy. Subscription apps on iOS have higher retention than web-only products. Apple's payment infrastructure handles billing seamlessly.

**Who is affected**: All TradeCoPilot users (Pro and Premium tiers), especially active day traders who need sub-10-second alert-to-action time.

## Functional Requirements

### FR-1: Push Notification Alerts
- Users receive native iOS push notifications for every trading alert (BUY, SELL, SHORT, NOTICE)
- Each notification displays: symbol, direction, price, and alert type in the notification preview
- Tapping a notification opens the app directly to that symbol's chart
- Users can configure which alert types trigger push notifications
- Acceptance: Alert fires on server → push arrives on phone within 5 seconds → tap opens correct symbol

### FR-2: Alert Feed with Trade Actions
- Scrollable feed of today's alerts, identical to the web Signal Feed
- Each alert shows: time, symbol, direction badge, alert type, entry/stop/target levels, AI narrative
- Inline action buttons: "Took It" / "Skip" (same as Telegram buttons)
- Tapping "Took It" opens a trade and tracks P&L
- Acceptance: All alerts from web dashboard appear in mobile feed with action buttons functional

### FR-3: Watchlist with Live Prices
- User's watchlist symbols displayed with live prices (polling every 15 seconds)
- Each symbol shows: price, change %, tradeability score badge, grade
- Tapping a symbol shows the chart and AI coach
- Add/remove symbols from watchlist
- Acceptance: Watchlist matches web dashboard, prices update every 15 seconds

### FR-4: Chart Viewer
- Interactive candlestick chart for any watchlist symbol
- Timeframe selector: 1m, 5m, 15m, 30m, 1H, 4H, D, W
- Overlay toggles: EMA 5/20/100/200, SMA 20/50/200, VWAP
- Support/resistance levels and entry/stop/target labels displayed
- Pinch to zoom, swipe to scroll
- Acceptance: Chart renders within 2 seconds, supports all timeframes, overlays match web

### FR-5: AI Trade Coach
- Chat interface to ask the AI coach about any symbol
- Same streaming responses as web (CHART READ, DAY TRADE, SWING TRADE, VERDICT)
- Quick-ask buttons: "Entry", "Stop", "Bias" (pre-built prompts)
- Conversation persists within session
- Acceptance: Coach responds with structured analysis, streaming text appears within 3 seconds

### FR-6: Open Positions & P&L
- View all open day trades and swing trades
- Each position shows: symbol, entry, current price, P&L ($ and %), stop, target
- Close/exit trade with current price
- Daily P&L summary at top
- Acceptance: Positions match web dashboard, P&L updates with live prices

### FR-7: Authentication
- Login with email/password (existing accounts)
- Biometric unlock (Face ID / Touch ID) after initial login
- Session persists with secure token storage
- Acceptance: Users log in with existing credentials, biometric re-auth works after app restart

### FR-8: Subscription Management
- Display current plan (Free trial, Pro, Premium) and days remaining
- Upgrade/downgrade via in-app purchase (Apple Pay)
- Acceptance: Users can view plan status and upgrade without leaving the app

## Non-Functional Requirements

### Performance
- App cold start to alert feed: under 3 seconds
- Push notification delivery: under 5 seconds from alert firing
- Chart render time: under 2 seconds for any timeframe
- Live price updates: every 15 seconds without battery drain

### Reliability
- App functions with intermittent connectivity (cached last-known prices, queued actions)
- Graceful degradation when API is unreachable (show cached data, retry indicator)
- No data loss on trade actions (Took It / Exit queued and retried if offline)

### Security
- Authentication tokens stored in iOS Keychain
- Biometric gating for trade actions (optional, user-configurable)
- No sensitive data in push notification payloads (use silent push + local fetch)

## User Scenarios

### Scenario 1: Alert to Trade in Under 10 Seconds
**Actor**: Pro subscriber, on their phone
**Trigger**: AAPL BUY alert fires during market hours
**Steps**:
1. Push notification appears: "AAPL BUY $258.86 — MA Bounce 20"
2. User taps notification
3. App opens to AAPL chart with entry/stop/target labels visible
4. User taps "Took It"
5. Trade is recorded, P&L tracking begins
**Expected Outcome**: From notification to trade acknowledgment in under 10 seconds

### Scenario 2: Morning Watchlist Check
**Actor**: Pro subscriber, before market open
**Trigger**: User opens app at 9:15 AM
**Steps**:
1. Sees watchlist ranked by tradeability score
2. Taps top-ranked symbol (NVDA, score 82)
3. Views daily chart with key levels
4. Asks AI coach "What's the best entry here?"
5. Gets structured response with day trade and swing trade levels
**Expected Outcome**: User has a trade plan before market opens

### Scenario 3: Managing Open Positions
**Actor**: Premium subscriber with 3 open trades
**Trigger**: Mid-day portfolio check
**Steps**:
1. Opens Positions tab
2. Sees all 3 trades with live P&L
3. One trade hit T1 — taps to see details
4. Decides to exit — taps "Close Trade"
5. Enters exit price, trade closes with final P&L
**Expected Outcome**: Position managed without opening laptop

### Scenario 4: Offline Resilience
**Actor**: User on subway with spotty connection
**Trigger**: App opened with no internet
**Steps**:
1. App shows cached watchlist with last-known prices (grayed timestamp)
2. User taps "Took It" on a cached alert
3. Action queued with "Pending sync" indicator
4. Connection restored — action syncs automatically
**Expected Outcome**: No data loss, actions complete when online

## Key Entities

| Entity       | Description                      | Key Fields                                                          |
| ------------ | -------------------------------- | ------------------------------------------------------------------- |
| Alert        | Trading signal from the system   | symbol, direction, alert_type, price, entry, stop, target, score    |
| Trade        | User's acknowledged position     | symbol, direction, entry_price, exit_price, pnl, status             |
| Watchlist    | User's tracked symbols           | symbol, tradeability_score, grade, live_price                       |
| User Session | Authentication state             | token, biometric_enabled, tier, trial_days_remaining                |
| Device       | Push notification registration   | device_token, user_id, notification_preferences                     |

## Success Criteria

- [ ] 80% of alerts result in push notification delivery within 5 seconds
- [ ] Users can go from notification tap to trade action in under 10 seconds
- [ ] App maintains 4.5+ star rating on App Store after 100 reviews
- [ ] 60% of Pro/Premium users adopt the mobile app within 30 days of launch
- [ ] Day 30 retention rate for mobile users exceeds 50%
- [ ] Trade action completion rate (Took It / Skip) increases by 30% vs Telegram-only
- [ ] App crashes fewer than 1% of sessions
- [ ] Subscription conversion rate via in-app purchase matches or exceeds web

## Edge Cases

- User has Free trial expired — show upgrade prompt, don't block app access entirely (let them see delayed alerts)
- Multiple devices logged in — push notifications go to all devices, trade actions sync across all
- Alert fires while user is in the AI coach chat — notification banner appears without interrupting chat
- User loses connection mid-trade-close — action queued, retried on reconnect, user notified of pending state
- App backgrounded for hours — on foreground, refresh all data silently before showing stale content

## Assumptions

- The existing FastAPI backend serves all data the mobile app needs (alerts, trades, watchlist, charts, AI coach) — no new backend services required
- Apple Developer Program enrollment ($99/year) will be obtained before development starts
- Push notification infrastructure will use Apple Push Notification Service (APNs) — the backend already has a device_tokens table
- In-app purchases will use Apple's StoreKit for subscription billing, potentially alongside existing Square billing
- Chart rendering will use a mobile-optimized charting library
- The app targets iOS 16+ (covers 95%+ of active iPhones)
- Initial launch focuses on iPhone only (iPad optimization is a follow-up)

## Constraints

- Apple requires 30% revenue share on in-app subscriptions (first year: 15% for Small Business Program if revenue under $1M)
- App Store review process takes 1-3 days per submission — plan releases accordingly
- Push notifications require user permission — must prompt at the right moment (after first alert, not on first launch)
- Biometric data never leaves the device — only unlock status is shared with the app

## Scope

### In Scope
- Native iOS app with all features listed above
- Push notification infrastructure (APNs integration)
- In-app purchase for subscription management
- Biometric authentication
- Offline caching and sync
- App Store listing and submission

### Out of Scope
- Android app (separate future initiative)
- iPad-optimized layout (iPhone-first, iPad works but not optimized)
- Apple Watch companion app (future enhancement)
- Social features (chat between traders, shared watchlists)
- Options trading interface (focus on equity and crypto alerts)
- Home screen widget (future enhancement, high value)

## Clarifications

_Added during `/speckit.clarify` sessions_

[NEEDS CLARIFICATION: Should the iOS app be built as a native Swift/SwiftUI app, or as a React Native wrapper around the existing web app? Native gives better performance and App Store approval odds, but React Native shares code with the web frontend and ships faster. This significantly impacts timeline and team skills needed.]

[NEEDS CLARIFICATION: Should in-app subscriptions replace Square billing entirely for mobile users, or run in parallel? Apple requires in-app purchase for digital subscriptions accessed within the app, but you could offer web-only billing at lower cost (no Apple 30% cut). This impacts revenue by 15-30%.]
