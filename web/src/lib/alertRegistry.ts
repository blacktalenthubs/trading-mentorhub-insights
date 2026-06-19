/** Alert pattern registry (#64 Sub-spec K) — the canonical explanation for every LIVE
 *  alert type the Pines fire. One source of truth for the human label + the education
 *  (what / why / how). `patternFor()` resolves any raw alert_type code (strips tv_/staged_
 *  prefixes, handles the per-level variants) to its family explanation. Cards, Strategy
 *  Analysis, and the Learn page all read this.
 */

export type PatternGroup = "Day" | "Swing" | "Trend";
export interface PatternInfo {
  code: string;
  label: string;
  group: PatternGroup;
  what: string; // what fired
  why: string;  // why it's an edge
  how: string;  // how to trade it (entry / stop / target)
}

const LEVELS: Record<string, { name: string; abbr: string }> = {
  pdh: { name: "prior-day high", abbr: "PDH" },
  pdl: { name: "prior-day low", abbr: "PDL" },
  pwh: { name: "prior-week high", abbr: "PWH" },
  pwl: { name: "prior-week low", abbr: "PWL" },
  pmh: { name: "prior-month high", abbr: "PMH" },
  pml: { name: "prior-month low", abbr: "PML" },
  orl: { name: "opening-range low", abbr: "ORL" },
};
function lvl(code: string) {
  for (const k of Object.keys(LEVELS)) if (code.includes(k)) return LEVELS[k];
  if (code.includes("avwap")) return { name: "anchored VWAP", abbr: "AVWAP" };
  return { name: "the level", abbr: "Level" };
}

function held(code: string): PatternInfo {
  const L = lvl(code);
  return {
    code, group: "Day", label: `${L.abbr} held`,
    what: `Price was above the ${L.name}, dipped down to test it, and closed back above — the level held as support.`,
    why: `A level that gets defended — buyers step in on the dip — is real support. You enter where risk is tightly defined and the crowd leans the same way.`,
    how: `Enter on the hold (close back above the level). Stop just below the level — if it breaks, the thesis is wrong. Target the next level above.`,
  };
}
function reclaim(code: string): PatternInfo {
  const L = lvl(code);
  return {
    code, group: "Day", label: `${L.abbr} reclaim`,
    what: `Price lost the ${L.name} (closed below it) then snapped back above — a reclaim.`,
    why: `Losing a level and reclaiming it traps the sellers who shorted the breakdown; their stops fuel the move back up — a liquidity-grab reversal. Only fires when the day OPENED above the level (owned support, not resistance).`,
    how: `Enter on the reclaim (close back above). Stop below the reclaim low. Target the next level up.`,
  };
}
function brk(code: string): PatternInfo {
  const L = lvl(code);
  return {
    code, group: "Day", label: `${L.abbr} break`,
    what: `Price broke and closed above the ${L.name} — a breakout through resistance.`,
    why: `Clearing a prior high removes overhead supply; breakouts that hold continue as trapped shorts cover and breakout buyers pile in.`,
    how: `Enter on the break or the retest-hold of the broken level. Stop back below it. Target the next level / measured move.`,
  };
}
function rejection(code: string): PatternInfo {
  const L = lvl(code);
  return {
    code, group: "Day", label: `${L.abbr} rejection`,
    what: `Price rallied up into the ${L.name} from below, wicked it, and closed back under — rejected at resistance.`,
    why: `A level approached from below is resistance. A clean rejection (sellers defend it) is a short — fade the failed push.`,
    how: `Short the rejection (close back below). Stop above the level. Target the level below.`,
  };
}

