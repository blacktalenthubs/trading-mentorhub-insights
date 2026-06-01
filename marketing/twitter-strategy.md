# Twitter / X Strategy — Brand-First, Employer-Safe

Copy-paste-ready setup for launching BusyTradersDesk on X without
exposing the founder identity. Designed for the Apple-employee constraint:
no face on video, no LinkedIn link, no personal-account tie-in.

Everything here can be executed in a single weekend session.

---

## 1. Identity rules — read first, follow always

**DO**
- Post as `@BusyTradersDesk` (the brand). No founder name anywhere.
- Use a separate browser profile / device for the brand account. Avoid the temptation to use your real-account browser session.
- Set up a separate email for everything brand-related: `founder@busytradersdesk.com` or similar. Never use your work email or your personal Apple ID email.
- If you ever register the LLC / DBA / brand entity, use that for Apple Developer + Google Play + Square + domain WHOIS. Adds ~$200/yr in compliance, buys clean separation.

**DON'T**
- Don't link your personal X to the brand (no quote-tweets, no follows, no replies from your real account).
- Don't post screenshots that include identifying metadata — laptop wallpaper, menu bar with your name, browser bookmarks, dock icons.
- Don't appear in video, podcast, or photo as the founder until you've decided about disclosure.
- Don't link the brand on your LinkedIn, GitHub, or any profile that names you.
- Don't add the brand handle to your real-account bio "I work on..." sections.
- Don't sign up to be a "maker" on Product Hunt under your real name — use the brand handle.

---

## 2. Brand account setup checklist

Create the `@BusyTradersDesk` X account from a fresh browser profile (Chrome → People → Add → separate user). Don't use your real-account browser.

