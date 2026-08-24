# My Setup — the pines I actually trade

The 48 pines in `active/`, `visual/`, `archive/` are experiments and history.
**These are the only ones I run.** Two kinds: *visual* (chart lines, no alerts —
they live in THIS folder) and *alert* (emit signals, bound to a TV watchlist alert —
they live in `../active/` because that's where the deploy tooling looks).

## Visual pines — in this folder (`my_setup/`)

| File | On the chart | Notes |
|------|-------------|-------|
| **`flat_mas_levels.pine`** ← **the one I load** | **EMA + SMA 5/20/50/100/200 · PDH/PDL · PWH/PWL · PMH/PML · PQH/PQL/PQC** — all in ONE pine | Nothing to forget to enable. Flat locked S/R: green = support (price above) / red = resistance (below). EMA solid · SMA dashed; daily solid · weekly dashed · monthly + quarter dotted (PQ thicker = the major rail). **Proximity band** (default 8%) hides far lines so the chart auto-zooms tight on low TFs (no lock-ratio hack); set 0 to draw all. PQ here is VISUAL only — the alert is in swing_trade. |
| `monthly_levels.pine` (MLV) | **Prior MONTH H/L/O/C** + ▲ reclaim / △ gap-and-go marks | OPTIONAL detail — adds the O/C levels + reclaim marks the one-pine doesn't. Draws the prior month only. |
| `weekly_levels.pine` (WLV) | **Prior WEEK H/L/O/C** + ▲ reclaim / △ gap-and-go marks | OPTIONAL detail — same, for the prior week. |

> Replaced the split `ema_levels_flat` + `sma_levels_flat` (two pines = forgot to enable
> one → missed entries, and their shared levels doubled up) with the single
> `flat_mas_levels.pine`.

## Alert pines — in `../active/` (bound to TV watchlist alerts)

| File | Fires | TV binding |
|------|-------|-----------|
| `../active/day_trade.pine` (RC) | Day-trade level engine: **prior-week + prior-month reclaim / gap-and-go** (`weekly_lvl_reclaim` / `monthly_lvl_reclaim`), rejection shorts, MA/EMA reclaims, gap-and-go | Bind on the day-trade TF (10–15m); watchlist-bound alert |
| `../active/swing_trade.pine` (PQ) | Swing: **prior-quarter** reclaim (`pq_reclaim`, PQ H/L/C only — PPQ dropped) + 200-MA bounce (`ma200_bounce`) | Bind on **4h** + the master watchlist (a 4h close above the level = a real reclaim) |

## Rule of thumb
- **Chart lines only → this folder.**
- **Emits an alert → `active/`** (so it deploys and can be watchlist-bound).
- Editing an alert pine? After deploying the source to TV you must **delete + recreate**
  the bound alert — TV snapshots the pine at alert-creation time.
