# My Setup — the pines I actually trade

The 48 pines in `active/`, `visual/`, `archive/` are experiments and history.
**These are the only ones I run.** Two kinds: *visual* (chart lines, no alerts —
they live in THIS folder) and *alert* (emit signals, bound to a TV watchlist alert —
they live in `../active/` because that's where the deploy tooling looks).

## Visual pines — in this folder (`my_setup/`)

| File | On the chart | Notes |
|------|-------------|-------|
| `ema_levels_flat.pine` | **EMA 5/20/50/100/200 + PDH/PDL · PWH/PWL · PMH/PML** | Flat locked S/R. Green = support (price above) / red = resistance (below). Solid = MA+daily · dashed = weekly · dotted = monthly. |
| `sma_levels_flat.pine` | **SMA 5/20/50/100/200 + the same 6 levels** | SMA twin of the above. Run one or both. |
| `monthly_levels.pine` (MLV) | **Prior MONTH H/L/O/C** + ▲ reclaim / △ gap-and-go marks | Visual twin of the monthly alert. Draws the prior month only. |
| `weekly_levels.pine` (WLV) | **Prior WEEK H/L/O/C** + ▲ reclaim / △ gap-and-go marks | Visual twin of the weekly alert. Draws the prior week only. |

## Alert pines — in `../active/` (bound to TV watchlist alerts)

| File | Fires | TV binding |
|------|-------|-----------|
| `../active/day_trade.pine` (RC) | Day-trade level engine: **prior-week + prior-month reclaim / gap-and-go** (`weekly_lvl_reclaim` / `monthly_lvl_reclaim`), rejection shorts, MA/EMA reclaims, gap-and-go | Bind on the day-trade TF (10–15m); watchlist-bound alert |
| `../active/swing_trade.pine` (PQ) | Swing: prior-quarter reclaim (`pq_reclaim`) + 200-MA bounce (`ma200_bounce`) | Bind on 1h + the master watchlist |

## Rule of thumb
- **Chart lines only → this folder.**
- **Emits an alert → `active/`** (so it deploys and can be watchlist-bound).
- Editing an alert pine? After deploying the source to TV you must **delete + recreate**
  the bound alert — TV snapshots the pine at alert-creation time.
