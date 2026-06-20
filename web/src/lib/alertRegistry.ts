/** Alert pattern registry (#64 Sub-spec K) — the canonical explanation for every LIVE
 *  alert type the Pines fire. One source of truth for the human label + the education
 *  (what / why / how, plus the structured entry / stop / target). `patternFor()` resolves
 *  any raw alert_type code (strips tv_/staged_ prefixes, handles per-level + per-MA variants)
 *  to its family explanation. Cards, Strategy Analysis, Declined, and the Learn page read this.
 */

export type PatternGroup = "Day" | "Swing" | "Trend" | "Context";
export interface PatternInfo {
  code: string;
  label: string;
  group: PatternGroup;
  dir?: "long" | "short";
  what: string;            // what fired
  why: string;             // why it's an edge
  how: string;             // one-line summary (fallback when entry/stop/target absent)
  entry?: string;          // structured plan — shown as chips on the Learn page
  stop?: string;
  target?: string;
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
  return { name: "the level", abbr: "the level" };
}
function maName(code: string): string {
  const m = code.match(/(ema|sma)(\d+)/);
  return m ? `${m[2]} ${m[1].toUpperCase()}` : "moving average";
}

function held(code: string): PatternInfo {
  const L = lvl(code);
  return {
    code, group: "Day", label: `${L.abbr} held`, dir: "long",
    what: `Price was above the ${L.name}, dipped down to test it, and closed back above — the level held as support.`,
    why: `A level that gets defended — buyers step in on the dip — is real support. You enter where risk is tightly defined and the crowd leans the same way.`,
    how: `Enter on the hold; stop below the level; target the next level up.`,
    entry: `On the hold — a close back above the ${L.abbr}`,
    stop: `Just below the ${L.abbr}; a break there means the thesis is wrong`,
    target: `The next level above`,
  };
}
function reclaim(code: string): PatternInfo {
  const L = lvl(code);
  return {
    code, group: "Day", label: `${L.abbr} reclaim`, dir: "long",
    what: `Price lost the ${L.name} (closed below it) then snapped back above — a reclaim.`,
    why: `Losing a level and reclaiming it traps the sellers who shorted the breakdown; their stops fuel the move back up — a liquidity-grab reversal. Only valid when the day OPENED above the level (owned support, not resistance).`,
    how: `Enter on the reclaim; stop below the reclaim low; target the next level up.`,
    entry: `On the reclaim — a close back above the ${L.abbr}`,
    stop: `Below the reclaim low (the undercut wick)`,
    target: `The next level above`,
  };
}
function brk(code: string): PatternInfo {
  const L = lvl(code);
  return {
    code, group: "Day", label: `${L.abbr} break`, dir: "long",
    what: `Price broke and closed above the ${L.name} — a breakout through resistance.`,
    why: `Clearing a prior high removes overhead supply; breakouts that hold continue as trapped shorts cover and breakout buyers pile in.`,
    how: `Enter on the break or its retest-hold; stop back below; target the next level.`,
    entry: `On the break, or the retest-hold of the broken ${L.abbr}`,
    stop: `Back below the broken ${L.abbr}`,
    target: `The next level / measured move`,
  };
}
function rejection(code: string): PatternInfo {
  const L = lvl(code);
  return {
    code, group: "Day", label: `${L.abbr} rejection`, dir: "short",
    what: `Price rallied up into the ${L.name} from below, wicked it, and closed back under — rejected at resistance.`,
    why: `A level approached from below is resistance. A clean rejection — sellers defend it — is a short; fade the failed push.`,
    how: `Short the rejection; stop above the level; target the level below.`,
    entry: `On the rejection — a close back below the ${L.abbr}`,
    stop: `Above the ${L.abbr}`,
    target: `The level below`,
  };
}
function maBounce(code: string): PatternInfo {
  const MA = maName(code);
  return {
    code, group: "Day", label: `${MA} bounce`, dir: "long",
    what: `In an uptrend, price pulled back to the ${MA}, tested it, and bounced — the moving average held as dynamic support.`,
    why: `A rising MA is a moving floor the trend defends. Buying the bounce keeps you with the trend at tight, well-defined risk just below the line — not chasing extended price.`,
    how: `Enter on the bounce; stop below the ${MA}; target the prior high.`,
    entry: `On the bounce — a close turning back up off the ${MA}`,
    stop: `Below the ${MA} / the bounce low`,
    target: `The prior high or next level up`,
  };
}
function maRejection(code: string): PatternInfo {
  const MA = maName(code);
  return {
    code, group: "Day", label: `${MA} rejection`, dir: "short",
    what: `In a downtrend, price rallied up into the ${MA} from below and rejected — the MA held as dynamic resistance.`,
    why: `A falling MA caps rallies in a downtrend; sellers defend it. Fading the rejection keeps you with the dominant trend at tight risk above the line.`,
    how: `Short the rejection; stop above the ${MA}; target the prior low.`,
    entry: `On the rejection — a close back below the ${MA}`,
    stop: `Above the ${MA}`,
    target: `The prior low`,
  };
}

