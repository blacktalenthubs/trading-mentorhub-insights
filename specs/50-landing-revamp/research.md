# Phase 0 Research — Spec 50 Landing Revamp

**Date**: 2026-05-16
**Method**: Direct file inspection (no agent delegation — the surface is small enough).
**Purpose**: Establish the baseline state before rewriting `LandingPage.tsx` so the diff is intentional and reviewable.

---

## 1. Current `LandingPage.tsx` baseline

| Property | Value |
|----------|-------|
| Path | `/Users/mentorhub/Documents/master-domain-hub/trade-analytics/web/src/pages/LandingPage.tsx` |
| Size | 934 LOC, single self-contained component, no extracted sub-components |
| Header comment | "Rebuilt around 5 AI pillars: Coach, CoPilot, Scan, Review, Pattern Library" |
| Aesthetic | Dark terminal — `bg-surface-0`, `text-text-primary`, blue accent, lucide-react icons |
| Track-record fetch | `usePublicTrackRecord()` hook fetches `/api/v1/intel/public-track-record?days=90` |
| Hero CTA target | `/register` |
| Anchor navigation | `#pillars`, `#pricing` (both anchors targeted by the LandingNav links) |

What the page markets today:
1. **AI Coach** — best-setups picker (live but retired marketing pillar per Spec 48)
2. **AI CoPilot** — chat surface (live)
3. **AI Scan** — *retired* (the V1 AI day-scanner; deleted in Spec 49 — but landing still markets it)
4. **AI Review** — post-mortem (some of this is live; some retired)
5. **Pattern Library** — `/learn` (live)
6. Pricing tier table
7. Track-record sample

Of those, the only **honest** pillars to retain are CoPilot (live), Pattern Library (live), and the Track Record (live). The whole "5 AI pillars" framing must go because two of the pillars don't exist anymore.

---

## 2. `App.tsx` route map state (after Spec 49)

`App.tsx` was edited in Spec 49 to drop the V1 React pages. Current state vs. Spec 50 FR-208 target:

**Public routes** (currently):
- `/`, `/learn`, `/learn/:cat`, `/learn/patterns/:patternId`, `/replay/:alertId`
- `/public/eod-report[/:date[/:symbol]]`
- `/track-record[/:date[/:symbol]]`
- `/login`, `/register`, `/reset-password`
- `/onboarding` (protected wrapper outside AppLayout)

FR-208 public-route target: ✅ **matches exactly**.

**Protected routes** (currently, all under `AppLayout`):
- `dashboard`, `trading` (TradingPageV2), `copilot`, `review`, `eod-report`, `trades`, `settings`, `billing`, `admin`, `ai-updates`, `watchlist`, `premarket`

FR-208 protected-route target: ✅ **matches exactly**.

**Legacy redirects** (currently):
- `/scanner` → `/trading`
- `/charts` → `/trading`
- `/alerts` → `/trading`

FR-209 target: ✅ **matches exactly**.

**Conclusion**: App.tsx is already correct. Spec 50's FR-208/FR-209 work is **already done as a side-effect of Spec 49 cleanup**. The plan's only App.tsx task is a sanity check.

---

## 3. `usePublicTrackRecord` baseline behavior

Current implementation (`LandingPage.tsx:17-35`):

```tsx
function usePublicTrackRecord(): TrackRecord | null {
  const [data, setData] = useState<TrackRecord | null>(null);
  useEffect(() => {
    fetch("/api/v1/intel/public-track-record?days=90")
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, []);
  return data;
}
```

Issues vs. Spec 50 FR-202 / FR-202b:
- ❌ No loading state — initial `null` is rendered as "..." (probably) but no explicit "track record loading…" copy
- ❌ Silent catch — API failure renders the page with permanent `null`, no fallback message
- ❌ No distinction between "API returned 0 data" (a real value, ship `0.0%`) and "API failed" (show fallback)
- ❌ Doesn't validate that `win_rate` is a finite number — feed it bad data and you get `NaN%` in the DOM (the exact thing FR-202b forbids)

