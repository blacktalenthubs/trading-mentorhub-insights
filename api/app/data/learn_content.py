"""Educational content for the Signal Library.

Each category has structured content explaining the trading pattern family,
why it works from a market structure perspective, when it fails, and pro tips.
"""

from __future__ import annotations

CATEGORIES: dict[str, dict] = {
    "entry_signals": {
        "name": "Entry Signals",
        "difficulty": "beginner",
        "tagline": "Buy when price bounces off support",
        "overview": (
            "Entry signals fire when price pulls back to a known support level "
            "and shows signs of bouncing. These levels include moving averages "
            "(20, 50, 100, 200 EMA/SMA), prior day lows, VWAP, Fibonacci "
            "retracements, and multi-day double bottoms. The system waits for "
            "price to touch the level AND show a bounce — not just touch it."
        ),
        "why_it_works": (
            "Institutions and algorithms place buy orders at predictable levels. "
            "The 20 EMA on a daily chart represents roughly one month of average price — "
            "when a stock in an uptrend pulls back to it, large buyers step in because "
            "the risk/reward is favorable. The same logic applies to prior day lows "
            "(traders who bought yesterday defend their positions) and VWAP (institutional "
            "benchmark). These aren't magic lines — they're levels where real money acts."
        ),
        "when_it_fails": (
            "In strong downtrends, bounces get sold into — price touches the 20 EMA, "
            "bounces 0.3%, then rolls over and breaks it. The system mitigates this by "
            "checking SPY regime (bearish regime demotes confidence), volume confirmation, "
            "and requiring the bounce to hold for multiple bars. But no filter is perfect — "
            "some bounces fail. That's why every signal has a stop loss."
        ),
        "how_to_read": [
            "Look for price pulling back into a rising moving average on the daily chart",
            "Volume should decrease on the pullback (sellers exhausted) and increase on the bounce",
            "RSI between 30-45 on the pullback is ideal — oversold but not broken",
            "The bounce bar should close in its upper half (buyers took control by close)",
        ],
        "pro_tips": [
            "MA200 bounces are the highest conviction — they only happen a few times per year per stock",
            "Double bottoms are stronger when the second test is on lower volume (less selling pressure)",
            "Always check SPY first — buying bounces in a bearish market regime is fighting the trend",
            "The best bounces happen in the first 2 hours of trading when volume is highest",
        ],
        "key_alert_types": [
            {"type": "ma_bounce_20", "name": "MA20 Bounce", "desc": "Price pulls back to 20-day moving average and bounces with volume confirmation"},
            {"type": "ma_bounce_50", "name": "MA50 Bounce", "desc": "Price tests the 50-day moving average — a key institutional support level"},
            {"type": "prior_day_low_reclaim", "name": "Prior Day Low Reclaim", "desc": "Price dips below yesterday's low then reclaims above it — trapped sellers become buyers"},
            {"type": "multi_day_double_bottom", "name": "Double Bottom", "desc": "Price tests the same support zone twice across multiple days and holds — strong base formation"},
            {"type": "fib_retracement_bounce", "name": "Fibonacci Bounce", "desc": "Price retraces to a key Fibonacci level (38.2%, 50%, 61.8%) and bounces"},
            {"type": "vwap_reclaim", "name": "VWAP Reclaim", "desc": "Price drops below VWAP then reclaims it — institutional buyers re-entering"},
        ],
    },
    "breakout_signals": {
        "name": "Breakout Signals",
        "difficulty": "intermediate",
        "tagline": "Catch the move when price breaks through resistance",
        "overview": (
            "Breakout signals fire when price pushes above a key resistance level "
            "with conviction. These include prior day highs, inside day ranges, "
            "consolidation patterns, and opening range highs. Breakouts represent "
            "a shift in supply/demand — sellers at that level are overwhelmed by buyers."
        ),
        "why_it_works": (
            "Markets consolidate before they move. When price breaks above a level "
            "that previously rejected it, stops get triggered (shorts covering), "
            "breakout traders enter (new longs), and the path of least resistance "
            "shifts upward. Prior day highs are especially significant because "
            "they represent the previous session's ceiling — breaking it means "
            "today's buyers are stronger than yesterday's sellers."
        ),
        "when_it_fails": (
            "False breakouts are the #1 risk. Price pokes above the level by a few cents, "
            "triggers entries, then reverses. The system requires volume confirmation "
            "and a close above the level (not just a wick). In choppy/range-bound markets, "
            "breakouts fail more often — the system checks SPY regime and flags these as CAUTION."
        ),
        "how_to_read": [
            "Identify the resistance level that price has tested 2+ times without breaking",
            "Watch for volume surge on the breakout bar — should be 1.5x+ average",
            "The breakout bar should close near its high (strong buyers, no selling into strength)",
            "After breakout, the old resistance should become new support on a retest",
        ],
        "pro_tips": [
            "Inside day breakouts are most reliable — the compressed range stores energy for a larger move",
            "Avoid breakouts in the last hour of trading — they often reverse by close",
            "Consolidation breakouts (3+ bars in a tight range) are higher quality than single-bar breaks",
            "Check if the breakout aligns with the sector trend — isolated stock breakouts in weak sectors often fail",
        ],
        "key_alert_types": [
            {"type": "prior_day_high_breakout", "name": "PDH Breakout", "desc": "Price breaks above yesterday's high with volume — new buyers overwhelming yesterday's sellers"},
            {"type": "inside_day_breakout", "name": "Inside Day Breakout", "desc": "Price breaks out of yesterday's range after consolidating within it — stored energy releasing"},
            {"type": "consol_breakout_long", "name": "Consolidation Breakout", "desc": "Price breaks up from a multi-bar tight range — compression precedes expansion"},
            {"type": "opening_range_breakout", "name": "Opening Range Breakout", "desc": "Price breaks above the first 30-minute high — sets the directional bias for the session"},
        ],
    },
    "short_signals": {
        "name": "Short Signals",
        "difficulty": "intermediate",
        "tagline": "Profit when price fails at resistance and turns down",
        "overview": (
            "Short signals identify opportunities to profit from falling prices. "
            "They fire when price gets rejected at resistance (EMA rejection, failed breakout, "
            "double top) or breaks down from support (VWAP loss, consolidation breakdown). "
            "Shorting is higher risk than going long — losses are theoretically unlimited — "
            "so the system applies stricter filters and tighter stops."
        ),
        "why_it_works": (
            "When price fails to break a resistance level, it tells you sellers are stronger "
            "than buyers at that price. Traders who bought the breakout attempt are now trapped "
            "with losing positions — as they sell, price accelerates downward. EMA rejections "
            "are particularly powerful in downtrends because the moving average acts as a ceiling "
            "that price can't reclaim."
        ),
        "when_it_fails": (
            "Shorting in strong uptrends is dangerous — price can grind higher through any "
            "resistance. The system checks the broader trend and SPY regime before firing shorts. "
            "Shorts also fail when there's a sudden catalyst (earnings surprise, Fed announcement) "
            "that overwhelms technical levels."
        ),
        "how_to_read": [
            "Look for price rallying into a falling EMA or prior resistance with decreasing volume",
            "The rejection bar should close in its lower half with a long upper wick (sellers rejected buyers)",
            "Check that the broader trend is down — shorting in uptrends is fighting momentum",
            "Volume on the rejection should ideally increase (aggressive selling)",
        ],
        "pro_tips": [
            "VWAP loss is a powerful intraday short trigger — it means institutional buyers have abandoned the stock",
            "Failed breakouts (price breaks above PDH then reverses) create the best shorts — trapped longs panic sell",
            "Always use a stop above the rejection level — short squeezes are violent and fast",
            "The best shorts happen when SPY is also weak — don't short individual stocks in a strong market",
        ],
        "key_alert_types": [
            {"type": "ema_rejection_short", "name": "EMA Rejection", "desc": "Price rallies to EMA and gets rejected — sellers defending the moving average ceiling"},
            {"type": "hourly_resistance_rejection_short", "name": "Hourly Resistance Rejection", "desc": "Price rejected at the hourly chart resistance level — multi-timeframe sellers"},
            {"type": "session_high_double_top", "name": "Double Top", "desc": "Price tests the same high twice and fails — buyers exhausted, reversal likely"},
            {"type": "vwap_loss", "name": "VWAP Loss", "desc": "Price drops below VWAP and stays under — institutional sentiment shifts bearish"},
        ],
    },
    "exit_alerts": {
        "name": "Exit Alerts",
        "difficulty": "beginner",
        "tagline": "Know exactly when to take profits or cut losses",
        "overview": (
            "Exit alerts tell you when an active trade reaches its target or stop level. "
            "This is the most important category — it's where money is actually made or preserved. "
            "T1 hits mean take partial profits. T2 hits mean the thesis played out fully. "
            "Stop hits mean the setup failed and it's time to exit with a controlled loss."
        ),
        "why_it_works": (
            "Most traders lose money not because they pick bad entries, but because they "
            "mismanage exits. They hold losers hoping for a recovery. They sell winners too early "
            "out of fear. Pre-defined targets and stops remove emotion from the exit decision. "
            "The system calculates T1 from the nearest structural level (not a fixed percentage) "
            "and the stop from below the support that triggered the entry."
        ),
        "when_it_fails": (
            "In fast-moving markets, price can gap through your stop — the actual loss may be "
            "larger than planned. T1 targets may be hit and then price continues much further, "
            "meaning you left money on the table. The system addresses this with T2 targets — "
            "take half at T1, let the rest run to T2."
        ),
        "how_to_read": [
            "When T1 fires: consider taking 50-75% off and moving stop to breakeven on the rest",
            "When T2 fires: close the remaining position — the full thesis has played out",
            "When stop fires: exit immediately — don't lower your stop hoping for recovery",
            "Track your T1 vs T2 hit rates — if T2 hits often after T1, consider holding runners",
        ],
        "pro_tips": [
            "Never move your stop further from entry — that's the #1 account-killing mistake",
            "After T1 hits, move your stop to breakeven — you're now playing with house money",
            "If you consistently see T2 hit after T1, consider a trailing stop instead of fixed T2",
            "Exit alerts always deliver regardless of your notification filters — they're that important",
        ],
        "key_alert_types": [
            {"type": "target_1_hit", "name": "Target 1 Hit", "desc": "Price reached your first profit target — consider taking partial profits"},
            {"type": "target_2_hit", "name": "Target 2 Hit", "desc": "Price reached full target — the complete thesis played out"},
            {"type": "stop_loss_hit", "name": "Stop Loss Hit", "desc": "Price hit your stop — exit with a controlled, pre-defined loss"},
            {"type": "auto_stop_out", "name": "Auto Stop", "desc": "System detected the setup is invalidated — protective exit before stop is hit"},
        ],
    },
    "resistance_warnings": {
        "name": "Resistance Warnings",
        "difficulty": "beginner",
        "tagline": "Know where the ceiling is before you buy",
        "overview": (
            "Resistance warnings fire when price approaches or gets rejected at levels where "
            "sellers historically appear — prior day highs, moving average resistance, weekly "
            "and monthly highs. These aren't trade signals — they're warnings. If you're long, "
            "consider tightening your stop. If you're thinking of buying, wait for a breakout "
            "confirmation instead."
        ),
        "why_it_works": (
            "Resistance levels exist because traders who bought at those prices in the past "
            "and are underwater will sell when price returns to their entry (to break even). "
            "Additionally, profit-takers sell at round numbers and prior highs. The more times "
            "a level is tested, the weaker it becomes — but until it breaks, it's a ceiling."
        ),
        "when_it_fails": (
            "Strong momentum can blow through resistance without pausing. This typically happens "
            "with high-volume breakouts, earnings beats, or sector-wide rallies. The warning "
            "becomes irrelevant if the breakout is genuine — which is why breakout signals exist "
            "as a separate category."
        ),
        "how_to_read": [
            "Resistance approaching = tighten stops on longs, don't add to positions",
            "Rejection at resistance = potential short entry or exit point for longs",
            "Multiple rejections at the same level = strong resistance, wait for a breakout with volume",
            "If price closes ABOVE resistance on high volume, the level is broken — it becomes support",
        ],
        "pro_tips": [
            "The #1 beginner mistake is buying AT resistance — wait for it to break or bounce first",
            "Prior day high resistance is strongest in the first hour of trading",
            "If your entry signal is right at a resistance level, the R:R is usually poor — skip it",
            "Weekly and monthly resistances are stronger than daily — they represent bigger timeframe sellers",
        ],
        "key_alert_types": [
            {"type": "resistance_prior_high", "name": "Prior High Resistance", "desc": "Price approaching yesterday's high — potential selling pressure ahead"},
            {"type": "pdh_rejection", "name": "PDH Rejection", "desc": "Price tested prior day high and was rejected — sellers are defending"},
            {"type": "ma_resistance", "name": "MA Resistance", "desc": "Moving average acting as a ceiling in a downtrend"},
            {"type": "weekly_high_resistance", "name": "Weekly High Resistance", "desc": "Approaching the weekly high — strong multi-day resistance zone"},
        ],
    },
    "support_warnings": {
        "name": "Support Warnings",
        "difficulty": "beginner",
        "tagline": "Know when the floor breaks so you can step aside",
        "overview": (
            "Support warnings fire when key support levels break — prior day lows, weekly lows, "
            "monthly lows, and structural support zones. When support breaks, the character of "
            "the market changes. Buyers who were defending that level are now trapped, and their "
            "selling accelerates the move down."
        ),
        "why_it_works": (
            "Support levels hold because buyers step in at those prices. When the buying pressure "
            "isn't enough to hold the level, it signals a shift — demand has dried up. Traders who "
            "bought at support are now losing money, and their stop losses trigger a cascade of "
            "selling. The prior support level often becomes new resistance."
        ),
        "when_it_fails": (
            "False breakdowns happen — price dips below support by a few cents, triggers stops, "
            "then reverses back above. This is called a 'stop hunt' or 'liquidity grab.' The system "
            "requires a sustained close below the level, not just a wick, to confirm the breakdown."
        ),
        "how_to_read": [
            "Support breakdown = exit longs, do NOT buy the dip immediately",
            "Watch for a retest of the broken support (now resistance) — if it holds as resistance, the breakdown is confirmed",
            "Volume on the breakdown matters — high volume = conviction, low volume = possible false move",
            "Weekly and monthly support breaks are more significant than daily",
        ],
        "pro_tips": [
            "Don't try to catch a falling knife — wait for a new base to form before buying",
            "Prior day low breakdown in the first hour often sets the tone for the entire session",
            "If SPY breaks support, expect most stocks to follow — it's a market-wide event",
            "The best re-entry after a breakdown is a PDL reclaim signal — price recovers above the broken level",
        ],
        "key_alert_types": [
            {"type": "support_breakdown", "name": "Support Breakdown", "desc": "Key support level broken — structure has changed, step aside"},
            {"type": "prior_day_low_breakdown", "name": "PDL Breakdown", "desc": "Price broke below yesterday's low — bearish shift for the session"},
            {"type": "weekly_low_breakdown", "name": "Weekly Low Breakdown", "desc": "Broke below the week's low — multi-day bearish signal"},
        ],
    },
    "swing_trade": {
        "name": "Swing Trade Setups",
        "difficulty": "advanced",
        "tagline": "Multi-day setups for bigger moves",
        "overview": (
            "Swing trade signals identify setups that play out over 2-10 days rather than "
            "intraday. They use daily chart patterns — RSI divergence, MACD crossovers, "
            "EMA crossovers, bull flags, and multi-day double bottoms. These require more "
            "patience and wider stops, but the targets are proportionally larger."
        ),
        "why_it_works": (
            "Daily chart patterns reflect the actions of larger participants — hedge funds, "
            "pension funds, and mutual funds that move slowly. When a stock shows RSI divergence "
            "(price makes a lower low but RSI makes a higher low), it means selling pressure is "
            "exhausting. Large buyers are accumulating quietly before the move up."
        ),
        "when_it_fails": (
            "Swing trades are exposed to overnight risk — earnings, macro events, and gap downs "
            "can invalidate a setup instantly. They also require larger stops (to accommodate "
            "daily volatility), meaning each loss is bigger in dollar terms. Position sizing must "
            "account for the wider stop."
        ),
        "how_to_read": [
            "Check the daily chart first — the pattern should be visible on daily timeframe",
            "RSI divergence is most reliable after a 3-5 day pullback in an overall uptrend",
            "EMA crossovers (5 crossing above 20) work best after a period of consolidation",
            "Set alerts on the daily close, not intraday — swing setups confirm on daily bars",
        ],
        "pro_tips": [
            "Size swing trades smaller than day trades — the wider stop means more risk per share",
            "Multi-day double bottoms are the highest conviction swing setup — they represent a tested floor",
            "Don't enter swing trades on Friday afternoon — you get 2 days of risk with no ability to exit",
            "Combine swing entries with intraday timing — use the daily for direction, the hourly for entry",
        ],
        "key_alert_types": [
            {"type": "multi_day_double_bottom", "name": "Multi-Day Double Bottom", "desc": "Same support zone tested across multiple days — strong base for a reversal"},
            {"type": "ema_crossover_5_20", "name": "EMA 5/20 Crossover", "desc": "Short-term momentum crossing above medium-term — trend shift signal"},
            {"type": "swing_rsi_divergence", "name": "RSI Divergence", "desc": "Price makes lower low but RSI makes higher low — selling exhaustion, reversal likely"},
            {"type": "swing_macd_crossover", "name": "MACD Crossover", "desc": "MACD line crosses above signal line — momentum turning bullish"},
        ],
    },
    "informational": {
        "name": "Market Context",
        "difficulty": "beginner",
        "tagline": "Read the field before you play",
        "overview": (
            "Informational alerts give you context about market structure without recommending "
            "a trade. Inside day forming, consolidation notices, first hour summaries, and gap fills "
            "help you understand what the market is doing before signals fire. Think of these as "
            "the weather report before you decide what to wear."
        ),
        "why_it_works": (
            "Context prevents bad trades. An inside day forming means the market is compressing — "
            "breakout trades will be more powerful when they come, but mean-reversion trades are "
            "risky because the range is tightening. A first hour summary tells you whether today "
            "is a trending or range-bound day, which determines which signal types are reliable."
        ),
        "when_it_fails": (
            "Context alerts aren't trade signals, so 'failing' isn't quite the right word. "
            "But they can be misleading — an inside day might not break out for days, or a "
            "consolidation might resolve with a whimper rather than a bang. Use them as "
            "information inputs, not decision points."
        ),
        "how_to_read": [
            "Inside day forming = expect a breakout (direction unknown) — tighten watchlist to breakout alerts",
            "Consolidation notice = range is tightening — breakout is coming, be ready",
            "First hour summary = sets the bias for the day — trending days favor breakouts, choppy days favor bounces",
            "Gap fill = price filled a gap from a prior session — watch for continuation or reversal at the fill level",
        ],
        "pro_tips": [
            "Inside days on SPY affect everything — when SPY compresses, individual stock breakouts also stall",
            "The first hour summary is most useful for filtering which signal categories to trust that day",
            "Don't trade based on informational alerts alone — wait for an entry or breakout signal",
            "These alerts are great for learning market structure even if you never trade from them",
        ],
        "key_alert_types": [
            {"type": "inside_day_forming", "name": "Inside Day Forming", "desc": "Today's range is within yesterday's range — compression before expansion"},
            {"type": "hourly_consolidation", "name": "Consolidation Notice", "desc": "Price in a tight range for multiple hours — breakout is building"},
            {"type": "first_hour_summary", "name": "First Hour Summary", "desc": "Recap of the opening range — sets directional bias for the session"},
            {"type": "gap_fill", "name": "Gap Fill", "desc": "Price filled a gap from a prior session — watch for reaction at this level"},
        ],
    },
}

# Category display order
CATEGORY_ORDER = [
    "entry_signals",
    "breakout_signals",
    "short_signals",
    "exit_alerts",
    "resistance_warnings",
    "support_warnings",
    "swing_trade",
    "informational",
]
