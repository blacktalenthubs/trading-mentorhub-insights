# Pre-Ad-Launch Smoke Tests

**Priority**: Critical — run before any paid traffic
**Created**: 2026-04-12
**Owner**: TBD

Every broken step in the funnel costs ad dollars. Run this checklist once end-to-end before enabling Google / Meta / TikTok ads. Revisit whenever you push changes that touch signup, billing, tier gating, or the landing page.

## 1. Landing Page Health (5 min)

Open `https://www.tradingwithai.ai` in an **incognito window** (no cached auth).

- [ ] Page loads in under 3 seconds (Chrome DevTools Network tab → Disable cache → refresh → check "Finish")
- [ ] No console errors (DevTools → Console → red messages = broken; ignore Chrome extension noise)
- [ ] Hero headline reads "AI finds the trade. You decide."
- [ ] Live track record stats render (not "---" — means API is responding)
- [ ] All 5 AI Pillar cards display with icons (Coach / CoPilot / Scan / Review / Pattern Library)
- [ ] Pricing table shows correct values: Free $0, Pro $49, Premium $99
- [ ] No marketing of features we don't have (no "Options Flow", "Sector Rotation", "Catalyst Calendar")
- [ ] Mobile: open on phone or Chrome → Device Toolbar → iPhone 14. Layout doesn't break.
- [ ] Favicon + title bar look right ("TradeCoPilot — AI Trading Platform…")

## 2. Social Meta Tags (2 min)

- [ ] Test at https://www.opengraph.xyz/ — enter `www.tradingwithai.ai`
- [ ] OG title and description render correctly
- [ ] Preview image displays (if you added one) — otherwise note as follow-up
- [ ] Twitter card preview via https://cards-dev.twitter.com/validator

## 3. Short Links + UTM Attribution (5 min)

Test each short link in a fresh incognito window:

- [ ] `www.tradingwithai.ai/tw` → lands on homepage, URL bar shows `?utm_source=twitter&utm_medium=bio`
- [ ] `www.tradingwithai.ai/tt` → TikTok UTM
- [ ] `www.tradingwithai.ai/ig` → Instagram UTM
- [ ] `www.tradingwithai.ai/dm` → Friend DM UTM
- [ ] `www.tradingwithai.ai/launch` → launch campaign UTM
- [ ] Unknown short code like `www.tradingwithai.ai/xyzabc` → renders landing page (SPA fallback works)

## 4. Signup Flow (10 min)

**Attribution + new account test:**

1. Fresh incognito window → `www.tradingwithai.ai/tw` (to capture UTM)
2. Wait for landing to finish loading (attribution is written to localStorage)
3. Click "Start Free — 3 Day Pro Trial"
4. Register with test email like `smoketest-<timestamp>@example.com`
5. After register completes:
   - [ ] Land on onboarding or dashboard (no 500 error)
   - [ ] Session is authenticated (sidebar shows nav)
   - [ ] Open `/admin` (as admin account separately) → User Debug → type the test email → confirm:
     - [ ] `resolved_tier: "pro"` (trial active)
     - [ ] `trial_days_left: 3`
     - [ ] `attribution_source: twitter` (on the backend — check via admin attribution widget "By source")
6. Check Telegram-linking prompt appears (Onboarding page or Settings → Notifications)

## 5. Trial → Free Transition (2 min, DB check)

- [ ] Use User Debug to set a test account's `trial_ends_at` to yesterday (via direct DB update if needed)
- [ ] Reload `/admin` + Inspect — confirm `resolved_tier` flips to `"free"`
- [ ] Confirm limits change: `ai_scan_alerts_per_day` becomes 7, `visible_alerts` becomes 10

## 6. Telegram Linking (5 min)

Use a test account (can be your main, or a brand new one):

- [ ] Settings → Notifications → click "Link Telegram"
- [ ] Token generated, redirect to Telegram opens bot
- [ ] `/start <token>` in the bot → response: "Account linked"
- [ ] Back on website, Settings shows "Telegram: Linked"
- [ ] Admin User Debug shows `telegram_chat_id` populated

## 7. Watchlist + AI Scan Delivery (10 min, during market hours or crypto)

- [ ] Add `ETH-USD` and `BTC-USD` to test account's watchlist (crypto works 24/7)
- [ ] Wait one scan cycle (5 min)
- [ ] Check `/admin` → User Debug on test account → `ai_wait_alerts_in_db > 0` (confirms scanner ran for this user)
- [ ] If AI fires an actionable signal, Telegram message arrives with "✅ Took It / ❌ Skip / 🔴 Exit" buttons
- [ ] Tap "Took It" → bot replies with "Trade ACK'd"
- [ ] Dashboard Active Positions shows the trade

