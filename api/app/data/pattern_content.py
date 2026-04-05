"""Per-rule educational content for Signal Library deep-dive pages.

Each pattern gets its own page at /learn/patterns/:pattern_id with:
- What it is, how to identify it, why it works
- Real win rate stats from production data
- Common mistakes, pro tips
"""

from __future__ import annotations

PATTERNS: dict[str, dict] = {
    "prior_day_low_reclaim": {
        "name": "Prior Day Low Reclaim",
        "category": "entry_signals",
        "difficulty": "beginner",
        "direction": "BUY",
        "tagline": "Price dips below yesterday's low then recovers — trapped sellers become buyers",
        "what_it_is": (
            "A Prior Day Low (PDL) reclaim happens when price dips below yesterday's low "
            "during the current session, then recovers and closes back above it. The dip "
            "below PDL triggers stop losses from yesterday's buyers, creating a liquidity "
            "flush. When price recovers above PDL, those stopped-out traders often re-enter, "
            "creating buying pressure."
        ),
        "how_to_identify": [
            "Price must dip at least 0.03% below yesterday's low (not just a wick touch)",
            "At least 2 of the last 3 bars must close above PDL (confirmation of reclaim)",
            "Price hasn't already run more than 2% above PDL (not chasing)",
            "Volume should increase on the reclaim bar (buyers stepping in)",
        ],
        "why_it_works": (
            "The PDL is a psychological level — traders who bought yesterday placed stops "
            "just below it. When price breaks below, those stops get triggered (forced selling). "
            "But if the break is shallow and price quickly recovers, it means the selling was "
            "exhausted and buyers are stronger than sellers at this level. The trapped shorts "
            "(who sold the breakdown) now need to cover, adding fuel to the bounce."
        ),
        "when_it_fails": (
            "PDL reclaims fail when the overall market is in a strong downtrend (bearish SPY "
            "regime). The bounce becomes a dead cat bounce — price reclaims PDL briefly, then "
            "rolls over and breaks it again with conviction. Also fails when volume on the "
            "reclaim is weak (no real buyer commitment) or when the stock is gapping down "
            "on news (structural breakdown, not a normal pullback)."
        ),
        "common_mistakes": [
            "Buying the first tick above PDL without waiting for confirmation (2/3 bars above)",
            "Not checking SPY regime — buying bounces in a bearish market is fighting the trend",
            "Setting stop too tight — needs room below PDL for noise",
            "Chasing a reclaim that already ran 1-2% above PDL",
        ],
        "pro_tips": [
            "The strongest reclaims happen in the first 2 hours of trading",
            "Look for a hammer or engulfing candle on the reclaim bar — shows buyer commitment",
            "If VWAP is above the reclaim level, the trade has institutional support",
            "Combine with MA confluence — PDL reclaim near 20EMA is a high-conviction setup",
        ],
    },
    "ma_bounce_20": {
        "name": "20 EMA Bounce",
        "category": "entry_signals",
        "difficulty": "beginner",
        "direction": "BUY",
        "tagline": "Price pulls back to the 20-day moving average and finds buyers",
        "what_it_is": (
            "A 20 EMA bounce occurs when a stock in an uptrend pulls back to its "
            "20-period exponential moving average and bounces. The 20 EMA represents "
            "roughly one month of average price — institutional traders use it as a "
            "reference point for 'buying the dip' in a healthy uptrend."
        ),
        "how_to_identify": [
            "Price must be within 0.4% of the 20 EMA (tight touch, not far away)",
            "The 20 EMA must be above the 50 EMA (confirms uptrend)",
            "The bounce bar should close above the 20 EMA (not just wick touch)",
            "Volume should ideally decrease on the pullback and increase on the bounce",
        ],
        "why_it_works": (
            "Moving averages are self-fulfilling prophecies — so many traders watch them "
            "that they become real support levels. The 20 EMA specifically attracts "
            "swing traders and algorithms that buy pullbacks in uptrends. When price "
            "touches the 20 EMA and holds, it confirms the uptrend is intact and buyers "
            "are defending the average."
        ),
        "when_it_fails": (
            "20 EMA bounces fail when the broader market shifts bearish (SPY breaks its "
            "own 20 EMA). They also fail when the stock's uptrend is exhausted — if price "
            "has bounced off the 20 EMA 4-5 times, each bounce gets weaker. Watch for "
            "decreasing volume on bounces and increasing volume on pullbacks as a warning."
        ),
        "common_mistakes": [
            "Buying before confirmation — the bar must close above the 20 EMA, not just touch it",
            "Ignoring the trend — if 20 EMA is below 50 EMA, this is NOT a bounce setup",
            "Setting target too aggressively — first target should be the prior swing high",
            "Not checking RSI — best bounces happen with RSI between 30-45 (oversold but not broken)",
        ],
        "pro_tips": [
            "200 EMA bounces are the highest conviction — they only happen a few times per year",
            "If the 20 and 50 EMA are converging, the bounce may fail (trend weakening)",
            "Volume ratio >1.5x on the bounce bar is a strong confirmation signal",
            "Best time for MA bounces is 10 AM - 12 PM when institutional order flow peaks",
        ],
    },
    "vwap_reclaim": {
        "name": "VWAP Reclaim",
        "category": "entry_signals",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Price drops below VWAP then recovers — institutional buyers re-entering",
        "what_it_is": (
            "VWAP (Volume Weighted Average Price) is the benchmark price that institutional "
            "traders use. A VWAP reclaim happens when price drops below VWAP in the morning, "
            "then recovers back above it with volume confirmation. This signals that "
            "institutional buyers consider the stock cheap relative to the day's average "
            "and are stepping in."
        ),
        "how_to_identify": [
            "Session low must occur in the first 60 minutes (morning dip)",
            "Price must recover at least 0.5% from the low within 15 minutes",
            "Volume on the recovery must be at least 1.2x average (institutional commitment)",
            "Price closes above VWAP (confirmed reclaim)",
        ],
        "why_it_works": (
            "VWAP is the price that large institutions measure their execution against. "
            "When price is below VWAP, institutions see it as 'cheap' — they get a better "
            "fill than the day's average. This creates natural buying pressure below VWAP. "
            "When enough buyers step in and price reclaims VWAP, it signals the morning "
            "selling is over and the stock is resuming its trend."
        ),
        "when_it_fails": (
            "VWAP reclaims fail when the selling is driven by a fundamental catalyst "
            "(earnings miss, downgrade, sector rotation). In these cases, price may briefly "
            "reclaim VWAP but the structural selling resumes. Also fails on low-volume "
            "reclaims — if volume isn't 1.2x+, the reclaim lacks conviction."
        ),
        "common_mistakes": [
            "Buying the moment price crosses VWAP without volume confirmation",
            "Not waiting for the 15-minute hold — early reclaims often fake out",
            "Ignoring the morning context — if SPY is also below VWAP, the reclaim is weaker",
            "Setting stop at VWAP (too tight) — stop should be below the session low",
        ],
        "pro_tips": [
            "VWAP reclaim has 100% win rate in our data — the volume gate makes it highly selective",
            "Best between 10-11 AM after the opening range establishes",
            "If price reclaims VWAP AND the 20 EMA on the same bar, conviction is very high",
            "Only fires for SPY, NVDA, and crypto — the volume gate is strict by design",
        ],
    },
    "consol_breakout_long": {
        "name": "Consolidation Breakout (Long)",
        "category": "breakout_signals",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Price breaks out of a multi-bar tight range — compressed energy releasing",
        "what_it_is": (
            "A consolidation breakout happens when price trades in a tight range for 3+ bars "
            "(15+ minutes), then breaks above the range high with volume. The tight range "
            "represents equilibrium between buyers and sellers. When one side wins, price "
            "moves decisively in that direction."
        ),
        "how_to_identify": [
            "At least 3 consecutive bars with a range of less than 0.3% (tight compression)",
            "Breakout bar closes above the consolidation high",
            "Volume on the breakout bar should be above average",
            "Prior trend direction supports the breakout (uptrend → long breakout stronger)",
        ],
        "why_it_works": (
            "Consolidation is the market catching its breath. Buyers and sellers are in "
            "equilibrium, and volatility contracts. When the range finally breaks, all the "
            "sidelined traders enter at once, creating a powerful directional move. The "
            "tighter and longer the consolidation, the more explosive the breakout."
        ),
        "when_it_fails": (
            "False breakouts happen when volume is weak or when the breakout occurs in the "
            "last hour of trading. Also fails when the broader market is range-bound — "
            "individual stock breakouts need market support to follow through."
        ),
        "common_mistakes": [
            "Chasing after the breakout has already moved 1%+ from the range",
            "Not checking if the breakout is supported by volume",
            "Trading breakouts in the last 30 minutes (low follow-through)",
            "Setting stop inside the consolidation range (should be below the range low)",
        ],
        "pro_tips": [
            "100% win rate in our data — the multi-bar requirement filters out noise",
            "15-minute consolidation breakouts are stronger than 5-minute ones",
            "If the consolidation forms just above VWAP or a key MA, the breakout is stronger",
            "Watch for decreasing volume during consolidation (coiling) then volume spike on break",
        ],
    },
    "prior_day_high_breakout": {
        "name": "Prior Day High Breakout",
        "category": "breakout_signals",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Price breaks above yesterday's high — today's buyers are stronger than yesterday's sellers",
        "what_it_is": (
            "A PDH breakout occurs when price closes above yesterday's high with conviction. "
            "The prior day high represents the ceiling from the previous session — breaking "
            "it means new demand is entering that wasn't there yesterday."
        ),
        "how_to_identify": [
            "Close must be at least 0.15% above PDH (not just a wick touch)",
            "Volume must be at least 0.8x average (confirmation of interest)",
            "Price must not have gapped above PDH at the open (that's not a breakout, it's a gap)",
            "The breakout bar should close in its upper half (buyers in control at close)",
        ],
        "why_it_works": (
            "PDH is where yesterday's sellers stopped buying. Breaking above it means "
            "today's buyers are willing to pay more than anyone paid yesterday. This "
            "often triggers a cascade: shorts covering, breakout traders entering, and "
            "algorithms detecting the new high."
        ),
        "when_it_fails": (
            "PDH breakouts fail when they occur on low volume (no real conviction) or "
            "in the last hour (insufficient time for follow-through). Also fails when "
            "SPY is rejecting its own PDH — individual stock breakouts rarely sustain "
            "without market support."
        ),
        "common_mistakes": [
            "Buying the first touch of PDH without waiting for a close above",
            "Not checking volume — a breakout on 0.5x volume is a fake",
            "Ignoring the morning gap — if price gapped above PDH at open, there's no breakout to buy",
            "Setting target too close — after a true breakout, let it run to T2",
        ],
        "pro_tips": [
            "92% win rate in our data — the volume + close confirmation makes it reliable",
            "Strongest before 11 AM when institutional order flow is highest",
            "If PDH breakout coincides with weekly high breakout, conviction doubles",
            "After breakout, PDH becomes support — if price retests and holds, add to position",
        ],
    },
    "session_low_bounce_vwap": {
        "name": "Session Low Bounce to VWAP",
        "category": "entry_signals",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Price bounces off the session low and targets VWAP — mean reversion play",
        "what_it_is": (
            "This pattern fires when the session low holds as support and price begins "
            "recovering toward VWAP. It's a mean-reversion setup — the idea is that price "
            "overshot to the downside and is snapping back toward fair value (VWAP)."
        ),
        "how_to_identify": [
            "Session low must have been tested and held (at least 2 touches)",
            "At least 60% of the last 18 bars must be above VWAP (not a breakdown)",
            "Price hasn't run too far above the session low (still near the bounce zone)",
            "Volume on the bounce bars should show buying interest",
        ],
        "why_it_works": (
            "VWAP acts as a magnet — price tends to revert toward it. When the session low "
            "holds and price starts recovering, traders who sold the low are now underwater "
            "and need to cover. Combined with VWAP attraction, this creates reliable upward "
            "pressure. 87% win rate in our data confirms this edge."
        ),
        "when_it_fails": (
            "Fails when the session low breaks on a retest — the second break is usually "
            "the real one. Also fails in strong downtrend days where VWAP keeps declining "
            "and the bounce target moves down with it."
        ),
        "common_mistakes": [
            "Buying before the session low is tested twice (need confirmation it holds)",
            "Using VWAP as stop (too tight) — stop should be below session low",
            "Not taking profits at VWAP — this is a mean-reversion trade, not a breakout",
            "Trading this in the last hour when VWAP is less meaningful",
        ],
        "pro_tips": [
            "87% win rate — one of the most reliable patterns in our system",
            "Best when combined with a support bounce (double confirmation)",
            "Take half at VWAP, let half run to PDH if momentum continues",
            "If the session low aligns with a prior day level, conviction increases",
        ],
    },
    "ema_rejection_short": {
        "name": "EMA Rejection Short",
        "category": "short_signals",
        "difficulty": "intermediate",
        "direction": "SHORT",
        "tagline": "Price rallies into an EMA overhead and gets rejected — sellers defending the ceiling",
        "what_it_is": (
            "An EMA rejection short fires when price rallies up to an overhead EMA (the MA "
            "is above price, acting as resistance) and gets rejected. The rejection bar "
            "closes in its lower half with a long upper wick, showing sellers overwhelmed "
            "buyers at that level."
        ),
        "how_to_identify": [
            "Price must rally into an overhead EMA (20, 50, or 100)",
            "The EMA is above price (acting as resistance, not support)",
            "Rejection bar closes in its lower 40% (sellers won the bar)",
            "Volume on the rejection bar confirms selling pressure",
        ],
        "why_it_works": (
            "In a downtrend, the EMA acts as a ceiling — traders who are short add to "
            "positions at the EMA, and failed longs bail out. The rejection confirms "
            "that the downtrend is intact and the rally was just a retracement, not a reversal."
        ),
        "when_it_fails": (
            "Fails when the stock has a catalyst that overwhelms technical levels (earnings "
            "beat, sector rotation). Also fails when SPY is breaking out — individual stock "
            "shorts rarely work when the market is ripping higher."
        ),
        "common_mistakes": [
            "Shorting before the rejection confirms (need bar close in lower 40%)",
            "Not having a stop above the EMA — if price closes above, the thesis is broken",
            "Shorting against a bullish SPY regime",
            "Holding too long — cover at the first support level (PDL, session low)",
        ],
        "pro_tips": [
            "85% win rate — very reliable when the setup is clean",
            "50 EMA rejection in a downtrend is the strongest variant",
            "If multiple EMAs are clustered near the same price, the resistance is stronger",
            "Best shorts happen before 2 PM — late session shorts can get squeezed into close",
        ],
    },
    "consol_breakout_short": {
        "name": "Consolidation Breakdown (Short)",
        "category": "short_signals",
        "difficulty": "intermediate",
        "direction": "SHORT",
        "tagline": "Price breaks down from a tight range — sellers overwhelm buyers",
        "what_it_is": (
            "The inverse of a consolidation breakout — price trades in a tight range then "
            "breaks below the range low with volume. Indicates sellers have won the "
            "equilibrium battle and price is heading lower."
        ),
        "how_to_identify": [
            "3+ bars in a tight range (less than 0.3% range)",
            "Breakdown bar closes below the consolidation low",
            "Volume confirms the breakdown",
            "Prior trend is down (breakdown aligned with momentum)",
        ],
        "why_it_works": (
            "Same mechanics as the long breakout but reversed. The tight range represents "
            "a pause in selling — when the range breaks down, it signals sellers are "
            "refreshed and ready to push lower. Longs trapped in the consolidation add "
            "fuel as they stop out."
        ),
        "when_it_fails": (
            "Fails on low volume breakdowns or when price quickly reclaims the range. "
            "Also fails near strong support levels (PDL, weekly low) where buyers step in."
        ),
        "common_mistakes": [
            "Shorting inside the range before the breakdown confirms",
            "Not covering at support levels (PDL, session low)",
            "Trading breakdowns in the last 30 minutes",
        ],
        "pro_tips": [
            "96% win rate — the tightest win rate of any pattern in our system",
            "Best when the consolidation forms just below a broken support level (resistance retest)",
            "Cover partial at first support, let rest run with trailing stop",
        ],
    },
    "vwap_loss": {
        "name": "VWAP Loss",
        "category": "short_signals",
        "difficulty": "beginner",
        "direction": "SHORT",
        "tagline": "Price drops below VWAP and stays under — institutional sentiment shifts bearish",
        "what_it_is": (
            "A VWAP loss occurs when price was trading above VWAP (bullish) then drops "
            "below and confirms with a close under VWAP. This signals that institutional "
            "traders are no longer supporting the stock at current levels."
        ),
        "how_to_identify": [
            "Price was above VWAP for the majority of the session (at least 5-6 bars)",
            "Price drops below VWAP and closes under it",
            "The breakdown bar shows conviction (close in lower 40%)",
            "Volume confirms the shift",
        ],
        "why_it_works": (
            "VWAP is the institutional benchmark. When price drops below it, every institution "
            "that bought above VWAP is now underwater. Some will sell to cut losses, adding "
            "to the selling pressure. The longer price was above VWAP before the loss, the "
            "more trapped longs there are."
        ),
        "when_it_fails": (
            "Fails near the end of day when VWAP becomes less meaningful. Also fails when "
            "the loss is a quick wick below VWAP that immediately recovers — need sustained "
            "close below."
        ),
        "common_mistakes": [
            "Shorting the first wick below VWAP without waiting for close confirmation",
            "Not checking if there's support just below VWAP (PDL, MA)",
            "Holding overnight — VWAP resets each session",
        ],
        "pro_tips": [
            "89% win rate — VWAP-based signals consistently outperform MA-based ones",
            "Strongest when price was above VWAP for 2+ hours then loses it suddenly",
            "Target: session low or PDL. Stop: above VWAP + small buffer",
        ],
    },
    "hourly_resistance_rejection_short": {
        "name": "Hourly Resistance Rejection",
        "category": "short_signals",
        "difficulty": "intermediate",
        "direction": "SHORT",
        "tagline": "Price rallies into hourly chart resistance and gets rejected",
        "what_it_is": (
            "This pattern detects when price rallies into a resistance level visible on the "
            "hourly chart and gets rejected. The hourly timeframe resistance is stronger than "
            "intraday levels because it represents multi-hour consensus on where sellers appear."
        ),
        "how_to_identify": [
            "Price rallies to within 0.3% of a horizontal resistance on the hourly chart",
            "Rejection bar closes in its lower 40% (sellers rejected the test)",
            "The resistance level has been tested at least once before",
            "Volume on the rejection confirms selling pressure",
        ],
        "why_it_works": (
            "Hourly resistance levels are more significant than 5-minute levels because "
            "they represent decisions by larger traders who operate on higher timeframes. "
            "When price fails at hourly resistance, it signals that the bigger players are "
            "not willing to let price through."
        ),
        "when_it_fails": (
            "Fails on strong momentum days where price powers through resistance. "
            "Also fails when the resistance level is 'weak' — only tested once with "
            "a brief touch rather than a sustained rejection."
        ),
        "common_mistakes": [
            "Shorting at resistance before seeing rejection confirmation",
            "Setting stop too tight — needs room above the resistance level",
            "Not checking the daily chart — if price is breaking out on the daily, hourly resistance will break",
        ],
        "pro_tips": [
            "82% win rate — multi-timeframe analysis adds conviction",
            "Strongest when the hourly resistance aligns with a daily level (PDH, MA)",
            "If price tests the same hourly resistance 3+ times without breaking, expect the break",
        ],
    },
    "multi_day_double_bottom": {
        "name": "Multi-Day Double Bottom",
        "category": "swing_trade",
        "difficulty": "advanced",
        "direction": "BUY",
        "tagline": "Same support zone tested twice across multiple days — strong base formation",
        "what_it_is": (
            "A multi-day double bottom occurs when a stock's daily swing low tests the same "
            "price zone (within 0.5%) on two separate days. This creates a visible 'W' pattern "
            "on the daily chart and signals that strong demand exists at that level."
        ),
        "how_to_identify": [
            "Two daily swing lows within 0.5% of each other",
            "The lows must be on different days (not same session)",
            "Price must recover at least partially after the second test",
            "Volume should show buying interest on the second bounce",
        ],
        "why_it_works": (
            "Double bottoms work because they prove demand is real. The first test could "
            "be coincidence, but the second test at the same level means buyers are "
            "deliberately defending that price. Institutions accumulate positions at "
            "double bottoms because the risk (stop below both lows) is well-defined."
        ),
        "when_it_fails": (
            "Fails when the third test of the same level breaks it — triple tests often "
            "fail because the buyers get exhausted. Also fails in bear markets where "
            "each bounce creates a lower high (descending triangle into breakdown)."
        ),
        "common_mistakes": [
            "Buying immediately at the second low without waiting for a bounce confirmation",
            "Setting stop too tight — needs to be below BOTH lows with buffer",
            "Not sizing down for swing trades (wider stops require smaller position)",
            "Entering on Friday (2 days of overnight risk before next session)",
        ],
        "pro_tips": [
            "65% win rate but larger R:R — swing trades aim for 3:1+ reward",
            "Strongest when the double bottom forms at a weekly support level",
            "The 'W' pattern is confirmed when price breaks above the middle peak",
            "If RSI shows divergence (price makes equal low but RSI makes higher low), conviction doubles",
        ],
    },
}

# Order for display
PATTERN_ORDER = [
    "vwap_reclaim",
    "consol_breakout_long",
    "consol_breakout_short",
    "prior_day_high_breakout",
    "session_low_bounce_vwap",
    "prior_day_low_reclaim",
    "vwap_loss",
    "ema_rejection_short",
    "ma_bounce_20",
    "vwap_bounce",  # stub — not fully written
    "hourly_resistance_rejection_short",
    "multi_day_double_bottom",
]
