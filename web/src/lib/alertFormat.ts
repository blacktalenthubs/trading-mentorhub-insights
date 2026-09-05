/** Shared formatting for alert types — used by the Signals feed and
 *  the browser-notification hook. */

/** True for SWING alerts (multi-day hold) — drives the "SWING ·" feed-label
 *  prefix. Matches style_for()'s swing bucket in alert_type_config.py: the
 *  30-RSI reclaim + daily RSI/EMA momentum, and — among the MA ladder — ONLY the
 *  200 EMA/SMA reclaim (major moving support, held for days). The 8/21/50/100
 *  bounces, ORB, levels and RC are DAY trades, NOT swings (user 2026-07-15,
 *  revises the earlier 50/100/200 rule). Keep in sync with style_for(). */
export function isSwingAlert(alertType?: string): boolean {
  const t = (alertType ?? "").replace(/^tv_/, "");
  if (t === "rsi_70" || t === "ema_5_20_cross" || t === "rsi_oversold") return true;
  if (t.startsWith("swing_")) return true;                 // 30-RSI reclaim (swing_rsi_30) etc.
  // MA ladder: ONLY the 200 EMA/SMA reclaim is a swing; 8/21/50/100 are day trades.
  if (t.startsWith("ma_bounce_long_v3") && /(ema|sma)200/.test(t)) return true;
  return false;
}

/** Short, human-readable setup name from a raw alert_type. SWING alerts get a
 *  "SWING ·" prefix so the swing book is visible at a glance in the feed. */
