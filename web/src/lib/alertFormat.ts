/** Shared formatting for alert types — used by the Signals feed and
 *  the browser-notification hook. */

/** True for SWING alerts (multi-day hold) — mirror of _is_swing_alert in
 *  api/.../tv_webhook.py: the daily RSI/EMA momentum rules + any slow-MA bounce
 *  (50/100/200, EMA or SMA). Keep the two in sync. */
export function isSwingAlert(alertType?: string): boolean {
  const t = (alertType ?? "").replace(/^tv_/, "");
  if (t === "rsi_70" || t === "ema_5_20_cross" || t === "rsi_oversold") return true;
  if (t.startsWith("ma_bounce_long_v3") && /50|100|200/.test(t)) return true;
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
  };
  return swing(NAMES[t] ?? t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()));
}

/** True for alerts that belong in the Signals feed — AI scans + TV signals, no WAITs. */
export function isFeedSignal(alertType?: string): boolean {
  const t = alertType ?? "";
  return t !== "ai_scan_wait" && (t.startsWith("ai_") || t.startsWith("tv_"));
}