const EXPLICIT: Record<string, PatternInfo> = {
  rc_4h: {
    code: "rc_4h", group: "Day", label: "RC 4h — reclaim low",
    what: "On the 4-hour chart, price undercut the prior 4h low and closed back above it.",
    why: "The cornerstone day-trade setup: the undercut sweeps stops below the prior 4h low, then the reclaim reverses on the trapped sellers. Higher-timeframe (4h) anchoring filters out 5-minute noise.",
    how: "Enter on the 4h close back above the prior 4h low. Stop below the undercut low. Target the nearest level/EMA above.",
  },
  rc_h: {
    code: "rc_h", group: "Day", label: "RC-H 4h — reclaim high",
    what: "Price dipped below the prior 4h high and closed back above it — a breakout-retest reclaim.",
    why: "A breakout that pulls back below the broken high then reclaims it shakes out weak hands before continuing — the cleanest version of a breakout entry.",
    how: "Enter on the reclaim of the prior 4h high. Stop below the retest low. Target the next level up.",
  },
  weekly_rc: {
    code: "weekly_rc", group: "Swing", label: "Weekly reclaim",
    what: "Price reclaimed a weekly level (closed back above it on the weekly timeframe).",
    why: "Weekly-level reclaims are higher-conviction, lower-stress swing reversals — institutional timeframe, fewer signals, bigger moves.",
    how: "Swing entry on the weekly reclaim. Stop below the weekly level. Hold for the higher-timeframe target (often RSI 70).",
  },
  ema_5_20_cross: {
    code: "ema_5_20_cross", group: "Swing", label: "5/20 EMA cross",
    what: "The daily 5 EMA crossed above the 20 EMA — a short-term momentum shift up.",
    why: "A classic momentum trigger (Steve Burns): the fast average crossing the slow one marks a trend turning up. Best on names already in a base.",
    how: "Swing entry on the cross. Stop below the recent swing low. Hold while 5 > 20; exit on the cross back down or RSI 70.",
  },
  rsi_oversold: {
    code: "rsi_oversold", group: "Swing", label: "RSI oversold reclaim",
    what: "Daily RSI dropped into oversold (30–35) and is turning back up — buying weakness.",
    why: "Institutions buy weakness in uptrends. Oversold-and-reclaiming on a strong name is a high-reward dip entry — never buy below 30 (falling knife).",
    how: "Enter as RSI reclaims from 30–35. Stop below the swing low. Target RSI 70.",
  },
  rsi_70: {
    code: "rsi_70", group: "Swing", label: "RSI 70 — momentum target",
    what: "Daily RSI reached 70 — the momentum/exit target for a swing bought on weakness.",
    why: "RSI 70 is where strength gets sold (institutional sell-into-strength). It's the natural exit for an RSI-30/EMA-hold swing.",
    how: "Use as a take-profit signal on swing longs, not a fresh entry.",
  },
  gap_fill: {
    code: "gap_fill", group: "Day", label: "Gap fill",
    what: "Price traded back into and filled an opening gap.",
    why: "Gaps act as magnets; the fill is a known target and often a reaction point.",
    how: "Trade the reaction at the fill — continuation or reversal depending on context. Defined target = the gap edge.",
  },
  gap_reject: {
    code: "gap_reject", group: "Day", label: "Gap reject",
    what: "Price approached a gap level and rejected it.",
    why: "An unfilled gap that rejects shows the move has strength — the gap holds as support/resistance.",
    how: "Trade in the direction of the rejection. Stop through the gap level.",
  },
  gap_support: {
    code: "gap_support", group: "Day", label: "Gap support",
    what: "A prior gap is acting as support on a pullback.",
    why: "Gap edges are remembered levels; price holding the gap = buyers defending it.",
    how: "Enter on the hold of the gap support. Stop below the gap. Target the next level up.",
  },
  lost_support_reject: {
    code: "lost_support_reject", group: "Day", label: "Lost-support rejection",
    what: "A former support level broke and is now rejecting price from below as resistance.",
    why: "Broken support flips to resistance — the dual-role flip. A rejection there confirms sellers are in control (short context).",
    how: "Short the rejection of broken support. Stop above the level. Target the level below.",
  },
};

export function patternFor(raw?: string | null): PatternInfo | null {
  if (!raw) return null;
  const c = raw.toLowerCase().replace(/^tv_/, "").replace(/^staged_/, "");
  if (EXPLICIT[c]) return EXPLICIT[c];
  if (/rc_?4h|rc4/.test(c)) return EXPLICIT.rc_4h;
  if (/rc_?h\b|rch/.test(c)) return EXPLICIT.rc_h;
  if (c.endsWith("_held") || c.includes("avwap_held")) return held(c);
  if (c.endsWith("_reclaim")) return reclaim(c);
  if (c.endsWith("_break")) return brk(c);
  if (c.endsWith("_rejection")) return rejection(c);
  return null;
}