export function formatSetup(alertType?: string): string {
  const t = (alertType ?? "").replace(/^tv_/, "").replace(/^ai_/, "");
  if (!t) return "Signal";
  const swing = (name: string) => (isSwingAlert(alertType) ? `SWING · ${name}` : name);
  // Scanner MA ladder — ma_reclaim_50 -> "50 SMA Reclaim", ema_bounce_21 -> "21 EMA Bounce".
  // Mirrors _pretty_setup() in alerting/notifier.py so the feed, Telegram and the
  // push notification all name the setup identically. Matched before the v3 family
  // so these don't fall through to the raw title-case ("Ema Reclaim 21").
  const ladder = t.match(/^(ma|ema)_(reclaim|bounce)_(\d{1,3})$/);
  if (ladder) {
    const kind = ladder[1] === "ma" ? "SMA" : "EMA";
    const verb = ladder[2].charAt(0).toUpperCase() + ladder[2].slice(1);
    return swing(`${ladder[3]} ${kind} ${verb}`);
  }
  // MA families — ma_bounce_long_v3_ema8_ema21 -> "EMA 8 + EMA 21 bounce"
  const ma = t.match(/^ma_(bounce_long|rejection_short|proximity_long|proximity_short)_v3_(.+)$/);
  if (ma) {
    const kind = ma[1] === "bounce_long" ? "bounce"
      : ma[1] === "rejection_short" ? "rejection" : "proximity";
    const mas = ma[2].split("_")
      .map((m) => m.toUpperCase().replace(/^(EMA|SMA)/, "$1 "))
      .join(" + ");
    return swing(`${mas} ${kind}`);
  }
  // Staged level events — staged_pdh_break -> "PDH break", staged_pwl_reclaim -> "Weekly low reclaim"
  const sm = t.match(/^staged_p([dwm])([hl])_(.+)$/);
  if (sm) {
    const lvl = sm[1] === "d"
      ? "PD" + sm[2].toUpperCase()
      : (sm[1] === "w" ? "Weekly " : "Monthly ") + (sm[2] === "h" ? "high" : "low");
    return swing(`${lvl} ${sm[3].replace(/_/g, " ")}`);
  }
  const NAMES: Record<string, string> = {
    // RC / reclaim family — TF-explicit so 4 fires on one name read as
    // "same setup, different timeframes", not 4 mystery signals.
    rc_4h_long: "4-hour low reclaim",
    rc_4h_hrec: "4-hour high break",
    rc_daily_long: "Prior-day low reclaim",
    rc_daily_hrec: "Prior-day high break",
    pq_reclaim: "Prior-quarter low reclaim (swing)",
    ma200_bounce: "200-MA bounce (swing)",
    pdh_held: "PDH reclaim / hold",
    pdl_held: "PDL reclaim / hold",
    orb_high_held: "ORB high held",
    orb_low_held: "ORB low held",
    weekly_lvl_reclaim: "Prior-week reclaim / gap",
    monthly_lvl_reclaim: "Prior-month reclaim / gap",
    weekly_lvl_reject: "Prior-week rejection",
    monthly_lvl_reject: "Prior-month rejection",
    daily_rc: "Daily low reclaim",
    weekly_rc: "Weekly low reclaim",
    monthly_rc: "Monthly low reclaim",
    fourh_reclaim: "4H reclaim (long)",
    fourh_reject: "4H rejection (short)",
    fourh_breakup: "4H break-up (long)",
    fourh_breakdn: "4H break-down (short)",
    fourh_ema_reclaim: "50 EMA reclaim (long)",
    fourh_ema_reject: "50 EMA rejection (short)",
    fourh_ema_breakup: "50 EMA break-up (long)",
    fourh_ema_breakdn: "50 EMA break-down (short)",
    fourh_ma200_reclaim: "200 reclaim (long)",
    gap_and_go: "Gap-and-Go (long)",
    reclaim_long: "Morning shakeout reclaim",
    gap_up_continuation_long: "Gap-up continuation",
    orb_break: "ORB break",
    orb_held: "ORB held",
    orb_retest: "ORB retest",
    orb_exit: "ORB exit",
    orb_reclaim_low: "ORB low reclaim",
    orb_reclaim_high: "ORB high reclaim",
    cml_held: "Month-low support hold",
    cml_reclaim: "Month-low reclaim",
    pml_held: "Prior-month-low support hold",
    monthly_box: "Monthly box breakout",
    mobo_rch: "Monthly high breakout",
    weekly_10w_held: "10-week MA support hold",
    weekly_10w_reclaim: "10-week MA reclaim",
    weekly_30w_held: "30-week MA support hold",
    weekly_30w_reclaim: "30-week MA reclaim",
    swing_rsi_30: "RSI-30 reclaim (the turn)",
    swing_sma50_reclaim: "50 SMA reclaim (swing)",
    swing_sma200_reclaim: "200 SMA reclaim (swing)",
    open_reclaimed: "Open reclaimed",
    open_held: "Open held",
    open_wick_reclaim: "Open wick reclaim",
    open_lost: "Open lost",
    htf_support_held: "HTF support held",
    htf_proximity: "HTF proximity",
    pullback_long: "Pullback continuation",
    rsi_70: "RSI 70 — momentum",
    ema_5_20_cross: "5/20 EMA cross",
    rsi_oversold: "RSI oversold buy zone (30-35)",
    gap_support: "Gap support bounce",
    gap_fill: "Gap fill → far edge",
    gap_reject: "Gap rejection",
    lost_support_reject: "Lost support → resistance",
    htf_sr_reject: "Multi-period resistance",
    htf_sr_bounce: "Multi-period support",
    // last4h_* is one alert_type covering high/low × break/reclaim/reject — the
    // specific trigger is resolved by setupTitle() below from the description.
    // These are only the fallback when that text is missing.
    last4h_long: "Last 4H reclaim / break",
    last4h_short: "Last 4H reject / breakdown",
    // Scanner long entries (scanner redesign) — the non-ladder rules the Day feed
    // shows. Without these the card falls back to raw title-case.
    prior_day_low_reclaim: "PDL reclaim",
    prior_day_high_breakout: "PDH breakout",
    pdh_retest_hold: "PDH retest / hold",
    multi_day_double_bottom: "Double bottom",
  };
  return swing(NAMES[t] ?? t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()));
}

