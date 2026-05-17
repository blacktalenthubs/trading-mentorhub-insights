# Copy Deck — Spec 50 Landing

**Purpose**: The exact words to ship on the new `LandingPage.tsx`. Reviewable before code lands so wording isn't a code-review concern.

**Voice**: Direct, technical, no hype. Talks to active retail traders who already use TradingView. No "revolutionary" / "game-changing" / "AI-powered" stock-marketing junk. Numbers > adjectives.

---

## Navbar

| Slot | Copy | Link |
|------|------|------|
| Brand | TradeCoPilot | `/` |
| Nav link 1 | Pattern Library | `/learn` |
| Nav link 2 | Track Record | `/track-record` |
| Auth — secondary | Sign in | `/login` |
| Auth — primary | Get started | `/register` |

(Mobile menu shows the same set.)

---

## Hero

**Eyebrow** (small label above headline):
> LIVE · V2 Pine + Triage pipeline

**Headline** (h1):
> TradingView's signal noise, filtered into conviction-rated trade alerts.

**Sub-headline** (lead paragraph):
> Every alert that fires gets a second pair of eyes from an LLM before it hits your Telegram. So you only look at the setups worth looking at.

**Live stat** (large display, exact text varies by state — see [hero-stat-fallback.md](./hero-stat-fallback.md) for the full state machine):
- Happy path: `{N}% win rate · last 90 days · {M} signals`
- 0-data path: `Track record building · {M} signals scored so far`
- Loading: `Track record loading…`
- Error: `Track record unavailable right now` *(plus a "Refresh" link)*

**Primary CTA**:
> Get started · free
linked to `/register`

**Secondary CTA** (text link, not button):
> See today's conviction picks →
linked to `/public/eod-report`

---

## What You Get

**Section eyebrow**:
> What lands in your Telegram

**Section headline** (h2):
> Four feeds. Built to be quiet.

**Section lead**:
> Most "AI trading" products fire on everything. This one fires when our Pine indicators see a real setup AND the LLM agrees it's worth your attention.

### Deliverable 1 — Telegram conviction channel

- Icon: `MessageCircle` (lucide)
- Status: **LIVE**
- Label: `Telegram · live channel`
- Headline: `HIGH-conviction alerts in your pocket`
- Body: `Every Pine-fired alert is rated by Claude Haiku against the SPY regime, your watchlist, and the setup's structural quality. Only the ones it grades HIGH or NORMAL hit the conviction channel — typically 3–10 per session, not 100.`
- CTA: *(none — Telegram channel is invite-on-signup)*

### Deliverable 2 — Live EOD recap

- Icon: `FileText`
- Status: **LIVE**
- Label: `Daily · 16:30 ET`
- Headline: `End-of-day debrief, every trading day`
- Body: `Every alert that fired today, every triage verdict, every outcome where the bars resolved. Shareable URL — bookmark today's, send it to a coach.`
- CTA: `See today's recap →` → `/public/eod-report`

### Deliverable 3 — AI Chart Critique

- Icon: `Eye`
- Status: **COMING SOON** (Spec 51)
- Label: `Beta · Pro tier`
- Headline: `Paste a chart, get a structured trade plan`
- Body: `Bias, key levels, entry, stop, first target, runner, invalidation — under 15 seconds. Built on the same engine that grades your Telegram alerts.`
- CTA: `Join waitlist` → `mailto:hello@tradingwithai.ai?subject=Chart%20Critique%20waitlist`

### Deliverable 4 — Pattern Education with live examples

- Icon: `BookOpen`
- Status: **COMING SOON** (Spec 52)
- Label: `Beta · all tiers`
- Headline: `Textbook patterns + today's real matches`
- Body: `Every pattern in the library shows you the setup, then shows you the live examples from this week on actual tickers. No more "imagine a bull flag" — we'll show you NVDA's, today, with the data.`
- CTA: `Join waitlist` → `mailto:hello@tradingwithai.ai?subject=Pattern%20Education%20waitlist`

---

## Proof Section

**Section eyebrow**:
> Live numbers, not testimonials

**Section headline** (h2):
> Every alert we've ever sent is public.

**Section lead**:
> No anonymous "9,576 engineers love us" claims. Just the actual signals, the actual outcomes, dated.

**Stat row** (3 cards, sourced from `/api/v1/intel/public-track-record?days=90`):

| Stat | Label |
|------|-------|
| `{N}%` | Win rate · last 90 days |
| `{M}` | Signals scored · last 90 days |
| `{K}` | Conviction picks today |

(0-data fallback uses the same logic as the hero stat — see hero-stat-fallback.md.)

**Proof CTA**:
> See every alert →
linked to `/track-record`

---

## Final CTA

**Headline** (h2):
> Stop reading every alert. Read the ones that matter.

**Body**:
> Free to start. Bring your own Pine indicators. Cancel any time. We don't even ask for a credit card on signup.

**Primary CTA**:
> Get started · free
linked to `/register`

---

## Footer

| Slot | Copy |
|------|------|
| Brand | TradeCoPilot · tradingwithai.ai |
| Year | © {currentYear} |
| Links (left → right) | `Pattern Library` · `Track Record` · `EOD Reports` · `Sign in` |
| Tagline (small, bottom) | Built on the V2 Pine + Triage stack. Spec 48 / 49 / 50. |

**No reference anywhere on the page to**:
- "AI scans the market" / "AI picks your trades"
- "5 AI pillars"
- `tradesignalwithai.com` (the legacy domain)
- `TradeSignal` as a brand
- Fake testimonials, fake user counts, unaffiliated company logos

---

## What this copy deliberately doesn't promise

- No claim of "X% return" or "average user makes $Y"
- No claim that the LLM is "right" — it's a "second pair of eyes," explicitly auxiliary
- No claim that the product is "the best" or "the leading" anything
- No claim about specific tickers or signals
