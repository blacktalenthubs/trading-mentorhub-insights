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
import {
  useScanner,
  useOHLCV,
  useAlertsToday,
  useAlertSessionDates,
  useAlertsForDate,
  useAckAlert,
  useSetAlertOutcome,
  useScorecard,
  useWatchlist,
  useAddSymbol,
  useRemoveSymbol,
  useLivePrices,
  useWatchlistRank,
} from "../api/hooks";
import type { WatchlistRankItem } from "../types";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SignalResult, Alert, ScorecardItem } from "../types";
import { formatSetup, isFeedSignal } from "../lib/alertFormat";
import CandlestickChart from "../components/CandlestickChart";
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
  Menu,
} from "lucide-react";

/* ── Constants ──────────────────────────────────────────────────────── */

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

/* ── EOD Scorecard — win rate by setup from the manual ✓/✗ marks ───── */

function Scorecard({ date }: { date: string }) {
  const { data } = useScorecard(date);
  const items: ScorecardItem[] = data?.items ?? [];

  if (items.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center px-4">
        <p className="text-xs text-text-faint text-center">
          No graded signals for this session yet — mark ✓ / ✗ on the cards.
        </p>
      </div>
    );
  }

  const renderGroup = (title: string, group: string) => {
    const rows = items.filter((i) => i.group === group);
    if (rows.length === 0) return null;
    return (
      <div className="mb-3">
        <div className="text-[10px] font-bold uppercase tracking-wide text-text-faint mb-1">
          {title}
        </div>
        {rows.map((i) => (
          <div
            key={i.alert_type}
            className="flex items-center justify-between py-1 border-b border-border-subtle/30 text-[11px]"
          >
            <span className="text-text-secondary truncate mr-2">
              {formatSetup(i.alert_type)}
            </span>
            <span className="font-mono shrink-0">
              <span className="text-bullish-text">{i.worked}</span>
              <span className="text-text-faint"> · </span>
              <span className="text-bearish-text">{i.failed}</span>
              <span
                className={`ml-2 font-bold ${
                  i.win_rate >= 50 ? "text-bullish-text" : "text-bearish-text"
                }`}
              >
                {i.win_rate}%
              </span>
            </span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="flex-1 overflow-y-auto px-3 py-2">
      {renderGroup("Day setups", "day")}
      {renderGroup("Swing setups", "swing")}
    </div>
  );
}

function SignalFeedTab({
  alerts,
  alertsError,
  onSelectSymbol,
  showNonRouted = false,
  signalDate = "",
}: {
  alerts?: Alert[];
  alertsError: unknown;
  onSelectSymbol: (sym: string) => void;
  showNonRouted?: boolean;
  signalDate?: string;
}) {
  const ack = useAckAlert();
  const setOutcome = useSetAlertOutcome();
  const [search, setSearch] = useState("");
  const [showScorecard, setShowScorecard] = useState(false);

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

  // AI scanner signals + every fired TradingView signal. WAITs excluded.
  // "Non-routed" is an exclusive view — on: only non-routed; off: only routed.
  const feedAlerts = (alerts ?? []).filter((a) => {
    if (!isFeedSignal(a.alert_type)) return false;
    const notRouted = a.suppressed_reason === "type_not_enabled";
    if (showNonRouted ? !notRouted : notRouted) return false;
    return true;
  });
  const q = search.trim().toUpperCase();
  const visible = q
    ? feedAlerts.filter((a) => (a.symbol || "").toUpperCase().includes(q))
    : feedAlerts;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Symbol search + scorecard toggle */}
      <div className="px-3 pt-2 pb-1 shrink-0 flex items-center gap-1.5">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search symbol…"
          className="flex-1 bg-surface-1 border border-border-subtle rounded px-2 py-1 text-[11px] text-text-secondary placeholder:text-text-faint focus:outline-none focus:border-accent/40"
        />
        <button
          onClick={() => setShowScorecard((v) => !v)}
          title="End-of-day scorecard — win rate by setup from your ✓/✗ marks"
          className={`shrink-0 text-[10px] px-2 py-1 rounded border transition-colors ${
            showScorecard
              ? "bg-accent/15 text-accent border-accent/40"
              : "bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2"
          }`}
        >
          Scorecard
        </button>
      </div>

      {showScorecard ? (
        <Scorecard date={signalDate} />
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
        const isTV = a.alert_type?.startsWith("tv_");
        const notRouted = a.suppressed_reason === "type_not_enabled";
        const dirText = a.direction === "BUY" ? "LONG"
          : a.direction === "SHORT" ? "SHORT"
          : a.direction === "NOTICE" ? "NOTICE" : (a.direction || "—");
        const dirCls = a.direction === "BUY"
          ? "bg-bullish/10 text-bullish-text border-bullish/20"
          : a.direction === "SHORT"
            ? "bg-orange-500/10 text-orange-400 border-orange-500/20"
            : "bg-warning/10 text-warning-text border-warning/20";
        const src = isTV ? "TV" : isAIScan ? "AI" : "";

        return (
          <div
            key={a.id}
            className={`bg-surface-2/40 border border-border-subtle/60 rounded-lg p-2.5 hover:border-accent/20 transition-colors cursor-pointer ${
              notRouted ? "opacity-55" : ""
            }`}
            onClick={() => onSelectSymbol(a.symbol)}
          >
            {/* Header — symbol, direction, source, time */}
            <div className="flex items-center justify-between mb-1.5">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-bold text-text-primary">{a.symbol}</span>
                <span className={`text-[9px] font-bold px-1 py-0.5 rounded border ${dirCls}`}>
                  {dirText}
                </span>
                {src && (
                  <span className="text-[8px] font-semibold px-1 py-0.5 rounded bg-surface-3 text-text-faint">
                    {src}
                  </span>
                )}
                {notRouted && (
                  <span className="text-[8px] font-bold px-1 py-0.5 rounded bg-surface-3 text-text-faint uppercase tracking-wide">
                    not routed
                  </span>
                )}
              </div>
              <span className="text-[10px] font-mono text-text-faint">{time}</span>
            </div>

            {/* Setup name */}
            <div className="text-[11px] font-medium text-text-secondary mb-1.5">
              {formatSetup(a.alert_type)}
            </div>

            {/* Trade levels — entry / stop / T1 / T2 */}
            {a.entry != null ? (
              <div className="grid grid-cols-4 gap-1.5 text-[10px]">
                <div>
                  <div className="text-text-faint">Entry</div>
                  <div className="font-mono font-bold text-accent">{fmtPrice(a.entry)}</div>
                </div>
                <div>
                  <div className="text-text-faint">Stop</div>
                  <div className="font-mono text-bearish-text">{fmtPrice(a.stop)}</div>
                </div>
                <div>
                  <div className="text-text-faint">T1</div>
                  <div className="font-mono text-bullish-text">{fmtPrice(a.target_1)}</div>
                </div>
                <div>
                  <div className="text-text-faint">T2</div>
                  <div className="font-mono text-text-secondary">{fmtPrice(a.target_2)}</div>
                </div>
              </div>
            ) : (
              a.message && (
                <p className="text-[10px] text-text-muted leading-relaxed line-clamp-2">
                  {a.message}
                </p>
              )
            )}

            {/* Action buttons — not shown on non-routed (review-only) rows */}
            {!notRouted && a.user_action == null && (a.direction === "BUY" || a.direction === "SHORT") && (
              <div className="flex gap-2 mt-2">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    ack.mutate({ id: a.id, action: "took" });
                  }}
                  className="rounded bg-bullish/15 px-2.5 py-0.5 text-[10px] font-semibold text-bullish-text hover:bg-bullish/25 transition-colors border border-bullish/20"
                >
                  Took
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    ack.mutate({ id: a.id, action: "skipped" });
                  }}
                  className="rounded bg-surface-4 px-2.5 py-0.5 text-[10px] font-semibold text-text-muted hover:bg-surface-3 transition-colors border border-border-subtle"
                >
                  Skip
                </button>
              </div>
            )}
            {a.user_action && (
              <span
                className={`mt-2 inline-flex text-[9px] font-bold px-1.5 py-0.5 rounded ${
                  a.user_action === "took"
                    ? "text-bullish-text bg-bullish/10 border border-bullish/20"
                    : "text-text-muted bg-surface-3 border border-border-subtle"
                }`}
              >
                {a.user_action === "took" ? "Took" : "Skipped"}
              </span>
            )}

            {/* Outcome grade — on every card, routed + non-routed */}
            <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-border-subtle/40">
              <span className="text-[9px] text-text-faint mr-auto">Did it work?</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setOutcome.mutate({ id: a.id, outcome: a.outcome === "worked" ? "clear" : "worked" });
                }}
                className={`rounded px-1.5 py-0.5 text-[10px] font-bold border transition-colors ${
                  a.outcome === "worked"
                    ? "bg-bullish/25 text-bullish-text border-bullish/30"
                    : "bg-surface-4 text-text-faint border-border-subtle hover:bg-surface-3"
                }`}
              >
                ✓ Worked
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setOutcome.mutate({ id: a.id, outcome: a.outcome === "failed" ? "clear" : "failed" });
                }}
                className={`rounded px-1.5 py-0.5 text-[10px] font-bold border transition-colors ${
                  a.outcome === "failed"
                    ? "bg-bearish/25 text-bearish-text border-bearish/30"
                    : "bg-surface-4 text-text-faint border-border-subtle hover:bg-surface-3"
                }`}
              >
                ✗ Didn't
              </button>
            </div>
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

  /* ── Panel state ── */
  const [watchlistCollapsed, setWatchlistCollapsed] = useState(false);
  // Mobile drawer — slides watchlist in from left on small screens
  const [mobileWatchlistOpen, setMobileWatchlistOpen] = useState(false);
  const [showRightPanel, setShowRightPanel] = useState(true);

  // Signals feed — which session to view ("" = today/latest)
  const [signalDate, setSignalDate] = useState<string>("");
  const [showNonRouted, setShowNonRouted] = useState(false);
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
  const selected = signals?.find((s) => s.symbol === selectedSymbol) ?? null;
  const tf = TIMEFRAMES[tfIdx];
  const { data: ohlcv } = useOHLCV(selected?.symbol ?? "", tf.period, tf.interval);

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
    ?.sort((a, b) => {
      const aScore = rankMap.get(a.symbol)?.score ?? 0;
      const bScore = rankMap.get(b.symbol)?.score ?? 0;
      if (aScore !== bScore) return bScore - aScore;
      return a.symbol.localeCompare(b.symbol);
    });

  // The signals shown in the right panel — today/latest, or a chosen past session.
  const activeAlerts = signalDate ? (pastAlerts ?? []) : todayAlerts;
  const activeAlertsError = signalDate ? pastAlertsError : alertsError;
  const feedCount = (activeAlerts ?? []).filter(
    (a) => isFeedSignal(a.alert_type) && a.suppressed_reason !== "type_not_enabled",
  ).length;

  const watchlistWidth = watchlistCollapsed ? 48 : 180;

  /* ────────────────────────────────────────────────────────────────── */

  return (
    <div className="flex h-full overflow-hidden">
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

      {/* ── CENTER: Chart + Top Bar + Bottom Strip ── */}
      <section className="flex-1 flex flex-col min-w-0 min-h-0 bg-surface-0 overflow-hidden">
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
        <div className="flex-1 min-h-0 relative chart-grid-bg">
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
              levels={showLevels ? chartLevels : []}
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

          {/* Asset filter + non-routed review toggle */}
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
            <button
              onClick={() => setShowNonRouted((v) => !v)}
              title="Show alert types that fired but aren't routed — review only"
              className={`ml-auto text-[10px] px-2.5 py-0.5 rounded-full border transition-colors ${
                showNonRouted
                  ? "bg-accent/15 text-accent border-accent/40"
                  : "bg-surface-1 text-text-muted border-border-subtle hover:bg-surface-2"
              }`}
            >
              Non-routed
            </button>
          </div>

          {/* Signal feed — AI scanner + TradingView signals */}
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <SignalFeedTab
              alerts={filterAlertsByAsset(activeAlerts)}
              alertsError={activeAlertsError}
              onSelectSymbol={selectSymbol}
              showNonRouted={showNonRouted}
              signalDate={signalDate}
            />
          </div>
        </aside>
      )}

      {/* ── Mobile signals panel — visible below lg ── */}
      <div className="fixed inset-x-0 bottom-14 z-20 lg:hidden bg-surface-1 border-t border-border-subtle">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border-subtle">
          <Zap className="h-3.5 w-3.5 text-accent" />
          <span className="text-xs font-bold text-text-primary">Signals</span>
          <select
            value={signalDate}
            onChange={(e) => setSignalDate(e.target.value)}
            className="ml-auto bg-surface-0 border border-border-subtle rounded px-2 py-0.5 text-[11px] text-text-secondary"
          >
            <option value="">Today</option>
            {(sessionDates ?? []).slice(1).map((d) => (
              <option key={d} value={d}>{formatSessionDate(d)}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-col h-[240px] overflow-hidden">
          <SignalFeedTab
            alerts={filterAlertsByAsset(activeAlerts)}
            alertsError={activeAlertsError}
            onSelectSymbol={selectSymbol}
            showNonRouted={showNonRouted}
            signalDate={signalDate}
          />
        </div>
      </div>
    </div>
  );
}