/** Card TITLE — like formatSetup, but for a rule whose ONE alert_type covers
 *  several distinct triggers (last4h_* = HIGH/LOW × BREAK/RECLAIM/REJECT/BREAKDOWN),
 *  it reads the alert's OWN description/message to name the actual trigger —
 *  "Last 4h Low Break", "Last 4h High Reclaim" — instead of the generic label.
 *  Every other type falls straight through to formatSetup(alert_type). */
export function setupTitle(a: { alert_type?: string | null; description?: string | null; message?: string | null }): string {
  const t = (a.alert_type ?? "").replace(/^tv_/, "").replace(/^ai_/, "");
  if (t === "last4h_long" || t === "last4h_short") {
    // last4h_* is an OVERLOADED alert_type: the prior_last_4h Pine fires the daily
    // 8/21/50 EMA·SMA reclaims AND the 4h high/low break under this one name. The
    // real trigger (which LEVEL) lives only in the description prose, so parse it
    // out and name the alert for what it actually is — "50 SMA Reclaim".
    const isLong = t === "last4h_long";
    const txt = `${a.description ?? ""} ${a.message ?? ""}`.toUpperCase();
    // Gap-and-go rides the last4h_long route (its own type is backend-retired) — name it directly.
    if (/GAP.?AND.?GO/.test(txt)) return "Gap-and-Go";
    // Verb: "back above/below" = defended the level (reclaim/reject); otherwise a break.
    const verb =
      /RECLAIM/.test(txt) || /BACK ABOVE/.test(txt) ? "Reclaim"
      : /REJECT/.test(txt) || /BACK BELOW/.test(txt) ? "Reject"
      : /BREAKDOWN/.test(txt) ? "Breakdown"
      : /BREAK/.test(txt) ? "Break"
      : isLong ? "Long" : "Short";
    // Level: a daily MA ("50 SMA", "8 EMA") wins; else the 4h high/low.
    const ma = txt.match(/(\d{1,3})\s*(EMA|SMA)/);
    const level = ma
      ? `${ma[1]} ${ma[2]}`
      : /HIGH/.test(txt) ? "Last 4h High"
      : /LOW/.test(txt) ? "Last 4h Low"
      : "Last 4h";
    return `${level} ${verb}`.trim();
  }
  return formatSetup(a.alert_type ?? undefined);
}

/** One-line plain-English explanation of what the setup MEANS — shown under the
 *  name in the feed so a user understands the signal without knowing the jargon.
 *  Returns "" when there's no blurb (the name alone is self-explanatory). */
