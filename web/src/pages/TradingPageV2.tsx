/** TradingPage V2 — Webull-quality layout with chart dominance.
 *
 *  Layout (desktop):
 *    Left:   180px compact watchlist (collapsible to 48px icon-only)
 *    Center: Chart (65-70% of viewport) + bottom setup strip
 *    Right:  320px tabbed sidebar (AI Coach | Signals | Options Flow)
 *
 *  Mobile: full-width chart + bottom tabs for AI/Signals
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import {
  useScanner,
  useOHLCV,
  useAlertsToday,
  useAlertSessionDates,
  useAlertsForDate,
  useWatchlist,
  useSectorsWatchlist,
  useAddSymbol,
  useCopySectorsWatchlist,
  useRemoveSymbol,
  useLivePrices,
  useWatchlistRank,
  useChartLevels,
  useAddChartLevel,
  useUpdateChartLevel,
  useDeleteChartLevel,
} from "../api/hooks";
import type { WatchlistRankItem } from "../types";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SignalResult, Alert } from "../types";
import { formatSetup, isFeedSignal } from "../lib/alertFormat";
import { toast } from "../components/Toast";
import CandlestickChart from "../components/CandlestickChart";
import SpyRegimeStrip from "../components/SpyRegimeStrip";
import { SkeletonRow } from "../components/ui/Skeleton";
import {
  Search,
  Target,
  ShieldAlert,
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

const TIMEFRAMES = [
  { label: "1m", period: "1d", interval: "1m" },
  { label: "5m", period: "5d", interval: "5m" },
  { label: "15m", period: "5d", interval: "15m" },
  { label: "30m", period: "5d", interval: "30m" },
  { label: "1H", period: "5d", interval: "60m" },
  { label: "4H", period: "1mo", interval: "60m" },
  { label: "D", period: "1y", interval: "1d" },
  { label: "W", period: "1y", interval: "1wk" },
] as const;

const DEFAULT_TF = 6; // Daily

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "\u2014";
  return v.toFixed(decimals);
}

function pctChange(current: number | null | undefined, ref: number | null | undefined): string | null {
  if (current == null || ref == null || ref === 0) return null;
  const pct = ((current - ref) / ref) * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
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

/* ── Compact Watchlist Row ──────────────────────────────────────────── */

