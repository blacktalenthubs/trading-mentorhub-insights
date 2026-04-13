# Feature Specification: iOS App — Ship via Capacitor

**Status**: Draft
**Created**: 2026-04-12
**Author**: Claude (speckit)
**Priority**: Medium-High — expands distribution beyond web; credibility for launch

## TL;DR

You already have Capacitor scaffolded. Don't rewrite. **Wrap the existing React app as an iOS app, polish it for native feel, ship to the App Store.** Realistic timeline: **4–6 weeks** including Apple review.

## Approach Decision

Four possible paths for iOS. Matrix of what each costs and delivers:

| Approach | Code reuse | Dev time | Native feel | Best for |
|---|---|---|---|---|
| **Capacitor** (chosen) | ~100% of web | 1–2 weeks to ship | 85% native | Solo founder, already scaffolded |
| React Native | ~30% (rewrite UI) | 2–4 months | 95% native | Scale to 100k+ users |
| Native Swift | 0% (full rewrite) | 4–6 months | 100% native | Premium-only product |
| PWA only | 100% | Days | 60% native | No App Store, no push |

**Chosen: Capacitor.** Reasoning:
- You already run `@capacitor/core` and have `web/ios/App/` scaffolded
- React app is the same UI you'd want on iOS — don't fork the codebase
- Apple reviewers accept Capacitor apps (Instagram, LinkedIn used to be Cordova/Capacitor-era wrappers)
- You can switch to React Native or native later if you hit performance walls
- Fastest path to App Store, lowest maintenance cost

## Current State Audit

**What's done:**
- Capacitor config at `web/capacitor.config.ts` (`appId: com.aicopilottrader.app`)
- iOS project generated at `web/ios/App/`
- Splash screen + status bar plugins configured
- Build pipeline exists (`npm run cap:build`, `cap:sync`, `cap:open:ios`)
- `useNativePlatform` hook in React detects Capacitor context

**What's missing (v1 blockers):**
- App Store Connect setup
- Apple Developer account ($99/yr)
- App icon set (1024x1024 + all iOS sizes)
- Launch screen (native, not just web splash)
- Proper bundle version management
- Push notification plumbing (APNs)
- Privacy policy + terms pages (App Store requires)
- App Store metadata (screenshots, description, keywords)
- Review prep (demo account, financial-app disclaimers)

**What's nice-to-have (v2):**
- Biometric auth (Face ID / Touch ID)
- Haptic feedback on alerts
- Native chart rendering for perf
- Widgets (home screen AI signal widget)
- Live Activities (lock screen signal tracking)
- Deep links from Telegram / email to specific alerts
- Share sheet for trade replays

## Problem Statement

