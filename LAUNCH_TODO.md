# Launch TODO — things only you can do

Companion to the 30-day sprint plan. Engineering work is shipped (Google +
Apple Sign-In, AuthShell redesign, last-seen tracking). Everything below
requires your accounts, your money, or your hands on a phone.

Cross items off as you go. Each block is self-contained — do them in any
order that fits your week.

---

## 1. Sign in with Apple — Apple Developer console (~45 min)

This unlocks the iOS App Store. Apple requires Sign in with Apple if you
offer any other social login (rule 4.8). The backend `/auth/apple` is
already shipped — it just needs the Services ID you create below.

1. Go to https://developer.apple.com/account/resources/identifiers/list/serviceId
2. Click the **+** button → **Services IDs** → Continue
3. **Description**: `BusyTradersDesk Sign In`
4. **Identifier**: `com.busytradersdesk.signin` (must be reverse-DNS, unique)
5. Continue → Register
6. Click the Services ID you just created
7. Check **Sign In with Apple** → click **Configure**
8. **Primary App ID**: pick your iOS app's App ID (create one first if needed at the App IDs section)
9. **Domains and Subdomains**: add
   - `busytradersdesk.com`
   - `www.busytradersdesk.com`
10. **Return URLs**: add `https://www.busytradersdesk.com`
11. Click **Next** → Apple will ask you to verify domain ownership
12. Apple gives you a file like `apple-developer-domain-association.txt` — **send it to me** and I'll place it at the right path
13. After Apple verifies, click **Save**

Then set these in Railway:

| Service | Variable | Value |
|---|---|---|
| API (`worker`) | `APPLE_CLIENT_ID` | `com.busytradersdesk.signin` |
| Web (`.env.production`) | `VITE_APPLE_CLIENT_ID` | `com.busytradersdesk.signin` |

For the web one, just edit `web/.env.production` in the repo, push, and the
next build will pick it up. Tell me the Services ID and I'll do this for
you.

---

## 2. Google Play Console — $25 one-time (~30 min)

1. Go to https://play.google.com/console/signup
2. Pick **Personal** account (faster identity verification than Org)
3. Pay $25 one-time fee (credit card)
4. Identity verification: government ID upload — can take 1-3 days
5. Once verified, you can create the app record

Don't sweat the long fields yet — I'll provide the copy in section 6.

---

## 3. Apple App Store Connect — app record (~20 min)

Assumes Apple Developer Program ($99/yr) is already active.

