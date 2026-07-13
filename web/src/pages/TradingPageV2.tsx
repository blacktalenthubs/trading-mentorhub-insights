/** TradingPage V2 — Webull-quality layout with chart dominance.
 *
 *  Layout (desktop):
 *    Left:   180px compact watchlist (collapsible to 48px icon-only)
 *    Center: Chart (65-70% of viewport) + bottom setup strip
 *    Right:  320px tabbed sidebar (AI Coach | Signals | Options Flow)
 *
 *  Mobile: full-width chart + bottom tabs for AI/Signals
 */

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import {
  useScanner,
  useOHLCV,
  useAlertsToday,
  useAlertSessionDates,
  useAlertsForDate,
  useWatchlist,
  useWatchlistGroups,
  useSectorsWatchlist,
  useMasterWatchlistView,
  useMe,
  useAddSymbol,
  useCopySectorsWatchlist,
  useRemoveSymbol,
  useToggleWatchlistFocus,
  useClearWatchlistFocus,
  useLivePrices,
  useWatchlistRank,
  useWatchlistSignalsToday,
  useChartLevels,
  useAddChartLevel,
  useUpdateChartLevel,
  useDeleteChartLevel,
  useMarketReports,
} from "../api/hooks";
import { PremarketPanel, type PmSignal } from "../components/PremarketPanel";
import type { WatchlistRankItem } from "../types";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SignalResult, Alert } from "../types";
import { formatSetup, isFeedSignal, setupBlurb } from "../lib/alertFormat";
import { DisclaimerFooter } from "../components/DisclaimerModal";
import { toast } from "../components/Toast";
import CandlestickChart from "../components/CandlestickChart";
import SpyRegimeStrip from "../components/SpyRegimeStrip";
import ThemeToggle from "../components/ThemeToggle";
import MarketClock from "../components/MarketClock";
import LevelMap from "../components/LevelMap";
import AlertLog from "../components/AlertLog";
import NewSignalToast from "../components/NewSignalToast";
import { SkeletonRow } from "../components/ui/Skeleton";
import {
  Search,
  Plus,
  X,
  Loader2,
  SlidersHorizontal,
  Brain,
  Zap,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Menu,
  Sparkles,
  Eye,
  EyeOff,
} from "lucide-react";

/* ── Constants ──────────────────────────────────────────────────────── */

// S/R line types — color + label applied when drawing / retyping a line.
const LINE_TYPES = {
  support:    { color: "#22c55e", label: "Support",    short: "S" },
  resistance: { color: "#ef4444", label: "Resistance", short: "R" },
  line:       { color: "#3b82f6", label: "Line",       short: "—" },
} as const;
type LineType = keyof typeof LINE_TYPES;

// Snap a clicked price to a clean increment scaled by magnitude, so S/R lines
// land on memorable levels rather than an arbitrary pixel price.
function snapPrice(p: number): number {
  const step = p >= 250 ? 0.1 : p >= 50 ? 0.05 : p >= 5 ? 0.01 : 0.001;
  return Math.round(p / step) * step;
}
function typeOfLevel(color: string): LineType {
  if (color === LINE_TYPES.support.color) return "support";
  if (color === LINE_TYPES.resistance.color) return "resistance";
  return "line";
}

// Prior-day + prior-week high/low from the chart's OHLCV — the only auto levels
// we draw (PDH/PDL/PWH/PWL). Computed from bars so it works on any timeframe/symbol.
function keyLevels(bars: { timestamp: string; high: number; low: number }[] | undefined) {
  const out = { pdh: null as number | null, pdl: null as number | null, pwh: null as number | null, pwl: null as number | null };
  if (!bars || bars.length === 0) return out;
  // Collapse bars into calendar days (intraday bars share a date).
  const days: { key: string; hi: number; lo: number }[] = [];
  for (const b of bars) {
    const k = b.timestamp.slice(0, 10);
    const last = days[days.length - 1];
    if (last && last.key === k) { last.hi = Math.max(last.hi, b.high); last.lo = Math.min(last.lo, b.low); }
    else days.push({ key: k, hi: b.high, lo: b.low });
  }
  if (days.length >= 2) { out.pdh = days[days.length - 2].hi; out.pdl = days[days.length - 2].lo; }
  // Collapse days into ISO weeks.
  const isoWeek = (dateStr: string) => {
    const d = new Date(dateStr + "T00:00:00Z");
    const day = (d.getUTCDay() + 6) % 7;            // Mon=0
    d.setUTCDate(d.getUTCDate() - day + 3);          // nearest Thursday
    const firstThu = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
    return d.getUTCFullYear() * 100 + (1 + Math.round((d.getTime() - firstThu.getTime()) / 6.048e8));
  };
  const weeks: { key: number; hi: number; lo: number }[] = [];
  for (const dd of days) {
    const k = isoWeek(dd.key);
    const last = weeks[weeks.length - 1];
    if (last && last.key === k) { last.hi = Math.max(last.hi, dd.hi); last.lo = Math.min(last.lo, dd.lo); }
    else weeks.push({ key: k, hi: dd.hi, lo: dd.lo });
  }
  if (weeks.length >= 2) { out.pwh = weeks[weeks.length - 2].hi; out.pwl = weeks[weeks.length - 2].lo; }
  return out;
}

const TIMEFRAMES = [
  { label: "1m", period: "1d", interval: "1m" },
  { label: "5m", period: "5d", interval: "5m" },
  { label: "15m", period: "5d", interval: "15m" },
  { label: "30m", period: "5d", interval: "30m" },
  { label: "1H", period: "5d", interval: "60m" },
  { label: "4H", period: "1mo", interval: "60m" },
  { label: "D", period: "1y", interval: "1d" },
  { label: "W", period: "2y", interval: "1wk" },
  { label: "M", period: "10y", interval: "1mo" },
] as const;

const DEFAULT_TF = 6; // Daily

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "\u2014";
  return v.toFixed(decimals);
}

/* ── Indicator config ──────────────────────────────────────────────── */

interface IndicatorDef {
  key: string;
  label: string;
  color: string;
  group: "ema" | "sma" | "other";
}

const ALL_INDICATORS: IndicatorDef[] = [
  { key: "ema8", label: "EMA 8", color: "#f472b6", group: "ema" },
  { key: "ema21", label: "EMA 21", color: "#60a5fa", group: "ema" },
  { key: "ema50", label: "EMA 50", color: "#f59e0b", group: "ema" },
  { key: "ema100", label: "EMA 100", color: "#a78bfa", group: "ema" },
  { key: "ema200", label: "EMA 200", color: "#34d399", group: "ema" },
  { key: "sma20", label: "SMA 20", color: "#38bdf8", group: "sma" },
  { key: "sma50", label: "SMA 50", color: "#fb923c", group: "sma" },
  { key: "sma100", label: "SMA 100", color: "#c084fc", group: "sma" },
  { key: "sma200", label: "SMA 200", color: "#4ade80", group: "sma" },
  { key: "vwap", label: "VWAP", color: "#e879f9", group: "other" },
  { key: "fvbands", label: "FV Bands", color: "#fb923c", group: "other" },
];

// Key EMAs always on by default: 8 / 21 / 50 / 100 / 200.
const DEFAULT_INDICATORS = new Set(["ema8", "ema21", "ema50", "ema100", "ema200"]);

function loadSavedIndicators(): Set<string> | null {
  try {
    // v2 key — bumped 2026-05-21 when the EMA defaults changed to 8/21/50/100/200.
    const raw = localStorage.getItem("chart_indicators_v2");
    if (!raw) return null;
    const arr = JSON.parse(raw);
    if (!Array.isArray(arr) || arr.length === 0) return null;
    const validKeys = new Set(ALL_INDICATORS.map((i) => i.key));
    const filtered = arr.filter((k: string) => validKeys.has(k));
    return filtered.length > 0 ? new Set(filtered) : null;
  } catch {
    return null;
  }
}

function scoreBadgeClass(score: number): string {
  if (score >= 70) return "bg-bullish/15 text-bullish-text border-bullish/25";
  if (score >= 40) return "bg-warning/15 text-warning-text border-warning/25";
  return "bg-surface-3 text-text-faint border-border-subtle";
}

/* ── Idea badge ──────────────────────────────────────────────────────
 * Flags setups the scanner folded in from your conviction / long-term ideas
 * (these aren't on your watchlist). Conviction = accent, long-term = green.
 * SOLID when at entry ("Potential Entry"), OUTLINE when only approaching, so
 * you can tell which are actionable now vs setting up. */
function IdeaBadge({ source, actionLabel, className = "" }: { source?: string; actionLabel?: string; className?: string }) {
  if (!source || source === "watchlist") return null;
  const atEntry = actionLabel === "Potential Entry";
  const isConv = source === "conviction";
  const tone = isConv
    ? (atEntry ? "bg-accent/15 text-accent border-transparent" : "text-accent border-accent/40")
    : (atEntry ? "bg-bullish/15 text-bullish-text border-transparent" : "text-bullish-text border-bullish/40");
  return (
    <span
      className={`shrink-0 inline-flex items-center text-[7.5px] font-bold uppercase tracking-wide px-1 py-px rounded border leading-none ${tone} ${className}`}
      title={`${isConv ? "Conviction" : "Long-term (swing)"} idea — ${atEntry ? "at entry today" : "approaching entry"}`}
    >
      {isConv ? "Conv" : "LT"}
    </span>
  );
}

/* ── Compact Watchlist Row ──────────────────────────────────────────── */

