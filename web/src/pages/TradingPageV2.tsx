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
  useAckAlert,
  useWatchlist,
  useAddSymbol,
  useRemoveSymbol,
  useLivePrices,
  useOptionsFlow,
  useWatchlistRank,
} from "../api/hooks";
import type { WatchlistRankItem } from "../types";
import { useCoachStream } from "../hooks/useCoachStream";
import { useFeatureGate } from "../hooks/useFeatureGate";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SignalResult, Alert } from "../types";
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
  Eye,
  Send,
  ChevronLeft,
  ChevronRight,
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
  { key: "ema5", label: "EMA 5", color: "#f472b6", group: "ema" },
  { key: "ema20", label: "EMA 20", color: "#60a5fa", group: "ema" },
  { key: "ema50", label: "EMA 50", color: "#f59e0b", group: "ema" },
  { key: "ema100", label: "EMA 100", color: "#a78bfa", group: "ema" },
  { key: "ema200", label: "EMA 200", color: "#34d399", group: "ema" },
  { key: "sma20", label: "SMA 20", color: "#38bdf8", group: "sma" },
  { key: "sma50", label: "SMA 50", color: "#fb923c", group: "sma" },
  { key: "sma100", label: "SMA 100", color: "#c084fc", group: "sma" },
  { key: "sma200", label: "SMA 200", color: "#4ade80", group: "sma" },
  { key: "vwap", label: "VWAP", color: "#e879f9", group: "other" },
];

const DEFAULT_INDICATORS = new Set(["ema5", "ema20", "ema100", "ema200"]);

