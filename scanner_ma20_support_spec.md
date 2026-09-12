# Scanner redesign — 20/200 MA support + PDH/PWH breakout + PDL/PWL reclaim

**Directive (2026-09-12):** the scanner sends ONLY the signals below; every other
signal rule is disabled.

## The only entry signals

| # | Signal | Rule key | Notes |
|---|--------|----------|-------|
| 1 | Daily **20 SMA** support, **rising** | `ma_reclaim_20` | open-above / wick-reclaim / hold of the daily 20 SMA, gated on the 20 **rising** (angle ≥ 30°) |
| 2 | Daily **200 SMA** support | `ma_reclaim_200` | open-above / wick-reclaim / hold of the daily 200 SMA |
| 3 | **Hourly 20 SMA** support, **rising** | `ma20_support_1h` (new) | same hold pattern on 1h bars, 1h-20 rising (angle ≥ 30°) |
| 4 | **Hourly 200 SMA** support | `ma200_support_1h` (new) | hold of the 1h 200 SMA |
| 5 | **PDH breakout** | `prior_day_high_breakout` | close above prior-day high on volume |
| 6 | **PDL reclaim** | `prior_day_low_reclaim` | opened above PDL, wicked to it, reclaimed |
| 7 | **PWH breakout** | `pwh_breakout_retest` | breaks the prior-week high THEN holds the retest |
| 8 | **PWL reclaim** | `pwl_reclaim` | opened above PWL, defended it |

Trade-management exits (`target_1_hit`, `target_2_hit`, `stop_loss_hit`,
`auto_stop_out`) stay ON — they close positions the scanner opened, not entry signals.

## Decisions (defaults, adjustable)

- **"Rising"** = the ma20_direction pine's angle read: the MA's 5-day rise measured in
  ATRs/bar → degrees, and rising = **angle ≥ 30°** (ideal-and-up; skips a flat/shallow
  20 drifting up). Constant `MA_RISE_ANGLE_MIN = 30` — one place to tune.
- **20 & 200 = separate signals** — a name at the rising 20 fires (1)/(3); a name at the
  200 fires (2)/(4). Not "both at once."
- **PWH breakout = breakout + retest-hold** (the only tradeable PWH rule that exists).
- **Hourly support pattern** = open-above / wick-reclaim / hold on the LAST completed
  hourly bar (same open-above idiom as the daily reclaim). Uses `fetch_hourly_bars`
  (~60d for a 200-bar SMA), cached; defensive (a fetch miss just skips, never breaks the poll).

## Files

- `alert_config.py` — `ENABLED_RULES` pruned to the 8 + exits.
- `analytics/intraday_data.py` — add `ma20_angle` / `ma200_angle` to `prior_day` (daily MA slope in degrees) for the rising gate.
- `analytics/intraday_rules.py` — enable `ma_reclaim_20` (gated rising) in the daily ladder; add `check_ma_support_1h` + `MA20_SUPPORT_1H` / `MA200_SUPPORT_1H` AlertTypes.
- `api/app/background/monitor.py` — fetch hourly bars per symbol; call the 1h support check.
- `web/src/lib/alertFormat.ts` + `alerting/notifier.py` — feed admission + labels for the new keys.