Verified shape of the API response (from Spec 49 smoke test):
```json
{"period_days":90,"total_signals":0,"wins":0,"losses":0,"win_rate":0.0,"by_alert_type":{}}
```

The new hook must distinguish three states: `{ status: "loading" }`, `{ status: "ok", data }`, `{ status: "error" }`. Render rules in [contracts/hero-stat-fallback.md](./contracts/hero-stat-fallback.md).

---

## 4. Design system available

`web/src/index.css` defines via Tailwind v4 `@theme`:

- **Surfaces**: `surface-0` (`#0f1117`, darkest) → `surface-4`
- **Borders**: `border-subtle`, `border-default`, `border-strong`
- **Text**: `text-primary` (`#e8ecf4`), `text-secondary`, `text-muted`, `text-faint`
- **Accent**: `accent` (`#3b82f6` blue), `accent-hover`, `accent-muted`, `accent-subtle`
- **Bull/Bear**: standard green/red for stats
- **Fonts**: DM Sans (display), Plus Jakarta Sans (body), JetBrains Mono (mono)

Reuse these — no new design tokens.

Existing icon library: `lucide-react`. Already imported in current LandingPage. Reuse.

---

## 5. Out-of-scope clarifications (informed defaults)

| Question | Default | Source |
|----------|---------|--------|
| What does the new hero CTA link to? | `/register` (matches current) | Existing flow; no register-flow change in scope |
| What does "Sign in" link to? | `/login` (matches current) | Same |
| Where does the "join waitlist" CTA for Spec 51/52 deliverables go? | `mailto:hello@tradingwithai.ai?subject=Waitlist...` | Lowest-friction default; operator can swap to a real waitlist URL later |
| Should the navbar have a "Pricing" link? | NO — drop it. Pricing on landing is out of scope (V3 manifest doesn't include pricing surface for trade-analytics yet) | Spec 48 manifest: "No multi-account / team / institutional pricing in v3" — implies pricing page is not v3 scope |
| Should the navbar have a "Pattern Library" link? | YES — keep linking to `/learn` (live) | Aligns with Spec 52 prep |
| Should the navbar have a "Track Record" link? | YES — keep linking to `/track-record` (live, used by FR-202b proof) | |
| Should the navbar have a "Conviction Channel" or "Telegram" link? | NO — too vendor-specific; mention inside the hero/what-you-get section instead | Cleaner |
| Mobile menu (hamburger) | YES — current page hides the desktop nav on `md:` and below, but doesn't expose a mobile menu. Add a simple `<details>` dropdown to keep accessibility AAA on mobile | FR-206 |

---

## 6. Risks (tracked, not blockers)

1. **5-tester usability test (SC-201)** is a manual ritual after the page ships. The plan documents how to run it but the result is not automatable; it falls to the operator post-launch.
2. **`PublicEODReportPage` may not have data on first day post-revamp**. The "live EOD recap" deep link in FR-203 might land on an empty page. The link target should default to the most-recent-date EOD report (no `:date` segment) so the page handles "no data today" itself.
3. **Brand audit** (SC-205): need to grep the whole rewritten page for `TradeSignal` / `tradesignalwithai` post-rewrite and ensure zero hits.
4. **Lighthouse / WCAG scan** (SC-204): not automated in this repo today. Manual run via Chrome DevTools after implementation.

---

## 7. What this research locks in for Phase 1

- Landing page is a full rewrite, target ~400 LOC (down from 934).
- App.tsx requires no further edits (Spec 49 already did the work).
- Hero stat hook gets rewritten to a 3-state machine.
- Reuse existing design tokens; no new components in `components/` for v1.
- Two "coming soon — join waitlist" affordances for Spec 51 (Chart Critique) and Spec 52 (Pattern Education Live).
- Pricing page link removed from navbar.
- Mobile menu added.