Current web distribution limits the user base:
- Can't be found in App Store (discoverability loss)
- No home-screen icon (friction on mobile)
- No push notifications (Telegram compensates, but some users don't use Telegram)
- Looks less "real" to skeptical users ("is this just a web site?")

For launch we need iOS to:
1. Be installable from App Store (credibility + discoverability)
2. Feel native enough that users don't notice it's a web wrapper
3. Receive push notifications natively (even if Telegram is primary)
4. Pass App Store review without rejection

## Goals

1. **Ship to App Store within 6 weeks** including Apple review time
2. Keep 100% feature parity with web (single codebase)
3. Get native push notifications as backup/alternative to Telegram
4. Establish the iOS release pipeline for future updates
5. **Not** invest in expensive native rewrites until proven users demand it

## Non-Goals (v1)

- Android app (separate spec — Capacitor supports it, but one platform at a time)
- Native chart rendering (web chart is good enough)
- Home screen widgets (iOS 14+ WidgetKit — separate spec if we want it)
- Live Activities / Dynamic Island (premium feature, post-launch)
- Offline mode (app is trading-only — requires network anyway)
- Biometric auth (can add later as polish)
- Deep linking from Telegram to in-app (future — ticket it)

## Phased Implementation

### Phase 1 — Native polish + plumbing (~1 week)
Make the Capacitor app feel native without changing functionality.

**Tasks:**
- [ ] App icon set generated (1024x1024 source → all iOS sizes via `cordova-res` or manual)
- [ ] Launch screen with logo (not white flash)
- [ ] Safe-area handling verified on iPhone 14/15 Pro notch + Dynamic Island
- [ ] Status bar style matches dark theme on every page
- [ ] Keyboard avoidance — forms don't cover input when keyboard opens
- [ ] Tap targets all ≥ 44pt (Apple minimum)
- [ ] Pull-to-refresh on dashboard, signal feed, review page
- [ ] Scroll behavior: momentum + rubber-banding feels right
- [ ] External links (`tradingwithai.ai/billing`) open in in-app browser (SFSafariViewController), not kicked out of the app
- [ ] "Back" gesture works consistently across SPA routes
- [ ] Appropriate `<meta viewport>` so iOS Safari webview doesn't zoom on input focus

**Plugins to add:**
- `@capacitor/push-notifications` — APNs integration
- `@capacitor/app` — lifecycle events (background/foreground)
- `@capacitor/haptics` — vibration on alert arrival
- `@capacitor/browser` — open external links in-app browser

**Acceptance:** You can't tell it's a web app by tapping around — no visible scrollbar, no address bar, no web-like flashes.

### Phase 2 — Push notifications (~3 days)
APNs setup so users get native notifications even without Telegram.

**Tasks:**
- [ ] Apple Developer account registered ($99/yr)
- [ ] App ID + APNs key created in Apple Developer portal
- [ ] Capacitor Push Notifications plugin wired up
- [ ] On first login: request push permission → register device token with our backend
- [ ] New `/api/v1/push/register` endpoint stores `(user_id, device_token, platform='ios')`
- [ ] Scanner sends to APNs for users with registered tokens (alongside / instead of Telegram based on user prefs)
- [ ] Handle notification tap → deep link to correct screen (signal detail, dashboard)
- [ ] Badge count updates on new alerts
- [ ] Notification Center grouping (collapse multiple alerts)

**Alternative to native APNs (faster):** use Firebase Cloud Messaging as abstraction layer.

**Acceptance:** New AI signal fires → iPhone lockscreen shows notification within 5 seconds → tap → app opens to the right alert.

### Phase 3 — App Store prep (~1 week, lots of waiting)

**Apple Developer account setup:**
- [ ] Enroll in Apple Developer Program
- [ ] Set up App Store Connect
- [ ] Create app listing under bundle ID `com.aicopilottrader.app`

**Metadata required:**
- [ ] App name: "TradeCoPilot AI" (or shorter — App Store limits to 30 chars)
- [ ] Subtitle (30 chars): e.g., "AI Trading Analyst"
- [ ] Promotional text (170 chars): refreshable without re-review
- [ ] Description (4000 chars): full value prop with disclaimers
- [ ] Keywords (100 chars): "AI trading, day trading, stock alerts, crypto alerts, chart analysis"
- [ ] Primary category: Finance
- [ ] Secondary category: Education (dual positioning helps)
- [ ] Age rating: 17+ (financial content)
- [ ] App icon (1024x1024 PNG, no alpha)
- [ ] Screenshots: minimum 3 per device size (iPhone 6.7" + 6.1" + iPad 12.9")
- [ ] Privacy policy URL: `tradingwithai.ai/privacy`
- [ ] Support URL: `tradingwithai.ai/support` (or same as main site)
- [ ] Marketing URL (optional): `tradingwithai.ai`

**Privacy "Nutrition Label":**
- [ ] Declare data collection: email, usage analytics, Telegram chat ID (contact info)
- [ ] Declare data linked to user: attribution, subscription status
- [ ] Declare third-parties: Square (billing), Telegram Bot API, Anthropic (AI)
- [ ] Clarify: we do NOT sell data; do NOT track across apps

**Required pages (build if missing):**
- [ ] `/privacy` — privacy policy (see risk section)
- [ ] `/terms` — terms of service
- [ ] `/support` — how to contact (email link is fine)

**Demo account:**
- [ ] Create a persistent demo account for App Review team
  - Email: `reviewer@appreview.tradingwithai.ai`
  - Password: documented in App Review Notes
  - Pre-loaded with watchlist + historical alerts so reviewer sees the product working
  - Ideally during market hours for live alerts

**Review notes:**
- [ ] Explain the app: educational AI-powered trading analysis, not a signal service
- [ ] Show where disclaimers appear ("Not financial advice")
- [ ] Explain billing (Square, external to IAP — requires "Reader App" exemption OR App Store IAP integration, see risks)

### Phase 4 — TestFlight beta (~1 week)
Get real users testing before public submission.

**Tasks:**
- [ ] First TestFlight build uploaded via Xcode
- [ ] Internal testing: you + 1-2 friends
- [ ] External testing: invite 5-10 Twitter followers who've expressed interest
- [ ] Collect feedback: crashes, UX issues, perf
- [ ] Fix critical bugs, ship new TestFlight builds
- [ ] Once stable for 3–5 days, submit for App Store review

### Phase 5 — App Store submission + review (~2–4 weeks variable)

**Apple review process:**
- Average first review: 24–48 hrs
- Financial/trading apps often get extra scrutiny — expect 3–7 days first pass
- Possible rejection reasons for this type of app (prep mitigations):
  - "Looks like a signal service" → emphasize educational framing in description
  - "External subscription" → either pivot to IAP OR qualify for Reader App exemption
  - "Missing disclosures" → privacy policy + "Not financial advice" must be obvious
  - "Demo account doesn't show app's value" → ensure demo account has active alerts

**After approval:**
- [ ] Release publicly (manual release recommended so you control the launch timing)
- [ ] Monitor App Store crashes / reviews daily for first month
- [ ] Respond to every review (engagement signal)
- [ ] Plan weekly OTA content updates (Capacitor: update web bundle without App Store resubmission — `@capacitor/live-updates` or similar)

## Billing Compliance Risk (CRITICAL)

**The hardest App Store review hurdle for this app.**

Apple requires in-app purchases (IAP) for digital subscriptions consumed in-app, with Apple taking 15–30% cut. They DO allow "Reader Apps" (Netflix, Spotify, Kindle) to use external billing with exemption — but the app can't direct users to sign up externally.

Our situation:
- Web app has Square billing for Pro/Premium
- If iOS app lets users subscribe via the web flow → Apple may reject

**Three paths forward:**

### Option A: Reader App exemption (recommended to try first)
- Users must sign up on the web, then log in to the iOS app
- iOS app shows subscription status but NO "Upgrade" button / link
- Add disclaimer: "Manage your subscription at tradingwithai.ai"
- Requires Apple to classify us as a Reader App (possible but not guaranteed)

### Option B: Apple IAP
- Implement native iOS subscriptions for Pro ($49) / Premium ($99)
- Apple takes 30% (15% after year one, or 15% in Small Business Program)
- Webhook syncs Apple subscriptions to our backend
- Users who already subscribe via web keep Square; new iOS users get IAP
- **Effort:** 3–5 days of work (StoreKit 2, receipt validation, webhook)

### Option C: Hybrid
- iOS: Apple IAP only (clean compliance)
- Web: Square (cheaper fees)
- If user subscribed via web, they see a "Subscription active on web" badge on iOS — no upgrade button shown
- Complex but maximizes revenue

**Recommendation:** Launch v1 as **Option A (Reader App)**. Submit to Apple. If rejected, fall back to **Option B**. Don't front-load complexity before knowing what Apple accepts.

## Financial App Specific Considerations

Apple treats trading apps with extra scrutiny. Mitigation:

- **Disclaimer in multiple places**: landing page, settings, every alert detail view — "Educational analysis, not financial advice"
- **No "buy" or "sell" recommendations** anywhere in copy — all AI output framed as "AI identified" not "buy this"
- **Transparency**: track record page shows losses
- **Age-gate 17+**
- **Link to terms + privacy policy**: required, must be accessible from app + App Store listing

## Functional Requirements

### FR-1: Native polish
- [ ] App icon generated from 1024x1024 master for all iOS sizes
- [ ] Launch screen storyboard uses app logo on brand background
- [ ] Safe areas respected on all screens (no content under notch or home indicator)
- [ ] External links open in in-app Safari (SFSafariViewController via `@capacitor/browser`)
- [ ] Dark mode correctly reflected in status bar
- Acceptance: submit a TestFlight build, verify on physical device

### FR-2: Push notifications
- [ ] User opts in on first login (or later via Settings)
- [ ] Device token registered with `/api/v1/push/register`
- [ ] Backend sends AI signals to APNs alongside Telegram (user chooses one or both)
- [ ] Tap on notification → deep-link to correct in-app screen
- Acceptance: AI LONG fires → iPhone notification within 5s → tap → app opens to that alert

### FR-3: App Store metadata
- [ ] Complete App Store Connect listing
- [ ] 3+ screenshots per device size
- [ ] Demo account credentials in review notes
- [ ] Privacy + Support URLs work
- Acceptance: Apple review queue accepts the submission

### FR-4: Billing compliance (Option A)
- [ ] iOS app does NOT show "Upgrade" buttons linking to external billing
- [ ] Subscription status visible (badge), not purchase flow
- [ ] Web app retains full Square billing flow
- [ ] Users upgrade on web, log into iOS, see Pro features unlocked
- Acceptance: reviewer can log in to demo Pro account and see app works; can't upgrade from within iOS

### FR-5: Privacy + Terms pages
- [ ] `/privacy` page exists and describes data handling
- [ ] `/terms` page exists with "not financial advice" + risk disclosures
- [ ] Both linked from iOS app Settings
- [ ] Both submitted in App Store Connect privacy questionnaire
- Acceptance: lawyer/counsel review (or use a template like Termly/iubenda initially)

### FR-6: OTA update strategy
- [ ] Define which changes require App Store resubmission vs OTA web bundle update
- [ ] Set up OTA pipeline (copy `web/dist/` to a CDN or use Capacitor Live Updates)
- [ ] Document the release process
- Acceptance: fix a bug in React code → deploy OTA → TestFlight users get it without re-downloading from App Store

## Timeline (Realistic)

| Week | Phase | Deliverable |
|---|---|---|
| 1 | Phase 1 | Native polish, app icon, launch screen, safe areas |
| 2 | Phase 2 | Push notifications working on TestFlight |
| 3 | Phase 3 | App Store Connect setup, metadata written, screenshots captured |
| 4 | Phase 4 | TestFlight beta with 5-10 external testers |
| 5 | Phase 5 | Submit to App Store |
| 5–6 | Review wait | Respond to review queries, fix rejections if any |
| 6+ | Launch | Public release timed to social media / ads push |

## Cost

| Item | Cost |
|---|---|
| Apple Developer Program | $99 / year |
| App icon design (Figma / Fiverr) | $0–$100 |
| Privacy policy generator (Termly, iubenda) | $0–$15 / month |
| Screenshots (Figma templates or real captures) | $0 |
| Push notification service (Firebase — free for our scale OR self-hosted APNs — free) | $0 |
| **Total startup cost** | **~$100–$200** |

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Apple rejects due to billing | Start with Reader App exemption; fallback to IAP if rejected |
| Financial-app extra scrutiny | Strong "educational" framing; disclaimers everywhere; track record shows losses |
| WebView performance on older iPhones | Target iOS 15+ only; test on iPhone SE 2nd gen baseline |
| Push notification permission denied | Telegram still primary; explain value of native push in onboarding |
| Demo account for reviewers gets abused | Rate limit it; reset weekly; don't make it an attack vector |
| Capacitor plugin bugs in production | Pin plugin versions; have rollback via OTA update |
| App rename from "TradeSignal" (current appName) | Decide early, commit to name for Apple listing |
| Privacy policy gaps | Use Termly / iubenda template initially; lawyer review before v1.1 |

## App Name Decision

Capacitor config currently says `appName: "TradeSignal"`. For App Store, consider:

- **TradeCoPilot AI** — matches brand
- **TradeCoPilot** — shorter, same brand
- **AI TradeCoPilot** — leads with AI for search
- **TradingWithAI** — matches domain

Pick ONE and update everywhere — Capacitor config, icon text, App Store listing. Changing later means new bundle ID which is painful.

**Recommendation: "TradeCoPilot AI"** (bundle ID stays `com.aicopilottrader.app` which already matches).

## Success Criteria

- [ ] App approved and live in US App Store within 6 weeks of Phase 1 start
- [ ] First 50 iOS users installed within 30 days of launch (from existing web audience + Twitter)
- [ ] Crash-free rate ≥ 99.5% in first month
- [ ] Average App Store rating ≥ 4.0 within 90 days (with 20+ reviews)
- [ ] Push notification opt-in rate ≥ 60%
- [ ] No App Store rejection for billing compliance

## Out of Scope (ticket for later)

- Android app (separate spec, same Capacitor codebase)
- iPad-specific UI (works but not optimized)
- macOS via Catalyst
- Apple Watch companion
- Siri Shortcuts (e.g., "Hey Siri, what's the AI saying about ETH?")
- Widget for home screen
- Live Activity for open positions (Dynamic Island)
- Deep link from Telegram bot → specific app screen

## Related

- `web/capacitor.config.ts` — existing scaffold
- `web/ios/App/` — iOS project
- `web/src/hooks/useNativePlatform.ts` — Capacitor detection
- `api/app/routers/push.py` — existing push endpoint scaffolding
- `specs/16-ios-mobile-app/` — earlier iOS spec (now superseded)
- Spec 28 — landing page (App Store listing copy draws from here)
- Spec 33 — social media (promote App Store download on launch)

## Open Questions (decide before starting)

1. **App name:** TradeCoPilot AI, TradeCoPilot, or TradingWithAI?
2. **Billing:** Reader App exemption or native IAP (or hybrid)?
3. **Launch timing:** simultaneous with paid ads, or staggered?
4. **Who handles Apple Developer account:** personal or LLC? (LLC gives "Company" badge; personal shows your name)
5. **Content updates:** OTA for every change, or only code-safe changes?
6. **iOS only for v1?** (recommend yes — Android adds complexity; ship iOS first)

## Next Action

If approved, Phase 1 starts with:
1. Decide the open questions (30 min)
2. Generate app icon + launch screen (half day)
3. Add native plugins (push, app, haptics, browser) — half day
4. Polish safe areas + keyboard — 1 day
5. First TestFlight build — end of week 1