- [ ] Sign up with `founder@busytradersdesk.com` (or a Gmail you control that isn't linked to your real identity)
- [ ] Phone verification: use Google Voice or a burner SMS if you want to keep your personal cell off the platform
- [ ] **Handle**: `@BusyTradersDesk`
- [ ] **Display name**: `BusyTradersDesk`
- [ ] **Bio** (160 char):
  ```
  Trading desk for busy professionals. AI-graded alerts (A/B/C). Pattern library + transparent EOD reports. Not advice. 🇺🇸
  ```
- [ ] **Location**: leave blank, or "Global" — never your real city
- [ ] **Website**: `https://www.busytradersdesk.com`
- [ ] **Birth date**: pick the brand's "founding date" (e.g. 1 Jan 2026), not your real one
- [ ] **Profile photo**: 400×400 PNG of the Crosshair logo on the gradient background (use the same asset you'll use for the iOS app icon)
- [ ] **Banner photo**: 1500×500 PNG with tagline + one chart. Free template: Canva → "X Banner"
- [ ] Turn ON two-factor auth via authenticator app (not SMS)
- [ ] In Settings → Privacy → DMs → "Allow message requests from everyone" (so cold DMs back to you work both ways)

---

## 3. Optional: pseudonymous founder persona

People follow people more than brands. A separate "founder" handle can amplify reach without revealing your identity. Skip this if you'd rather keep it brand-only.

Setup mirrors above but:

- [ ] Handle: something like `@busyquant`, `@deskforatrader`, `@trading_with_a_dayjob` — pick a vibe
- [ ] Bio: `Built BusyTradersDesk. Day-job trader. I post about VWAP slope, alert grades, and the trades I take after-hours.`
- [ ] Profile photo: an abstract avatar (not your face). Tools: https://dicebear.com or any avatar generator
- [ ] This account quote-tweets and amplifies `@BusyTradersDesk` posts in a first-person voice

If you use both: 80% of your time on the brand account, 20% on the founder persona. Don't try to maintain two equal voices.

---

## 4. Posting cadence — Week 1

Same posts as `marketing/week1-content.md` but rewritten in brand voice
(no first-person "I built this"). Copy-paste these directly into Buffer
or just post them at the times below.

### Monday 9:30 AM ET — "alerts are noise"
```
The trading platform problem nobody admits:

Most alerts are noise. You learn to ignore them — then you ignore the one that mattered.

BusyTradersDesk grades every alert A / B / C using volume + VWAP slope.

Grade A = both gates pass. ~12% of fires. The rest are filterable.

→ busytradersdesk.com
```

### Tuesday 9:30 AM ET — chart of the day
*Attach a chart screenshot from yesterday's session with the entry/stop/target marked.*

```
A Grade-A alert from yesterday:

NVDA reclaimed PDH at $145.20 on 2.4× volume with VWAP slope +0.18%.

Entry triggered. Walked to +1.8R before close.

That's what "Grade A" means here — not subjective conviction, just two numerical gates that don't lie.

Full track record: busytradersdesk.com/track-record
```

### Wednesday 7 PM ET — counter-positioning
```
Counterintuitive take:

The best feature in a trading platform isn't "more alerts." It's the alert *not firing*.

When BusyTradersDesk sees no valid setup, it says WAIT. No suggestion. No "maybe try this."

Most platforms can't say "nothing right now" — it kills engagement metrics.

Ours can.
```

### Thursday 9:30 AM ET — educational thread (4 tweets)
Tweet 1:
```
Most "VWAP bounce" setups fail because traders watch the line, not the slope.

A flat VWAP says nothing. A rising VWAP says "the average buyer is paying more than they were 5 minutes ago." That's the signal.

How to read VWAP slope, in 3 tweets 🧵
```

Tweet 2 (reply to 1):
```
VWAP slope = (VWAP_now - VWAP_5min_ago) / VWAP_5min_ago × 100

Positive = institutional bid is climbing.
Negative = institutional bid is fading.
Near zero = sideways, no edge.

Most platforms show you the VWAP. Few show you whether it's accelerating.
```

Tweet 3 (reply to 2):
```
BusyTradersDesk gates every long alert on slope ≥ +0.05%.

Anything below that = noise. The threshold isn't sacred — it's just "more positive than coincidence."

Tighten or loosen for your style. Default is 0.05%.
```

Tweet 4 (reply to 3):
```
Full grading system + the Pine v5 script that generates these alerts is documented in our Pattern Library, free to read:

busytradersdesk.com/learn

No signup needed. Bookmark for the next time you want to defend a trade idea with numbers instead of vibes.
```

### Friday 9 AM ET — Friday retro hook
```
Most traders review their week and conclude "I should size bigger."

Wrong question.

Right question: "which patterns am I taking that don't have edge?"

We built a Friday AI retro into BusyTradersDesk that crunches every fire from the week and tells you which patterns to stop trusting.

Free preview on the public EOD page:

busytradersdesk.com/public/eod-report
```

---

## 5. DM template — brand handle to cold prospects

Send 5-10 of these per day to traders with 500-5000 followers who tweet
their setups with charts. ~10% reply rate, ~3-5% become users.

```
Hey — saw your post about [specific trade or pattern they mentioned]. Real read on the [VWAP / volume / pattern] side.

We built BusyTradersDesk to grade alerts A/B/C automatically (volume × VWAP slope). B and C get filtered.

Would you want 90 days of free Pro in exchange for honest feedback on whether the grading matches what your eye is doing already?

No promo expected — we just want to compare our grades to a real trader's gut on the same setups.
```

**What to look for**: people whose recent tweets show actual chart work
+ structured language ("I'm watching for the reclaim of...", "set my
stop at..."). Skip the meme-trade replies and the "trust me bro" calls.

**What never to do**: mass-DM with the same template, send to people with
< 500 followers (looks predatory), include the link in the first
message (Twitter shadow-throttles links in DMs).

---

## 6. Twitter Ads playbook

Run from `https://ads.x.com`. Connect billing to a card under the brand
identity if possible (LLC / DBA), or your personal card as fallback.

### Pixel install (before any ads)

Add the X conversion pixel to busytradersdesk.com. Without this, the
algorithm is flying blind.

- [ ] Go to https://ads.x.com → Tools → Conversion tracking
- [ ] Create event: `signup_completed`
- [ ] Copy the pixel snippet
- [ ] Tell me the snippet — I'll wire it into `web/index.html` and rebuild

### Targeting that works for trading

Set these as Saved Audiences in X Ads:

**Audience A — "Keyword Intent"**
- Keywords (people tweeting these): `swing trade`, `day trade`, `VWAP`, `watchlist`, `scanner`, `alert`, `setup`
- Language: English
- Location: US, Canada, UK (your APIs cover US markets best)

**Audience B — "Follower Lookalikes"**
- People who follow these accounts:
  - `@StockTwits`
  - `@unusual_whales`
  - `@Trade_Ideas`
  - `@MarketWatch`
  - `@DeItaone`
  - `@SqueezeMetrics`
- Location: US, Canada, UK

**Audience C — "Retargeting"** (set up after 1000 site visitors accumulate)
- Pixel: anyone who visited busytradersdesk.com in last 30 days
- Exclude: anyone who already signed up

**Audience to AVOID**:
- Interest = "Finance" (too broad, mostly retail meme traders)
- Interest = "Stocks" (same)
- "Lookalikes of US population" (waste of money)

### Budget allocation — $100/mo starter

- $50/mo — boost the single tweet from Week 1 that earned the most organic engagement. Update weekly.
- $30/mo — follower campaign on the brand account targeting Audience A. Optimize for "new followers." Builds long-term organic reach.
- $20/mo — reserve for amplifying a clear winner if one emerges (a Substack post that gets RTs, a Pattern Library page that drives signups).

### Scale-up ladder — when to move budgets

| Trigger | Action |
|---|---|
| One ad → > 3% conversion rate (link click to signup) | Double its budget for the week |
| One tweet hits 10K+ organic impressions | Don't promote it (free reach already winning) |
| Audience B (lookalikes) outperforms Audience A | Pause A, double B |
| Cost per signup < $5 | Increase total ad budget by 50% |
| Cost per signup > $20 after 1 week | Pause that ad, change creative |

### Format rules

- Text + 1 chart screenshot beats text-only beats text + meme
- Ad copy ≤ 240 chars (leaves room for the auto-appended URL)
- Include numbers — "+1.8R", "2.4× volume", "12% Grade A rate" — beats adjectives
- Use the exact same language as the landing page so the bounce rate stays low

---

## 7. What to skip (given the constraint)

Stays off:
- TikTok, Instagram (video / face)
- YouTube (face)
- Podcast guesting (voice)
- Public Product Hunt launch with founder byline
- LinkedIn posts
- Press / media interviews
- "Founder thought leadership" Substack posts under your name

Stays on:
- X / Twitter (brand handle, optionally founder persona)
- Reddit (already pseudonymous)
- Substack (anonymous / brand byline)
- Discord / Telegram (brand handle)
- Blog posts on busytradersdesk.com (no author byline)
- All paid ads
- All SEO content
- DMs from brand handle

---

## 8. Things I'll do for you once you tell me they're done

- [ ] You paste the X conversion pixel snippet → I wire it into `web/index.html`
- [ ] You pick a brand handle + create it → I add the X meta-tags so unfurled links use brand images
- [ ] You give me a 400×400 PNG of the logo → I'll add it as `apple-touch-icon` and Open Graph image so shared links look professional
- [ ] You give me 1500×500 banner image → I'll store it in the repo for reference (X profile only, no integration needed)

---

## 9. 30-minute Saturday setup checklist

If you want to do it all in one sitting:

- [ ] 5 min — fresh browser profile + email
- [ ] 5 min — create `@BusyTradersDesk`
- [ ] 5 min — banner + avatar (Canva / export from Figma)
- [ ] 5 min — bio + website link + 2FA
- [ ] 5 min — copy the X conversion pixel snippet, send to me
- [ ] 5 min — paste Week 1 Monday tweet into drafts (or schedule for 9:30 AM Monday)

You're live. Real launch is Monday morning.
