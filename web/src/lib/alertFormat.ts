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
    pq_reclaim: "Prior-quarter reclaim (swing)",
    ma200_bounce: "200-MA bounce (swing)",
    pdh_held: "PDH reclaim / hold",
    pdl_held: "PDL reclaim / hold",
    orb_high_held: "ORB high held",
    orb_low_held: "ORB low held",
    weekly_lvl_reclaim: "Prior-week reclaim / gap",
    monthly_lvl_reclaim: "Prior-month reclaim / gap",
    weekly_lvl_reject: "Prior-week rejection",
    monthly_lvl_reject: "Prior-month rejection",
    weekly_rc: "Weekly level reclaim",
    monthly_rc: "Monthly level reclaim",
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
  };
  return swing(NAMES[t] ?? t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()));
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
  const BLURB: Record<string, string> = {
    pq_reclaim: "Daily close bounced the prior-quarter low, reclaimed the close, or broke the high — bottom-bounce / breakout swing.",
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
    weekly_rc: "Reclaimed or broke a prior-week level — swing heads-up.",
    monthly_rc: "Reclaimed or broke a prior-month level — position heads-up.",
    reclaim_long: "Faked under the morning high, snapped back with room above.",
    gap_up_continuation_long: "Gapped up and held the gap — trend continuation.",
    orb_break: "Broke through the opening-range high/low (or yesterday's) on a 15-minute close — a momentum breakout.",
    orb_held: "Tested the opening range or yesterday's high/low and held it — support.",
    orb_retest: "Broke out, came back to retest the level, and it held — a continuation entry.",
    orb_exit: "Gave back the level it had been holding on a 15-minute close — time to exit.",
    rsi_oversold: "RSI in the 30-35 buy zone — washed out, turning up.",
    rsi_70: "RSI tagged 70 — momentum / extension (trim zone).",
    swing_rsi_30: "Reclaimed after an RSI-30 washout — the turn.",
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
  };
  return BLURB[t] ?? "";
}

/** True for alerts that belong in the Signals feed — AI scans + TV signals, no WAITs. */
export function isFeedSignal(alertType?: string): boolean {
  const t = alertType ?? "";
  return t !== "ai_scan_wait" && (t.startsWith("ai_") || t.startsWith("tv_"));
}