export function setupBlurb(alertType?: string): string {
  const t = (alertType ?? "").replace(/^tv_/, "").replace(/^ai_/, "");
  // MA bounce family → "Pulled back to the EMA 21 and held it as support."
  const ma = t.match(/^ma_bounce_long_v3_(.+)$/);
  if (ma) {
    const m = ma[1]
      .split("_")
      .map((x) => x.toUpperCase().replace(/^(EMA|SMA)/, "$1 "))
      .join(" + ");
    return `Pulled back to the ${m} and held it as support.`;
  }
  // Staged level events → "Price held the prior-day low as support."
  const sm = t.match(/^staged_p([dwm])([hl])_(.+)$/);
  if (sm) {
    const lvl = sm[1] === "d" ? "prior-day" : sm[1] === "w" ? "prior-week" : "prior-month";
    const hl = sm[2] === "h" ? "high" : "low";
    const act = sm[3].includes("held")
      ? `held the ${lvl} ${hl} as support`
      : sm[3].includes("break")
        ? `broke the ${lvl} ${hl}`
        : sm[3].includes("reject")
          ? `rejected off the ${lvl} ${hl}`
          : `${sm[3].replace(/_/g, " ")} the ${lvl} ${hl}`;
    return `Price ${act}.`;
  }
  // Scanner MA ladder → the open-above reclaim, spelled out. This is the redesign's
  // core rule: the level was SUPPORT at the open, not resistance being ramped into.
  const ladder = t.match(/^(ma|ema)_(reclaim|bounce)_(\d{1,3})$/);
  if (ladder) {
    const kind = ladder[1] === "ma" ? "SMA" : "EMA";
    const lvl = `${ladder[3]} ${kind}`;
    return ladder[2] === "reclaim"
      ? `Opened ABOVE the ${lvl}, wicked down to tag it, and closed back above — the level held as support. Entry = the reclaim close, stop 0.5% below the level.`
      : `Pulled back to the ${lvl} and bounced off it.`;
  }
  const BLURB: Record<string, string> = {
    pq_reclaim: "Undercut the prior-quarter LOW (the low of the candle) and closed back above it — a bottom-bounce swing. Low only; no close/high.",
    ma200_bounce: "Daily close reclaimed the 200 EMA/SMA — the institutional dip-buy zone; a swing bottom.",
    rc_4h_long: "Dipped under the 4-hour low and reclaimed it — bounce off support.",
    rc_4h_hrec: "Pushed back above the 4-hour high — continuation.",
    pdl_held: "Wicked to/below the prior-day low and closed back above it — reclaim or support-hold. Entry = the level, stop below it.",
    pdh_held: "Wicked to/below the prior-day high and closed back above it — reclaim or retest-hold. Entry = the level, stop below it.",
    rc_daily_long: "Dipped under yesterday's low and reclaimed it — bounce.",
    rc_daily_hrec: "Pushed back above yesterday's high — continuation.",
    weekly_lvl_reclaim: "Reclaimed the prior week's high or low (was below → closed above), or gapped up above it and held. Entry = the level, stop = the day low.",
    monthly_lvl_reclaim: "Reclaimed the prior month's high or low (was below → closed above), or gapped up above it and held. Entry = the level, stop = the day low.",
    weekly_lvl_reject: "Rallied up into the prior week's high or low from below and closed back under — resistance held.",
    monthly_lvl_reject: "Rallied up into the prior month's high or low from below and closed back under — resistance held.",
    daily_rc: "Undercut the prior-day LOW (the candle's low) and closed back above it — a clean reclaim. Validation channel.",
    weekly_rc: "Undercut the prior-week LOW (the candle's low) and closed back above it — a clean reclaim. Validation channel.",
    monthly_rc: "Undercut the prior-month LOW (the candle's low) and closed back above it — a clean reclaim. Validation channel.",
    fourh_reclaim: "Wicked below a prior 4h level and closed back above — support held. Stop = the swept wick.",
    fourh_reject: "Wicked above a prior 4h level and closed back below — resistance held. Stop = the swept wick.",
    fourh_breakup: "Closed up through a prior 4h level — continuation. Stop back below the level.",
    fourh_breakdn: "Closed down through a prior 4h level — continuation. Stop back above the level.",
    fourh_ema_reclaim: "Wicked below the daily 50 EMA and closed back above — dynamic support held. Stop = the swept wick.",
    fourh_ema_reject: "Poked above the daily 50 EMA and closed back below — dynamic resistance held. Stop = the swept wick.",
    fourh_ema_breakup: "Closed up through the daily 50 EMA — continuation. Stop back below the EMA.",
    fourh_ema_breakdn: "Closed down through the daily 50 EMA — continuation. Stop back above the EMA.",
    fourh_ma200_reclaim: "Wicked below the daily 200 SMA/EMA and closed back above — structural support held. Stop = the swept wick.",
    gap_and_go: "Opened above the prior high (PDH) and holding above it — momentum continuation. Stop = the morning low.",
    reclaim_long: "Faked under the morning high, snapped back with room above.",
    gap_up_continuation_long: "Gapped up and held the gap — trend continuation.",
    orb_break: "Broke through the opening-range high/low (or yesterday's) on a 15-minute close — a momentum breakout.",
    orb_held: "Tested the opening range or yesterday's high/low and held it — support.",
    orb_retest: "Broke out, came back to retest the level, and it held — a continuation entry.",
    orb_exit: "Gave back the level it had been holding on a 15-minute close — time to exit.",
    rsi_oversold: "RSI in the 30-35 buy zone — washed out, turning up.",
    rsi_70: "RSI tagged 70 — momentum / extension (trim zone).",
    swing_rsi_30: "Reclaimed after an RSI-30 washout — the turn.",
    swing_sma50_reclaim: "Wicked below the 50 SMA and closed back above — held support. Stop = the swept low.",
    swing_sma200_reclaim: "Recovered/held the 200 SMA — the structural line. Long-hold accumulation. Stop = the swept low.",
    ema_5_20_cross: "5-EMA crossed above the 20-EMA — momentum turn.",
    cml_held: "Held this month's low as support.",
    cml_reclaim: "Undercut this month's low and reclaimed it.",
    pml_held: "Held last month's low as support.",
    monthly_box: "Broke out of a multi-month base — the big-run setup.",
    mobo_rch: "Broke a prior-month high that had capped it — breakout.",
    weekly_10w_held: "Held the 10-week moving average as support.",
    weekly_10w_reclaim: "Reclaimed the 10-week moving average.",
    weekly_30w_held: "Held the 30-week moving average as support.",
    weekly_30w_reclaim: "Reclaimed the 30-week moving average.",
    // Scanner long entries — mirrors ALERT_TYPE_DESCRIPTIONS in
    // api/app/models/alert_type_config.py.
    prior_day_low_reclaim: "Dipped below yesterday's low and closed back above it — the breakdown failed. Entry = the reclaim close, stop 0.5% below the level.",
    prior_day_high_breakout: "Broke above yesterday's high on confirming volume — resistance taken out.",
    pdh_retest_hold: "Broke above yesterday's high, pulled back to retest it and held — PDH flipped to support. The re-entry if you missed the breakout.",
    multi_day_double_bottom: "A daily swing-low zone already tested twice is being retested intraday — buyers defended this price before.",
  };
  return BLURB[t] ?? "";
}

