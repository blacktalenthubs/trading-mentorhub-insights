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
    "ma_bounce_50": {
        "name": "50 EMA Bounce",
        "category": "entry_signals",
        "difficulty": "beginner",
        "direction": "BUY",
        "tagline": "Price pulls back to the 50-day EMA and finds institutional support",
        "what_it_is": (
            "A 50 EMA bounce occurs when a stock in a medium-term uptrend pulls back "
            "to its 50-period exponential moving average. The 50 EMA is watched by "
            "institutional traders and fund managers as a key trend-following indicator."
        ),
        "how_to_identify": [
            "Price must be within 0.5% of the 50 EMA",
            "The 50 EMA should be rising or flat (not falling)",
            "The bounce bar closes above the 50 EMA",
            "RSI should be between 35-50 (oversold enough but not broken)",
        ],
        "why_it_works": (
            "The 50 EMA represents roughly 2.5 months of average price. Institutional "
            "investors use it as a 'healthy correction' buying level. When price touches "
            "the 50 EMA in an uptrend, algorithms and fund managers add to positions."
        ),
        "when_it_fails": (
            "Fails when the 50 EMA breaks decisively on high volume — this signals a "
            "trend change, not a pullback. Also fails when the 20 EMA has already crossed "
            "below the 50 EMA (death cross forming)."
        ),
        "common_mistakes": [
            "Buying the first touch without waiting for a close above the MA",
            "Not checking if the 50 EMA is still rising (flat or falling = weaker signal)",
            "Ignoring the broader market — if SPY is below its 50 EMA, individual bounces are riskier",
        ],
        "pro_tips": [
            "50 EMA bounces are best for swing trades — hold for days, not minutes",
            "If the 200 EMA is nearby as well, it's a high-conviction 'confluence' bounce",
            "Volume should dry up on the pullback and increase on the bounce day",
        ],
    },
    "prior_day_low_bounce": {
        "name": "Prior Day Low Bounce",
        "category": "entry_signals",
        "difficulty": "beginner",
        "direction": "BUY",
        "tagline": "Price approaches yesterday's low and holds — buyers defend the level",
        "what_it_is": (
            "A PDL bounce occurs when price approaches the prior day low but doesn't "
            "break it. Instead, buyers step in and price bounces off the level. Unlike "
            "a PDL reclaim (which requires breaking below first), a bounce shows the "
            "level is being defended proactively."
        ),
        "how_to_identify": [
            "Bar low within 0.2% of prior day low",
            "No bar broke below PDL (held above)",
            "Last several bars all closed above PDL",
            "Price hasn't already run too far above",
        ],
        "why_it_works": (
            "Buyers who entered yesterday placed stops below PDL. When price approaches "
            "but doesn't break, it shows the support is genuine — not just stops being "
            "hunted. Proactive defense of a level is stronger than a stop-loss flush."
        ),
        "when_it_fails": (
            "Fails when the bounce is weak (small volume, no conviction candle) and "
            "price eventually breaks below on the next attempt."
        ),
        "common_mistakes": [
            "Confusing a brief pause near PDL with a genuine bounce",
            "Not waiting for a confirmation close above PDL",
        ],
        "pro_tips": [
            "A PDL bounce with a hammer candle is the highest-conviction version",
            "If VWAP is above PDL, the bounce has stronger institutional backing",
        ],
    },
    "inside_day_breakout": {
        "name": "Inside Day Breakout",
        "category": "entry_signals",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Yesterday's range was inside the prior day's range — coiled spring ready to explode",
        "what_it_is": (
            "An inside day is when the entire day's range fits within the prior day's range "
            "(lower high and higher low). This compression represents indecision — both buyers "
            "and sellers are waiting. When price breaks above the inside day's high, the "
            "compression unwinds and a directional move begins."
        ),
        "how_to_identify": [
            "Yesterday's high was lower than the day before's high",
            "Yesterday's low was higher than the day before's low",
            "Today's price breaks above yesterday's high with volume",
            "The breakout bar should close near its high (momentum)",
        ],
        "why_it_works": (
            "Inside days compress volatility. Traders on both sides are positioned just "
            "outside the range — breakout triggers a cascade of orders. The tighter the "
            "inside day, the more explosive the breakout tends to be."
        ),
        "when_it_fails": (
            "Fails when the breakout has no volume (false breakout) or when the market "
            "regime is choppy — inside day breakouts need trend to sustain."
        ),
        "common_mistakes": [
            "Trading inside day breakdowns in bull markets (go with the trend)",
            "Not setting stop below the inside day low (the trade is wrong if price re-enters the range)",
        ],
        "pro_tips": [
            "Inside days after a strong trend move are the highest probability",
            "Multiple consecutive inside days (2-3) create even tighter coils",
            "The best inside day breakouts gap above the range at the open",
        ],
    },
    "opening_range_breakout": {
        "name": "Opening Range Breakout",
        "category": "entry_signals",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "First 30 minutes set the range — breakout above signals the day's direction",
        "what_it_is": (
            "The opening range is the high and low established in the first 30 minutes "
            "of trading. When price breaks above this range with volume, it signals "
            "that buyers have taken control and the day's trend is likely higher."
        ),
        "how_to_identify": [
            "Wait for the first 30 minutes to establish the range",
            "Price must break above the opening range high",
            "Volume on the breakout bar should exceed the opening range average",
            "Breakout bar should close near its high",
        ],
        "why_it_works": (
            "The first 30 minutes represent the battle between overnight positions "
            "and fresh day orders. Once the range is established and broken, the "
            "direction tends to persist because trapped shorts cover and momentum "
            "traders pile in."
        ),
        "when_it_fails": (
            "Fails when the overall market is trendless (choppy). Also fails when "
            "the opening range is too wide (> 1.5 ATR) — the breakout has less room to run."
        ),
        "common_mistakes": [
            "Trading ORB before 30 minutes are up (range not established)",
            "Not accounting for a wide opening range (reduces R:R)",
        ],
        "pro_tips": [
            "Narrow opening ranges (< 0.5 ATR) produce the best breakouts",
            "The best ORBs align with the daily bias (gap up + breakout = strong)",
        ],
    },
    "gap_fill": {
        "name": "Gap Fill",
        "category": "entry_signals",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Price gaps down at open then fills back to yesterday's close — trapped sellers exit",
        "what_it_is": (
            "A gap fill occurs when a stock opens below the prior day's close (gap down) "
            "and then rallies back up to fill the gap. Gaps represent emotional reactions "
            "to overnight news — filling the gap means the reaction was overdone."
        ),
        "how_to_identify": [
            "Stock opens at least 0.5% below yesterday's close",
            "Price starts recovering toward yesterday's close during the session",
            "Volume increases on the recovery (real buying, not dead cat bounce)",
        ],
        "why_it_works": (
            "Most gaps fill within 1-3 days. Overnight sellers who panicked realize "
            "the news wasn't as bad as feared. Short sellers who faded the gap start "
            "covering. The combination drives price back toward the prior close."
        ),
        "when_it_fails": (
            "Fails when the gap is caused by fundamental news (earnings miss, FDA "
            "rejection) — structural gaps don't fill quickly."
        ),
        "common_mistakes": [
            "Buying the open of a gap down without waiting for a base to form",
            "Not distinguishing between technical gaps (fill) and news gaps (don't fill)",
        ],
        "pro_tips": [
            "Gap fills work best when the stock is in an overall uptrend",
            "Watch for a 15-minute base formation before entering",
        ],
    },
    "support_breakdown": {
        "name": "Support Breakdown",
        "category": "short_signals",
        "difficulty": "intermediate",
        "direction": "SHORT",
        "tagline": "Key support level breaks with volume — trend reversal confirmed",
        "what_it_is": (
            "A support breakdown occurs when price closes below a key support level "
            "(prior day low, nearest support, or multi-day swing low) with conviction "
            "volume. This signals that buyers can no longer defend the level."
        ),
        "how_to_identify": [
            "Close below the support level (not just a wick)",
            "Volume at least 1.5x average (conviction)",
            "Close in the lower 20% of the bar range (sellers in control)",
        ],
        "why_it_works": (
            "When support breaks on high volume, stops below the level get triggered "
            "(forced selling), and breakout short sellers enter. The combination creates "
            "a cascade that drives price lower quickly."
        ),
        "when_it_fails": (
            "Fails when the breakdown is on low volume (no conviction) or when the "
            "broader market is bullish — breakdowns in bull markets often reverse."
        ),
        "common_mistakes": [
            "Shorting the first wick below support without waiting for a close",
            "Not checking the broader trend — shorting breakdowns in a bull market",
        ],
        "pro_tips": [
            "The best breakdowns happen in the first 2 hours and on gap-down days",
            "If the breakdown aligns with a bearish SPY regime, conviction is highest",
        ],
    },
    "session_high_double_top": {
        "name": "Session High Double Top",
        "category": "short_signals",
        "difficulty": "intermediate",
        "direction": "SHORT",
        "tagline": "Session high tested twice and rejected — sellers control resistance",
        "what_it_is": (
            "A session high double top occurs when the day's high is tested twice "
            "during the session and rejected both times. The double rejection creates "
            "a clear resistance ceiling and signals that sellers are stronger at that level."
        ),
        "how_to_identify": [
            "Session high tested at least twice with a pullback between tests",
            "The second test fails to break above the first high",
            "Last bar closes in the lower 50% of its range (rejection)",
        ],
        "why_it_works": (
            "Double tops at session highs show supply is concentrated at that level. "
            "Buyers tried twice to push through and failed — this exhaustion leads to "
            "profit-taking and short entries from pattern traders."
        ),
        "when_it_fails": (
            "Fails when the third attempt breaks through — persistent buyers eventually "
            "overwhelm sellers. Also fails in strong uptrends where double tops are "
            "just pauses before continuation."
        ),
        "common_mistakes": [
            "Shorting after only one test (need at least two)",
            "Not setting a stop above the double top high",
        ],
        "pro_tips": [
            "Double tops that form at a daily level (PDH, weekly high) are highest conviction",
            "Volume should decrease on the second test — shows buyer exhaustion",
        ],
    },
    "pdh_failed_breakout": {
        "name": "Prior Day High Failed Breakout",
        "category": "short_signals",
        "difficulty": "intermediate",
        "direction": "SHORT",
        "tagline": "Price breaks above yesterday's high then fails — trapped longs fuel the reversal",
        "what_it_is": (
            "A PDH failed breakout happens when price breaks above the prior day high "
            "but fails to hold and closes back below it. Breakout buyers who chased the "
            "move are now trapped above resistance."
        ),
        "how_to_identify": [
            "Price must have broken above prior day high",
            "Price then closes back below prior day high (failed to hold)",
            "The failure bar shows selling pressure (close in lower half of range)",
        ],
        "why_it_works": (
            "Failed breakouts are powerful reversal signals because they trap aggressive "
            "buyers above resistance. When the breakout fails, those buyers' stops get "
            "triggered below PDH, adding selling pressure to the reversal."
        ),
        "when_it_fails": (
            "Fails when the pullback below PDH is brief and price quickly reclaims — "
            "this is a re-test, not a failure."
        ),
        "common_mistakes": [
            "Shorting too early — wait for a close below PDH, not just a wick",
            "Not having a stop above the breakout high",
        ],
        "pro_tips": [
            "The best failed breakouts happen late in the session (no time to recover)",
            "If the failure happens on decreasing volume, it's more likely to stick",
        ],
    },
    "session_low_double_bottom": {
        "name": "Session Low Double Bottom",
        "category": "entry_signals",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Session low tested twice and held — strong demand zone confirmed",
        "what_it_is": (
            "An intraday double bottom forms when the session low is tested twice "
            "and bounces both times. The 'W' pattern on intraday charts signals that "
            "a floor has been established and buyers are defending aggressively."
        ),
        "how_to_identify": [
            "Two tests of the same low zone (within 0.3%)",
            "Recovery between the two tests (price pulls back up)",
            "Volume increases on the second bounce (buyer conviction)",
        ],
        "why_it_works": (
            "The first test could be coincidental support. The second test at the same "
            "level proves the demand is real. Short sellers who held through both tests "
            "start covering, adding buying fuel."
        ),
        "when_it_fails": (
            "Fails when the third test of the level breaks through — triple bottoms "
            "at the same intraday level often fail."
        ),
        "common_mistakes": [
            "Not waiting for the second test — the first bounce could be a dead cat",
            "Setting stop right at the double bottom level (needs cushion below)",
        ],
        "pro_tips": [
            "Double bottoms at a daily support level (PDL, 200MA) are highest conviction",
            "RSI divergence on the second test (higher RSI low) confirms the pattern",
        ],
    },
    "weekly_high_breakout": {
        "name": "Weekly High Breakout",
        "category": "entry_signals",
        "difficulty": "advanced",
        "direction": "BUY",
        "tagline": "Price breaks above last week's high — multi-day momentum confirmed",
        "what_it_is": (
            "A weekly high breakout occurs when price closes above the prior week's "
            "high. This is a significant structural breakout because weekly levels "
            "are watched by swing traders and institutions."
        ),
        "how_to_identify": [
            "Price must close above the prior week's high (not just a wick)",
            "Volume should be above average on the breakout day",
            "SPY/market should be supportive (not breaking down)",
        ],
        "why_it_works": (
            "Weekly levels represent larger timeframe consensus. Breaking a weekly "
            "high means the trend is strong enough to push through a level that "
            "held all of last week. Swing traders and algorithms use weekly levels "
            "for position entries."
        ),
        "when_it_fails": (
            "Fails when the breakout is on light volume or when the broader "
            "market is at resistance (weekly high breakouts in a bearish market)."
        ),
        "common_mistakes": [
            "Buying the intraday break without waiting for a daily close above",
            "Not accounting for the weekly range — if last week was huge, the breakout may stall",
        ],
        "pro_tips": [
            "Weekly breakouts that align with monthly uptrends are the strongest",
            "If the stock consolidated near the weekly high for 2-3 days, the breakout has more power",
        ],
    },
    "intraday_support_bounce": {
        "name": "Intraday Support Bounce",
        "category": "entry_signals",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Hourly swing low holds and price bounces — short-term demand zone confirmed",
        "what_it_is": (
            "An intraday support bounce occurs when price pulls back to a level that "
            "previously acted as an hourly swing low and bounces. These are short-term "
            "support levels created during the current session."
        ),
        "how_to_identify": [
            "A prior hourly low must have bounced at least twice",
            "Price approaches within proximity of that level",
            "The bounce bar closes in the upper half of its range",
        ],
        "why_it_works": (
            "Intraday support levels form because buyers remember where they previously "
            "bought. When price returns to the same level, the same buyers add to "
            "positions. Short sellers also cover at known support."
        ),
        "when_it_fails": (
            "Fails when the level has been tested too many times (3+) — each test "
            "weakens support as buyers run out of capital to deploy."
        ),
        "common_mistakes": [
            "Trading every minor bounce — focus on levels tested at least twice",
            "Not having a clear stop below the support level",
        ],
        "pro_tips": [
            "Strongest bounces happen at support levels that align with a VWAP or MA",
            "If the market is trending up, intraday support bounces have higher win rates",
        ],
    },
    "swing_rsi_30_bounce": {
        "name": "RSI 30 Bounce (Swing)",
        "category": "swing_trade",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Daily RSI crosses back above 30 — oversold reversal for multi-day hold",
        "what_it_is": (
            "An RSI 30 bounce is a swing trade entry that fires when the daily RSI14 "
            "crosses above 30 after being below. This indicates the stock was oversold "
            "and selling pressure is exhausting — a mean reversion trade."
        ),
        "how_to_identify": [
            "Daily RSI14 was below 30 yesterday",
            "Daily RSI14 is now at or above 30 today",
            "Daily close in the upper 50% of the day's range (buying pressure)",
        ],
        "why_it_works": (
            "RSI below 30 means the stock has been sold off heavily. When RSI crosses "
            "back above 30, it signals the selling is done and buyers are stepping in. "
            "Mean reversion from RSI 30 to RSI 45-50 typically represents a 3-8% move."
        ),
        "when_it_fails": (
            "Fails in genuine downtrends where RSI stays below 30 for extended periods. "
            "Also fails when the oversold condition is caused by fundamental news (earnings, "
            "downgrade) rather than technical selling."
        ),
        "common_mistakes": [
            "Buying while RSI is still falling below 30 (wait for the cross back above)",
            "Holding too long — the target is RSI 45-50, not RSI 70",
        ],
        "pro_tips": [
            "RSI 30 bounces near the 200-day MA are the highest conviction",
            "If weekly RSI is also oversold, the bounce tends to be larger",
            "Use daily close as your stop — not intraday wicks",
        ],
    },
    "swing_200ma_hold": {
        "name": "200 MA Hold (Swing)",
        "category": "swing_trade",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Price wicks to 200-day moving average and holds — institutional floor",
        "what_it_is": (
            "A 200 MA hold is a swing entry when price pulls back to the 200-day moving "
            "average and closes above it. The 200 MA is the most watched institutional "
            "level — fund managers use it as the dividing line between bull and bear markets."
        ),
        "how_to_identify": [
            "Daily low wicks to within 1% of the 200 MA",
            "Daily close remains above the 200 MA",
            "Stock was previously above the 200 MA (pullback, not breakdown)",
        ],
        "why_it_works": (
            "The 200 MA is where institutional capital deploys. When a stock in a "
            "long-term uptrend pulls back to its 200 MA, pension funds, ETFs, and "
            "algorithmic systems buy the dip. The stop is clearly defined (close below)."
        ),
        "when_it_fails": (
            "Fails when the stock breaks below the 200 MA on high volume — this signals "
            "a trend change. Also fails when the 200 MA is declining (stock in a downtrend "
            "already)."
        ),
        "common_mistakes": [
            "Buying at the 200 MA when the MA is falling (bearish structure)",
            "Setting an intraday stop instead of a daily close stop",
        ],
        "pro_tips": [
            "200 MA holds with RSI below 40 are the best risk/reward setups",
            "Target the 50 MA or 20 MA for the first profit take",
            "This is a swing trade — hold for days/weeks, not hours",
        ],
    },
    "swing_weekly_support": {
        "name": "Weekly Support Hold (Swing)",
        "category": "swing_trade",
        "difficulty": "advanced",
        "direction": "BUY",
        "tagline": "Prior week's low defended on daily close — multi-week support confirmed",
        "what_it_is": (
            "A weekly support hold fires when price approaches the prior week's low "
            "and closes above it. Weekly levels are significant because they represent "
            "the consensus of an entire week of trading."
        ),
        "how_to_identify": [
            "Daily low within 1% of prior week low",
            "Daily close remains above prior week low",
            "Close in upper 50% of daily range (buyers defending)",
        ],
        "why_it_works": (
            "Weekly levels are watched by larger timeframe traders — swing traders, "
            "position traders, and institutions. A defense of the prior week low means "
            "the larger trend is intact and the pullback was healthy."
        ),
        "when_it_fails": (
            "Fails when the weekly low is part of a larger downtrend — the defense "
            "is temporary before the next leg lower."
        ),
        "common_mistakes": [
            "Not checking the monthly trend — weekly support in a monthly downtrend is weak",
        ],
        "pro_tips": [
            "Weekly support near a 200 MA or monthly level = highest conviction",
            "Target the prior week high for T1",
        ],
    },
    "ema_bounce_20": {
        "name": "EMA 20 Bounce (Intraday)",
        "category": "entry_signals",
        "difficulty": "beginner",
        "direction": "BUY",
        "tagline": "5-minute price bounces off the 20 EMA during a trending session",
        "what_it_is": (
            "An intraday EMA 20 bounce occurs on 5-minute bars when price pulls back "
            "to the 20 EMA and bounces during a trending session. Day traders use the "
            "intraday 20 EMA as a pullback entry in momentum moves."
        ),
        "how_to_identify": [
            "Price in an intraday uptrend (making higher highs)",
            "5-min bar touches the 20 EMA and closes above it",
            "The 20 EMA is rising",
        ],
        "why_it_works": (
            "In a trending session, the 20 EMA acts as a moving support floor. "
            "Algorithmic traders and scalpers buy pullbacks to this level, creating "
            "a self-reinforcing pattern."
        ),
        "when_it_fails": (
            "Fails when the trend is weakening — multiple EMA tests in a short period "
            "indicate exhaustion, not strength."
        ),
        "common_mistakes": [
            "Buying every EMA touch — the first 2-3 are high probability, later ones are risky",
        ],
        "pro_tips": [
            "The first touch of the session's 20 EMA is usually the strongest bounce",
            "If volume decreases on the pullback and increases on the bounce, that's confirmation",
        ],
    },
    "morning_low_breakdown": {
        "name": "Morning Low Breakdown",
        "category": "short_signals",
        "difficulty": "intermediate",
        "direction": "SHORT",
        "tagline": "First hour's low breaks — session direction shifts bearish",
        "what_it_is": (
            "A morning low breakdown occurs when the low established in the first "
            "trading hour is broken with volume. The first hour sets the tone — when "
            "its low breaks, it signals that the initial buying was exhausted."
        ),
        "how_to_identify": [
            "First hour's low must have been tested or held for several bars",
            "Price breaks below the opening range low on volume >= 1.2x average",
            "Breakdown bar closes near its low",
        ],
        "why_it_works": (
            "The first hour represents the strongest conviction of the day. When "
            "its low breaks, buyers who entered early are now underwater and forced "
            "to sell, accelerating the move lower."
        ),
        "when_it_fails": (
            "Fails when the broader market is bullish and the breakdown is bought "
            "up quickly — look for SPY regime confirmation."
        ),
        "common_mistakes": [
            "Shorting before the breakdown is confirmed with volume",
        ],
        "pro_tips": [
            "Morning low breakdowns on gap-down days are the strongest",
            "If VWAP is above the morning low, the breakdown has more room to run",
        ],
    },
    "vwap_bounce": {
        "name": "VWAP Bounce",
        "category": "entry_signals",
        "difficulty": "intermediate",
        "direction": "BUY",
        "tagline": "Price pulls back to VWAP and bounces — institutional average price holds as support",
        "what_it_is": (
            "A VWAP bounce occurs when price pulls back to the Volume Weighted Average "
            "Price and bounces. VWAP represents the average price institutions have "
            "traded at during the session — it acts as fair value."
        ),
        "how_to_identify": [
            "Price was above VWAP, pulls back to touch it",
            "Bounce bar closes above VWAP",
            "The pullback to VWAP is on declining volume (healthy pullback)",
        ],
        "why_it_works": (
            "Institutions benchmark their fills against VWAP. When price returns to "
            "VWAP from above, institutions see it as a chance to add at fair value. "
            "Algorithmic execution programs trigger buys at VWAP."
        ),
        "when_it_fails": (
            "Fails when price has been below VWAP for most of the session — the "
            "VWAP touch is resistance, not support."
        ),
        "common_mistakes": [
            "Not checking whether price came from above or below VWAP",
            "VWAP bounces late in the session are weaker than morning ones",
        ],
        "pro_tips": [
            "First VWAP touch of the session has the highest bounce rate",
            "VWAP bounces above a rising 20 EMA are the best setups",
        ],
    },
    "ma_bounce_200": {
        "name": "200 EMA Bounce (Intraday)",
        "category": "entry_signals",
        "difficulty": "advanced",
        "direction": "BUY",
        "tagline": "Price bounces off the 200-period EMA on intraday charts — major trend support",
        "what_it_is": (
            "An intraday 200 EMA bounce occurs when price pulls back to the 200-period "
            "EMA on 5-minute charts. The 200 EMA on intraday is a major structural level "
            "that represents the entire day's trend."
        ),
        "how_to_identify": [
            "Price within 0.4% of the 200 EMA on 5-min bars",
            "The 200 EMA is flat or rising (not falling)",
            "Bounce bar closes above the 200 EMA",
        ],
        "why_it_works": (
            "The 200 EMA on intraday charts is the last line of defense for the day's "
            "trend. A bounce here means the trend is still intact. Breaking it signals "
            "a potential trend reversal."
        ),
        "when_it_fails": "Fails when the trend has already broken down and the 200 EMA is declining.",
        "common_mistakes": [
            "Trading 200 EMA bounces in a clearly bearish session",
        ],
        "pro_tips": [
            "200 EMA bounces that align with a daily support level are highest conviction",
        ],
    },
}

# Order for display
PATTERN_ORDER = [
    # Entry signals — BUY
    "prior_day_low_reclaim",
    "prior_day_low_bounce",
    "ma_bounce_20",
    "ma_bounce_50",
    "ma_bounce_200",
    "ema_bounce_20",
    "vwap_reclaim",
    "vwap_bounce",
    "consol_breakout_long",
    "prior_day_high_breakout",
    "weekly_high_breakout",
    "inside_day_breakout",
    "opening_range_breakout",
    "gap_fill",
    "session_low_double_bottom",
    "session_low_bounce_vwap",
    "intraday_support_bounce",
    # Short signals
    "ema_rejection_short",
    "consol_breakout_short",
    "support_breakdown",
    "session_high_double_top",
    "pdh_failed_breakout",
    "morning_low_breakdown",
    "vwap_loss",
    "hourly_resistance_rejection_short",
    # Swing trades
    "multi_day_double_bottom",
    "swing_rsi_30_bounce",
    "swing_200ma_hold",
    "swing_weekly_support",
]