1. Go to https://appstoreconnect.apple.com
2. Click **My Apps** → **+** → **New App**
3. **Platforms**: iOS
4. **Name**: BusyTradersDesk
5. **Primary Language**: English (U.S.)
6. **Bundle ID**: pick the App ID you created in step 1 (or create one at https://developer.apple.com/account/resources/identifiers/list)
7. **SKU**: `busytradersdesk-ios-001` (just an internal identifier)
8. **User Access**: Full Access
9. Create

You now have a placeholder app record. We'll fill in screenshots and copy
later (section 6).

---

## 4. iOS app icon — 1024×1024 PNG (DIY in ~30 min)

The fastest path: export the Crosshair logo from the landing page as a
1024×1024 PNG with the gradient background.

Option A — DIY in Figma:
1. Open https://figma.com (free)
2. Create a 1024×1024 frame
3. Background: linear gradient from `#7B61FF` (accent) to `#a855f7` (purple), 135°
4. Center the Lucide `Crosshair` icon (you can download SVG from https://lucide.dev/icons/crosshair) at 480×480, white fill
5. Export as PNG @ 1× → `icon-1024.png`
6. Send me the file and I'll integrate it into the iOS + Android builds

Option B — Pay someone:
- Fiverr: search "iOS app icon" — ~$20-30 for 24hr turnaround
- Brief: "Cypherpunk dark trading desk. Purple→pink gradient. White crosshair/scope. Square 1024×1024."

Option C — Use an AI generator (cheapest, risky):
- Midjourney, DALL-E, or Bing Image Creator
- Prompt: `"app icon, dark purple to pink gradient background, white crosshair/scope target, minimalist, square, no text, 1024x1024"`
- Pick the cleanest result; you may need 5-10 attempts

---

## 5. Screenshots — store listings (~1.5 hr)

Apple requires 6.7" iPhone (1290×2796) AND 5.5" iPhone (1242×2208).
Google Play needs at least 2 phone screenshots (1080×1920 minimum).

Required shots — minimum 5 across both stores:

1. **Hero shot**: trading page with a real grade-A alert visible
2. **Watchlist**: with 5-6 tickers populated
3. **Trade Ideas (AI Scans)**: 3-4 setups
4. **EOD Report**: showing real outcomes
5. **Sign-in screen**: showcasing Google + Apple options

Two paths:

**Path A (recommended)**: take real screenshots on a real iPhone Pro Max
(or via Xcode Simulator → iPhone 15 Pro Max).
1. Launch the app, navigate to each screen
2. Cmd+S in simulator captures the screen
3. Resize to 1290×2796 (Simulator outputs the right size already for iPhone 15 Pro Max)

**Path B**: use a mockup tool like https://shotbot.io or https://mockup.photos
- Upload your raw screenshots
- They add device frame + marketing background + text overlay
- Free tiers available, ~$10/mo for clean output

---

## 6. Store listing copy — paste these as-is

### App Name (30 char max)
```
BusyTradersDesk
```

### Subtitle / Short description (80 char max for Apple, 80 for Google)
```
Trading desk for the hours you're not at one
```

### Promotional Text (170 char, iOS only, editable any time)
```
Setups graded A/B/C by volume + VWAP slope. Real outcomes from actual post-fire price action. A Friday AI retro of what worked. Built for traders with day jobs.
```

### Description (4000 char max — same on both stores)
```
Your trading desk for the hours you're not at one.

BusyTradersDesk scans your watchlist during market hours, maps every setup to a documented pattern, and files a transparent end-of-day report — so you trade on structure, not FOMO. Built for self-directed traders with day jobs.

WHAT YOU GET

· Setup grades — every alert is graded A, B, or C using volume and VWAP slope. Grade A = both gates pass. Filter to only see what matters.

· Real outcomes — we walk the bars after every alert to compute MFE/MAE in R-multiples. No synthetic win rates. No marketing math. You see what actually happened.

· Daily EOD report — public, transparent, share-able. Every fire from the day with the grade and the outcome.

· AI Friday retro — Claude reviews your week and tells you what worked, what didn't, and which patterns to stop trusting.

· Pattern library — 14 documented setups with the rules, the chart, and the historical performance.

· Pre-market brief — earnings on your watchlist, SPY regime, AI best setups, swing picks, social trending tickers — read it before the open.

· Live alerts — Telegram, push notifications, or in-app feed. You decide.

PRICING

· Free tier — 5 symbols, 3 AI queries per day. Forever.
· Pro — $49/mo for unlimited symbols, full screener, swing scanner, Friday AI retro.
· 3-day Pro trial included for every new account. No card required.

WHO THIS IS FOR

Self-directed traders who can't watch screens 9 to 4. Who want educational reasoning behind every alert. Who care about the outcome, not the dopamine hit.

WHO THIS IS NOT FOR

Signal-followers looking for a magic copy-trade service. Day traders who want 100 alerts a day. People expecting financial advice.

DISCLAIMER

Not investment advice. Educational and informational use only. You are responsible for your own trades.

QUESTIONS

support@busytradersdesk.com
```

### Keywords (100 char max, comma-separated, iOS)
```
trading,alerts,vwap,stocks,crypto,charts,watchlist,scanner,patterns,daytrade,swing,signal,eod
```

### Category
- Primary: **Finance**
- Secondary: **Productivity**

### Age Rating
- iOS: **17+** (frequent/intense simulated gambling — Apple's category for trading apps)
- Google: **PEGI 18 / Teen** depending on region

### Privacy Policy URL
```
https://www.busytradersdesk.com/privacy
```
*If `/privacy` doesn't exist yet, I can scaffold one. Tell me.*

### Support URL
```
https://www.busytradersdesk.com/support
```
*Or just `mailto:support@busytradersdesk.com` if you don't have a support page.*

### Demo account for Apple reviewers
Create a dedicated reviewer account:
- Email: `applereviewer@busytradersdesk.com` (or use a gmail you control)
- Password: something simple they can type, like `Review2026!`
- Add 5 tickers to its watchlist (AAPL, NVDA, TSLA, SPY, QQQ)
- In App Store Connect → App Review Info, paste the credentials

---

## 7. iOS TestFlight (after step 1 + Sign in with Apple is wired)

After I push the Capacitor build:

1. App Store Connect → My Apps → BusyTradersDesk → **TestFlight** tab
2. Wait for the build to appear (15-30 min after upload)
3. Once it shows "Ready to Submit", add yourself as an **Internal Tester** (no review needed)
4. Install the TestFlight app on your iPhone, accept the invite
5. Test every screen, especially:
   - Sign in with Apple flow (must work for App Store approval)
   - Push notifications (kill the app, fire a test alert, ensure it pops)
   - Chart performance on real hardware
   - Subscription upgrade (taps to web — Apple is fine with this for non-IAP)

---

## 8. Play Store closed test

After I push the Android AAB:

1. Play Console → BusyTradersDesk → **Testing** → **Closed testing**
2. Create a new track called "closed-test-1"
3. Upload the AAB
4. **Testers**: add at least 12 Google accounts (yours + 11 friends/Substack subscribers)
5. Share the opt-in link with them
6. They MUST install and sign in at least once
7. Wait 14 days from track creation (Google's rule)
8. Then promote to production

To recruit 12 testers fast:
- Email your Substack list with a "early Android tester" CTA
- Post on X: "Looking for 12 Android testers — get free Pro for 60 days"
- Personal DMs to traders you know

---

## 9. Ad creative — copy-paste ready

You said $100-300/mo across Twitter/X + Reddit + Substack. Drafts are in
`marketing/week1-content.md` (next file). They're ready to post; just
pick which day each goes out.

---

## 10. Google Analytics — replace placeholder ID

Current `web/index.html` has a placeholder `G-EQ2E6BRMMT`. If you want
real analytics:

1. Go to https://analytics.google.com → Admin → Create Property
2. Property name: BusyTradersDesk
3. Time zone: your local
4. Currency: USD
5. Industry: Finance
6. Business size: Small
7. Get your Measurement ID (format: `G-XXXXXXXXXX`)
8. Send it to me and I'll swap it in

This isn't blocking for launch but you'll want it before ads start so
you can see which channels actually convert.

---

## Quick reference — env vars summary

| Variable | Where set | Status | What it unlocks |
|---|---|---|---|
| `GOOGLE_CLIENT_ID` | Railway worker | ✓ done | Backend Google verification |
| `VITE_GOOGLE_CLIENT_ID` | `web/.env.production` | ✓ done | Frontend Google button |
| `APPLE_CLIENT_ID` | Railway worker | **YOU** — after section 1 | Backend Apple verification |
| `VITE_APPLE_CLIENT_ID` | `web/.env.production` | **YOU** — paste Services ID, I rebuild | Frontend Apple button |
| Google Play `$25` | Play Console signup | **YOU** — section 2 | Android Store access |

---

## Decision points where I need your call

- **Privacy + Terms pages**: do those exist or should I scaffold them? Required by Apple/Google.
- **App icon path** — DIY in Figma, $25 on Fiverr, or AI-generated? Pick one.
- **Twitter/X handle** — confirm the handle so I include it in marketing drafts and store listing.
- **Substack handle** — same.
- **Support email** — `support@busytradersdesk.com` or something else? Required field for both stores.

Ping me on any of these and I'll handle whatever can be done from code.