/** The scanner's long-entry rules (monitor.py + alert_config.ENABLED_RULES). These
 *  carry NO ai_/tv_ prefix — the scanner writes the bare rule key — so before the
 *  scanner redesign they were filtered out of the feed, the alert log and the in-app
 *  notification alike: Phase 1's alerts recorded to the DB and were never seen.
 *  Shorts, resistance and weekly/monthly NOTICE rules stay out — the redesign
 *  delivers long entries only, and the feed shows the trade set. */
const SCANNER_ENTRY_TYPES = new Set([
  "prior_day_low_reclaim",
  "prior_day_high_breakout",
  "pdh_retest_hold",
  "multi_day_double_bottom",
]);
/** ma_reclaim_50 / ema_reclaim_21 … — the open-above MA ladder. Reclaims only:
 *  the bounce rules were deprecated by the redesign and cannot fire. */
const SCANNER_LADDER_RE = /^(ma|ema)_reclaim_\d{1,3}$/;

export function isScannerEntry(alertType?: string): boolean {
  const t = alertType ?? "";
  return SCANNER_ENTRY_TYPES.has(t) || SCANNER_LADDER_RE.test(t);
}

/** True for alerts that belong in the Signals feed — AI scans, TV signals and the
 *  scanner's own long entries. No WAITs. */
export function isFeedSignal(alertType?: string): boolean {
  const t = alertType ?? "";
  if (t === "ai_scan_wait") return false;
  return t.startsWith("ai_") || t.startsWith("tv_") || isScannerEntry(t);
}