## 8. Rate Limit Caps (free tier, 5 min)

Set a test account to `free` tier (or wait for trial to expire):

- [ ] Force 8+ actionable alerts through (hard if market is quiet — alternative: manually set `_user_delivered_count` via a debug endpoint, or just verify the limit is 7 in User Debug)
- [ ] 8th alert: expect "Daily AI scan limit reached (7/7)" Telegram message exactly once
- [ ] 9th, 10th: no Telegram sent, no duplicate cap message
- [ ] Confirm in User Debug: `limit_reached_notified: true`
- [ ] Dashboard banner appears: "Daily AI scan limit reached"

## 9. Billing / Upgrade Path (10 min — CAREFUL, real Square)

- [ ] Billing page loads, shows current tier + trial state
- [ ] Click "Upgrade to Pro"
- [ ] Square card form loads (no console errors, no broken iframe)
- [ ] Test with Square's **sandbox test card** (NOT a real card — confirm you're pointed at Square sandbox, not production!)
- [ ] Confirm subscription creates → `resolved_tier` flips to `"pro"` in User Debug
- [ ] Cancel subscription works → reverts to `"free"` after period end

## 10. Public Pages (no auth required, 3 min)

- [ ] `www.tradingwithai.ai/learn` loads with pattern categories
- [ ] `www.tradingwithai.ai/learn/patterns/prior_day_low_bounce` loads pattern detail
- [ ] `www.tradingwithai.ai/replay/<any-valid-alert-id>` loads replay (pick an ID from admin)
- [ ] None of these require login

## 11. Admin Security (2 min)

**Critical — don't leak admin pages to regular users.**

- [ ] Log in as a non-admin test user
- [ ] Navigate to `/admin` → should show "Access denied" or redirect, NOT the admin UI
- [ ] Direct API call as non-admin: `GET /api/v1/admin/stats` returns 403, not 200
- [ ] Admin email list in `admin.py` includes only approved emails

## 12. Error Monitoring (1 min)

- [ ] Railway logs are flowing — open latest deployment logs, confirm recent entries
- [ ] No repeated ERROR / CRITICAL lines in last hour
- [ ] If Sentry/other error tracker is set up, confirm ingesting

## 13. Analytics (1 min)

- [ ] GA4 Measurement ID pasted in `web/index.html` (look for `G-XXXXXXXXXX`, NOT the placeholder)
- [ ] Refresh landing page → open GA4 Real-time report → confirm your pageview lands
- [ ] Admin attribution widget: after smoke test signups, shows `twitter`, `tiktok` etc. under "By source"

## 14. SEO Basics (2 min)

- [ ] `view-source:www.tradingwithai.ai` — `<title>` and `<meta name="description">` correct
- [ ] Structured data (FAQPage in `<head>` as JSON-LD) matches actual FAQ content on site
- [ ] `robots.txt` exists at `/robots.txt` (if you want SEO — otherwise note as follow-up)

## 15. Mobile Signup Test (5 min)

Actual mobile phone, not desktop simulator:

- [ ] Open short link on phone (`tradingwithai.ai/tw`)
- [ ] Hero reads cleanly, CTA button tappable
- [ ] Register form works on mobile keyboard
- [ ] Post-signup page readable on mobile
- [ ] Telegram link via mobile opens Telegram app natively

---

## Post-Test Cleanup

- [ ] Delete smoke test accounts created during testing (admin panel has "Delete User" or use DB query)
- [ ] Reset any test users' `trial_ends_at` if you modified it
- [ ] Reset test Square subscription if live tier test was run
- [ ] Note any failed checks in a new `tickets/` file for follow-up

## Known Deferred Items (not blocking)

- [ ] Apex domain redirect (`tradingwithai.ai` without www) — see `tickets/apex-domain-redirect.md`
- [ ] Rate limit persistence across worker restarts — see `tickets/ai-scan-rate-limit-persistence.md`
- [ ] Deprecate rule-based alerting — see `tickets/deprecate-rule-based-alerting.md` (set `RULE_ENGINE_ENABLED=false` env var before ads go live)

## Ship Criteria

All non-deferred boxes checked. If any fail, fix before any ad spend. A broken signup flow costs 10x what a polish item does.