function CompactWatchlistRow({
  signal,
  selected,
  onClick,
  onRemove,
  livePrice,
  rankItem,
  collapsed,
}: {
  signal: SignalResult;
  selected: boolean;
  onClick: () => void;
  onRemove?: () => void;
  livePrice?: { price: number; change_pct: number };
  rankItem?: WatchlistRankItem;
  collapsed: boolean;
}) {
  const [hovered, setHovered] = useState(false);
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
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={`group relative flex w-full items-center px-2.5 py-2 text-left transition-all duration-100 ${
        selected
          ? "bg-accent/[0.06] border-l-2 border-accent"
          : "border-l-2 border-transparent hover:bg-surface-2/60"
      }`}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[12px] font-bold text-text-primary leading-tight truncate">
            {signal.symbol}
          </span>
          {/* Score badge on hover */}
          {hovered && (
            <span
              className={`text-[8px] font-bold px-1 py-px rounded border leading-tight ${scoreBadgeClass(score)}`}
            >
              {score}
            </span>
          )}
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
      {hovered && onRemove && (
        <button
          onClick={(e) => { e.stopPropagation(); onRemove(); }}
          className="shrink-0 text-text-faint hover:text-bearish-text transition-colors p-0.5"
          title="Remove from watchlist"
        >
          <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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

function SignalFeedTab({
  alerts,
  alertsError,
  onSelectSymbol,
  signalDate: _signalDate = "",
}: {
  alerts?: Alert[];
  alertsError: unknown;
  onSelectSymbol: (sym: string) => void;
  signalDate?: string;
}) {
  const [search, setSearch] = useState("");
  // Sort options — persisted to localStorage so refresh doesn't reset.
  type FeedSort = "time" | "grade" | "vol" | "slope" | "symbol";
  const SORT_LABELS: Record<FeedSort, string> = {
    time: "Newest", grade: "Grade A→C", vol: "Volume ×",
    slope: "Slope %", symbol: "Symbol",
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
  const [typeFilterOpen, setTypeFilterOpen] = useState(false);
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

  // AI scanner signals + every fired TradingView signal. WAITs and
  // non-routed alerts are excluded — the user filters via Settings
  // (alert types + grade), not in the feed.
  //
  // suppressed_reason filter list:
  //   • type_not_enabled — user toggled the type off; not interesting
  //   • confluence_collapsed:* — same-moment confluence (e.g. gap_up_continuation
  //     and staged_pdh_break fired together; the break already shows). Showing
  //     both makes the feed look like double-fires per stock.
  const feedAlerts = (alerts ?? []).filter((a) => {
    if (!isFeedSignal(a.alert_type)) return false;
    if (a.suppressed_reason === "type_not_enabled") return false;
    if (a.suppressed_reason?.startsWith("confluence_collapsed")) return false;
    return true;
  });
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
    ? feedAlerts.filter((a) => (a.symbol || "").toUpperCase().includes(q))
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
    // default: time desc (newest first)
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

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

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Grade filter chips — view-only, doesn't affect Telegram routing */}
      <div className="px-3 pt-2 pb-1 shrink-0 flex items-center gap-1">
        {(["all", "A", "B", "C"] as const).map((g) => {
          const style = gradeFilter === g ? CHIP_STYLES[g].active : CHIP_STYLES[g].inactive;
          const count = g === "all" ? feedAlerts.length : gradeCounts[g];
          return (
            <button
              key={g}
              onClick={() => changeGradeFilter(g)}
              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-colors ${style}`}
              title={g === "all" ? "Show all grades" : `Show Grade ${g} only`}
            >
              {g === "all" ? "All" : g} <span className="opacity-70 font-normal">{count}</span>
            </button>
          );
        })}
      </div>

      {/* Search + Types + Sort dropdowns — single row */}
      <div className="px-3 pt-1 pb-1.5 shrink-0 flex items-center gap-1.5 relative">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search symbol…"
          className="flex-1 bg-surface-1 border border-border-subtle rounded px-2 py-1 text-[11px] text-text-secondary placeholder:text-text-faint focus:outline-none focus:border-accent/40"
        />
        <button
          onClick={() => setTypeFilterOpen((v) => !v)}
          className={`shrink-0 text-[10px] px-2 py-1 rounded border flex items-center gap-1 transition-colors ${
            hiddenTypes.size > 0
              ? "bg-accent/10 text-accent border-accent/40 hover:bg-accent/15"
              : "bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2"
          }`}
          title={hiddenTypes.size > 0 ? `${hiddenTypes.size} type(s) hidden — click to manage` : "Hide alert types from feed"}
        >
          <span className="text-text-faint">Types</span>
          {hiddenTypes.size > 0 && (
            <span className="text-accent font-semibold">{typeOptions.length - hiddenTypes.size}/{typeOptions.length}</span>
          )}
          <ChevronDown className="h-3 w-3" />
        </button>
        <button
          onClick={() => setSortOpen((v) => !v)}
          className="shrink-0 text-[10px] px-2 py-1 rounded border bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2 flex items-center gap-1"
          title="Sort signals"
        >
          <span className="text-text-faint">Sort:</span>
          <span className="text-text-secondary font-medium">{SORT_LABELS[sortBy]}</span>
          <ChevronDown className="h-3 w-3" />
        </button>
        {sortOpen && (
          <>
            <button
              className="fixed inset-0 z-30 cursor-default"
              onClick={() => setSortOpen(false)}
              aria-label="Close sort menu"
            />
            <div className="absolute right-3 top-full mt-1 z-40 bg-surface-1 border border-border-subtle rounded-md shadow-lg overflow-hidden min-w-[140px]">
              {(["time", "grade", "vol", "slope", "symbol"] as const).map((opt) => (
                <button
                  key={opt}
                  onClick={() => changeSort(opt)}
                  className={`w-full text-left px-3 py-1.5 text-[11px] transition-colors ${
                    sortBy === opt
                      ? "bg-accent/15 text-accent"
                      : "text-text-secondary hover:bg-surface-2"
                  }`}
                >
                  {SORT_LABELS[opt]}
                </button>
              ))}
            </div>
          </>
        )}
        {typeFilterOpen && (
          <>
            <button
              className="fixed inset-0 z-30 cursor-default"
              onClick={() => setTypeFilterOpen(false)}
              aria-label="Close type filter"
            />
            <div className="absolute right-3 top-full mt-1 z-40 bg-surface-1 border border-border-subtle rounded-md shadow-lg overflow-hidden min-w-[260px] max-h-[60vh] flex flex-col">
              <div className="flex items-center justify-between px-3 py-1.5 border-b border-border-subtle bg-surface-2/40">
                <span className="text-[10px] uppercase tracking-wide text-text-faint">Show / hide types</span>
                <button
                  onClick={clearHiddenTypes}
                  className="text-[10px] text-accent hover:text-accent-hover disabled:opacity-30 disabled:cursor-default"
                  disabled={hiddenTypes.size === 0}
                >
                  Show all
                </button>
              </div>
              <div className="overflow-y-auto">
                {typeOptions.length === 0 ? (
                  <p className="px-3 py-3 text-[11px] text-text-faint">No alerts in feed</p>
                ) : typeOptions.map(([t, n]) => {
                  const hidden = hiddenTypes.has(t);
                  return (
                    <label
                      key={t}
                      className="flex items-center gap-2 px-3 py-1.5 text-[11px] cursor-pointer hover:bg-surface-2 transition-colors"
                    >
                      <input
                        type="checkbox"
                        checked={!hidden}
                        onChange={() => toggleHiddenType(t)}
                        className="h-3 w-3 accent-accent"
                      />
                      <span className={`flex-1 truncate ${hidden ? "text-text-faint line-through" : "text-text-secondary"}`}>
                        {formatSetup(t)}
                      </span>
                      <span className="text-text-faint">{n}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          </>
        )}
      </div>

      {alerts === undefined ? (
        // Still loading the initial fetch — show skeleton cards rather than
        // an empty "No signals" message that flashes for 200-500ms.
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2" aria-busy="true">
          <SkeletonRow count={6} h={88} gap={8} />
        </div>
      ) : visible.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-text-faint">
            {q ? `No ${q} signals in this session` : "No signals in this session"}
          </p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
          {visible.map((a) => {
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

        return (
          <div
            key={a.id}
            className="bg-surface-2/40 border border-border-subtle/60 rounded-lg p-2.5 hover:border-accent/30 transition-colors cursor-pointer"
            onClick={() => onSelectSymbol(a.symbol)}
          >
            {/* Header — symbol, direction, grade, (AI badge if AI), time */}
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-bold text-text-primary">{a.symbol}</span>
                <span className={`text-[9px] font-bold px-1 py-0.5 rounded border ${dirCls}`}>
                  {dirText}
                </span>
                {a.grade && (() => {
                  const g = a.grade;
                  const gCls = g === "A" ? "bg-bullish text-white border-bullish"
                    : g === "B" ? "bg-warning/80 text-white border-warning"
                    : "bg-surface-4 text-text-faint border-border-subtle";
                  const gTitle = g === "A" ? "Grade A — high conviction (vol ≥ 2× AND slope ≥ +0.05%)"
                    : g === "B" ? "Grade B — partial gate (one of vol/slope passes)"
                    : "Grade C — no quality gate passed";
                  return (
                    <span
                      title={gTitle}
                      className={`text-[9px] font-bold px-1.5 py-0.5 rounded border cursor-help ${gCls}`}
                    >
                      {g}
                    </span>
                  );
                })()}
                {isAIScan && (
                  <span className="text-[8px] font-semibold px-1 py-0.5 rounded bg-accent/15 text-accent">
                    AI
                  </span>
                )}
              </div>
              <span className="text-[10px] font-mono text-text-faint">{time}</span>
            </div>

            {/* Setup name (description on hover via tooltip) */}
            <div
              className="text-[11px] font-medium text-text-secondary mb-1 cursor-help"
              title={a.description || formatSetup(a.alert_type)}
            >
              {formatSetup(a.alert_type)}
            </div>

            {/* Quality strip — vol + slope */}
            {(a.volume_ratio != null || a.vwap_slope_pct != null) && (
              <div className="flex items-center gap-3 mb-1.5 text-[10px] font-mono">
                {a.volume_ratio != null && (() => {
                  const v = a.volume_ratio;
                  const cls = v >= 2.0 ? "text-bullish-text"
                    : v >= 1.5 ? "text-warning-text"
                    : v >= 1.0 ? "text-text-secondary"
                    : "text-text-faint";
                  return (
                    <span className={cls}>
                      Vol <span className="font-semibold">{v.toFixed(2)}×</span>
                    </span>
                  );
                })()}
                {a.vwap_slope_pct != null && (() => {
                  const s = a.vwap_slope_pct;
                  const cls = s >= 0.05 ? "text-bullish-text"
                    : s >= 0 ? "text-text-secondary"
                    : s >= -0.30 ? "text-warning-text"
                    : "text-bearish-text";
                  const sign = s > 0 ? "+" : "";
                  return (
                    <span className={cls}>
                      Slope <span className="font-semibold">{sign}{s.toFixed(2)}%</span>
                    </span>
                  );
                })()}
              </div>
            )}

            {/* Trade levels — entry / stop / T1 only (T2 dropped per UX cleanup) */}
            {a.entry != null ? (
              <div className="grid grid-cols-3 gap-1.5 text-[10px]">
                <div>
                  <div className="text-text-faint">Entry</div>
                  <div className="font-mono font-bold text-accent">{fmtPrice(a.entry)}</div>
                </div>
                <div>
                  <div className="text-text-faint">Stop</div>
                  <div className="font-mono text-bearish-text">{fmtPrice(a.stop)}</div>
                </div>
                <div>
                  <div className="text-text-faint">Target</div>
                  <div className="font-mono text-bullish-text">{fmtPrice(a.target_1)}</div>
                </div>
              </div>
            ) : (
              a.message && (
                <p className="text-[10px] text-text-muted leading-relaxed line-clamp-2">
                  {a.message}
                </p>
              )
            )}
          </div>
        );
      })}
        </div>
      )}
    </div>
  );
}

/* ── Bottom Setup Strip ───────────────────────────────────────────── */

function BottomStrip({ signal: s }: { signal: SignalResult }) {
  const risk = s.risk_per_share ?? (s.entry && s.stop ? s.entry - s.stop : null);
  const riskPct = (Number(localStorage.getItem("ts_risk_pct")) || 1) / 100;
  const portfolioSize =
    Number(localStorage.getItem("ts_portfolio_size")) || 50_000;
  const shares =
    risk && risk > 0 ? Math.floor(portfolioSize * riskPct / risk) : null;
  const t1Pct = pctChange(s.target_1, s.entry);

  return (
    <div className="border-t border-border-subtle bg-surface-1 px-4 py-2 shrink-0">
      {/* Row 1: Setup context */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] leading-relaxed">
        {s.nearest_support != null && (
          <span className="text-text-secondary">
            Support:{" "}
            <span className="font-mono text-accent">${fmt(s.nearest_support)}</span>
            {s.support_label && (
              <span className="text-text-muted"> ({s.support_label})</span>
            )}
          </span>
        )}
        <span className="text-text-faint">|</span>
        <span className="text-text-secondary">
          {s.support_status}
        </span>
        <span className="text-text-faint">|</span>
        <span className="text-text-secondary">
          {s.direction}
        </span>
        <span className="text-text-faint">|</span>
        <span className="text-text-muted italic">{s.pattern}</span>
      </div>

      {/* Row 2: Trade plan */}
      {s.entry != null && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 mt-1 text-[11px]">
          <span className="flex items-center gap-1">
            <Target className="h-3 w-3 text-accent" />
            <span className="text-text-faint">Entry</span>
            <span className="font-mono font-bold text-accent">${fmt(s.entry)}</span>
          </span>
          <span className="flex items-center gap-1">
            <ShieldAlert className="h-3 w-3 text-bearish-text/60" />
            <span className="text-text-faint">Stop</span>
            <span className="font-mono font-medium text-bearish-text">${fmt(s.stop)}</span>
          </span>
          <span>
            <span className="text-text-faint">T1</span>{" "}
            <span className="font-mono font-medium text-bullish-text">
              ${fmt(s.target_1)}
            </span>
            {t1Pct && (
              <span className="font-mono text-[10px] text-bullish-text/70 ml-0.5">
                {t1Pct}
              </span>
            )}
          </span>
          <span>
            <span className="text-text-faint">T2</span>{" "}
            <span className="font-mono text-text-secondary/60">${fmt(s.target_2)}</span>
          </span>
          <span className="font-mono font-bold text-accent bg-accent/10 px-1.5 py-0.5 rounded text-[10px] border border-accent/20">
            R:R {fmt(s.rr_ratio, 1)}:1
          </span>
          {shares != null && (
            <span className="text-text-muted">
              {shares} <span className="text-[10px]">shares</span>
            </span>
          )}
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
    setMobileWatchlistOpen(false);  // close drawer when symbol picked on mobile
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
  const [watchlistCollapsed, setWatchlistCollapsed] = useState(false);
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
  const [showRightPanel, setShowRightPanel] = useState(true);

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
  const watchlistSymbols = new Set(watchlistItems?.map((w) => w.symbol) ?? []);
  const { data: rankItems } = useWatchlistRank();
  const rankMap = new Map<string, WatchlistRankItem>();
  rankItems?.forEach((r) => rankMap.set(r.symbol, r));

  /* ── Editor's Picks (admin's public watchlist) ── */
  const { data: sectorsItems } = useSectorsWatchlist();
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

  const chartIndicators = ALL_INDICATORS.filter((ind) => activeIndicators.has(ind.key)).map(
    ({ key, color }) => ({ key, color })
  );

  /* ── Auto-select first symbol ── */
  if (!selectedSymbol && signals && signals.length > 0) {
    const entry = signals.find((s) => s.action_label === "Potential Entry");
    selectSymbol(entry?.symbol ?? signals[0].symbol);
  }

  /* ── Prefetch chart data ── */
  useEffect(() => {
    if (!signals) return;
    const tf = TIMEFRAMES[DEFAULT_TF];
    signals.slice(0, 5).forEach((s) => {
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
    const s = selected;
    const tradePrices = new Set(
      [s.entry, s.stop, s.target_1]
        .filter((v): v is number => v != null)
        .map((v) => Math.round(v * 100))
    );
    const isDup = (p: number) => tradePrices.has(Math.round(p * 100));
    const lvls: Array<{
      id: number;
      symbol: string;
      price: number;
      label: string;
      color: string;
    }> = [];
    if (s.ref_day_high != null && !isDup(s.ref_day_high))
      lvls.push({ id: -1, symbol: s.symbol, price: s.ref_day_high, label: "Prior High", color: "#22c55e" });
    if (s.ref_day_low != null && !isDup(s.ref_day_low))
      lvls.push({ id: -2, symbol: s.symbol, price: s.ref_day_low, label: "Prior Low", color: "#ef4444" });
    if (s.nearest_support != null && !isDup(s.nearest_support)) {
      const isBroken = (s.close ?? 0) < s.nearest_support;
      lvls.push({
        id: -3,
        symbol: s.symbol,
        price: s.nearest_support,
        label: isBroken ? "Resistance" : "Support",
        color: isBroken ? "#ef4444" : "#f59e0b",
      });
    }
    // VWAP level — key inflection point
    if ((s as any).vwap != null && !isDup((s as any).vwap)) {
      lvls.push({
        id: -4,
        symbol: s.symbol,
        price: (s as any).vwap,
        label: "VWAP",
        color: "#a855f7",
      });
    }
    return lvls;
  })();

  /* ── Filtered signals ── */
  const filteredSignals = signals
    ?.filter(
      (s) => !searchFilter || s.symbol.toLowerCase().includes(searchFilter.toLowerCase())
    )
    // Stable alphabetical sort — was sorting by rankMap.score, which caused
    // the entire list to reorder when /scanner/watchlist-rank (slow yfinance
    // call) returned 2-5s after first paint. Users saw it as "loading
    // latency". Rank badge still shows per row, just doesn't drive order.
    ?.sort((a, b) => a.symbol.localeCompare(b.symbol));

  // The signals shown in the right panel — today/latest, or a chosen past session.
  const activeAlerts = signalDate ? (pastAlerts ?? []) : todayAlerts;
  const activeAlertsError = signalDate ? pastAlertsError : alertsError;
  const feedCount = (activeAlerts ?? []).filter(
    (a) => isFeedSignal(a.alert_type) && a.suppressed_reason !== "type_not_enabled",
  ).length;

  const watchlistWidth = watchlistCollapsed ? 48 : 180;

  /* ────────────────────────────────────────────────────────────────── */

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── SPY Regime strip — pinned top, polls 60s ── */}
      <div className="shrink-0 px-2 pt-1.5 pb-1">
        <SpyRegimeStrip />
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
          {!watchlistCollapsed && (
            <span className="text-[11px] font-semibold text-text-secondary tracking-wide">
              Watchlist
            </span>
          )}
          <button
            onClick={() => {
              setWatchlistCollapsed((v) => !v);
              triggerResize();
            }}
            className="p-1 rounded text-text-faint hover:text-text-secondary hover:bg-surface-2/60 transition-colors"
            title={watchlistCollapsed ? "Expand watchlist" : "Collapse watchlist"}
          >
            {watchlistCollapsed ? (
              <ChevronRight className="h-3.5 w-3.5" />
            ) : (
              <ChevronLeft className="h-3.5 w-3.5" />
            )}
          </button>
        </div>

        {/* Search (only when expanded) */}
        {!watchlistCollapsed && (
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
                placeholder="Search..."
                className="w-full bg-surface-2/50 border border-border-subtle rounded py-1 pl-7 pr-6 text-[11px] text-text-primary placeholder:text-text-faint focus:outline-none focus:border-accent/50 transition-colors"
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
          {filteredSignals?.map((s) => (
            <CompactWatchlistRow
              key={s.symbol}
              signal={s}
              selected={selectedSymbol === s.symbol}
              onClick={() => selectSymbol(s.symbol)}
              onRemove={() => _removeSymbol.mutate(s.symbol)}
              livePrice={livePrices[s.symbol]}
              rankItem={rankMap.get(s.symbol)}
              collapsed={watchlistCollapsed}
            />
          ))}
        </div>

        {/* Editor's Picks — admin's curated watchlist. Collapsible; auto-
            expanded by default. Hero CTA at top when the user's personal
            watchlist is empty (new accounts). "Copy all" bulk-adds every
            missing symbol with one click. */}
        {!watchlistCollapsed && sectorsItems && sectorsItems.length > 0 && (
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
        {!watchlistCollapsed && (
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
              : "calc(17rem + env(safe-area-inset-bottom))",
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

          {/* Right: Indicators + Panel toggle */}
          <div className="flex items-center gap-1.5">
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
                  </div>
                </div>
              )}
            </div>

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

            {/* Draw S/R level — click to arm, then click the chart to drop a line */}
            <button
              onClick={() => setDrawMode((v) => !v)}
              disabled={!selectedSymbol}
              className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors border disabled:opacity-40 ${
                drawMode
                  ? "bg-accent text-white border-accent"
                  : "bg-surface-2/50 text-text-muted border-border-subtle hover:text-text-secondary"
              }`}
              title={`Draw a ${newLineType === "line" ? "level" : LINE_TYPES[newLineType].label} line — then click the chart`}
            >
              <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: drawMode ? "#ffffff" : LINE_TYPES[newLineType].color }} />
              <span className="hidden lg:inline">{drawMode ? "Drawing…" : "Draw"}</span>
            </button>

            {/* Saved S/R lines manager */}
            <div className="relative" ref={levelsPanelRef}>
              <button
                onClick={() => setShowLevelsPanel((v) => !v)}
                className={`flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium transition-colors border ${
                  showLevelsPanel
                    ? "bg-accent/15 text-accent border-accent/30"
                    : "bg-surface-2/50 text-text-muted border-border-subtle hover:text-text-secondary"
                }`}
                title="Your saved S/R lines for this symbol"
              >
                <span className="hidden lg:inline">Lines</span>
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
                  {/* New-line type — applied to the next line you draw */}
                  <div className="flex items-center gap-1 px-1 pb-1.5 mb-1 border-b border-border-subtle">
                    <span className="text-[10px] text-text-faint mr-0.5">New:</span>
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
                  </div>
                  {(userLevels ?? []).length === 0 ? (
                    <p className="text-[11px] text-text-faint px-1 py-2 leading-relaxed">
                      Tap <span className="text-accent font-medium">Draw</span>, then click the chart at a level.
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

        {/* Mobile: horizontal symbol pills */}
        <div className="flex gap-1.5 overflow-x-auto px-3 py-1.5 md:hidden shrink-0 no-scrollbar">
          {signals?.map((s) => (
            <button
              key={s.symbol}
              onClick={() => selectSymbol(s.symbol)}
              className={`shrink-0 rounded-md px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
                selectedSymbol === s.symbol
                  ? "bg-accent text-white"
                  : "bg-surface-3 text-text-muted"
              }`}
            >
              {s.symbol}
            </button>
          ))}
        </div>

        {/* Chart area — flex-1 to fill remaining space */}
        <div className="flex-1 min-h-0 relative">
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
              entry={showLevels ? (selected.entry ?? undefined) : undefined}
              stop={showLevels ? (selected.stop ?? undefined) : undefined}
              target={showLevels ? (selected.target_1 ?? undefined) : undefined}
              direction={(selected.direction === "SHORT" ? "SHORT" : "LONG")}
              levels={showLevels ? chartLevels : []}
              userLevels={userLevels ?? []}
              drawMode={drawMode}
              onAddLevel={handleAddLevel}
              indicators={chartIndicators}
              hideWicks={hideWicks}
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

        {/* Bottom setup strip */}
        {selected && <BottomStrip signal={selected} />}
      </section>

      {/* ── RIGHT: Signals feed (desktop) ── */}
      {showRightPanel && (
        <aside className="hidden lg:flex flex-col w-[320px] bg-surface-0 border-l border-border-subtle shrink-0">
          {/* Header — title, count, session picker */}
          <div className="flex items-center gap-2 border-b border-border-subtle shrink-0 h-14 px-3">
            <Zap className="h-4 w-4 text-accent" />
            <span className="text-sm font-bold text-text-primary">Signals</span>
            {feedCount > 0 && (
              <span className="text-[9px] font-bold min-w-[16px] h-[16px] flex items-center justify-center rounded-full bg-accent/15 text-accent px-1">
                {feedCount}
              </span>
            )}
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
          </div>

          {/* Asset filter — All / Stocks / Crypto */}
          <div className="flex items-center gap-1.5 px-3 py-2 border-b border-border-subtle shrink-0">
            {(["all", "stocks", "crypto"] as const).map((k) => (
              <button
                key={k}
                onClick={() => changeAssetFilter(k)}
                className={`text-[10px] px-2.5 py-0.5 rounded-full border transition-colors ${
                  assetFilter === k
                    ? "bg-accent/15 text-accent border-accent/40"
                    : "bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2"
                }`}
              >
                {k === "all" ? "All" : k === "stocks" ? "Stocks" : "Crypto"}
              </button>
            ))}
          </div>

          {/* Signal feed — AI scanner + TradingView signals */}
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <SignalFeedTab
              alerts={filterAlertsByAsset(activeAlerts)}
              alertsError={activeAlertsError}
              onSelectSymbol={selectSymbol}
              signalDate={signalDate}
            />
          </div>
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
        <button
          onClick={toggleMobileSignals}
          className="w-full flex items-center gap-2 px-3 py-2 border-b border-border-subtle text-left active:bg-surface-2/40 transition-colors"
          aria-label={mobileSignalsCollapsed ? "Expand signals" : "Collapse signals"}
        >
          <Zap className="h-3.5 w-3.5 text-accent" />
          <span className="text-xs font-bold text-text-primary">Signals</span>
          {!mobileSignalsCollapsed && (
            <select
              value={signalDate}
              onChange={(e) => setSignalDate(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              className="ml-auto bg-surface-0 border border-border-subtle rounded px-2 py-0.5 text-[11px] text-text-secondary"
            >
              <option value="">Today</option>
              {(sessionDates ?? []).slice(1).map((d) => (
                <option key={d} value={d}>{formatSessionDate(d)}</option>
              ))}
            </select>
          )}
          {mobileSignalsCollapsed ? (
            <ChevronUp className="h-4 w-4 text-text-muted ml-auto" />
          ) : (
            <ChevronDown className="h-4 w-4 text-text-muted" />
          )}
        </button>
        {!mobileSignalsCollapsed && (
          <div className="flex flex-col h-[240px] overflow-hidden">
            <SignalFeedTab
              alerts={filterAlertsByAsset(activeAlerts)}
              alertsError={activeAlertsError}
              onSelectSymbol={selectSymbol}
              signalDate={signalDate}
            />
          </div>
        )}
      </div>
      </div>
    </div>
  );
}
