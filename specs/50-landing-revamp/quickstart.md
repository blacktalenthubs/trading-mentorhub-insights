# Quickstart Runbook — Spec 50 Landing Revamp

**Purpose**: Sequenced steps for executing the landing rewrite.
**Audience**: maintainer / agent.
**Estimated**: ~3 hours focused work + ~1 hour responsive/accessibility polish.

---

## Phase A — Pre-flight (5 min)

1. Confirm `web/src/App.tsx` route map matches FR-208/FR-209 (per [research.md §2](./research.md#2-apptsx-route-map-state-after-spec-49) it already does post-Spec 49). One grep:
   ```bash
   cd trade-analytics
   grep -E "Route path=\"(scanner|charts|alerts)\"" web/src/App.tsx
   # Expect 3 lines, each redirecting to /trading
   ```
2. Confirm `web/src/pages/LandingPage.tsx` still exists at 934 LOC (this is what we're replacing).
3. Confirm no other component imports `LandingPage` (it's only routed from App.tsx). One grep:
   ```bash
   grep -rn "LandingPage" web/src --include="*.tsx" --include="*.ts" | grep -v "pages/LandingPage.tsx"
   # Expect 1 hit: web/src/App.tsx
   ```

If anything unexpected, stop and investigate.

---

## Phase B — Rewrite LandingPage.tsx (90 min)

1. Open `web/src/pages/LandingPage.tsx`.
2. Read the existing `usePublicTrackRecord` hook (lines 17–35) — note the silent `.catch(() => {})`.
3. Replace the entire file body with the new implementation per:
   - [data-model.md](./data-model.md) — component tree
   - [contracts/copy-deck.md](./contracts/copy-deck.md) — exact words
   - [contracts/component-map.md](./contracts/component-map.md) — layout + icons + colors
   - [contracts/hero-stat-fallback.md](./contracts/hero-stat-fallback.md) — the 3-state hook + render branches
4. Keep the file as one component (don't extract sub-components in this pass).
5. Target: ≤400 LOC (down from 934).

---

## Phase C — Verify build + manual visual smoke (30 min)

1. From `web/`:
   ```bash
   cd web
   npm run build
   ```
   Must be green. No TypeScript errors, no Vite errors.

2. Start dev server + open landing:
   ```bash
   npm run dev  # or it's already running from earlier
   ```
   Open `http://localhost:5173/`.

3. Visual smoke at three viewports (Chrome DevTools):
   - **1280px desktop** — full nav visible, 2-col deliverables, all sections render
   - **768px tablet** — nav still desktop, 2-col deliverables, no layout breaks
   - **360px mobile** — hamburger nav, 1-col deliverables, primary CTA reachable without horizontal scroll

4. Stat state checks (live API at `http://localhost:8000`):
   - With the local DB empty (post-Spec 49 smoke state): hero stat should render the **0-data branch** ("Track record building")
   - To simulate **error branch**: kill the local API, refresh the page, hero should show "Track record unavailable right now · Refresh"
   - To simulate **loading branch**: throttle network to "Slow 3G" in DevTools, refresh, observe "Track record loading…" before the fetch resolves

5. Brand audit (SC-203 + SC-205):
   ```bash
   grep -i "tradesignal\|5 ai pillars\|ai scans the market\|ai picks" web/src/pages/LandingPage.tsx
   # Expect: zero hits
   ```

---

## Phase D — Accessibility manual scan (20 min)

1. Install axe DevTools Chrome extension if not installed.
2. Open `http://localhost:5173/`, run axe scan.
3. Goal: 0 critical violations. Address any that appear (most likely color-contrast on a status pill; fix by darkening text or lightening background).
4. Keyboard nav: Tab through every interactive element. Verify focus ring is visible on every one.
5. Mobile: open at 360px, verify hamburger menu is operable.

---

## Phase E — Document + commit (10 min)

1. Append a one-line "DONE" note to `trade-analytics/specs/50-landing-revamp/decision.md` (create if needed): waitlist email destination chosen (default `mailto:hello@tradingwithai.ai` if no operator override).
2. **DO NOT commit yet** if reviewer (operator) hasn't signed off.
3. Once approved:
   ```bash
   git add web/src/pages/LandingPage.tsx
   git add trade-analytics/specs/50-landing-revamp/
   git commit -m "landing: V2 revamp per spec 50 (5 pillars → 4 deliverables + live proof)"
   ```

---

## Phase F — Manual usability test (post-launch, scheduled)

Per SC-201: 5 first-time visitors, 15-second comprehension.

1. Recruit 5 testers who haven't seen the product.
2. Show them the landing for 15 seconds, then hide it.
3. Ask: "in your own words, what does this product do, and what would you get if you paid for it?"
4. Score: did ≥4 of 5 mention (a) "filters trading alerts" / "rates them" AND (b) "delivers them via Telegram" / "in your inbox"?
5. Record results in `decision.md`. SC-201 passes if yes.

This step happens on the operator's calendar, not automated.

---

## Rollback plan

If the new landing ships and metrics tank (bounce rate up significantly, conversion down), `git revert` the commit and the old `LandingPage.tsx` returns instantly. Landing rewrites are reversible.

---

## Done definition

- [ ] FR-208 / FR-209 verified (already done post-Spec 49)
- [ ] New `LandingPage.tsx` matches the copy deck + component map
- [ ] `npm run build` green
- [ ] Visual smoke at 1280 / 768 / 360 px — all good
- [ ] Hero stat tested in 4 states (loading / happy / 0-data / error)
- [ ] Brand audit grep clean
- [ ] axe scan: 0 critical violations
- [ ] Waitlist mailto chosen + recorded in decision.md
- [ ] Operator sign-off received
- [ ] Commit + push
- [ ] 5-tester usability check scheduled (SC-201)
