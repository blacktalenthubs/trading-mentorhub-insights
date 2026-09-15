# Scanner expansion — 4H support bounces + 1H/4H rejection shorts

**Directive (2026-09-14, user):** grow the scanner's day-trade coverage with the SMAs
acting as support/resistance on the **4-hour** chart (GOOGL example), and add **short**
signals for the index/proxy set off **1H + 4H** SMA rejections.

## Already done (merged, awaiting worker restart)
| Signal | Rule | PR |
|---|---|---|
| Daily 50 SMA bounce (intraday) | `ma_reclaim_50` | #1262 |
| Daily 150 SMA reclaim | `ma_reclaim_150` | #1257 |

## NEW — 4H support bounces (LONG, day-trade)
Price holding the **4H** 20 / 50 / 200 SMA as support — the same tag-and-hold mechanic
as the existing hourly support (`check_ma_support_1h` is timeframe-agnostic; feed it 4H
bars). 4H bars = resample the 1H fetch to 4H (yfinance has no native 4H).

| Rule | MA | Rising-gated? |
|---|---|---|
| `ma20_support_4h`  | 4H 20  | yes (≥ 15°, like the 1H 20) |
| `ma50_support_4h`  | 4H 50  | no (structural) |
| `ma200_support_4h` | 4H 200 | no (structural) |

Fires ~once per 4H bar close. Whole universe (52), same as the 1H support.

## NEW — 1H / 4H rejection SHORTS (index set only)
Price rallies UP to a falling/overhead SMA on the **1H or 4H**, tags it, closes back
below = resistance held → **SHORT**. The mirror of the support hold (a `check_ma_reject_htf`
helper, inverse of `check_ma_support_1h`: high within `prox` of the MA, close < MA,
MA falling/overhead).

- **Universe:** `SHORT_UNIVERSE` = **SPY · QQQ · SMH · DRAM** (currently
  `{SPY, QQQ, SMH, ETH-USD}` — swap ETH→DRAM, or keep ETH; confirm).
- **MAs × timeframes:** 20 / 50 / 200 on **1H** and **4H** → 6 short rules:
  `ma20_reject_1h ma50_reject_1h ma200_reject_1h ma20_reject_4h ma50_reject_4h ma200_reject_4h`.
- Entry = the rejection close, stop just above the MA, target = extension down.

## Files
- `analytics/intraday_rules.py` — new AlertTypes; `check_ma_reject_htf` (1H/4H reject);
  the 4H support reuses `check_ma_support_1h`.
- `api/app/background/monitor.py` — fetch 4H bars (resample 1H); call the 4H support
  checks (all symbols) + the 1H/4H reject checks (SHORT_UNIVERSE only).
- `alert_config.py` — add the 9 new keys to `ENABLED_RULES`; set `SHORT_UNIVERSE`.
- `alerting/notifier.py` + `web/src/lib/alertFormat.ts` — labels + feed admission.
- Catalog (`alert_type_config.py`) auto-adds via `_scanner_catalog()`.

## Open decisions (confirm before build)
1. **Short universe** — SPY/QQQ/SMH/**DRAM** (drop ETH-USD from shorts)? Or keep ETH too?
2. **Short MAs** — 20/50/200 on BOTH 1H and 4H (6 rules), or a leaner set (e.g. 50/200 only)?
3. **4H 20 rising-gate** — require the 4H 20 rising (≥15°) for the long bounce, like the 1H 20?
