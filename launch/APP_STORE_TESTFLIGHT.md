# App Store → 100 testers (TestFlight) — launch plan

**TL;DR:** the iOS app already exists as a Capacitor webview wrapper that loads
`busytradersdesk.com`. Getting to 100 testers does **not** require building a native
app — it's **TestFlight**, which needs only a quick beta review (hours, not the full
App Store review) and supports up to **10,000** testers. The work is *packaging +
account steps*, almost all of which need **you** (Apple account, signing, upload).

---

## What already exists (good news)
- `web/capacitor.config.ts` — Capacitor configured, `webDir: dist`, `server.url:
  https://www.busytradersdesk.com` → the app is a thin shell over the live site, so
  **every web deploy updates the app automatically.** No app rebuild per change.
- `web/ios/App/` — the Xcode project (`.xcodeproj` + `.xcworkspace`).
- `apple.p8` in the repo root — an **App Store Connect API key** (used for automated
  TestFlight uploads via `xcrun altool` / Fastlane).

## ⚠️ Brand mismatch to decide FIRST (blocks naming)
| Field | Current value | Should be |
|---|---|---|
| `appId` | `com.aicopilottrader.app` | hard to change once an App Store record exists — **keep it** unless no record yet |
| `appName` (Capacitor) | `TradeSignal` | `BusyTradersDesk` |
| App Store listing name | — | **BusyTradersDesk** |

> The `appId` (bundle ID) is **permanent** once you create the App Store Connect
> record. If you've never created one, change it to `com.busytradersdesk.app` NOW.
> If a record already exists under `com.aicopilottrader.app`, keep the bundle ID and
> just set the **display name** to BusyTradersDesk (users only see the display name).
> **This is the one decision I can't make for you — check App Store Connect.**

---

## The path (fastest → 100 testers)
1. **iOS / TestFlight** — ready to go; ~1–2 hrs of *your* account work + a beta review.
2. **Android / Play internal testing** — *not started* (no `android/` project). Would
   need `npx cap add android` + a Google Play Console account ($25 one-time). Defer to
   phase 2 unless your testers are Android-heavy.

---

## Checklist — iOS TestFlight

### Needs YOU (account / signing / submit — I can't do these)
- [ ] **Apple Developer Program** membership active ($99/yr) on your Apple ID.
- [ ] Decide the **bundle ID** (see brand mismatch above).
- [ ] In **App Store Connect**: create the app record (name *BusyTradersDesk*, the
      bundle ID, primary language, category **Finance**).
- [ ] **Signing**: open `web/ios/App` in Xcode → Signing & Capabilities → select your
      team → let Xcode manage signing (or use the `apple.p8` API key for CI upload).
- [ ] **Privacy**: App Store requires a privacy policy URL + the privacy "nutrition
      label" (what data you collect). You collect email + usage → declare it.
      *(I can draft the privacy policy page — say the word.)*
- [ ] **Screenshots** — 6.7" (iPhone 15 Pro Max) at minimum. Capture: the live
      Signals feed, a chart with an alert, the EOD report, the Conviction tab.
      *(I can script `capture_screenshot` via the TV MCP, or you snap them in the
      simulator — 4–6 images.)*
- [ ] **Build + upload**: `cd web && npm run build && npx cap sync ios` → open Xcode →
      Product ▸ Archive → Distribute ▸ App Store Connect ▸ Upload. (Or Fastlane with
      the `apple.p8` key for one-command upload — I can set that up.)
- [ ] In TestFlight: add the build, fill **"What to test"**, add testers by email
      (internal testers = your team, up to 100 instantly; external = up to 10k after a
      ~1-day beta review).

### I can prep autonomously (ready for you in the morning)
- [x] **This plan** + the checklist.
- [x] **Listing copy** (below) — ready to paste into App Store Connect.
- [ ] **Fastlane lane** for one-command TestFlight upload using `apple.p8` (offer).
- [ ] **Privacy policy page** draft (offer).
- [ ] **Screenshot capture script** (offer).

---

## App Store / TestFlight listing copy (ready to paste)

**Name:** BusyTradersDesk
**Subtitle (30 chars):** Trade alerts for busy people
**Promotional text:** Real-time setups with the exact entry, stop, and target — so
you trade your plan, not your screen.

**Description:**
> BusyTradersDesk watches the market so you don't have to stare at charts all day.
>
> You get real-time alerts the moment a high-quality setup forms — each one with the
> exact entry, a tight stop, and a target, plus a quality grade. The whole system runs
> on one rule: buy strength at support, sell into resistance, never chase a breakout.
>
> • Live signal feed — see every setup as it fires, with entry / stop / target
> • One clean chart with your levels and moving averages labeled
> • Conviction list — the names worth owning, from analyst-backed strength
> • End-of-day report — review what fired and what was held back
> • Risk-management first — every alert ships a defined stop
>
> Built for self-directed traders with day jobs. For educational and informational
> purposes only — not financial advice.

**Keywords:** trading,stocks,alerts,signals,day trading,swing,SPY,options,watchlist,charts
**Support URL:** https://www.busytradersdesk.com
**Category:** Finance

---

## My recommendation for tonight
The bundle-ID decision is the only true blocker and it's yours. Everything else I can
queue up: **say the word and I'll (1) draft the privacy policy page, (2) set up a
Fastlane lane so upload is one command, and (3) write the screenshot-capture script.**
Then in the morning you do the Apple-account steps + hit upload, and you're on
TestFlight the same day.