function loadSavedIndicators(): Set<string> | null {
  try {
    const raw = localStorage.getItem("chart_indicators");
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

/* ── AI Coach Tab ─────────────────────────────────────────────────── */

function AICoachTab({
  symbol,
  ohlcv,
  timeframe,
}: {
  symbol: string | null;
  ohlcv?: import("../api/hooks").OHLCBar[];
  timeframe?: string;
}) {
  const { messages, streaming, sendMessage, stopStreaming, clearMessages, setChartContext } =
    useCoachStream();
  const [input, setInput] = useState("");
  const [lastAutoSymbol, setLastAutoSymbol] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (symbol && ohlcv && ohlcv.length > 0) {
      setChartContext({ symbol, timeframe: timeframe || "D", bars: ohlcv });
    }
  }, [symbol, ohlcv, timeframe, setChartContext]);

  // Track symbol changes — update context but DON'T clear messages.
  // Users want their conversation history to persist across symbol switches.
  useEffect(() => {
    if (symbol && symbol !== lastAutoSymbol) {
      setLastAutoSymbol(symbol);
    }
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streaming]);

  function getCurrentChartContext() {
    if (symbol && ohlcv && ohlcv.length > 0) {
      return { symbol, timeframe: timeframe || "D", bars: ohlcv };
    }
    return undefined;
  }

  function handleSend() {
    if (!input.trim()) return;
    const prompt = symbol ? `[Looking at ${symbol}] ${input.trim()}` : input.trim();
    sendMessage(prompt, getCurrentChartContext());
    setInput("");
  }

  return (
    <div className="flex h-full flex-col">
      {/* Quick prompts when empty */}
      {messages.length === 0 && symbol && !streaming && (
        <div className="px-3 py-3 space-y-1.5 shrink-0">
          <p className="text-[10px] font-semibold uppercase text-text-faint tracking-wider mb-1">
            Ask about {symbol}
          </p>
          {[
            { tag: "Entry", q: "What's the best entry strategy here?" },
            { tag: "Stop", q: "Where should I set my stop?" },
            { tag: "Bias", q: "Is this setup high conviction?" },
          ].map(({ tag, q }) => (
            <button
              key={q}
              onClick={() =>
                sendMessage(`[Looking at ${symbol}] ${q}`, getCurrentChartContext())
              }
              className="flex items-center gap-2 w-full rounded-lg bg-surface-2/60 border border-border-subtle/50 px-3 py-2 text-left text-xs text-text-muted hover:bg-accent/[0.06] hover:border-accent/20 hover:text-text-secondary transition-all duration-150"
            >
              <span className="shrink-0 text-[9px] font-bold uppercase tracking-wider text-accent bg-accent/10 px-1.5 py-0.5 rounded">
                {tag}
              </span>
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2 space-y-3 min-h-0">
        {messages.map((m, i) => {
          if (i === 0 && m.role === "user") return null;
          return (
            <div
              key={i}
              className={`text-[13px] leading-[1.6] ${m.role === "user" ? "text-accent" : "text-text-secondary"}`}
            >
              {m.role === "user" ? (
                <p className="font-medium bg-accent/[0.06] rounded-lg px-3 py-2 border border-accent/10">
                  {m.content}
                </p>
              ) : m.content.toLowerCase().includes("limit reached") || m.content.toLowerCase().includes("upgrade") ? (
                <div className="bg-surface-2/60 rounded-lg border border-accent/20 p-4 text-center">
                  <p className="text-text-secondary text-sm mb-3">{m.content}</p>
                  <Link
                    to="/billing"
                    className="inline-block px-4 py-2 rounded-lg bg-accent text-white text-sm font-semibold hover:bg-accent-hover transition-colors"
                  >
                    Upgrade Plan →
                  </Link>
                </div>
              ) : (
                <div className="bg-surface-2/60 rounded-lg border border-border-subtle p-3 relative">
                  <p
                    className="whitespace-pre-wrap text-[13px]"
                    dangerouslySetInnerHTML={{
                      __html: m.content
                        .replace(
                          /\*\*(.+?)\*\*/g,
                          "<strong class='text-text-primary font-semibold'>$1</strong>"
                        )
                        .replace(/^• /gm, "&#8226; "),
                    }}
                  />
                </div>
              )}
            </div>
          );
        })}
        {streaming && (
          <div className="flex items-center gap-2 text-xs bg-surface-2/40 rounded-lg px-3 py-2 border border-border-subtle/50">
            <span className="flex gap-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: "0ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: "150ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-accent animate-bounce" style={{ animationDelay: "300ms" }} />
            </span>
            <span className="text-text-muted">Analyzing...</span>
            <button onClick={stopStreaming} className="ml-auto text-bearish-text hover:text-bearish text-[10px] font-medium">
              Stop
            </button>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border-subtle p-2.5 shrink-0">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder={symbol ? `Ask about ${symbol}...` : "Ask the AI coach..."}
            disabled={streaming}
            className="flex-1 rounded-lg border border-border-subtle bg-surface-2 px-3 py-1.5 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none disabled:opacity-50 transition-all"
          />
          <button
            onClick={handleSend}
            disabled={streaming || !input.trim()}
            className="rounded-lg bg-accent px-2.5 py-1.5 text-white transition-all hover:bg-accent-hover disabled:opacity-40"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <div className="flex items-center justify-between mt-1.5">
          <span
            className={`text-[9px] font-mono px-1.5 py-0.5 rounded-full ring-1 ring-inset uppercase flex items-center gap-1 ${
              streaming
                ? "bg-accent/10 text-accent ring-accent/20"
                : "bg-bullish/10 text-bullish-text ring-bullish/20"
            }`}
          >
            <span className={`w-1 h-1 rounded-full ${streaming ? "bg-accent animate-pulse" : "bg-bullish"}`} />
            {streaming ? "Thinking" : "Live"}
          </span>
          {messages.length > 0 && (
            <button
              onClick={() => {
                clearMessages();
                setLastAutoSymbol(null);
              }}
              className="text-[10px] text-text-faint hover:text-text-muted"
            >
              Clear
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── AI WAITs Feed Tab ─────────────────────────────────────────────
 *  WAIT signals only — informational, shows what AI is ignoring.
 *  Used to build trust (AI is disciplined, not noisy).
 */

function AIScanFeedTab({
  alerts,
  onSelectSymbol,
}: {
  alerts?: Alert[];
  onSelectSymbol: (sym: string) => void;
}) {
  const { tier } = useFeatureGate();
  const isFree = tier === "free";
  const visibleLimit = isFree ? 5 : null;
  // WAIT alerts only — LONG/SHORT/RESISTANCE/EXIT live in the Signals tab
  const aiAlerts = (alerts?.filter((a) => a.alert_type === "ai_scan_wait") ?? [])
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());

  if (aiAlerts.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-xs text-text-faint">No AI waits yet today</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
      {aiAlerts.map((a, idx) => {
        // Free tier: blur alerts beyond limit
        if (visibleLimit && idx >= visibleLimit) {
          return (
            <div key={a.id} className="relative">
              <div className="blur-sm opacity-40 bg-surface-2/40 border border-border-subtle/60 rounded-lg p-2.5">
                <div className="text-[11px] text-text-muted">AI Scan alert</div>
              </div>
              {idx === visibleLimit && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <Link to="/billing" className="bg-accent text-white text-xs font-semibold px-4 py-2 rounded-lg hover:bg-accent-hover transition-colors">
                    Upgrade for unlimited AI scans
                  </Link>
                </div>
              )}
            </div>
          );
        }
        const time = new Date(a.created_at).toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        });
        const isWait = a.alert_type === "ai_scan_wait" || a.direction === "NOTICE";
        const isLong = a.direction === "BUY";
        const badge = isWait
          ? "bg-gray-500/10 text-gray-400 border-gray-500/20"
          : isLong
            ? "bg-purple-500/10 text-purple-400 border-purple-500/20"
            : "bg-orange-500/10 text-orange-400 border-orange-500/20";
        const label = isWait ? "WAIT" : isLong ? "AI LONG" : "AI RESISTANCE";

        return (
          <div
            key={a.id}
            className={`border border-border-subtle/60 rounded-lg p-2.5 cursor-pointer transition-colors ${
              isWait ? "bg-surface-2/20 opacity-60" : "bg-surface-2/40 hover:border-purple-500/20"
            }`}
            onClick={() => onSelectSymbol(a.symbol)}
          >
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-bold text-text-primary">{a.symbol}</span>
                <span className={`text-[9px] font-semibold px-1 py-0.5 rounded border ${badge}`}>
                  {label}
                </span>
                {a.price > 0 && (
                  <span className="text-[10px] font-mono text-text-muted">${a.price?.toFixed(2)}</span>
                )}
              </div>
              <span className="text-[10px] font-mono text-text-faint">{time}</span>
            </div>
            <p className="text-[11px] text-text-muted leading-relaxed line-clamp-2">
              {a.message}
            </p>
            {!isWait && a.entry && (
              <div className="flex gap-3 mt-1 text-[10px] text-text-faint">
                <span>Entry: <span className="text-purple-400 font-mono">${a.entry?.toFixed(2)}</span></span>
                {a.stop && <span>Stop: <span className="text-red-400 font-mono">${a.stop?.toFixed(2)}</span></span>}
                {a.target_1 && <span>T1: <span className="text-emerald-400 font-mono">${a.target_1?.toFixed(2)}</span></span>}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}


/* ── Signal Feed Tab ──────────────────────────────────────────────── */

function SignalFeedTab({
  alerts,
  alertsError,
  onSelectSymbol,
}: {
  alerts?: Alert[];
  alertsError: unknown;
  onSelectSymbol: (sym: string) => void;
}) {
  const ack = useAckAlert();

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

  // Show actionable AI alerts only — LONG / SHORT / RESISTANCE / EXIT.
  // WAIT lives in the AI Waits tab. Rule-based alerts are deprecated (Spec 34).
  const ruleAlerts = alerts?.filter((a) => {
    if (!a.alert_type?.startsWith("ai_")) return false;  // no rule-based
    if (a.alert_type === "ai_scan_wait") return false;   // WAITs go to the other tab
    return true;
  }) ?? [];

  if (ruleAlerts.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-xs text-text-faint">No AI signals yet today</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
      {ruleAlerts.map((a) => {
        const time = new Date(a.created_at).toLocaleTimeString("en-US", {
          hour: "2-digit",
          minute: "2-digit",
        });
        const isAIScan = a.alert_type?.startsWith("ai_");
        const dirLabel = isAIScan ? "AI SCAN" : a.direction === "SHORT" ? "RESISTANCE" : a.direction;
        const dirBadge = isAIScan
            ? "bg-purple-500/10 text-purple-400 border-purple-500/20"
            : a.direction === "BUY"
              ? "bg-bullish/10 text-bullish-text border-bullish/20"
              : a.direction === "SHORT"
                ? "bg-orange-500/10 text-orange-400 border-orange-500/20"
                : "bg-warning/10 text-warning-text border-warning/20";

        return (
          <div
            key={a.id}
            className="bg-surface-2/40 border border-border-subtle/60 rounded-lg p-2.5 hover:border-accent/20 transition-colors cursor-pointer"
            onClick={() => onSelectSymbol(a.symbol)}
          >
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] font-bold text-text-primary">{a.symbol}</span>
                <span className={`text-[9px] font-semibold px-1 py-0.5 rounded border ${dirBadge}`}>
                  {dirLabel}
                </span>
              </div>
              <span className="text-[10px] font-mono text-text-faint">{time}</span>
            </div>
            <p className="text-[11px] text-text-muted leading-relaxed line-clamp-2">
              {a.message}
            </p>
            {/* Action buttons */}
            {a.user_action == null && (a.direction === "BUY" || a.direction === "SHORT") && (
              <div className="flex gap-2 mt-1.5">
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
                className={`mt-1.5 inline-flex text-[9px] font-bold px-1.5 py-0.5 rounded ${
                  a.user_action === "took"
                    ? "text-bullish-text bg-bullish/10 border border-bullish/20"
                    : "text-text-muted bg-surface-3 border border-border-subtle"
                }`}
              >
                {a.user_action === "took" ? "Took" : "Skipped"}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Options Flow Tab ─────────────────────────────────────────────── */

function OptionsFlowTab({ symbols }: { symbols: string }) {
  const { data: flowItems, isLoading } = useOptionsFlow(symbols);

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center gap-2">
        <Loader2 className="h-3 w-3 animate-spin text-text-faint" />
        <span className="text-xs text-text-faint">Scanning options chains...</span>
      </div>
    );
  }

  if (!flowItems || flowItems.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-xs text-text-faint">No unusual options activity detected</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
      {flowItems.map((item, i) => (
        <div
          key={`${item.symbol}-${item.type}-${item.strike}-${item.expiry}-${i}`}
          className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-surface-2/40 border border-border-subtle/60 hover:border-accent/20 transition-colors"
        >
          <span className="text-[11px] font-bold text-text-primary w-10 shrink-0">
            {item.symbol}
          </span>
          <span
            className={`text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 ${
              item.type === "CALL"
                ? "bg-bullish/10 text-bullish-text border border-bullish/20"
                : "bg-bearish/10 text-bearish-text border border-bearish/20"
            }`}
          >
            {item.type}
          </span>
          <div className="flex flex-col flex-1 min-w-0">
            <span className="font-mono text-[11px] text-text-secondary">${item.strike}</span>
            <span className="text-[10px] text-text-faint">{item.expiry}</span>
          </div>
          <div className="flex flex-col items-end shrink-0">
            <span className="font-mono text-[11px] text-text-primary">
              {item.volume.toLocaleString()}
            </span>
            <span
              className={`text-[10px] font-bold ${item.volume_oi_ratio >= 10 ? "text-accent" : "text-text-muted"}`}
            >
              {item.volume_oi_ratio.toFixed(1)}x
            </span>
          </div>
        </div>
      ))}
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

/* ── Right Panel Tabs ─────────────────────────────────────────────── */

type RightTab = "ai" | "signals" | "flow" | "aiscan";

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
  const [rightTab, setRightTab] = useState<RightTab>("ai");
  const [showRightPanel, setShowRightPanel] = useState(true);
  const [mobileTab, setMobileTab] = useState<RightTab>("ai");

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
      localStorage.setItem("chart_indicators", JSON.stringify([...next]));
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

  // Count only actionable AI signals for the badge — not rules, not WAITs
  const alertCount = todayAlerts?.filter((a) =>
    a.alert_type?.startsWith("ai_") && a.alert_type !== "ai_scan_wait"
  ).length ?? 0;
  const flowSymbols =
    selected?.symbol ||
    (signals ?? [])
      .map((s) => s.symbol)
      .slice(0, 5)
      .join(",") ||
    "SPY";

  const watchlistWidth = watchlistCollapsed ? 48 : 180;

  /* ────────────────────────────────────────────────────────────────── */

  return (
    <div className="flex h-full overflow-hidden">
      {/* ── LEFT: Compact Watchlist ── */}
      <aside
        className="hidden md:flex flex-col bg-surface-1 border-r border-border-subtle shrink-0 transition-all duration-200"
        style={{ width: watchlistWidth }}
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
          {/* Left: Symbol + Price + Change */}
          <div className="flex items-center gap-2.5 min-w-0">
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

      {/* ── RIGHT: Tabbed Sidebar (desktop) ── */}
      {showRightPanel && (
        <aside className="hidden lg:flex flex-col w-[320px] bg-surface-0 border-l border-border-subtle shrink-0">
          {/* Tab bar */}
          <div className="flex border-b border-border-subtle shrink-0 h-10">
            {(
              [
                { key: "ai" as RightTab, label: "AI Coach", icon: Brain, badge: 0 },
                { key: "signals" as RightTab, label: "AI Signals", icon: Zap, badge: alertCount },
                { key: "aiscan" as RightTab, label: "AI Waits", icon: Eye, badge: 0 },
              ]
            ).map(({ key, label, icon: Icon, badge }) => (
              <button
                key={key}
                onClick={() => setRightTab(key)}
                className={`flex-1 flex items-center justify-center gap-1.5 text-[11px] font-medium transition-colors relative ${
                  rightTab === key
                    ? "text-accent"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">{label}</span>
                {badge != null && badge > 0 && (
                  <span className="text-[8px] font-bold min-w-[14px] h-[14px] flex items-center justify-center rounded-full bg-bearish/15 text-bearish-text ring-1 ring-inset ring-bearish/20 px-0.5">
                    {badge}
                  </span>
                )}
                {rightTab === key && (
                  <span className="absolute bottom-0 left-2 right-2 h-0.5 bg-accent rounded-t" />
                )}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <div className={rightTab === "ai" ? "flex-1 flex flex-col min-h-0" : "hidden"}>
              <AICoachTab
                symbol={selected?.symbol ?? null}
                ohlcv={ohlcv}
                timeframe={tf.label}
              />
            </div>
            {rightTab === "signals" && (
              <SignalFeedTab
                alerts={todayAlerts}
                alertsError={alertsError}
                onSelectSymbol={selectSymbol}
              />
            )}
            {rightTab === "aiscan" && (
              <AIScanFeedTab
                alerts={todayAlerts}
                onSelectSymbol={selectSymbol}
              />
            )}
          </div>
        </aside>
      )}

      {/* ── Mobile bottom tabs (AI / Signals) — visible below lg ── */}
      <div className="fixed inset-x-0 bottom-14 z-20 lg:hidden bg-surface-1 border-t border-border-subtle">
        {/* Mobile tab content */}
        <div className="h-[280px] overflow-hidden">
          {mobileTab === "ai" && (
            <AICoachTab
              symbol={selected?.symbol ?? null}
              ohlcv={ohlcv}
              timeframe={tf.label}
            />
          )}
          {mobileTab === "signals" && (
            <SignalFeedTab
              alerts={todayAlerts}
              alertsError={alertsError}
              onSelectSymbol={selectSymbol}
            />
          )}
          {mobileTab === "flow" && <OptionsFlowTab symbols={flowSymbols} />}
        </div>

        {/* Mobile tab bar */}
        <div className="flex border-t border-border-subtle">
          {(
            [
              { key: "ai" as RightTab, label: "AI", icon: Brain },
              { key: "signals" as RightTab, label: "Signals", icon: Zap },
              { key: "aiscan" as RightTab, label: "Waits", icon: Eye },
            ] as const
          ).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setMobileTab(key)}
              className={`flex-1 flex items-center justify-center gap-1 py-2 text-[10px] font-medium transition-colors ${
                mobileTab === key ? "text-accent" : "text-text-muted"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