const EXPLICIT: Record<string, PatternInfo> = {
  rc_4h: {
    code: "rc_4h", group: "Day", label: "RC 4h — reclaim low", dir: "long",
    what: "On the 4-hour chart, price undercut the prior 4h low and closed back above it.",
    why: "The cornerstone day-trade setup: the undercut sweeps stops below the prior 4h low, then the reclaim reverses on the trapped sellers. 4h anchoring filters out 5-minute noise.",
    how: "Enter on the 4h reclaim; stop below the undercut low; target the nearest level/EMA above.",
    entry: "On the 4h close back above the prior 4h low",
    stop: "Below the undercut low (the stop sweep)",
    target: "The nearest level / EMA above",
  },
  rc_h: {
    code: "rc_h", group: "Day", label: "RC-H 4h — reclaim high", dir: "long",
    what: "Price dipped below the prior 4h high and closed back above it — a breakout-retest reclaim.",
    why: "A breakout that pulls back below the broken high then reclaims it shakes out weak hands before continuing — the cleanest version of a breakout entry.",
    how: "Enter on the reclaim of the prior 4h high; stop below the retest low; target the next level up.",
    entry: "On the reclaim of the prior 4h high",
    stop: "Below the retest low",
    target: "The next level up",
  },
  weekly_rc: {
    code: "weekly_rc", group: "Swing", label: "Weekly reclaim", dir: "long",
    what: "Price reclaimed a weekly level (closed back above it on the weekly timeframe).",
    why: "Weekly-level reclaims are higher-conviction, lower-stress swing reversals — institutional timeframe, fewer signals, bigger moves.",
    how: "Swing entry on the weekly reclaim; stop below the weekly level; hold for the higher-timeframe target.",
    entry: "On the weekly close back above the level",
    stop: "Below the weekly level",
    target: "The higher-timeframe target (often RSI 70)",
  },
  ema_5_20_cross: {
    code: "ema_5_20_cross", group: "Swing", label: "5/20 EMA cross", dir: "long",
    what: "The daily 5 EMA crossed above the 20 EMA — a short-term momentum shift up.",
    why: "A classic momentum trigger (Steve Burns): the fast average crossing the slow one marks a trend turning up. Best on names already in a base.",
    how: "Swing entry on the cross; stop below the recent swing low; exit on the cross back down or RSI 70.",
    entry: "On the daily 5-over-20 EMA cross",
    stop: "Below the recent swing low",
    target: "Hold while 5 > 20; take profit near RSI 70",
  },
  rsi_oversold: {
    code: "rsi_oversold", group: "Swing", label: "RSI oversold reclaim", dir: "long",
    what: "Daily RSI dropped into oversold (30–35) and is turning back up — buying weakness in an uptrend.",
    why: "Institutions buy weakness in uptrends. Oversold-and-reclaiming on a strong name is a high-reward dip entry — never buy below 30 (falling knife).",
    how: "Enter as RSI reclaims from 30–35; stop below the swing low; target RSI 70.",
    entry: "As RSI turns back up out of the 30–35 zone",
    stop: "Below the swing low",
    target: "RSI 70",
  },
  rsi_70: {
    code: "rsi_70", group: "Swing", label: "RSI 70 — momentum target",
    what: "Daily RSI reached 70 — the momentum/exit target for a swing bought on weakness.",
    why: "RSI 70 is where strength gets sold (institutional sell-into-strength). It's the natural exit for an RSI-30 / EMA-hold swing, not a fresh entry.",
    how: "Use as a take-profit signal on swing longs — this is an EXIT, not an entry.",
  },
  gap_support: {
    code: "gap_support", group: "Day", label: "Gap support bounce", dir: "long",
    what: "A prior unfilled gap you opened above is acting as support on a pullback, and held.",
    why: "Gap edges are remembered levels; price holding the gap means buyers are defending it — a dip-buy with the gap as a clean line in the sand.",
    how: "Enter on the hold of the gap support; stop below the gap; target the next level up.",
    entry: "On the hold of the gap edge as support",
    stop: "Below the gap",
    target: "The next level up",
  },
  gap_fill: {
    code: "gap_fill", group: "Day", label: "Gap fill",
    what: "Price traded back into and filled an opening gap.",
    why: "Gaps act as magnets; the fill is a known target and often a reaction point — continuation or reversal depending on context.",
    how: "Trade the reaction at the fill; the gap edge is the defined target.",
  },
  gap_reject: {
    code: "gap_reject", group: "Day", label: "Gap reject", dir: "short",
    what: "Price approached an overhead gap level and rejected it.",
    why: "An unfilled gap that rejects shows the move still has strength — the gap holds as resistance.",
    how: "Trade in the direction of the rejection; stop through the gap level.",
    entry: "On the rejection of the overhead gap",
    stop: "Through (above) the gap level",
    target: "The level below",
  },
  gap_up_continuation_long: {
    code: "gap_up_continuation_long", group: "Day", label: "Gap-and-go", dir: "long",
    what: "The stock opened ABOVE the prior-day high (a gap up) and held, continuing higher.",
    why: "An opening gap above resistance with no overhead supply runs on momentum; the open acts as support for the day — you ride the trapped shorts and FOMO.",
    how: "Enter on the hold above the open; stop below the opening-range low; target the measured move.",
    entry: "On the hold above the opening price",
    stop: "Below the opening-range low",
    target: "The measured move / next level up",
  },
  pullback_long: {
    code: "pullback_long", group: "Day", label: "Uptrend pullback (Buy 1)", dir: "long",
    what: "In an established uptrend, price pulled back and is resuming — a continuation entry.",
    why: "Buying a pullback in an uptrend gets you in WITH the trend at better risk than chasing. The trend is the edge; the pullback is just a better price.",
    how: "Enter as the pullback resumes up; stop below the pullback low; target the prior high.",
    entry: "As the pullback resumes higher",
    stop: "Below the pullback low",
    target: "The prior high / trend extension",
  },
  lost_support_reject: {
    code: "lost_support_reject", group: "Day", label: "Lost-support rejection", dir: "short",
    what: "A former support level broke and is now rejecting price from below as resistance.",
    why: "Broken support flips to resistance — the dual-role flip. A rejection there confirms sellers are in control.",
    how: "Short the rejection of broken support; stop above the level; target the level below.",
    entry: "On the rejection of the broken level from below",
    stop: "Above the level",
    target: "The level below",
  },
  htf_sr_bounce: {
    code: "htf_sr_bounce", group: "Swing", label: "Multi-period support bounce", dir: "long",
    what: "Price wicked down into a clustered weekly/monthly support floor and closed back above.",
    why: "When several weekly/monthly levels stack at one price, that's a wall the whole market sees. A bounce off a multi-period floor is high-conviction support.",
    how: "Long on the bounce off the cluster; stop below the cluster; target the next HTF level up.",
    entry: "On the bounce off the weekly/monthly cluster",
    stop: "Below the cluster",
    target: "The next higher-timeframe level up",
  },
  htf_sr_reject: {
    code: "htf_sr_reject", group: "Swing", label: "Multi-period resistance reject", dir: "short",
    what: "Price wicked up into a clustered weekly/monthly resistance wall and closed back below.",
    why: "Stacked weekly/monthly highs are a wall everyone watches. A rejection there is a high-conviction short against a level the whole market respects.",
    how: "Short the rejection of the cluster; stop above it; target the next HTF level down.",
    entry: "On the rejection of the weekly/monthly cluster",
    stop: "Above the cluster",
    target: "The next higher-timeframe level down",
  },
  index_open_strength: {
    code: "index_open_strength", group: "Context", label: "Index above its open",
    what: "The index (SPY/QQQ) reclaimed and is holding above today's opening price — broad-market strength.",
    why: "This is market context, not a single-name trade: when the index holds above its open, the tape is healthy and your long setups have a tailwind.",
    how: "Use as a regime filter — favor longs when this is on; it confirms the broad tape supports your entries.",
  },
};

export function patternFor(raw?: string | null): PatternInfo | null {
  if (!raw) return null;
  const c = raw.toLowerCase().replace(/^tv_/, "").replace(/^staged_/, "");
  if (EXPLICIT[c]) return EXPLICIT[c];
  if (/rc_?4h|rc4/.test(c)) return EXPLICIT.rc_4h;
  if (/rc_?h\b|rch/.test(c)) return EXPLICIT.rc_h;
  if (/ma_bounce/.test(c)) return maBounce(c);
  if (/ma_rejection/.test(c)) return maRejection(c);
  if (c.endsWith("_held") || c.includes("avwap_held")) return held(c);
  if (c.endsWith("_reclaim")) return reclaim(c);
  if (c.endsWith("_break")) return brk(c);
  if (c.endsWith("_rejection")) return rejection(c);
  return null;
}
