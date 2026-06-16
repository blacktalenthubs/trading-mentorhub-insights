# Landing page — simplify for newcomers

**The problem you named:** the page explains *the machinery*, not *the value*. A
friend who's never heard "EMA bounce" hits jargon in the first breath and bounces.

**Current hero subhead (line 120):**
> "Setups graded A / B / C by volume + VWAP slope. Real outcomes computed from actual
> post-fire price action — not synthetic win rates. A Friday AI retro of what worked."

Four pieces of jargon (A/B/C, VWAP slope, post-fire price action, synthetic win rates)
before the reader knows what they'd *get*. The headline is great
("Your trading desk for the hours you're not at one") — keep it. Fix everything under it.

---

## The 4 principles
1. **Lead with the outcome, not the mechanism.** "Know when to buy and sell," not
   "graded by VWAP slope."
2. **One promise, repeated.** Buy strength at support, never chase — fewer, better
   signals. That's the whole pitch.
3. **Show, don't tell.** The sample alert card (already on the page!) does more than a
   paragraph. Lead with it.
4. **Jargon → only after the value lands.** Keep A/B/C, MFE/MAE etc. for a "for the
   nerds" section near the bottom, not the hero.

---

## The 10-second explainer (for the very top / a friend)
> **BusyTradersDesk tells you when to buy and sell.** When a stock sets up a quality
> trade, you get an alert with the exact entry, a stop so you know your risk, and a
> target. It watches the market all day so you don't have to.

---

## Hero rewrite (drop-in)
**Keep** the headline + the sample alert card. **Replace** the subhead + the 3 metrics:

**Subhead (was the jargon line):**
> Get an alert the moment a quality setup forms — with the exact price to buy, where
> to get out if you're wrong, and your target. No staring at charts. No guessing.
> Just your plan, ready to act on.

**The 3 hero metrics (was "A/B/C · Public · MFE/MAE"):**
| was | →  now (plain) |
|---|---|
| `A / B / C` — Setup grade per alert | **Entry · Stop · Target** — every alert |
| `Public` — Daily EOD reports | **Real-time** — the moment it fires |
| `MFE / MAE` — Real outcomes | **1 rule** — buy support, never chase |

---

## Section-by-section reframe (the page has ~10 `<h2>` sections)
Rewrite each headline as a **benefit**, body in **plain English**:

| Keep the idea, change the words |
|---|
| **"What you get"** — a live feed of trade alerts, each with entry/stop/target. *(Show 2–3 sample cards.)* |
| **"How it works"** — 3 steps: (1) we watch the market, (2) a setup forms → you get an alert, (3) you decide and trade your plan. |
| **"Why it's different"** — it only flags **support in an uptrend** (buy strength), never chases breakouts → fewer, higher-quality alerts. Risk is built in: every alert has a stop. |
| **"For people with day jobs"** — runs all day so you don't have to watch; alerts come to your phone (Telegram / push). |
| **"Proof"** — keep the live track record + "see yesterday's EOD report" (this is your trust builder — keep it prominent). |
| **"For the data nerds"** *(near bottom, opt-in)* — *here* you can mention A/B/C grades, volume×, VWAP slope, MFE/MAE real outcomes. Newcomers skip it; pros love it. |

---

## What I did vs. what's next
- **Drafted** this plan + the exact hero copy (above).
- **Implemented** a first pass of the hero subhead + metrics on branch
  `landing-simplify-hero` (a **draft PR — not merged**), so you can *see* it rendered
  and react. Everything below the hero is left for your direction (the section bodies
  are subjective — I didn't want to rewrite your whole public page blind).
- **Next, on your nod:** roll the plain-language reframe through the sections above,
  add the 10-second explainer band at the very top, and move the jargon to a
  bottom "for the data nerds" strip.

> Deliberately conservative: the landing page is your storefront + carries your taste
> (Apple-tight). I'd rather hand you a draft hero + a clear plan than redesign the
> whole thing while you sleep and miss the mark.