function CompactWatchlistRow({
  signal,
  selected,
  onClick,
  onRemove,
  onToggleFocus,
  focused,
  livePrice,
  rankItem,
  collapsed,
  hasSignal,
}: {
  signal: SignalResult;
  selected: boolean;
  onClick: () => void;
  onRemove?: () => void;
  onToggleFocus?: () => void;
  focused?: boolean;
  livePrice?: { price: number; change_pct: number };
  rankItem?: WatchlistRankItem;
  collapsed: boolean;
  hasSignal?: boolean;
}) {
  // Row actions reveal on hover (desktop) but are ALWAYS visible on touch
  // (pointer-coarse) — otherwise there's no way to focus/remove on mobile.
  const reveal = "opacity-0 pointer-events-none transition-opacity group-hover:opacity-100 group-hover:pointer-events-auto pointer-coarse:opacity-100 pointer-coarse:pointer-events-auto";
  const displayPrice = livePrice?.price ?? signal.close;
  const changePct = livePrice?.change_pct ?? 0;
  const changeColor = changePct >= 0 ? "text-bullish-text" : "text-bearish-text";
  const score = rankItem?.score ?? signal.score;

  if (collapsed) {
    return (
      <button
        onClick={onClick}
        title={`${signal.symbol} $${fmt(displayPrice)}`}
        className={`group relative w-full py-2 text-center text-[11px] font-bold transition-colors ${
          selected
            ? "text-accent bg-accent/[0.08] border-l-2 border-accent"
            : "text-text-secondary hover:text-text-primary hover:bg-surface-2/60 border-l-2 border-transparent"
        }`}
      >
        {signal.symbol.slice(0, 4)}
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      className={`group relative flex w-full items-center px-2.5 py-2 text-left transition-all duration-100 ${
        selected
          ? "bg-accent/[0.06] border-l-2 border-accent"
          : "border-l-2 border-transparent hover:bg-surface-2/60"
      }`}
    >
      {/* Focus star — always visible if focused; otherwise reveal on hover
          (desktop) and ALWAYS on touch. p-1.5 = comfortable mobile tap target. */}
      {onToggleFocus && signal.source === "watchlist" && (
        <button
          onClick={(e) => { e.stopPropagation(); onToggleFocus(); }}
          className={`shrink-0 mr-0.5 p-1.5 transition-colors ${
            focused
              ? "text-amber-400 hover:text-amber-300"
              : `text-text-faint hover:text-amber-400 ${reveal}`
          }`}
          title={focused ? "Remove from today's focus" : "Add to today's focus"}
        >
          <svg className="h-3 w-3" fill={focused ? "currentColor" : "none"} stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.196-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.783-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
          </svg>
        </button>
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[12px] font-bold text-text-primary leading-tight truncate">
            {signal.symbol}
          </span>
          {/* Amber "signal fired today" dot */}
          {hasSignal && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400 shadow-[0_0_4px_rgba(245,183,61,0.7)]" title="Signal fired today" />}
          {/* Source badge — conviction / long-term idea, at-entry vs approaching. */}
          <IdeaBadge source={signal.source} actionLabel={signal.action_label} />
          {/* Score badge — reveal on hover (desktop), always on touch */}
          <span
            className={`text-[8px] font-bold px-1 py-px rounded border leading-tight opacity-0 group-hover:opacity-100 pointer-coarse:opacity-100 transition-opacity ${scoreBadgeClass(score)}`}
          >
            {score}
          </span>
        </div>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="font-mono text-[11px] text-text-secondary leading-none tabular-nums">
            ${fmt(displayPrice)}
          </span>
          <span className={`font-mono text-[10px] leading-none tabular-nums ${changeColor}`}>
            {changePct >= 0 ? "+" : ""}
            {changePct.toFixed(2)}%
          </span>
        </div>
      </div>
      {onRemove && signal.source === "watchlist" && (
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className={`shrink-0 p-1.5 text-text-faint hover:text-bearish-text active:text-bearish-text transition-colors ${reveal}`}
          title="Remove from watchlist"
          aria-label={`Remove ${signal.symbol} from watchlist`}
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </button>
  );
}

/* ── Signal Feed Tab ──────────────────────────────────────────────── */

/** Format an ISO session date (YYYY-MM-DD) as e.g. "May 20". */
function formatSessionDate(iso: string): string {
  const d = new Date(`${iso}T12:00:00`);
  return isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const fmtPrice = (v: number | null | undefined) =>
  v != null ? `$${v.toFixed(2)}` : "—";

// Short, human label for an alert that fired but was NOT routed to Telegram
// (recorded for review). Kept visible in-feed, greyed + badged, so the user
// can evaluate what the gates caught. type_not_enabled / confluence_collapsed
// are filtered out upstream — they never reach here.
const NOT_ROUTED_LABELS: Record<string, string> = {
  spy_below_pdl: "SPY < PDL",
  uptrend_gate_failed: "uptrend gate",
  basing_chop: "chop",
  outside_session: "off-hours",
  not_focus: "not in Focus",
  type_not_enabled: "type off",
  spy_market_gate: "SPY gate",
};
function notRoutedLabel(reason?: string | null): string | null {
  if (!reason) return null;
  return NOT_ROUTED_LABELS[reason] ?? reason.replace(/_/g, " ").slice(0, 24);
}

// A human badge for the COLLAPSED reasons (hidden from the feed unless "Show
// collapsed" is on). Carries the price/anchor it lost to so the dedup is auditable.
// Returns null for non-collapse reasons (so the card shows NOT SENT instead).
function collapsedLabel(reason?: string | null): string | null {
  if (!reason) return null;
  const i = reason.indexOf(":");
  const base = i >= 0 ? reason.slice(0, i) : reason;
  const anchor = i >= 0 ? reason.slice(i + 1) : "";
  if (base === "dedup_confluence") return `merged · $${anchor}`;
  if (base === "dedup_chase") return `chase · ≥ $${anchor}`;
  if (base === "dedup_cooldown") return "cooldown · < 30m";
  if (base === "confluence_collapsed") return "same-bar";
  if (reason === "late_session") return "late session";
  return null;
}

function SignalFeedTab({
  alerts,
  alertsError,
  onSelectSymbol,
  signalDate = "",
  assetFilter = "all",
  onAssetFilterChange,
}: {
  alerts?: Alert[];
  alertsError: unknown;
  onSelectSymbol: (sym: string) => void;
  signalDate?: string;
  assetFilter?: "all" | "stocks" | "crypto";
  onAssetFilterChange?: (a: "all" | "stocks" | "crypto") => void;
}) {
  const [search, setSearch] = useState("");
  // "Show collapsed" — reveal the deduped/merged alerts (hidden by default) so the
  // dedup is auditable. Persisted; default OFF (clean feed).
  const [showCollapsed, setShowCollapsed] = useState<boolean>(
    () => typeof window !== "undefined" && localStorage.getItem("show_collapsed") === "1",
  );
  function toggleShowCollapsed() {
    setShowCollapsed((p) => {
      const next = !p;
      try { localStorage.setItem("show_collapsed", next ? "1" : "0"); } catch { /* ignore */ }
      return next;
    });
  }
  // Sort options — persisted to localStorage so refresh doesn't reset.
  type FeedSort = "time" | "grade" | "vol" | "slope" | "symbol" | "rr";
  const SORT_LABELS: Record<FeedSort, string> = {
    time: "Newest", grade: "Grade A→C", vol: "Volume ×",
    slope: "Slope %", symbol: "Symbol", rr: "R:R (reward:risk)",
  };
  const [sortBy, setSortBy] = useState<FeedSort>(() => {
    if (typeof window === "undefined") return "time";
    return (localStorage.getItem("signal_feed_sort") as FeedSort) || "time";
  });
  const [sortOpen, setSortOpen] = useState(false);
  function changeSort(s: FeedSort) {
    setSortBy(s);
    setSortOpen(false);
    try { localStorage.setItem("signal_feed_sort", s); } catch {}
  }

  // Grade chip filter — view-only, doesn't affect Telegram routing.
  // "all" → show every grade. "A"/"B"/"C" → only that grade.
  type GradeFilter = "all" | "A" | "B" | "C";
  const [gradeFilter, setGradeFilter] = useState<GradeFilter>(() => {
    if (typeof window === "undefined") return "all";
    return (localStorage.getItem("signal_feed_grade") as GradeFilter) || "all";
  });
  function changeGradeFilter(g: GradeFilter) {
    setGradeFilter(g);
    try { localStorage.setItem("signal_feed_grade", g); } catch {}
  }

  // Which panel is showing: the live delivered feed, or the not-routed
  // 3 STYLE panels (day_trade / swing / long_term). Every alert is FILED by style —
  // delivered AND recorded-not-delivered (the latter shown dimmed + "NOT SENT"). Tracking
  // and delivery are separate; only Telegram/push are gated, the feed shows everything.
  const [view, setView] = useState<"premarket" | "day" | "swing">("day");
  // Premarket signals are persisted per session in market_reports[premarket_signals],
  // so honor the session date picker like the day/position feeds do (the alerts prop
  // is already date-filtered by the parent). No date selected → latest report.
  const { data: pmReport } = useMarketReports(signalDate || undefined);
  const pmSignals = useMemo<PmSignal[]>(() => {
    try { return (JSON.parse(pmReport?.premarket_signals?.body ?? "{}").signals ?? []) as PmSignal[]; }
    catch { return []; }
  }, [pmReport]);

  // Type hide-list — view-only. Set of alert_type strings to exclude from
  // the feed. Lets the user temporarily mute noisy types (e.g. historical
  // mtd_avwap_held already in DB) without touching Settings/routing.
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(() => {
    if (typeof window === "undefined") return new Set();
    try {
      const raw = localStorage.getItem("signal_feed_hidden_types");
      return new Set(raw ? (JSON.parse(raw) as string[]) : []);
    } catch { return new Set(); }
  });
  // One combined "Filters" popover holds asset class + grade + type hide-list,
  // so the toolbar stays at two rows instead of four.
  const [filtersOpen, setFiltersOpen] = useState(false);
  function toggleHiddenType(t: string) {
    setHiddenTypes((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t); else next.add(t);
      try { localStorage.setItem("signal_feed_hidden_types", JSON.stringify([...next])); } catch {}
      return next;
    });
  }
  function clearHiddenTypes() {
    setHiddenTypes(new Set());
    try { localStorage.removeItem("signal_feed_hidden_types"); } catch {}
  }
  function hideAllTypes(types: string[]) {
    const next = new Set(types);
    setHiddenTypes(next);
    try { localStorage.setItem("signal_feed_hidden_types", JSON.stringify([...next])); } catch {}
  }

  if (alertsError) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <p className="text-xs text-bearish-text mb-2">Failed to load alerts</p>
          <button
            onClick={() => window.location.reload()}
            className="text-[10px] text-accent hover:text-accent-hover"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // The feed, split by trade STYLE. Each panel shows ALL its alerts — delivered AND
  // recorded-not-delivered (gate catches: type off, SPY gate, grade, allowlists). The
  // undelivered ones render dimmed + "NOT SENT". Same-moment dup noise
  // (confluence_collapsed) and the Spec 67 entry/time dedup drops (dedup_cooldown /
  // dedup_chase) are dropped from the feed — collapsed to the first/best entry.
  // styleOf falls back to day_trade for old rows.
  // CLEAN FEED (2026-07-02): the panels show DELIVERED alerts ONLY (suppressed_reason IS NULL).
  // Everything recorded-but-not-delivered — NOT SENT gate catches (type off / SPY gate / grade /
  // allowlist) AND dedup-collapsed — is hidden by default and revealed by the toggle for review,
  // so the live feed reads as "what actually sent" and isn't a wall of NOT SENT.
  const feedAllRaw = (alerts ?? []).filter(
    (a) => isFeedSignal(a.alert_type) && (showCollapsed || !a.suppressed_reason),
  );
  // Count of everything hidden from the clean feed (not-sent + deduped) — the toggle badge.
  const collapsedCount = (alerts ?? []).filter(
    (a) => isFeedSignal(a.alert_type) && !!a.suppressed_reason,
  ).length;
  // Day vs Swing (2026-07-07). DAY = a day trade — you're OUT by the close (sell it that session
  // at some point). SWING = held multiple days, as long as the thesis holds (swing + long-term
  // styles). Premarket is its own isolated channel.
  const dayAlerts = feedAllRaw.filter((a) => ((a as { style?: string }).style ?? "day_trade") === "day_trade");
  const swingAlerts = feedAllRaw.filter((a) => ((a as { style?: string }).style ?? "day_trade") !== "day_trade");
  const feedAlerts = view === "premarket" ? [] : view === "day" ? dayAlerts : swingAlerts;
  // Counts per grade for the chip badges.
  const gradeCounts = feedAlerts.reduce(
    (acc, a) => {
      const g = (a.grade ?? "C").toUpperCase();
      if (g === "A") acc.A++;
      else if (g === "B") acc.B++;
      else acc.C++;
      return acc;
    },
    { A: 0, B: 0, C: 0 },
  );
  // Per-type counts for the type-filter popover (built from the pre-hide
  // list so the user can still see — and re-show — types they're hiding).
  const typeCounts = feedAlerts.reduce<Record<string, number>>((acc, a) => {
    const t = a.alert_type || "unknown";
    acc[t] = (acc[t] ?? 0) + 1;
    return acc;
  }, {});
  const typeOptions = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);
  const q = search.trim().toUpperCase();
  let filtered = q
    ? feedAlerts.filter((a) => (a.symbol || "").toUpperCase().includes(q) || formatSetup(a.alert_type).toUpperCase().includes(q) || (a.alert_type || "").toUpperCase().includes(q))
    : feedAlerts;
  if (hiddenTypes.size > 0) {
    filtered = filtered.filter((a) => !hiddenTypes.has(a.alert_type || "unknown"));
  }
  if (gradeFilter !== "all") {
    filtered = filtered.filter((a) => (a.grade ?? "C").toUpperCase() === gradeFilter);
  }

  // Sort applied client-side so the user can flip it without an extra fetch.
  const GRADE_RANK: Record<string, number> = { A: 3, B: 2, C: 1 };
  const visible = [...filtered].sort((a, b) => {
    if (sortBy === "grade") {
      const ga = GRADE_RANK[a.grade ?? "C"] ?? 0;
      const gb = GRADE_RANK[b.grade ?? "C"] ?? 0;
      if (ga !== gb) return gb - ga;
      // Tie-break by time desc.
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    }
    if (sortBy === "vol") {
      const va = a.volume_ratio ?? -1;
      const vb = b.volume_ratio ?? -1;
      if (va !== vb) return vb - va;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    }
    if (sortBy === "slope") {
      const sa = a.vwap_slope_pct ?? -999;
      const sb = b.vwap_slope_pct ?? -999;
      if (sa !== sb) return sb - sa;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    }
    if (sortBy === "symbol") {
      return (a.symbol || "").localeCompare(b.symbol || "");
    }
    if (sortBy === "rr") {
      const rrOf = (x: typeof a) => (x.entry != null && x.target_1 != null && x.stop != null && x.entry !== x.stop) ? Math.abs((x.target_1 - x.entry) / (x.entry - x.stop)) : -1;
      const ra = rrOf(a), rb = rrOf(b);
      if (ra !== rb) return rb - ra;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    }
    // default: time desc (newest first)
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  const listAlerts = visible;

  // Grade chip — visual style per letter.
  const CHIP_STYLES: Record<GradeFilter, { active: string; inactive: string }> = {
    all: {
      active: "bg-accent text-bg-base border-accent",
      inactive: "bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2",
    },
    A: {
      active: "bg-bullish text-bg-base border-bullish",
      inactive: "bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2",
    },
    B: {
      active: "bg-warning text-bg-base border-warning",
      inactive: "bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2",
    },
    C: {
      active: "bg-text-faint text-bg-base border-text-faint",
      inactive: "bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2",
    },
  };

  // How many filters are active right now (grade/types only count in the live
  // feed — the not-routed view ignores them). Drives the Filters badge + chips.
  const activeFilterCount =
    (assetFilter !== "all" ? 1 : 0) +
    (gradeFilter !== "all" ? 1 : 0) +
    (hiddenTypes.size > 0 ? 1 : 0);
  function clearAllFilters() {
    onAssetFilterChange?.("all");
    changeGradeFilter("all");
    clearHiddenTypes();
    setSearch("");
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Row 1 — Signals / Not-routed segmented control + Sort */}
      <div className="px-3 pt-2 pb-1.5 shrink-0 flex items-center gap-2">
        <div className="flex items-center rounded-md border border-border-subtle overflow-hidden text-[10px] font-semibold">
          {([["premarket", "Premarket"], ["day", "Day"], ["swing", "Swing"]] as const).map(([id, label], i) => (
            <button
              key={id}
              onClick={() => setView(id)}
              title={id === "premarket"
                ? "Premarket signals — an isolated channel (Focus names at a key level before the open). Separate from your RTH alerts."
                : id === "day"
                ? "Day trades — you must SELL the same day at some point (out by the close). Intraday reclaims, ORB, PDL held, gap-and-go."
                : "Swing trades — HOLD multiple days as long as the thesis holds. 5/20 cross, RSI-30 buy, 200-EMA hold, weekly/monthly levels, base setups."}
              className={`px-2.5 py-1 transition-colors ${i > 0 ? "border-l border-border-subtle" : ""} ${view === id ? "bg-accent text-bg-base" : "bg-surface-1 text-text-muted hover:bg-surface-2"}`}
            >
              {label} <span className="opacity-70 font-normal">{id === "premarket" ? pmSignals.length : id === "day" ? dayAlerts.length : swingAlerts.length}</span>
            </button>
          ))}
        </div>
        <div className="ml-auto relative">
          <button
            onClick={() => setSortOpen((v) => !v)}
            className="text-[10px] px-2 py-1 rounded border bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2 flex items-center gap-1"
            title="Sort signals"
          >
            <span className="text-text-faint">Sort</span>
            <span className="text-text-secondary font-medium">{SORT_LABELS[sortBy]}</span>
            <ChevronDown className="h-3 w-3" />
          </button>
          {sortOpen && (
            <>
              <button className="fixed inset-0 z-30 cursor-default" onClick={() => setSortOpen(false)} aria-label="Close sort menu" />
              <div className="absolute right-0 top-full mt-1 z-40 bg-surface-1 border border-border-subtle rounded-md shadow-lg overflow-hidden min-w-[140px]">
                {(["time", "grade", "vol", "slope", "symbol", "rr"] as const).map((opt) => (
                  <button
                    key={opt}
                    onClick={() => changeSort(opt)}
                    className={`w-full text-left px-3 py-1.5 text-[11px] transition-colors ${sortBy === opt ? "bg-accent/15 text-accent" : "text-text-secondary hover:bg-surface-2"}`}
                  >
                    {SORT_LABELS[opt]}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Subtle meaning of the selected book — what "day" vs "swing" actually asks of you. */}
      {view !== "premarket" && (
        <div className="px-3 pb-1 -mt-0.5 text-[10px] text-text-faint shrink-0">
          {view === "day"
            ? "Day trade — sell it the same session at some point (out by the close)."
            : "Swing — hold multiple days, as long as the thesis stays good."}
        </div>
      )}

      {/* Row 2 — Search (primary) + one Filters popover (asset · grade · types) */}
      <div className="px-3 pb-1.5 shrink-0 flex items-center gap-1.5 relative">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-text-faint pointer-events-none" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search symbol or pattern…"
            className="w-full bg-surface-1 border border-border-subtle rounded pl-7 pr-6 py-1 text-[11px] text-text-secondary placeholder:text-text-faint focus:outline-none focus:border-accent/40"
          />
          {search && (
            <button onClick={() => setSearch("")} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-text-faint hover:text-text-secondary" aria-label="Clear search">
              <X className="h-3 w-3" />
            </button>
          )}
        </div>
        <button
          onClick={() => setFiltersOpen((v) => !v)}
          className={`shrink-0 text-[10px] px-2 py-1 rounded border flex items-center gap-1 transition-colors ${
            activeFilterCount > 0
              ? "bg-accent/10 text-accent border-accent/40 hover:bg-accent/15"
              : "bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2"
          }`}
          title="Filter by asset, grade, and alert type"
        >
          <SlidersHorizontal className="h-3 w-3" />
          <span>Filters</span>
          {activeFilterCount > 0 && (
            <span className="ml-0.5 min-w-[14px] text-center text-[9px] font-bold rounded-full bg-accent text-bg-base px-1">{activeFilterCount}</span>
          )}
        </button>
        {collapsedCount > 0 && (
          <button
            onClick={toggleShowCollapsed}
            title={showCollapsed
              ? "Hide NOT SENT / deduped — show delivered only"
              : `Review ${collapsedCount} recorded-but-not-sent alerts (NOT SENT + deduped)`}
            className={`shrink-0 text-[10px] px-2 py-1 rounded border flex items-center gap-0.5 transition-colors ${
              showCollapsed
                ? "bg-accent/10 text-accent border-accent/40 hover:bg-accent/15"
                : "bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2"
            }`}
          >
            <span>⋯</span><span className="font-bold">{collapsedCount}</span>
          </button>
        )}
        {filtersOpen && (
          <>
            <button className="fixed inset-0 z-30 cursor-default" onClick={() => setFiltersOpen(false)} aria-label="Close filters" />
            <div className="absolute right-3 top-full mt-1 z-40 bg-surface-1 border border-border-subtle rounded-md shadow-lg overflow-hidden w-[260px] max-h-[70vh] flex flex-col">
              {/* Asset class */}
              <div className="px-3 py-2 border-b border-border-subtle">
                <div className="text-[9px] uppercase tracking-wide text-text-faint mb-1.5">Asset</div>
                <div className="flex items-center gap-1">
                  {(["all", "stocks", "crypto"] as const).map((k) => (
                    <button
                      key={k}
                      onClick={() => onAssetFilterChange?.(k)}
                      className={`flex-1 text-[10px] px-2 py-1 rounded border transition-colors ${assetFilter === k ? "bg-accent/15 text-accent border-accent/40" : "bg-surface-2 text-text-muted border-border-subtle hover:bg-surface-3"}`}
                    >
                      {k === "all" ? "All" : k === "stocks" ? "Stocks" : "Crypto"}
                    </button>
                  ))}
                </div>
              </div>
              {/* Grade — live feed only */}
              {(
                <div className="px-3 py-2 border-b border-border-subtle">
                  <div className="text-[9px] uppercase tracking-wide text-text-faint mb-1.5">Grade</div>
                  <div className="flex items-center gap-1">
                    {(["all", "A", "B", "C"] as const).map((g) => {
                      const count = g === "all" ? feedAlerts.length : gradeCounts[g];
                      return (
                        <button
                          key={g}
                          onClick={() => changeGradeFilter(g)}
                          className={`flex-1 text-[10px] px-1.5 py-1 rounded border transition-colors ${gradeFilter === g ? CHIP_STYLES[g].active : CHIP_STYLES[g].inactive}`}
                          title={g === "all" ? "All grades" : `Grade ${g}`}
                        >
                          {g === "all" ? "All" : g} <span className="opacity-70 font-normal">{count}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
              {/* Types — live feed only */}
              {(
                <>
                  <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-subtle bg-surface-2/40">
                    <span className="text-[9px] uppercase tracking-wide text-text-faint">Alert types</span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => hideAllTypes(typeOptions.map(([t]) => t))}
                        className="text-[10px] text-text-secondary hover:text-text-primary disabled:opacity-30 disabled:cursor-default"
                        disabled={typeOptions.length === 0 || hiddenTypes.size === typeOptions.length}
                      >
                        Hide all
                      </button>
                      <span className="text-text-faint">·</span>
                      <button
                        onClick={clearHiddenTypes}
                        className="text-[10px] text-accent hover:text-accent-hover disabled:opacity-30 disabled:cursor-default"
                        disabled={hiddenTypes.size === 0}
                      >
                        Show all
                      </button>
                    </div>
                  </div>
                  <div className="overflow-y-auto">
                    {typeOptions.length === 0 ? (
                      <p className="px-3 py-3 text-[11px] text-text-faint">No alerts in feed</p>
                    ) : typeOptions.map(([t, n]) => {
                      const hidden = hiddenTypes.has(t);
                      return (
                        <label key={t} className="flex items-center gap-2 px-3 py-1.5 text-[11px] cursor-pointer hover:bg-surface-2 transition-colors">
                          <input type="checkbox" checked={!hidden} onChange={() => toggleHiddenType(t)} className="h-3 w-3 accent-accent" />
                          <span className={`flex-1 truncate ${hidden ? "text-text-faint line-through" : "text-text-secondary"}`}>{formatSetup(t)}</span>
                          <span className="text-text-faint">{n}</span>
                        </label>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </div>

      {/* Row 3 — active filter chips (only shown when something is filtering) */}
      {activeFilterCount > 0 && (
        <div className="px-3 pb-1.5 shrink-0 flex flex-wrap items-center gap-1">
          {assetFilter !== "all" && (
            <button onClick={() => onAssetFilterChange?.("all")} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/30 hover:bg-accent/15">
              {assetFilter === "crypto" ? "Crypto" : "Stocks"} <X className="h-2.5 w-2.5" />
            </button>
          )}
          {gradeFilter !== "all" && (
            <button onClick={() => changeGradeFilter("all")} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/30 hover:bg-accent/15">
              Grade {gradeFilter} <X className="h-2.5 w-2.5" />
            </button>
          )}
          {hiddenTypes.size > 0 && (
            <button onClick={clearHiddenTypes} className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full bg-accent/10 text-accent border border-accent/30 hover:bg-accent/15">
              {hiddenTypes.size} type{hiddenTypes.size > 1 ? "s" : ""} off <X className="h-2.5 w-2.5" />
            </button>
          )}
          <button onClick={clearAllFilters} className="text-[10px] text-text-faint hover:text-text-secondary px-1">Clear all</button>
        </div>
      )}

      {view === "premarket" ? (
        <PremarketPanel signals={pmSignals} onSelectSymbol={onSelectSymbol} />
      ) : alerts === undefined ? (
        // Still loading the initial fetch — show skeleton cards rather than
        // an empty "No signals" message that flashes for 200-500ms.
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2" aria-busy="true">
          <SkeletonRow count={6} h={88} gap={8} />
        </div>
      ) : listAlerts.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-text-faint">
            {q
              ? `No ${q} alerts`
              : `No alerts this session`}
          </p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
          {listAlerts.map((a) => {
        const time = new Date(a.created_at).toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "America/Chicago",
        });
        const isAIScan = a.alert_type?.startsWith("ai_");
        const dirText = a.direction === "BUY" ? "LONG"
          : a.direction === "SHORT" ? "SHORT"
          : a.direction === "NOTICE" ? "NOTICE" : (a.direction || "—");
        const dirCls = a.direction === "BUY"
          ? "bg-bullish/10 text-bullish-text border-bullish/20"
          : a.direction === "SHORT"
            ? "bg-orange-500/10 text-orange-400 border-orange-500/20"
            : "bg-warning/10 text-warning-text border-warning/20";
        // Collapsed (deduped/merged) — only visible when "Show collapsed" is on.
        // Badge it distinctly + dim hard so it reads as "dropped, for audit".
        const colLabel = collapsedLabel(a.suppressed_reason);
        // Fired but not routed to Telegram (e.g. SPY < PDL) — show greyed +
        // badged so it's reviewable without reading as a live, delivered call.
        const nrLabel = colLabel ? null : notRoutedLabel(a.suppressed_reason);
        const rr = a.entry != null && a.target_1 != null && a.stop != null && a.entry !== a.stop
          ? Math.abs((a.target_1 - a.entry) / (a.entry - a.stop))
          : null;

        return (
          <div
            key={a.id}
            className={`bg-surface-2/40 border border-border-subtle/60 rounded-lg p-3 hover:border-accent/40 transition-colors cursor-pointer${colLabel ? " opacity-40" : nrLabel ? " opacity-55" : ""}`}
            onClick={() => onSelectSymbol(a.symbol)}
          >
            {/* row 1 — symbol · direction · (AI · NOT SENT) ··· R:R · time */}
            <div className="flex items-center gap-2">
              <span className="font-mono text-[15px] font-bold text-text-primary">{a.symbol}</span>
              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${dirCls}`}>{dirText}</span>
              {isAIScan && (
                <span className="text-[8px] font-semibold px-1 py-0.5 rounded bg-accent/15 text-accent">AI</span>
              )}
              {colLabel && (
                <span
                  title={`Collapsed by dedup — ${a.suppressed_reason}. Recorded, not delivered (one alert per price level).`}
                  className="text-[8px] font-bold px-1 py-0.5 rounded bg-surface-4 text-text-muted border border-border-subtle cursor-help"
                >
                  ⋯ {colLabel}
                </span>
              )}
              {nrLabel && (
                <span
                  title={`Not sent to Telegram — ${a.suppressed_reason}. Recorded for review.`}
                  className="text-[8px] font-bold px-1 py-0.5 rounded bg-bearish/15 text-bearish-text border border-bearish/30 cursor-help"
                >
                  NOT SENT
                </span>
              )}
              <div className="ml-auto flex items-center gap-2 shrink-0">
                {rr != null && (
                  <span
                    className={`font-mono text-[15px] font-bold ${rr >= 2 ? "text-bullish-text" : "text-text-muted"}`}
                    title={rr >= 2 ? "Reward ≥ 2× the risk" : "Reward-to-risk"}
                  >
                    {rr.toFixed(1)}R
                  </span>
                )}
                <span className="font-mono text-[10px] text-text-faint">{time}</span>
              </div>
            </div>

            {/* row 2 — setup name · grade */}
            <div className="mt-1.5 flex items-center gap-2">
              <span
                className="text-[13px] font-semibold text-text-primary truncate cursor-help"
                title={a.description || formatSetup(a.alert_type)}
              >
                {formatSetup(a.alert_type)}
              </span>
              {a.grade && (() => {
                const g = a.grade;
                const gCls = g === "A" ? "bg-bullish text-white border-bullish"
                  : g === "B" ? "bg-warning/80 text-white border-warning"
                  : "bg-surface-4 text-text-faint border-border-subtle";
                const slope = a.vwap_slope_pct != null ? ` · slope ${a.vwap_slope_pct > 0 ? "+" : ""}${a.vwap_slope_pct.toFixed(2)}%` : "";
                const vol = a.volume_ratio != null ? ` · vol ${a.volume_ratio.toFixed(2)}×` : "";
                const gTitle = (g === "A" ? "Grade A — high conviction (vol ≥ 2× AND slope ≥ +0.05%)"
                  : g === "B" ? "Grade B — partial gate (one of vol/slope passes)"
                  : "Grade C — no quality gate passed") + vol + slope;
                return (
                  <span title={gTitle} className={`ml-auto shrink-0 text-[10px] font-bold px-1.5 py-0.5 rounded border cursor-help ${gCls}`}>{g}</span>
                );
              })()}
            </div>

            {/* plain-English meaning — what the setup IS, so jargon ("Rc 4h Hrec") isn't the only
                label. Uses the curated per-type blurb; a.message is an unreliable "[TV] type (tf)"
                fallback for NOT_SENT alerts, so it is NOT preferred here. */}
            {setupBlurb(a.alert_type) && (
              <p className="mt-1 text-[11px] leading-snug text-text-muted line-clamp-2">
                {setupBlurb(a.alert_type)}
              </p>
            )}

            {/* the plan — entry / target / stop as a clean 3-col grid (mono numbers) */}
            {a.entry != null ? (
              <div className="mt-2 grid grid-cols-3 gap-px rounded-md overflow-hidden bg-surface-3">
                <div className="bg-surface-1 px-2 py-1.5">
                  <div className="font-mono text-[8px] uppercase tracking-wide text-text-faint">Entry</div>
                  <div className="font-mono text-[12px] font-bold text-accent">{fmtPrice(a.entry)}</div>
                </div>
                <div className="bg-surface-1 px-2 py-1.5">
                  <div className="font-mono text-[8px] uppercase tracking-wide text-text-faint">Target</div>
                  <div className="font-mono text-[12px] font-bold text-bullish-text">{fmtPrice(a.target_1)}</div>
                </div>
                <div className="bg-surface-1 px-2 py-1.5">
                  <div className="font-mono text-[8px] uppercase tracking-wide text-text-faint">Stop</div>
                  <div className="font-mono text-[12px] font-bold text-bearish-text">{fmtPrice(a.stop)}</div>
                </div>
              </div>
            ) : (
              a.message && (
                <p className="mt-2 text-[11px] text-text-muted leading-relaxed line-clamp-2">{a.message}</p>
              )
            )}
          </div>
        );
      })}
          <DisclaimerFooter />
        </div>
      )}
    </div>
  );
}

/* ── Main TradingPage V2 ─────────────────────────────────────────── */

export default function TradingPageV2() {
  /* ── Data hooks ── */
  const { data: signals, isLoading, refetch, isFetching, error: scanError } = useScanner();
  const { data: todayAlerts, error: alertsError } = useAlertsToday();
  const { data: livePriceData } = useLivePrices();
  const livePrices = livePriceData?.prices ?? {};
  const queryClient = useQueryClient();

  /* ── Selection state ── */
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(() => {
    return localStorage.getItem("chart_selected_symbol") || null;
  });
  const selectSymbol = useCallback((sym: string) => {
    setSelectedSymbol(sym);
    localStorage.setItem("chart_selected_symbol", sym);
    setMobileWatchlistOpen(false);   // close watchlist drawer when symbol picked on mobile
    // Picking a symbol = "show me the chart" → collapse the mobile signals panel so
    // the chart goes full-height (it was compressed behind the open 17rem panel).
    // Transient (no localStorage write) — the user's explicit chevron toggle still
    // persists. Setter is stable, so it needs no dep. No-op on desktop (panel is lg:hidden).
    setMobileSignalsCollapsed(true);
  }, []);

  /* ── Deep-link routing ──
     /trading?symbol=<SYM>  → opens the chart on that symbol (focus list, dashboard, etc.)
     /trading?alert=<id>    → push-notification tap; resolve alert → symbol
     Clear the query param after handling so refresh doesn't re-trigger. */
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    const symParam = searchParams.get("symbol");
    if (symParam) {
      selectSymbol(symParam.toUpperCase());
      searchParams.delete("symbol");
      setSearchParams(searchParams, { replace: true });
      return;
    }
    const alertId = searchParams.get("alert");
    if (!alertId || !todayAlerts) return;
    const target = todayAlerts.find((a) => String(a.id) === alertId);
    if (target) {
      selectSymbol(target.symbol);
    }
    searchParams.delete("alert");
    setSearchParams(searchParams, { replace: true });
  }, [searchParams, todayAlerts, selectSymbol, setSearchParams]);

  /* ── Timeframe ── */
  const [tfIdx, setTfIdx] = useState(() => {
    const saved = localStorage.getItem("chart_timeframe");
    return saved ? Number(saved) : DEFAULT_TF;
  });

  /* ── Indicators ── */
  const [activeIndicators, setActiveIndicators] = useState<Set<string>>(() => {
    return loadSavedIndicators() ?? DEFAULT_INDICATORS;
  });
  const [showLevels, setShowLevels] = useState(
    () => localStorage.getItem("chart_levels") !== "false"
  );
  const [hideWicks, setHideWicks] = useState(
    () => localStorage.getItem("chart_wicks") === "true"
  );
  const [showVolume, setShowVolume] = useState(
    () => localStorage.getItem("chart_volume") !== "false"
  );
  function toggleVolume() {
    setShowVolume((v) => { localStorage.setItem("chart_volume", String(!v)); return !v; });
  }
  const [maOff, setMaOff] = useState(() => localStorage.getItem("chart_ma_off") === "true");
  function toggleMaOff() {
    setMaOff((v) => { localStorage.setItem("chart_ma_off", String(!v)); return !v; });
  }
  const [showIndicatorPanel, setShowIndicatorPanel] = useState(false);
  const indicatorPanelRef = useRef<HTMLDivElement>(null);

  /* ── Draw S/R levels (persisted per symbol via /charts/levels) ── */
  const [drawMode, setDrawMode] = useState(false);
  const [showLevelsPanel, setShowLevelsPanel] = useState(false);
  const [newLineType, setNewLineType] = useState<LineType>(
    () => (localStorage.getItem("chart_line_type") as LineType) || "line"
  );
  const levelsPanelRef = useRef<HTMLDivElement>(null);
  const lastAddRef = useRef<{ key: string; t: number }>({ key: "", t: 0 });
  function pickLineType(t: LineType) {
    setNewLineType(t);
    try { localStorage.setItem("chart_line_type", t); } catch { /* ignore */ }
  }

  /* ── Panel state ── */
  // Chart-hero default: watchlist starts as a slim rail so the chart leads; the user's
  // expand/collapse choice persists (#64-E de-densify).
  const [watchlistCollapsed, setWatchlistCollapsed] = useState(() => {
    if (typeof window === "undefined") return true;
    return localStorage.getItem("watchlist_collapsed") !== "0";
  });
  useEffect(() => {
    try { localStorage.setItem("watchlist_collapsed", watchlistCollapsed ? "1" : "0"); } catch { /* ignore */ }
  }, [watchlistCollapsed]);
  const [watchSort, setWatchSort] = useState<"symbol" | "change_desc" | "change_asc" | "price_desc">(
    () => (localStorage.getItem("watchlist_sort") as any) || "symbol"
  );
  function cycleWatchSort() {
    const order = ["symbol", "change_desc", "change_asc", "price_desc"] as const;
    const next = order[(order.indexOf(watchSort) + 1) % order.length];
    setWatchSort(next);
    try { localStorage.setItem("watchlist_sort", next); } catch { /* ignore */ }
  }
  // Mobile drawer — slides watchlist in from left on small screens
  const [mobileWatchlistOpen, setMobileWatchlistOpen] = useState(false);
  const [mobileSignalsCollapsed, setMobileSignalsCollapsed] = useState<boolean>(() => {
    return localStorage.getItem("mobile_signals_collapsed") === "1";
  });
  const toggleMobileSignals = useCallback(() => {
    setMobileSignalsCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("mobile_signals_collapsed", next ? "1" : "0");
      return next;
    });
  }, []);

  // Chart only listens to window resize; tell it the available space changed
  // so it re-fits when the signals panel collapses/expands on mobile.
  useEffect(() => {
    const t = setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
    return () => clearTimeout(t);
  }, [mobileSignalsCollapsed]);
  // Chart-hero default: signals panel open on wide screens, on-demand below 1280px so the
  // chart isn't crammed; the user's choice persists. New fires still surface via the pop-up
  // over the chart when the panel is closed (#64-E de-densify).
  // Right sidebar tab — Signals feed · per-symbol Level Map · Alert Log tape.
  const [rightTab, setRightTab] = useState<"signals" | "levels" | "log">("signals");
  const [showRightPanel, setShowRightPanel] = useState(() => {
    if (typeof window === "undefined") return true;
    const saved = localStorage.getItem("trading_right_panel");
    if (saved != null) return saved === "1";
    return window.innerWidth >= 1280;
  });
  useEffect(() => {
    try { localStorage.setItem("trading_right_panel", showRightPanel ? "1" : "0"); } catch { /* ignore */ }
  }, [showRightPanel]);

  // ── New-signal pop-up ──
  // Surface a freshly-fired A/B signal as a tappable card over the chart so the
  // user doesn't miss it while the Signals panel is collapsed. Diff today's
  // alerts against a seen-id set (mirrors useSignalNotifications). Auto-dismiss
  // after ~8s; tap → jump chart to that symbol + expand the panel.
  const seenAlertIds = useRef<Set<number> | null>(null);
  const [newSignal, setNewSignal] = useState<Alert | null>(null);
  useEffect(() => {
    if (!todayAlerts) return;
    if (seenAlertIds.current === null) {
      seenAlertIds.current = new Set(todayAlerts.map((a) => a.id));
      return;
    }
    const seen = seenAlertIds.current;
    let latest: Alert | null = null;
    for (const a of todayAlerts) {
      if (seen.has(a.id)) continue;
      seen.add(a.id);
      const g = (a.grade || "").toUpperCase();
      // Only truly-routed A/B alerts pop a toast — a not-routed alert (any
      // suppressed_reason, e.g. SPY < PDL) is review-only, never a live ping.
      if ((g === "A" || g === "B") && isFeedSignal(a.alert_type) && !a.suppressed_reason) {
        latest = a; // show the most recent qualifying one if several arrive together
      }
    }
    if (latest) setNewSignal(latest);
  }, [todayAlerts]);
  useEffect(() => {
    if (!newSignal) return;
    const t = setTimeout(() => setNewSignal(null), 8000);
    return () => clearTimeout(t);
  }, [newSignal]);
  const handleNewSignalTap = useCallback((a: Alert) => {
    selectSymbol(a.symbol);
    setMobileSignalsCollapsed(false);
    try { localStorage.setItem("mobile_signals_collapsed", "0"); } catch { /* ignore */ }
    setNewSignal(null);
  }, [selectSymbol]);

  // Signals feed — which session to view ("" = today/latest)
  const [signalDate, setSignalDate] = useState<string>("");
  const { data: sessionDates } = useAlertSessionDates();
  const { data: pastAlerts, error: pastAlertsError } = useAlertsForDate(signalDate);

  // Asset class filter for AI Signals + AI Updates tabs (persists in localStorage)
  type AssetFilter = "all" | "stocks" | "crypto";
  const [assetFilter, setAssetFilter] = useState<AssetFilter>(
    () => (typeof window !== "undefined"
      ? (localStorage.getItem("trading_asset_filter") as AssetFilter) || "all"
      : "all")
  );
  function changeAssetFilter(next: AssetFilter) {
    setAssetFilter(next);
    try { localStorage.setItem("trading_asset_filter", next); } catch {}
  }
  function filterAlertsByAsset<T extends { symbol?: string }>(alerts: T[] | undefined): T[] {
    if (!alerts) return [];
    if (assetFilter === "all") return alerts;
    return alerts.filter((a) => {
      const isCrypto = a.symbol?.toUpperCase().endsWith("-USD");
      return assetFilter === "crypto" ? !!isCrypto : !isCrypto;
    });
  }

  /* ── Watchlist ── */
  const { data: watchlistItems } = useWatchlist();
  const addSymbol = useAddSymbol();
  const _removeSymbol = useRemoveSymbol(); void _removeSymbol;
  const toggleFocusMut = useToggleWatchlistFocus();
  const clearFocusMut = useClearWatchlistFocus();
  const watchlistSymbols = new Set(watchlistItems?.map((w) => w.symbol) ?? []);
  const focusSymbols = new Set(
    (watchlistItems ?? []).filter((w) => w.focus).map((w) => w.symbol),
  );
  const { data: rankItems } = useWatchlistRank();
  const rankMap = new Map<string, WatchlistRankItem>();
  rankItems?.forEach((r) => rankMap.set(r.symbol, r));

  // Watchlist panel redesign — amber "fired today" dot + row sparklines.
  const { data: sigTodayData } = useWatchlistSignalsToday();
  const signalTodaySet = new Set((sigTodayData?.symbols ?? []).map((s) => s.toUpperCase()));
  const { data: wlGroups } = useWatchlistGroups();
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  // Focus filter — visual-only toggle for the sidebar. Persists in localStorage.
  // Default OFF so the full list shows; user explicitly opts in to focus view.
  const [focusOnly, setFocusOnly] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem("watchlist_focus_only") === "1";
  });
  const [masterView, setMasterView] = useState(false);  // admin: show the master watchlist as the list
  function toggleFocusOnly() {
    setMasterView(false);
    setFocusOnly((v) => {
      try { localStorage.setItem("watchlist_focus_only", v ? "0" : "1"); } catch {}
      return !v;
    });
  }

  /* ── Editor's Picks (admin's public watchlist) ── */
  const { data: sectorsItems } = useSectorsWatchlist();
  const { data: me } = useMe();
  const isAdmin = !!me?.is_admin;
  const { data: masterData } = useMasterWatchlistView(isAdmin && masterView);
  const copySectors = useCopySectorsWatchlist();
  // Default-expanded — only collapsed if the user has explicitly collapsed
  // it before (key set to "0"). New users see the picks immediately.
  const [sectorsExpanded, setSectorsExpanded] = useState<boolean>(() => {
    if (typeof window === "undefined") return true;
    return localStorage.getItem("sectors_expanded") !== "0";
  });
  function toggleSectors() {
    setSectorsExpanded((v) => {
      try { localStorage.setItem("sectors_expanded", v ? "0" : "1"); } catch {}
      return !v;
    });
  }
  const missingSectorSymbols = (sectorsItems ?? [])
    .map((s) => s.symbol)
    .filter((s) => !watchlistSymbols.has(s));
  function copyAllSectors() {
    if (missingSectorSymbols.length === 0) return;
    copySectors.mutate(undefined, {
      onSuccess: () => {
        toast.success(`Synced ${missingSectorSymbols.length} symbols + sector groups`);
      },
    });
  }
  const userWatchlistEmpty = (watchlistItems?.length ?? 0) === 0;

  const [searchFilter, setSearchFilter] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);
  const searchUpper = searchFilter.trim().toUpperCase();
  const isValidTicker = /^[A-Z]{1,5}(-[A-Z]{3,4})?$/.test(searchUpper);
  const canAdd = isValidTicker && searchUpper.length >= 1 && !watchlistSymbols.has(searchUpper);

  function handleAddFromSearch() {
    if (!canAdd) return;
    addSymbol.mutate(searchUpper, {
      onSuccess: () => setSearchFilter(""),
    });
  }

  /* ── Indicator toggles ── */
  function toggleIndicator(key: string) {
    setActiveIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      localStorage.setItem("chart_indicators_v2", JSON.stringify([...next]));
      return next;
    });
  }
  function toggleLevels() {
    setShowLevels((v) => {
      localStorage.setItem("chart_levels", String(!v));
      return !v;
    });
  }
  function toggleWicks() {
    setHideWicks((v) => {
      localStorage.setItem("chart_wicks", String(!v));
      return !v;
    });
  }

  // `maOff` hides ALL MAs/EMAs/VWAP at once without losing the user's selection,
  // so they can flip back to the same set. Persists across reloads.
  const chartIndicators = maOff
    ? []
    : ALL_INDICATORS.filter((ind) => activeIndicators.has(ind.key)).map(({ key, color }) => ({ key, color }));

  /* ── Auto-select first symbol ── */
  if (!selectedSymbol && signals && signals.length > 0) {
    const entry = signals.find((s) => s.action_label === "Potential Entry");
    selectSymbol(entry?.symbol ?? signals[0].symbol);
  }

  /* ── Prefetch chart data ── */
  useEffect(() => {
    if (!signals) return;
    const tf = TIMEFRAMES[DEFAULT_TF];
    // Warm more of the visible list so a click loads from cache (was 5). De-duped by
    // symbol so we don't prefetch the same name twice.
    const seen = new Set<string>();
    signals.slice(0, 20).forEach((s) => {
      if (seen.has(s.symbol)) return;
      seen.add(s.symbol);
      queryClient.prefetchQuery({
        queryKey: ["ohlcv", s.symbol, tf.period, tf.interval],
        queryFn: () =>
          api.get(`/charts/ohlcv/${s.symbol}?period=${tf.period}&interval=${tf.interval}`),
        staleTime: 15 * 60_000,
      });
    });
  }, [signals, queryClient]);

  /* ── Close indicator panel on outside click ── */
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        indicatorPanelRef.current &&
        !indicatorPanelRef.current.contains(e.target as Node)
      ) {
        setShowIndicatorPanel(false);
      }
    }
    if (showIndicatorPanel) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showIndicatorPanel]);

  /* ── Trigger chart resize when panels toggle ── */
  const triggerResize = useCallback(() => {
    setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
  }, []);

  /* ── Derived state ── */
  const watchlistSignal = signals?.find((s) => s.symbol === selectedSymbol) ?? null;
  // Ad-hoc fallback: screener / non-watchlist symbols still chart (no scanner levels).
  // chartLevels and all `selected.X` reads are null-safe, so empty levels are fine.
  const selected =
    watchlistSignal ??
    (selectedSymbol
      ? ({
          symbol: selectedSymbol, close: 0, last_close: 0,
          entry: null, stop: null, target_1: null, target_2: null,
          direction: "LONG", score: 0, score_label: "",
          support_label: "", support_status: "", nearest_support: null,
          ref_day_high: null, ref_day_low: null, ma20: null, ma50: null,
        } as unknown as SignalResult)
      : null);
  const tf = TIMEFRAMES[tfIdx];
  const { data: ohlcv } = useOHLCV(selectedSymbol ?? "", tf.period, tf.interval);

  /* ── User S/R levels ── */
  const { data: userLevels } = useChartLevels(selectedSymbol ?? "");
  const addLevel = useAddChartLevel();
  const updateLevel = useUpdateChartLevel();
  const delLevel = useDeleteChartLevel();
  const handleAddLevel = useCallback((price: number) => {
    if (!selectedSymbol || !price) return;
    const snapped = snapPrice(price);
    // Guard against rapid duplicate fires before the levels list refetches.
    const key = `${selectedSymbol}:${snapped}`;
    if (lastAddRef.current.key === key && Date.now() - lastAddRef.current.t < 1500) return;
    // Dedup: don't stack a new line on top of one already at (≈) this price.
    const dup = (userLevels ?? []).some((l) => Math.abs(l.price - snapped) / snapped < 0.0015);
    if (dup) { toast.info("A line is already at that level"); return; }
    lastAddRef.current = { key, t: Date.now() };
    const t = LINE_TYPES[newLineType];
    addLevel.mutate({ symbol: selectedSymbol, price: snapped, label: t.label, color: t.color });
  }, [selectedSymbol, newLineType, addLevel, userLevels]);

  const chartLevels = (() => {
    if (!selected) return [];
    // Only the levels traders actually mark: prior-day + prior-week high/low.
    const kl = keyLevels(ohlcv);
    const sym = selected.symbol;
    const lvls: Array<{ id: number; symbol: string; price: number; label: string; color: string }> = [];
    if (kl.pdh != null) lvls.push({ id: -1, symbol: sym, price: kl.pdh, label: "PDH", color: "#22c55e" });
    if (kl.pdl != null) lvls.push({ id: -2, symbol: sym, price: kl.pdl, label: "PDL", color: "#ef4444" });
    if (kl.pwh != null) lvls.push({ id: -3, symbol: sym, price: kl.pwh, label: "PWH", color: "#14b8a6" });
    if (kl.pwl != null) lvls.push({ id: -4, symbol: sym, price: kl.pwl, label: "PWL", color: "#f97316" });
    return lvls;
  })();

  /* ── Filtered signals ── */
  const filteredSignals = signals
    ?.filter(
      (s) => !searchFilter || s.symbol.toLowerCase().includes(searchFilter.toLowerCase())
    )
    ?.filter((s) => !focusOnly || focusSymbols.has(s.symbol))
    ?.filter((s) => s.source === "watchlist")   // watchlist only — scanner "ideas" live on the Trade Ideas tab
    // User-chosen sort (persisted). %change/price pull from live prices.
    ?.slice()
    .sort((a, b) => {
      const ca = livePrices[a.symbol]?.change_pct ?? 0;
      const cb = livePrices[b.symbol]?.change_pct ?? 0;
      const pa = livePrices[a.symbol]?.price ?? 0;
      const pb = livePrices[b.symbol]?.price ?? 0;
      switch (watchSort) {
        case "change_desc": return cb - ca;
        case "change_asc": return ca - cb;
        case "price_desc": return pb - pa;
        default: return a.symbol.localeCompare(b.symbol);
      }
    });

  // The signals shown in the right panel — today/latest, or a chosen past session.
  const activeAlerts = signalDate ? (pastAlerts ?? []) : todayAlerts;
  // Alert markers for the charted symbol (memoized so the chart doesn't redraw every render).
  const symbolAlertMarkers = useMemo(
    () => (activeAlerts ?? [])
      .filter((a) => a.symbol === selectedSymbol && ["BUY", "SHORT", "SELL"].includes((a.direction || "").toUpperCase()))
      .map((a) => ({ created_at: a.created_at, direction: a.direction, grade: a.grade })),
    [activeAlerts, selectedSymbol],
  );
  const activeAlertsError = signalDate ? pastAlertsError : alertsError;
  const feedCount = (activeAlerts ?? []).filter(
    (a) => isFeedSignal(a.alert_type) && a.suppressed_reason !== "type_not_enabled",
  ).length;

  const watchlistWidth = watchlistCollapsed ? 48 : 232;
  // The desktop sidebar can be collapsed (icon-rail) but the mobile drawer must
  // always render the full layout — prices, the focus/favorite star, and the
  // remove control. Without this, opening the drawer while the desktop sidebar
  // is collapsed showed centered symbol-only rows with no way to favorite.
  const watchlistExpanded = !watchlistCollapsed || mobileWatchlistOpen;

  // Sector groups — map each row to its watchlist group (sector), ordered by the
  // user's sort_order; ungrouped / folded-in ideas fall into General Market / Ideas.
  const groupedSignals = useMemo(() => {
    const nameById = new Map<number, string>();
    (wlGroups ?? []).forEach((g) => nameById.set(g.id, g.name));
    const orderByName = new Map<string, number>();
    [...(wlGroups ?? [])].sort((a, b) => a.sort_order - b.sort_order).forEach((g, i) => orderByName.set(g.name, i));
    const symToGroup = new Map<string, string>();
    (watchlistItems ?? []).forEach((it) => {
      symToGroup.set(it.symbol.toUpperCase(), (it.group_id != null ? nameById.get(it.group_id) : null) ?? "General Market");
    });
    const groups = new Map<string, SignalResult[]>();
    (filteredSignals ?? []).forEach((s) => {
      const g = symToGroup.get(s.symbol.toUpperCase()) ?? (s.source === "watchlist" ? "General Market" : "Ideas");
      let arr = groups.get(g);
      if (!arr) { arr = []; groups.set(g, arr); }
      arr.push(s);
    });
    return [...groups.entries()].sort((a, b) => (orderByName.get(a[0]) ?? 98) - (orderByName.get(b[0]) ?? 98));
  }, [filteredSignals, watchlistItems, wlGroups]);

  // Admin master-watchlist list — the curated universe grouped by sector, searchable/
  // collapsible, click a symbol to chart it. Separate from the personal-watchlist machinery.
  const renderMasterList = () => {
    const q = searchFilter.toLowerCase();
    return (masterData?.groups ?? []).map((g) => {
      const syms = q ? g.symbols.filter((sy) => sy.toLowerCase().includes(q)) : g.symbols;
      if (syms.length === 0) return null;
      const key = "M:" + g.name;
      const isCollapsed = collapsedGroups.has(key);
      return (
        <div key={key}>
          <button
            onClick={() => setCollapsedGroups((prev) => { const nx = new Set(prev); if (nx.has(key)) nx.delete(key); else nx.add(key); return nx; })}
            className="flex w-full items-center gap-1 px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider text-amber-400/80 hover:text-amber-400 transition-colors"
          >
            <ChevronRight className={`h-2.5 w-2.5 transition-transform ${isCollapsed ? "" : "rotate-90"}`} />
            {g.name}
            <span className="ml-auto font-normal text-text-faint">{syms.length}</span>
          </button>
          {!isCollapsed && syms.map((sy) => {
            const lp = livePrices[sy];
            const chg = lp?.change_pct ?? null;
            return (
              <button
                key={sy}
                onClick={() => selectSymbol(sy)}
                className={`flex w-full items-center gap-2 px-2.5 py-1 text-left transition-colors ${selectedSymbol === sy ? "bg-accent/15" : "hover:bg-surface-2"}`}
              >
                <span className="font-mono text-[11px] font-semibold text-text-primary">{sy}</span>
                {chg != null && (
                  <span className={`ml-auto font-mono text-[10px] ${chg >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                    {chg >= 0 ? "+" : ""}{chg.toFixed(2)}%
                  </span>
                )}
              </button>
            );
          })}
        </div>
      );
    });
  };

  const renderWlRow = (s: SignalResult) => (
    <CompactWatchlistRow
      key={s.symbol}
      signal={s}
      selected={selectedSymbol === s.symbol}
      onClick={() => selectSymbol(s.symbol)}
      onRemove={() => _removeSymbol.mutate(s.symbol)}
      onToggleFocus={() => toggleFocusMut.mutate(s.symbol)}
      focused={focusSymbols.has(s.symbol)}
      livePrice={livePrices[s.symbol]}
      rankItem={rankMap.get(s.symbol)}
      collapsed={!watchlistExpanded}
      hasSignal={signalTodaySet.has(s.symbol.toUpperCase())}
    />
  );

  /* ────────────────────────────────────────────────────────────────── */

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Top strip — regime pills (poll 60s) on the left, theme toggle pinned
            right. The toggle keeps the strip present even when regime data is
            unavailable, so dark/light is always one click away. ── */}
      <div className="shrink-0 px-2 py-1 flex items-center gap-3 flex-wrap">
        <MarketClock />
        <SpyRegimeStrip />
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
      {/* ── Mobile backdrop when drawer open ── */}
      {mobileWatchlistOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 md:hidden"
          onClick={() => setMobileWatchlistOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* ── LEFT: Compact Watchlist ── */}
      <aside
        className={`flex flex-col bg-surface-1 border-r border-border-subtle shrink-0 transition-all duration-200 fixed inset-y-0 left-0 z-40 md:static md:translate-x-0 ${
          mobileWatchlistOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
        style={{ width: typeof window !== "undefined" && window.innerWidth < 768 ? 280 : watchlistWidth }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-2 py-2 border-b border-border-subtle shrink-0 h-10">
          {watchlistExpanded && (
            <span className="text-[11px] font-semibold text-text-secondary tracking-wide">
              Watchlist
            </span>
          )}
          <div className="flex items-center gap-0.5">
            {watchlistExpanded && (
              <button
                onClick={cycleWatchSort}
                className="flex items-center gap-1 rounded border border-border-subtle px-1.5 py-0.5 text-[10px] font-semibold font-mono text-text-muted hover:border-accent/40 hover:text-text-secondary hover:bg-surface-2/60 transition-colors"
                title="Sort watchlist — click to cycle A–Z · %↓ · %↑ · $↓ (persists)"
              >
                <span className="text-text-faint">⇅</span>
                {watchSort === "change_desc" ? "%↓" : watchSort === "change_asc" ? "%↑" : watchSort === "price_desc" ? "$↓" : "A–Z"}
              </button>
            )}
            {/* Mobile: close the drawer. Desktop: collapse to the icon rail. */}
            <button
              onClick={() => setMobileWatchlistOpen(false)}
              className="md:hidden p-1 rounded text-text-faint hover:text-text-secondary hover:bg-surface-2/60 transition-colors"
              aria-label="Close watchlist"
            >
              <X className="h-4 w-4" />
            </button>
            <button
              onClick={() => {
                setWatchlistCollapsed((v) => !v);
                triggerResize();
              }}
              className="hidden md:block p-1 rounded text-text-faint hover:text-text-secondary hover:bg-surface-2/60 transition-colors"
              title={watchlistCollapsed ? "Expand watchlist" : "Collapse watchlist"}
            >
              {watchlistCollapsed ? (
                <ChevronRight className="h-3.5 w-3.5" />
              ) : (
                <ChevronLeft className="h-3.5 w-3.5" />
              )}
            </button>
          </div>
        </div>

        {/* Focus filter chip — visual-only filter for today's focus list.
            On the mobile drawer (mobileWatchlistOpen) ALWAYS show the chips, even when the
            desktop sidebar is collapsed — otherwise mobile gets a long list with no filters. */}
        {watchlistExpanded && (
          <div className="px-2 py-1.5 border-b border-border-subtle shrink-0 flex items-center gap-1 flex-wrap">
            <button
              onClick={toggleFocusOnly}
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-colors ${
                !focusOnly
                  ? "bg-accent/15 text-accent border-accent/40"
                  : "bg-surface-2 text-text-muted border-border-subtle hover:bg-surface-3"
              }`}
              title="Show every watchlist symbol"
            >
              All <span className="opacity-70 font-normal">{watchlistItems?.length ?? 0}</span>
            </button>
            <button
              onClick={toggleFocusOnly}
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-colors flex items-center gap-1 ${
                focusOnly
                  ? "bg-amber-400/15 text-amber-400 border-amber-400/40"
                  : "bg-surface-2 text-text-muted border-border-subtle hover:bg-surface-3"
              }`}
              title="Show today's focus only (visual filter — alerts still fire on every symbol)"
            >
              <svg className="h-2.5 w-2.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.196-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.783-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z" />
              </svg>
              Focus <span className="opacity-70 font-normal">{focusSymbols.size}</span>
            </button>
            {isAdmin && (
              <button
                onClick={() => { setMasterView((v) => !v); setFocusOnly(false); }}
                className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-colors flex items-center gap-1 ${
                  masterView
                    ? "bg-accent/15 text-accent border-accent/40"
                    : "bg-surface-2 text-text-muted border-border-subtle hover:bg-surface-3"
                }`}
                title="Master watchlist — the curated platform universe (admin-only)"
              >
                Master <span className="opacity-70 font-normal">{masterData?.count ?? sectorsItems?.length ?? 0}</span>
              </button>
            )}
            {focusSymbols.size > 0 && (
              <button
                onClick={() => clearFocusMut.mutate()}
                disabled={clearFocusMut.isPending}
                className="ml-auto text-[9px] text-text-faint hover:text-text-secondary disabled:opacity-30"
                title="Clear all focus stars"
              >
                Reset
              </button>
            )}
          </div>
        )}

        {/* Search (when expanded, or always on the mobile drawer) */}
        {watchlistExpanded && (
          <div className="px-2 py-1.5 border-b border-border-subtle shrink-0">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-text-faint" />
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                onFocus={() => setSearchFocused(true)}
                onBlur={() => setTimeout(() => setSearchFocused(false), 150)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && canAdd) handleAddFromSearch();
                }}
                placeholder={`Search ${watchlistItems?.length ? watchlistItems.length + " " : ""}symbols…`}
                className="w-full bg-surface-2/50 border border-border-subtle rounded py-2 md:py-1 pl-7 pr-6 text-[13px] md:text-[11px] text-text-primary placeholder:text-text-faint focus:outline-none focus:border-accent/50 transition-colors"
              />
              {searchFilter && (
                <button
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => setSearchFilter("")}
                  className="absolute right-1.5 top-1/2 -translate-y-1/2 text-text-faint hover:text-text-muted"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>
            {/* Add symbol */}
            {searchFilter && canAdd && searchFocused && (
              <button
                onMouseDown={(e) => e.preventDefault()}
                onClick={handleAddFromSearch}
                disabled={addSymbol.isPending}
                className="mt-1 w-full flex items-center gap-1.5 px-2 py-1 rounded bg-accent/10 border border-accent/20 text-[10px] text-accent hover:bg-accent/20 transition-colors disabled:opacity-50"
              >
                {addSymbol.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Plus className="h-3 w-3" />
                )}
                Add <span className="font-bold">{searchUpper}</span>
              </button>
            )}
          </div>
        )}

        {/* Symbol list */}
        <div className="flex-1 overflow-y-auto no-scrollbar">
          {isLoading && (
            <div className="p-3 text-center">
              <Loader2 className="h-3 w-3 animate-spin text-text-faint mx-auto" />
            </div>
          )}
          {scanError && !isLoading && (
            <div className="p-2 text-center">
              <p className="text-[10px] text-bearish-text mb-1">Scan failed</p>
              <button onClick={() => refetch()} className="text-[10px] text-accent">
                Retry
              </button>
            </div>
          )}
          {/* Collapsed icon-rail → flat rows. Expanded → grouped by sector with
              collapsible headers (the mock's "groups mirror your watchlist sectors"). */}
          {masterView
            ? renderMasterList()
            : !watchlistExpanded
            ? filteredSignals?.map(renderWlRow)
            : groupedSignals.map(([groupName, rows]) => {
                const isCollapsed = collapsedGroups.has(groupName);
                return (
                  <div key={groupName}>
                    <button
                      onClick={() =>
                        setCollapsedGroups((prev) => {
                          const n = new Set(prev);
                          if (n.has(groupName)) n.delete(groupName); else n.add(groupName);
                          return n;
                        })
                      }
                      className="flex w-full items-center gap-1 px-2.5 py-1 text-[9px] font-bold uppercase tracking-wider text-amber-400/80 hover:text-amber-400 transition-colors"
                    >
                      <ChevronRight className={`h-2.5 w-2.5 transition-transform ${isCollapsed ? "" : "rotate-90"}`} />
                      {groupName}
                      <span className="ml-auto font-normal text-text-faint">{rows.length}</span>
                    </button>
                    {!isCollapsed && rows.map(renderWlRow)}
                  </div>
                );
              })}
        </div>

        {/* Editor's Picks — admin's curated watchlist. Collapsible; auto-
            expanded by default. Hero CTA at top when the user's personal
            watchlist is empty (new accounts). "Copy all" bulk-adds every
            missing symbol with one click. */}
        {watchlistExpanded && sectorsItems && sectorsItems.length > 0 && (
          <div className="border-t border-border-subtle shrink-0 max-h-[55%] overflow-hidden flex flex-col bg-surface-1">
            {/* Empty-state hero — only shown when user has zero personal symbols */}
            {userWatchlistEmpty && missingSectorSymbols.length > 0 && (
              <div className="mx-2 mt-2 mb-1 p-2.5 rounded-md bg-accent/10 border border-accent/30">
                <div className="flex items-start gap-2">
                  <Sparkles className="h-3.5 w-3.5 text-accent shrink-0 mt-0.5" />
                  <div className="flex-1 min-w-0">
                    <p className="text-[10.5px] font-semibold text-text-primary leading-tight mb-0.5">
                      Start with the editor's {missingSectorSymbols.length} picks
                    </p>
                    <p className="text-[9.5px] text-text-muted leading-snug mb-1.5">
                      Curated by admin. You'll still get alerts on every symbol — this just adds them to your watchlist for quick charting.
                    </p>
                    <button
                      onClick={copyAllSectors}
                      disabled={copySectors.isPending}
                      className="w-full flex items-center justify-center gap-1 px-2 py-1 rounded bg-accent text-bg-base text-[10px] font-semibold hover:bg-accent-hover disabled:opacity-50 transition-colors"
                    >
                      {copySectors.isPending ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Plus className="h-3 w-3" />
                      )}
                      Copy all to my watchlist
                    </button>
                  </div>
                </div>
              </div>
            )}

            <div className="flex items-center justify-between px-2 py-1.5 gap-1">
              <button
                onClick={toggleSectors}
                className="flex-1 flex items-center gap-1 hover:opacity-80 transition-opacity text-left"
                title="Editor's curated picks — admin updates appear here automatically"
              >
                <Sparkles className="h-3 w-3 text-accent" />
                <span className="text-[10px] uppercase tracking-wide font-semibold text-text-secondary">
                  Editor's Picks <span className="text-text-faint normal-case">{sectorsItems.length}</span>
                </span>
                <ChevronDown
                  className={`h-3 w-3 text-text-faint transition-transform ${sectorsExpanded ? "" : "-rotate-90"}`}
                />
              </button>
              {!userWatchlistEmpty && missingSectorSymbols.length > 0 && (
                <button
                  onClick={copyAllSectors}
                  disabled={copySectors.isPending}
                  className="text-[9px] px-1.5 py-0.5 rounded bg-accent/15 text-accent hover:bg-accent/25 disabled:opacity-50 transition-colors font-semibold flex items-center gap-0.5"
                  title={`Add ${missingSectorSymbols.length} missing symbols to my watchlist`}
                >
                  {copySectors.isPending ? (
                    <Loader2 className="h-2.5 w-2.5 animate-spin" />
                  ) : (
                    <Plus className="h-2.5 w-2.5" />
                  )}
                  Copy all
                </button>
              )}
            </div>
            {sectorsExpanded && (
              <div className="flex-1 overflow-y-auto no-scrollbar pb-1">
                {sectorsItems.map((s) => {
                  const owned = watchlistSymbols.has(s.symbol);
                  return (
                    <div
                      key={s.id}
                      className="flex items-center justify-between px-2 py-1 hover:bg-surface-2/40 transition-colors"
                    >
                      <button
                        onClick={() => selectSymbol(s.symbol)}
                        className="text-[11px] font-medium text-text-secondary hover:text-text-primary truncate"
                      >
                        {s.symbol}
                      </button>
                      {owned ? (
                        <span className="text-[9px] text-text-faint">added</span>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            addSymbol.mutate(s.symbol);
                          }}
                          disabled={addSymbol.isPending}
                          className="p-0.5 rounded text-accent hover:bg-accent/10 disabled:opacity-50"
                          title={`Add ${s.symbol} to my watchlist`}
                        >
                          <Plus className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        {watchlistExpanded && (
          <div className="px-2 py-1.5 border-t border-border-subtle shrink-0 flex items-center justify-between">
            <span className="text-[9px] text-text-faint">
              {watchlistItems?.length ?? 0} symbols
            </span>
            {isFetching && <Loader2 className="h-2.5 w-2.5 animate-spin text-text-faint" />}
          </div>
        )}
      </aside>

      {/* ── CENTER: Chart + Top Bar + Bottom Strip ──
         Inline padding-bottom (instead of arbitrary Tailwind class) so the
         reservation always applies — JIT can miss arbitrary values inside
         template literals. lg breakpoint = 1024px (Tailwind default). */}
      <section
        className="flex-1 flex flex-col min-w-0 min-h-0 bg-surface-0 overflow-hidden"
        style={{
          // Reserve space for the signals panel (which sits above the bottom
          // nav). Includes safe-area-inset-bottom so the chart doesn't extend
          // into the home-indicator zone on notched iPhones.
          paddingBottom:
            typeof window !== "undefined" && window.innerWidth >= 1024
              ? 0
              : mobileSignalsCollapsed
              ? "calc(2.5rem + env(safe-area-inset-bottom))"
              : "calc(14rem + env(safe-area-inset-bottom))",
        }}
      >
        {/* Top bar */}
        <header className="h-11 border-b border-border-subtle px-3 flex items-center justify-between shrink-0 bg-surface-0">
          {/* Left: Mobile menu + Symbol + Price + Change */}
          <div className="flex items-center gap-2.5 min-w-0">
            <button
              onClick={() => setMobileWatchlistOpen(true)}
              className="md:hidden p-1.5 -ml-1.5 rounded text-text-secondary hover:text-text-primary hover:bg-surface-2/60 transition-colors"
              aria-label="Open watchlist"
            >
              <Menu className="h-5 w-5" />
            </button>
            {selected ? (
              <>
                <span className="text-lg font-bold tracking-tight text-text-primary font-display">
                  {selected.symbol}
                </span>
                <span
                  className={`text-lg font-mono tabular-nums ${
                    (livePrices[selected.symbol]?.change_pct ?? 0) >= 0
                      ? "text-bullish-text"
                      : "text-bearish-text"
                  }`}
                >
                  ${fmt(livePrices[selected.symbol]?.price ?? selected.close)}
                </span>
                {livePrices[selected.symbol] && (
                  <span
                    className={`text-[11px] font-mono tabular-nums px-1.5 py-0.5 rounded ${
                      livePrices[selected.symbol].change_pct >= 0
                        ? "text-bullish-text bg-bullish/10"
                        : "text-bearish-text bg-bearish/10"
                    }`}
                  >
                    {livePrices[selected.symbol].change_pct >= 0 ? "+" : ""}
                    {livePrices[selected.symbol].change_pct.toFixed(2)}%
                  </span>
                )}
              </>
            ) : (
              <span className="text-sm text-text-faint">Select a symbol</span>
            )}
          </div>

          {/* Center: Timeframe pills */}
          <div className="hidden sm:flex items-center bg-surface-2/50 p-0.5 rounded-lg border border-border-subtle">
            {TIMEFRAMES.map((t, i) => (
              <span key={t.label} className="flex items-center">
                {i === 6 && (
                  <span className="w-px h-3.5 bg-border-default mx-0.5 shrink-0" />
                )}
                <button
                  onClick={() => {
                    setTfIdx(i);
                    localStorage.setItem("chart_timeframe", String(i));
                  }}
                  className={`px-2 py-0.5 text-[10px] font-medium rounded transition-colors ${
                    i === tfIdx
                      ? "bg-accent text-white shadow-sm"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {t.label}
                </button>
              </span>
            ))}
          </div>

          {/* Right: Indicators + Panel toggle. shrink-0 so the icon buttons
              keep their size; the left symbol/price block truncates to yield
              space on narrow phones (can't use overflow scroll here — it would
              clip the indicator/saved-lines popovers). */}
          <div className="flex items-center gap-1 sm:gap-1.5 shrink-0">
            {/* Indicators popover */}
            <div className="relative" ref={indicatorPanelRef}>
              <button
                onClick={() => setShowIndicatorPanel((v) => !v)}
                className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors border ${
                  showIndicatorPanel
                    ? "bg-accent/15 text-accent border-accent/30"
                    : "bg-surface-2/50 text-text-muted border-border-subtle hover:text-text-secondary"
                }`}
              >
                <SlidersHorizontal className="h-3 w-3" />
                <span className="hidden lg:inline">Indicators</span>
              </button>

              {/* Popover */}
              {showIndicatorPanel && (
                <div className="absolute top-full right-0 mt-1 w-[240px] bg-surface-2 border border-border-default rounded-lg shadow-elevated z-30 p-2.5 space-y-2.5">
                  {(["ema", "sma", "other"] as const).map((group) => (
                    <div key={group}>
                      <p className="text-[9px] font-semibold uppercase tracking-wider text-text-faint mb-1">
                        {group === "other" ? "Other" : group.toUpperCase() + "s"}
                      </p>
                      <div className="space-y-0.5">
                        {ALL_INDICATORS.filter((ind) => ind.group === group).map(
                          (ind) => (
                            <label
                              key={ind.key}
                              className="flex items-center gap-2 cursor-pointer px-1.5 py-0.5 rounded hover:bg-surface-3/50 transition-colors"
                            >
                              <input
                                type="checkbox"
                                checked={activeIndicators.has(ind.key)}
                                onChange={() => toggleIndicator(ind.key)}
                                className="sr-only"
                              />
                              <span
                                className={`w-3 h-3 rounded border-2 flex items-center justify-center transition-colors ${
                                  activeIndicators.has(ind.key)
                                    ? "border-transparent"
                                    : "border-border-default"
                                }`}
                                style={{
                                  backgroundColor: activeIndicators.has(ind.key)
                                    ? ind.color
                                    : "transparent",
                                }}
                              >
                                {activeIndicators.has(ind.key) && (
                                  <svg
                                    className="w-2 h-2 text-white"
                                    viewBox="0 0 12 12"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="2"
                                  >
                                    <path d="M2 6l3 3 5-5" />
                                  </svg>
                                )}
                              </span>
                              <span
                                className="w-2 h-0.5 rounded-full"
                                style={{ backgroundColor: ind.color }}
                              />
                              <span className="text-[11px] text-text-secondary">
                                {ind.label}
                              </span>
                            </label>
                          )
                        )}
                      </div>
                    </div>
                  ))}
                  {/* Levels + Wicks */}
                  <div className="border-t border-border-subtle pt-2 space-y-0.5">
                    <label className="flex items-center gap-2 cursor-pointer px-1.5 py-0.5 rounded hover:bg-surface-3/50 transition-colors">
                      <input
                        type="checkbox"
                        checked={showLevels}
                        onChange={toggleLevels}
                        className="sr-only"
                      />
                      <span
                        className={`w-3 h-3 rounded border-2 flex items-center justify-center transition-colors ${showLevels ? "bg-accent border-transparent" : "border-border-default"}`}
                      >
                        {showLevels && (
                          <svg className="w-2 h-2 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M2 6l3 3 5-5" />
                          </svg>
                        )}
                      </span>
                      <span className="text-[11px] text-text-secondary">Levels</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer px-1.5 py-0.5 rounded hover:bg-surface-3/50 transition-colors">
                      <input
                        type="checkbox"
                        checked={!hideWicks}
                        onChange={toggleWicks}
                        className="sr-only"
                      />
                      <span
                        className={`w-3 h-3 rounded border-2 flex items-center justify-center transition-colors ${!hideWicks ? "bg-accent border-transparent" : "border-border-default"}`}
                      >
                        {!hideWicks && (
                          <svg className="w-2 h-2 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M2 6l3 3 5-5" />
                          </svg>
                        )}
                      </span>
                      <span className="text-[11px] text-text-secondary">Wicks</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer px-1.5 py-0.5 rounded hover:bg-surface-3/50 transition-colors">
                      <input type="checkbox" checked={showVolume} onChange={toggleVolume} className="sr-only" />
                      <span className={`w-3 h-3 rounded border-2 flex items-center justify-center transition-colors ${showVolume ? "bg-accent border-transparent" : "border-border-default"}`}>
                        {showVolume && (
                          <svg className="w-2 h-2 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M2 6l3 3 5-5" />
                          </svg>
                        )}
                      </span>
                      <span className="text-[11px] text-text-secondary">Volume</span>
                    </label>
                  </div>
                </div>
              )}
            </div>

            <span className="w-px h-4 bg-border-subtle/70 mx-0.5 shrink-0" />

            {/* MAs toggle — hide/show ALL EMAs/SMAs/VWAP at once (keeps your
                selection so you can flip back to the same set). */}
            <button
              onClick={toggleMaOff}
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors border ${
                !maOff
                  ? "bg-accent/15 text-accent border-accent/30"
                  : "bg-surface-2/50 text-text-muted border-border-subtle hover:text-text-secondary"
              }`}
              title={maOff ? "Show moving averages" : "Hide all moving averages"}
            >
              {!maOff ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
              <span className="hidden lg:inline">MAs</span>
            </button>

            {/* Levels toggle — hide/show the auto lines (entry/stop/target + PDH/PDL/
                S/R) for a clean chart. Your own drawn lines stay either way. */}
            <button
              onClick={toggleLevels}
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors border ${
                showLevels
                  ? "bg-accent/15 text-accent border-accent/30"
                  : "bg-surface-2/50 text-text-muted border-border-subtle hover:text-text-secondary"
              }`}
              title={showLevels ? "Hide auto levels (entry/stop/target, PDH/PDL, S/R)" : "Show auto levels"}
            >
              {showLevels ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
              <span className="hidden lg:inline">Levels</span>
            </button>

            <span className="w-px h-4 bg-border-subtle/70 mx-0.5 shrink-0" />

            {/* Levels — one popover: draw + line-type + saved S/R manager (#64-E de-densify) */}
            <div className="relative" ref={levelsPanelRef}>
              <button
                onClick={() => setShowLevelsPanel((v) => !v)}
                disabled={!selectedSymbol}
                className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors border disabled:opacity-40 ${
                  drawMode
                    ? "bg-accent text-white border-accent"
                    : showLevelsPanel
                    ? "bg-accent/15 text-accent border-accent/30"
                    : "bg-surface-2/50 text-text-muted border-border-subtle hover:text-text-secondary"
                }`}
                title="Draw & manage your S/R lines for this symbol"
              >
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: drawMode ? "#ffffff" : LINE_TYPES[newLineType].color }} />
                <span className="hidden lg:inline">{drawMode ? "Drawing…" : "Levels"}</span>
                {(userLevels?.length ?? 0) > 0 && (
                  <span className="font-mono text-[9px] bg-surface-4/60 px-1 rounded">{userLevels!.length}</span>
                )}
              </button>
              {showLevelsPanel && (
                <div className="absolute top-full right-0 mt-1 w-[230px] bg-surface-2 border border-border-default rounded-lg shadow-elevated z-30 p-2 space-y-0.5">
                  <div className="flex items-center justify-between px-1 pb-1">
                    <span className="text-[9px] font-semibold uppercase tracking-wider text-text-faint">
                      S/R lines · {selectedSymbol ?? "—"}
                    </span>
                    {(userLevels ?? []).length > 0 && (
                      <button
                        onClick={() => {
                          if (!selectedSymbol) return;
                          (userLevels ?? []).forEach((l) => delLevel.mutate({ id: l.id, symbol: selectedSymbol }));
                        }}
                        className="text-[9px] text-text-faint hover:text-bearish-text"
                        title="Remove all lines for this symbol"
                      >
                        Clear all
                      </button>
                    )}
                  </div>
                  {/* Pick a type, then Draw — arms + closes so you can click the chart */}
                  <div className="flex items-center gap-1 px-1 pb-1.5 mb-1 border-b border-border-subtle">
                    {(["support", "resistance", "line"] as LineType[]).map((t) => (
                      <button
                        key={t}
                        onClick={() => pickLineType(t)}
                        className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border transition-colors ${
                          newLineType === t ? "border-accent/40 text-text-primary" : "border-transparent text-text-muted hover:bg-surface-3/50"
                        }`}
                        style={newLineType === t ? { backgroundColor: LINE_TYPES[t].color + "22" } : undefined}
                      >
                        <span className="w-2 h-0.5 rounded-full" style={{ backgroundColor: LINE_TYPES[t].color }} />
                        {t === "line" ? "Line" : LINE_TYPES[t].label}
                      </button>
                    ))}
                    <button
                      onClick={() => { setDrawMode(true); setShowLevelsPanel(false); }}
                      className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold bg-accent text-white hover:bg-accent-hover"
                      title="Arm draw, then click the chart at a level"
                    >
                      + Draw
                    </button>
                  </div>
                  {(userLevels ?? []).length === 0 ? (
                    <p className="text-[11px] text-text-faint px-1 py-2 leading-relaxed">
                      Pick a type, tap <span className="text-accent font-medium">+ Draw</span>, then click the chart at a level.
                    </p>
                  ) : (
                    [...(userLevels ?? [])].sort((a, b) => b.price - a.price).map((lvl) => (
                      <div
                        key={lvl.id}
                        className="flex items-center justify-between px-1.5 py-1 rounded hover:bg-surface-3/50 group"
                      >
                        <span className="flex items-center gap-1.5">
                          {/* dot — click cycles Support → Resistance → Line */}
                          <button
                            onClick={() => {
                              if (!selectedSymbol) return;
                              const cur = typeOfLevel(lvl.color);
                              const next: LineType = cur === "support" ? "resistance" : cur === "resistance" ? "line" : "support";
                              updateLevel.mutate({ id: lvl.id, symbol: selectedSymbol, color: LINE_TYPES[next].color, label: LINE_TYPES[next].label });
                            }}
                            className="w-2.5 h-2.5 rounded-full shrink-0 hover:ring-2 hover:ring-white/20"
                            style={{ backgroundColor: lvl.color || "#94a3b8" }}
                            title="Click to change type (Support / Resistance / Line)"
                          />
                          {/* editable price — Enter or blur to reprice */}
                          <span className="text-[11px] text-text-faint">$</span>
                          <input
                            key={lvl.price}
                            defaultValue={lvl.price.toFixed(2)}
                            inputMode="decimal"
                            onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                            onBlur={(e) => {
                              const v = parseFloat(e.target.value);
                              if (selectedSymbol && !isNaN(v) && v > 0 && v !== lvl.price) {
                                updateLevel.mutate({ id: lvl.id, symbol: selectedSymbol, price: v });
                              }
                            }}
                            className="w-14 bg-transparent font-mono text-[11px] text-text-secondary rounded px-0.5 focus:bg-surface-1 focus:text-text-primary focus:outline-none focus:ring-1 focus:ring-accent/40"
                          />
                        </span>
                        <button
                          onClick={() => selectedSymbol && delLevel.mutate({ id: lvl.id, symbol: selectedSymbol })}
                          className="text-text-faint hover:text-bearish-text opacity-0 group-hover:opacity-100 transition-opacity"
                          title="Remove line"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            <span className="w-px h-4 bg-border-subtle/70 mx-0.5 shrink-0" />

            {/* Right panel toggle (desktop) */}
            <button
              onClick={() => {
                setShowRightPanel((v) => !v);
                triggerResize();
              }}
              className={`hidden lg:flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors border ${
                showRightPanel
                  ? "bg-accent/10 text-accent border-accent/20"
                  : "bg-surface-2/50 text-text-muted border-border-subtle"
              }`}
              title={showRightPanel ? "Hide panel" : "Show panel"}
            >
              <Brain className="h-3 w-3" />
            </button>
          </div>
        </header>

        {/* Mobile: timeframe pills (above symbol strip — desktop has them in header) */}
        <div className="flex gap-1 overflow-x-auto px-3 py-1.5 md:hidden shrink-0 no-scrollbar border-b border-border-subtle bg-surface-1/40">
          {TIMEFRAMES.map((t, i) => (
            <button
              key={t.label}
              onClick={() => {
                setTfIdx(i);
                localStorage.setItem("chart_timeframe", String(i));
              }}
              className={`shrink-0 rounded px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                i === tfIdx
                  ? "bg-accent text-white"
                  : "bg-surface-3 text-text-secondary"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Mobile: horizontal symbol pills — badge conviction / long-term ideas
            the scanner folded in, so they're distinguishable here too (the
            watchlist drawer with full controls is off-canvas on mobile). */}
        <div className="flex gap-1.5 overflow-x-auto px-3 py-1.5 md:hidden shrink-0 no-scrollbar">
          {signals?.map((s) => (
            <button
              key={s.symbol}
              onClick={() => selectSymbol(s.symbol)}
              className={`shrink-0 inline-flex items-center gap-1 rounded-md px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
                selectedSymbol === s.symbol
                  ? "bg-accent text-white"
                  : "bg-surface-3 text-text-muted"
              }`}
            >
              {s.symbol}
              {selectedSymbol !== s.symbol && (
                <IdeaBadge source={s.source} actionLabel={s.action_label} />
              )}
            </button>
          ))}
        </div>

        {/* Chart area — flex-1 to fill remaining space */}
        <div className="flex-1 min-h-0 relative">
          {newSignal && (
            <NewSignalToast
              alert={newSignal}
              onTap={() => handleNewSignalTap(newSignal)}
              onDismiss={() => setNewSignal(null)}
            />
          )}
          {selected && ohlcv && ohlcv.length > 0 ? (
            <CandlestickChart
              data={(() => {
                // Patch last bar with live price so chart matches watchlist
                const lp = livePrices[selected.symbol]?.price;
                if (!lp || ohlcv.length === 0) return ohlcv;
                const bars = [...ohlcv];
                const last = { ...bars[bars.length - 1] };
                last.close = lp;
                if (lp > last.high) last.high = lp;
                if (lp < last.low) last.low = lp;
                bars[bars.length - 1] = last;
                return bars;
              })()}
              showTradePanel={false}
              levels={showLevels ? chartLevels : []}
              userLevels={userLevels ?? []}
              drawMode={drawMode}
              onAddLevel={handleAddLevel}
              indicators={chartIndicators}
              hideWicks={hideWicks}
              showVolume={showVolume}
              alertMarkers={symbolAlertMarkers}
              height={0}
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              {selected ? (
                <div className="w-full h-full flex flex-col items-center justify-center gap-3 px-8">
                  <div className="flex items-end gap-1 h-32 w-full max-w-md">
                    {Array.from({ length: 30 }).map((_, i) => (
                      <div
                        key={i}
                        className="flex-1 bg-surface-3 rounded-sm animate-pulse"
                        style={{
                          height: `${20 + Math.sin(i * 0.5) * 40 + Math.random() * 30}%`,
                          animationDelay: `${i * 30}ms`,
                        }}
                      />
                    ))}
                  </div>
                  <span className="text-xs text-text-faint">Loading chart...</span>
                </div>
              ) : (
                <div className="text-center">
                  <p className="text-sm text-text-muted">Select a symbol to view analysis</p>
                  <p className="text-xs text-text-faint mt-1">
                    Click any symbol in the watchlist
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

      </section>

      {/* ── RIGHT: Signals feed (desktop) ── */}
      {showRightPanel && (
        <aside className="hidden lg:flex flex-col w-[320px] bg-surface-0 border-l border-border-subtle shrink-0">
          {/* Header — Signals | Levels tabs + (session picker on the Signals tab) */}
          <div className="flex items-center gap-2 border-b border-border-subtle shrink-0 h-14 px-3">
            <Zap className="h-4 w-4 text-accent shrink-0" />
            <div className="flex items-center rounded-md border border-border-subtle overflow-hidden text-[11px] font-semibold">
              <button
                onClick={() => setRightTab("signals")}
                className={`px-2.5 py-1 transition-colors ${rightTab === "signals" ? "bg-accent text-bg-base" : "bg-surface-1 text-text-muted hover:bg-surface-2"}`}
              >
                Signals{" "}
                {feedCount > 0 && <span className="opacity-70 font-normal">{feedCount}</span>}
              </button>
              <button
                onClick={() => setRightTab("levels")}
                title="Key-level ladder for the selected chart symbol"
                className={`px-2.5 py-1 border-l border-border-subtle transition-colors ${rightTab === "levels" ? "bg-accent text-bg-base" : "bg-surface-1 text-text-muted hover:bg-surface-2"}`}
              >
                Levels
              </button>
              <button
                onClick={() => setRightTab("log")}
                title="Running tape of every alert that fired this session"
                className={`px-2.5 py-1 border-l border-border-subtle transition-colors ${rightTab === "log" ? "bg-accent text-bg-base" : "bg-surface-1 text-text-muted hover:bg-surface-2"}`}
              >
                Log
              </button>
            </div>
            {rightTab !== "levels" && (
              <select
                value={signalDate}
                onChange={(e) => setSignalDate(e.target.value)}
                title="Review a past session"
                className="ml-auto bg-surface-1 border border-border-subtle rounded px-2 py-1 text-[11px] text-text-secondary"
              >
                <option value="">Today</option>
                {(sessionDates ?? []).slice(1).map((d) => (
                  <option key={d} value={d}>{formatSessionDate(d)}</option>
                ))}
              </select>
            )}
          </div>

          {rightTab === "levels" ? (
            /* Per-symbol key-level ladder (the selected chart symbol). */
            <LevelMap symbol={selectedSymbol} />
          ) : rightTab === "log" ? (
            /* Running tape of every alert that fired this session (newest first). */
            <AlertLog alerts={activeAlerts} onSelectSymbol={selectSymbol} />
          ) : (
            /* Signal feed — AI scanner + TradingView signals. Asset filter lives
               inside the Filters popover with grade + types (one less control row). */
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
              <SignalFeedTab
                alerts={filterAlertsByAsset(activeAlerts)}
                alertsError={activeAlertsError}
                onSelectSymbol={selectSymbol}
                signalDate={signalDate}
                assetFilter={assetFilter}
                onAssetFilterChange={changeAssetFilter}
              />
            </div>
          )}
        </aside>
      )}

      {/* ── Mobile signals panel — fixed above bottom nav, collapsible.
         Bottom offset = nav height (3.5rem) + safe-area-inset-bottom so the
         panel sits fully ABOVE the iPhone home-indicator area. With just
         bottom-14, the home-indicator zone covered the panel completely on
         notched iPhones — observed 2026-05-28. */}
      <div
        className="fixed inset-x-0 z-40 lg:hidden bg-surface-1 border-t-2 border-accent/30 shadow-[0_-4px_12px_rgba(0,0,0,0.25)]"
        style={{ bottom: "calc(3.5rem + env(safe-area-inset-bottom))" }}
      >
        {/* header — Signals | Levels | Log tabs (parity with the desktop panel) + collapse */}
        <div className="flex items-center gap-1.5 px-3 py-2 border-b border-border-subtle">
          <Zap className="h-3.5 w-3.5 text-accent shrink-0" />
          <div className="flex items-center rounded-md border border-border-subtle overflow-hidden text-[10px] font-semibold">
            <button
              onClick={() => { setRightTab("signals"); setMobileSignalsCollapsed(false); }}
              className={`px-2 py-0.5 transition-colors ${rightTab === "signals" ? "bg-accent text-bg-base" : "bg-surface-0 text-text-muted"}`}
            >
              Signals{feedCount > 0 && <span className="opacity-70 font-normal"> {feedCount}</span>}
            </button>
            <button
              onClick={() => { setRightTab("levels"); setMobileSignalsCollapsed(false); }}
              className={`px-2 py-0.5 border-l border-border-subtle transition-colors ${rightTab === "levels" ? "bg-accent text-bg-base" : "bg-surface-0 text-text-muted"}`}
            >
              Levels
            </button>
            <button
              onClick={() => { setRightTab("log"); setMobileSignalsCollapsed(false); }}
              className={`px-2 py-0.5 border-l border-border-subtle transition-colors ${rightTab === "log" ? "bg-accent text-bg-base" : "bg-surface-0 text-text-muted"}`}
            >
              Log
            </button>
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            {rightTab !== "levels" && !mobileSignalsCollapsed && (
              <select
                value={signalDate}
                onChange={(e) => setSignalDate(e.target.value)}
                className="bg-surface-0 border border-border-subtle rounded px-2 py-0.5 text-[11px] text-text-secondary"
              >
                <option value="">Today</option>
                {(sessionDates ?? []).slice(1).map((d) => (
                  <option key={d} value={d}>{formatSessionDate(d)}</option>
                ))}
              </select>
            )}
            <button onClick={toggleMobileSignals} aria-label={mobileSignalsCollapsed ? "Expand panel" : "Collapse panel"} className="p-0.5 text-text-muted">
              {mobileSignalsCollapsed ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {!mobileSignalsCollapsed && (
          <div className="flex flex-col h-[240px] overflow-hidden">
            {rightTab === "levels" ? (
              <LevelMap symbol={selectedSymbol} />
            ) : rightTab === "log" ? (
              <AlertLog alerts={activeAlerts} onSelectSymbol={selectSymbol} />
            ) : (
              <SignalFeedTab
                alerts={filterAlertsByAsset(activeAlerts)}
                alertsError={activeAlertsError}
                onSelectSymbol={selectSymbol}
                signalDate={signalDate}
                assetFilter={assetFilter}
                onAssetFilterChange={changeAssetFilter}
              />
            )}
          </div>
        )}
      </div>
      </div>
    </div>
  );
}
