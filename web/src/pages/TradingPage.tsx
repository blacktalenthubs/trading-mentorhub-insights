/** Trading — the ONE page traders live on all day.
 *
 *  Layout (desktop):
 *    Left:   320px watchlist panel (search + AI-ranked symbols)
 *    Center: Chart canvas (hero) + cockpit trade plan strip
 *    Right:  340px AI Coach (top) + Signal Feed (bottom)
 *
 *  Mobile: horizontal symbol pills + stacked chart/plan
 */

import { useState, useRef, useEffect } from "react";
import { useScanner, useOHLCV, useAlertsToday, useAckAlert, useWatchlist, useAddSymbol, useRemoveSymbol, useLivePrices, useOptionsFlow, useCatalysts, useWatchlistRank } from "../api/hooks";
import type { CatalystItem } from "../api/hooks";
import type { WatchlistRankItem } from "../types";
import { useCoachStream } from "../hooks/useCoachStream";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SignalResult, Alert } from "../types";
import CandlestickChart from "../components/CandlestickChart";
import SectorRotation from "../components/SectorRotation";
import {
  RefreshCw, Brain, Send, Search, Target, ShieldAlert,
  PanelRightOpen, PanelRightClose, Plus, X, Loader2,
  ChevronDown, ChevronUp, Activity, SlidersHorizontal,
  Zap,
} from "lucide-react";

/* ── constants ────────────────────────────────────────────────────── */


const SETUP_LABELS: Record<string, { text: string; class: string }> = {
  "Potential Entry": { text: "Entry", class: "text-bullish-text bg-bullish/10" },
  Watch: { text: "Watch", class: "text-warning-text bg-warning/10" },
  "No Setup": { text: "No Setup", class: "text-text-faint bg-surface-3" },
};

const TIMEFRAMES = [
  { label: "1m", period: "1d", interval: "1m" },
  { label: "5m", period: "5d", interval: "5m" },
  { label: "15m", period: "5d", interval: "15m" },
  { label: "30m", period: "5d", interval: "30m" },
  { label: "1H", period: "5d", interval: "60m" },
  { label: "4H", period: "1mo", interval: "60m" },
  { label: "D", period: "1y", interval: "1d" },
  { label: "W", period: "1y", interval: "1wk" },
  { label: "M", period: "5y", interval: "1mo" },
] as const;

const DEFAULT_TF = 6; // Daily
const DEFAULT_PORTFOLIO = Number(localStorage.getItem("ts_portfolio_size")) || 50_000;

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
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
  { key: "ema5",   label: "EMA 5",   color: "#f472b6", group: "ema" },
  { key: "ema20",  label: "EMA 20",  color: "#60a5fa", group: "ema" },
  { key: "ema50",  label: "EMA 50",  color: "#f59e0b", group: "ema" },
  { key: "ema100", label: "EMA 100", color: "#a78bfa", group: "ema" },
  { key: "ema200", label: "EMA 200", color: "#34d399", group: "ema" },
  { key: "sma20",  label: "SMA 20",  color: "#38bdf8", group: "sma" },
  { key: "sma50",  label: "SMA 50",  color: "#fb923c", group: "sma" },
  { key: "sma100", label: "SMA 100", color: "#c084fc", group: "sma" },
  { key: "sma200", label: "SMA 200", color: "#4ade80", group: "sma" },
  { key: "vwap",   label: "VWAP",    color: "#e879f9", group: "other" },
];

const DEFAULT_INDICATORS = new Set(["ema5", "ema20", "ema100", "ema200"]);

/* ── Watchlist signal row ──────────────────────────────────────────── */

function scoreBadgeClass(score: number): string {
  if (score >= 70) return "bg-bullish/15 text-bullish-text border-bullish/25";
  if (score >= 40) return "bg-warning/15 text-warning-text border-warning/25";
  return "bg-surface-3 text-text-faint border-border-subtle";
}

function SignalRow({
  signal: s,
  selected,
  onClick,
  onRemove,
  livePrice,
  rankItem,
  isTopPick,
}: {
  signal: SignalResult;
  selected: boolean;
  onClick: () => void;
  onRemove?: (e: React.MouseEvent) => void;
  livePrice?: { price: number; change_pct: number };
  rankItem?: WatchlistRankItem;
  isTopPick?: boolean;
}) {
  const [showSignal, setShowSignal] = useState(false);
  const displayPrice = livePrice?.price ?? s.close;
  const changeColor = livePrice
    ? (livePrice.change_pct >= 0 ? "text-bullish-text" : "text-bearish-text")
    : ((s.close ?? 0) >= (s.entry ?? s.close ?? 0) ? "text-bullish-text" : "text-bearish-text");

  const setupInfo = SETUP_LABELS[s.action_label] || { text: s.action_label, class: "text-text-faint bg-surface-3" };

  return (
    <div
      onMouseEnter={() => setShowSignal(true)}
      onMouseLeave={() => setShowSignal(false)}
      className="relative"
    >
      <button
        onClick={onClick}
        className={`group flex w-full items-center px-3 py-2.5 text-left transition-all duration-150 ${
          selected
            ? "bg-accent/[0.06] border-l-2 border-accent"
            : isTopPick
            ? "border-l-2 border-bullish/50 bg-bullish/[0.03]"
            : "border-l-2 border-transparent hover:bg-surface-2/60"
        }`}
      >
        <div className="w-[56px] relative">
          <div className="flex items-center gap-1">
            <span className="text-sm font-bold text-text-primary leading-tight">{s.symbol}</span>
            {isTopPick && (
              <span className="text-[7px] font-bold uppercase tracking-wider text-bullish-text bg-bullish/10 px-1 py-px rounded leading-tight border border-bullish/20">
                Top
              </span>
            )}
          </div>
          <span className={`inline-block mt-0.5 px-1.5 py-px rounded text-[9px] font-semibold leading-tight ${setupInfo.class}`}>
            {setupInfo.text}
          </span>
        </div>
        <div className="flex-1 flex flex-col items-end gap-0.5">
          <div className="font-mono text-sm text-text-primary leading-none">${fmt(displayPrice)}</div>
          {livePrice ? (
            <div className={`font-mono text-[10px] leading-none ${changeColor}`}>
              {livePrice.change_pct >= 0 ? "+" : ""}{livePrice.change_pct.toFixed(2)}%
            </div>
          ) : s.volume_ratio != null && s.volume_ratio > 0 ? (
            <div className={`font-mono text-[10px] leading-none ${changeColor}`}>
              {s.volume_ratio.toFixed(1)}x vol
            </div>
          ) : null}
        </div>
        <div className="w-12 ml-2.5 flex flex-col items-center gap-0.5">
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold leading-tight border ${scoreBadgeClass(rankItem?.score ?? s.score)}`}>
            {rankItem?.score ?? s.score}
          </span>
          <span className="text-[9px] text-text-faint leading-tight">
            {(rankItem?.score ?? s.score) >= 70 ? "Strong" : (rankItem?.score ?? s.score) >= 50 ? "Moderate" : "Weak"}
          </span>
        </div>
        {/* Remove button — appears on hover */}
        {onRemove && (
          <span
            onClick={onRemove}
            className="ml-1 p-1 rounded opacity-0 group-hover:opacity-100 text-text-faint hover:text-bearish-text hover:bg-bearish/10 transition-all duration-150"
            title={`Remove ${s.symbol}`}
          >
            <X className="h-3 w-3" />
          </span>
        )}
      </button>
      {/* Signal tooltip on hover */}
      {showSignal && rankItem?.signal && (
        <div className="absolute left-3 right-3 -bottom-0.5 translate-y-full z-20 px-2.5 py-1.5 rounded-md bg-surface-3 border border-border-subtle shadow-lg text-[10px] text-text-secondary leading-snug pointer-events-none">
          {rankItem.signal}
        </div>
      )}
    </div>
  );
}

/* ── Catalyst banner ─────────────────────────────────────────────── */

function CatalystBanner({
  catalysts,
  onSelectSymbol,
}: {
  catalysts: CatalystItem[];
  onSelectSymbol: (symbol: string) => void;
}) {
  // Only show catalysts within 3 days
  const urgent = catalysts.filter((c) => c.days_away <= 3);
  if (urgent.length === 0) return null;

  function daysLabel(days: number): string {
    if (days === 0) return "today";
    if (days === 1) return "tomorrow";
    return `in ${days} days`;
  }


  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-warning/10 border-b border-warning/20 text-xs shrink-0 overflow-x-auto no-scrollbar">
      <span className="shrink-0 text-warning-text font-semibold">&#9888;</span>
      <div className="flex items-center gap-3 min-w-0">
        {urgent.map((c, i) => (
          <span key={`${c.symbol}-${c.event}`} className="flex items-center gap-1 shrink-0">
            {i > 0 && <span className="text-warning-text/40 mr-1">|</span>}
            <button
              onClick={() => onSelectSymbol(c.symbol)}
              className="font-semibold text-warning-text hover:text-warning-text/80 underline underline-offset-2 decoration-warning/30 transition-colors"
            >
              {c.symbol}
            </button>
            <span className="text-text-secondary">
              {c.event === "EARNINGS" ? "earnings" : "ex-dividend"}{" "}
              {daysLabel(c.days_away)}
              {c.event === "EARNINGS" && c.timing && c.timing !== "Unknown" && (
                <span className="text-text-muted"> ({c.timing})</span>
              )}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

/* ── Cockpit trade plan strip ──────────────────────────────────────── */

function CockpitStrip({ signal: s }: { signal: SignalResult }) {
  const risk = s.risk_per_share ?? (s.entry && s.stop ? s.entry - s.stop : null);
  const riskPct = (Number(localStorage.getItem("ts_risk_pct")) || 1) / 100;
  const shares = risk && risk > 0 ? Math.floor(DEFAULT_PORTFOLIO * riskPct / risk) : null;
  const stopPct = pctChange(s.stop, s.entry);
  const t1Pct = pctChange(s.target_1, s.entry);

  if (s.entry == null) return null;

  return (
    <div className="h-[96px] border-t-2 border-accent/20 bg-surface-1 px-3 sm:px-5 flex items-center shrink-0 overflow-x-auto no-scrollbar relative">
      {/* Subtle gradient */}
      <div className="absolute inset-0 bg-gradient-to-r from-accent/[0.04] via-transparent to-accent/[0.04] pointer-events-none" />

      <div className="flex items-center h-full min-w-max w-full relative">
        {/* Setup type */}
        <div className="flex flex-col justify-center pr-5">
          <span className="text-[10px] uppercase tracking-wider text-text-faint font-medium mb-1">Setup</span>
          <div className="flex items-center gap-2">
            <span className={`w-1.5 h-5 rounded-full ${s.direction === "LONG" || s.direction === "Bullish" ? "bg-bullish" : "bg-bearish"}`} />
            <div>
              <div className="text-sm font-bold text-text-primary">{s.action_label}</div>
              <div className="text-[10px] text-text-faint">{s.pattern}</div>
            </div>
          </div>
        </div>

        <div className="w-px h-10 bg-border-subtle mx-2" />

        {/* Entry */}
        <div className="flex flex-col justify-center px-4 hover:bg-surface-2/30 h-full transition-colors rounded-lg">
          <span className="text-[10px] uppercase tracking-wider text-text-faint font-medium mb-1 flex items-center gap-1">
            Entry <Target className="h-2.5 w-2.5 text-accent" />
          </span>
          <div className="font-mono text-lg font-bold text-accent">${fmt(s.entry)}</div>
        </div>

        <div className="w-px h-10 bg-border-subtle mx-2" />

        {/* Stop */}
        <div className="flex flex-col justify-center px-4 hover:bg-surface-2/30 h-full transition-colors rounded-lg">
          <span className="text-[10px] uppercase tracking-wider text-text-faint font-medium mb-1 flex items-center gap-1">
            Stop <ShieldAlert className="h-2.5 w-2.5 text-text-faint" />
          </span>
          <div className="flex items-end gap-2">
            <span className="font-mono text-lg font-medium text-bearish-text">${fmt(s.stop)}</span>
            {stopPct && (
              <span className="font-mono text-[10px] text-bearish-text/70 bg-bearish/10 px-1 py-0.5 rounded mb-0.5">{stopPct}</span>
            )}
          </div>
        </div>

        <div className="w-px h-10 bg-border-subtle mx-2" />

        {/* Targets */}
        <div className="flex flex-col justify-center px-4 hover:bg-surface-2/30 h-full transition-colors rounded-lg">
          <div className="flex gap-5">
            <div>
              <span className="text-[10px] uppercase tracking-wider text-text-faint font-medium mb-1 block">T1</span>
              <div className="flex items-end gap-1">
                <span className="font-mono text-base font-medium text-bullish-text">${fmt(s.target_1)}</span>
                {t1Pct && <span className="font-mono text-[9px] text-bullish-text pb-0.5">{t1Pct}</span>}
              </div>
            </div>
            <div>
              <span className="text-[10px] uppercase tracking-wider text-text-faint font-medium mb-1 block">T2</span>
              <span className="font-mono text-base font-medium text-text-secondary/60">${fmt(s.target_2)}</span>
            </div>
          </div>
        </div>

        <div className="w-px h-10 bg-border-subtle mx-2" />

        {/* R:R & Shares */}
        <div className="flex flex-col justify-center px-4">
          <div className="flex gap-5">
            <div>
              <span className="text-[10px] uppercase tracking-wider text-text-faint font-medium mb-1 block">R:R</span>
              <div className="font-mono text-base font-bold text-accent bg-accent/10 px-2.5 py-0.5 rounded border border-accent/20 text-center">
                {fmt(s.rr_ratio, 1)}:1
              </div>
            </div>
            <div>
              <span className="text-[10px] uppercase tracking-wider text-text-faint font-medium mb-1 block">Shares</span>
              <div className="font-mono text-base text-text-secondary">
                {shares ?? "—"} <span className="text-xs text-text-faint font-sans">sh</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── AI Coach panel ────────────────────────────────────────────────── */

function AIPanel({ symbol, signal: _signal, ohlcv, timeframe }: {
  symbol: string | null;
  signal: SignalResult | null;
  ohlcv?: import("../api/hooks").OHLCBar[];
  timeframe?: string;
}) {
  const { messages, streaming, sendMessage, stopStreaming, clearMessages, setChartContext } = useCoachStream();
  const [input, setInput] = useState("");
  const [lastAutoSymbol, setLastAutoSymbol] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Update chart context whenever symbol/timeframe/bars change
  useEffect(() => {
    if (symbol && ohlcv && ohlcv.length > 0) {
      setChartContext({ symbol, timeframe: timeframe || "D", bars: ohlcv });
    }
  }, [symbol, ohlcv, timeframe, setChartContext]);

  // Clear coach messages when switching symbols — fresh slate, no stale analysis
  useEffect(() => {
    if (symbol && symbol !== lastAutoSymbol) {
      setLastAutoSymbol(symbol);
      clearMessages();
    }
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll on new content
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streaming]);

  // Build current chart context for manual sends
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
      {/* Header */}
      <div className="p-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-accent/20 border border-accent/30 flex items-center justify-center relative overflow-hidden ai-sweep-glow">
            <Brain className="h-3 w-3 text-accent relative z-10" />
          </div>
          <span className="text-sm font-semibold text-text-primary">AI Coach</span>
        </div>
        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button onClick={() => { clearMessages(); setLastAutoSymbol(null); }} className="text-[10px] text-text-faint hover:text-text-muted">
              Clear
            </button>
          )}
          <span className={`text-[10px] font-mono px-2 py-0.5 rounded-full ring-1 ring-inset uppercase flex items-center gap-1.5 ${
            streaming
              ? "bg-accent/10 text-accent ring-accent/20"
              : "bg-bullish/10 text-bullish-text ring-bullish/20"
          }`}>
            <span className={`w-1.5 h-1.5 rounded-full ${streaming ? "bg-accent animate-pulse" : "bg-bullish"}`} />
            {streaming ? "Thinking" : "Live"}
          </span>
        </div>
      </div>

      {/* Quick prompts when empty */}
      {messages.length === 0 && symbol && !streaming && (
        <div className="px-3 pb-3 space-y-1.5">
          <p className="text-[10px] font-semibold uppercase text-text-faint tracking-wider mb-1">Ask about {symbol}</p>
          {[
            { emoji: "Entry", q: "What's the best entry strategy here?" },
            { emoji: "Stop", q: "Where should I set my stop?" },
            { emoji: "Bias", q: "Is this setup high conviction?" },
          ].map(({ emoji, q }) => (
            <button
              key={q}
              onClick={() => sendMessage(`[Looking at ${symbol}] ${q}`, getCurrentChartContext())}
              className="flex items-center gap-2 w-full rounded-lg bg-surface-2/60 border border-border-subtle/50 px-3 py-2 text-left text-xs text-text-muted hover:bg-accent/[0.06] hover:border-accent/20 hover:text-text-secondary transition-all duration-150"
            >
              <span className="shrink-0 text-[9px] font-bold uppercase tracking-wider text-accent bg-accent/10 px-1.5 py-0.5 rounded">{emoji}</span>
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
            <div key={i} className={`text-[13px] leading-[1.6] ${m.role === "user" ? "text-accent" : "text-text-secondary"}`}>
              {m.role === "user" ? (
                <p className="font-medium bg-accent/[0.06] rounded-lg px-3 py-2 border border-accent/10">{m.content}</p>
              ) : (
                <div
                  className="bg-surface-2/60 rounded-lg border border-border-subtle p-3.5 relative"
                >
                  {i === 1 && (
                    <div className="absolute top-0 left-0 w-full h-0.5 bg-gradient-to-r from-accent via-purple to-accent rounded-t-lg opacity-50" />
                  )}
                  <p
                    className="whitespace-pre-wrap text-[13px]"
                    dangerouslySetInnerHTML={{
                      __html: m.content
                        .replace(/\*\*(.+?)\*\*/g, "<strong class='text-text-primary font-semibold'>$1</strong>")
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
            <button onClick={stopStreaming} className="ml-auto text-bearish-text hover:text-bearish text-[10px] font-medium">Stop</button>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border-subtle p-3 shrink-0 bg-surface-1/30">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder={symbol ? `Ask about ${symbol}...` : "Ask the AI coach..."}
            disabled={streaming}
            className="flex-1 rounded-lg border border-border-subtle bg-surface-2 px-3 py-2 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none disabled:opacity-50 transition-all"
          />
          <button
            onClick={handleSend}
            disabled={streaming || !input.trim()}
            className="rounded-lg bg-accent px-3 py-2 text-white transition-all hover:bg-accent-hover disabled:opacity-40 hover:shadow-md hover:shadow-accent/20"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Alert timeline item ───────────────────────────────────────────── */

function AlertTimelineItem({ alert: a, onSelectSymbol }: { alert: Alert; onSelectSymbol?: (sym: string) => void }) {
  const ack = useAckAlert();
  const time = new Date(a.created_at).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });

  const dirBadge =
    a.direction === "BUY"
      ? "bg-bullish/10 text-bullish-text border-bullish/20"
      : a.direction === "SHORT"
      ? "bg-bearish/10 text-bearish-text border-bearish/20"
      : "bg-warning/10 text-warning-text border-warning/20";

  const dotColor =
    a.direction === "BUY" ? "bg-bullish" :
    a.direction === "SHORT" ? "bg-bearish" :
    a.direction === "SELL" ? "bg-warning" : "bg-text-faint";

  return (
    <div className="relative pl-10 py-2 group">
      {/* Time label */}
      <div className="absolute left-0 top-2.5 w-9 text-[10px] font-mono text-text-faint text-right">{time}</div>
      {/* Dot on timeline */}
      <div className={`absolute left-[38px] top-[14px] w-2 h-2 rounded-full ${dotColor} ring-[3px] ring-surface-0 z-10`} />
      {/* Card */}
      <div
        className="bg-surface-2/40 border border-border-subtle/60 rounded-lg p-2.5 group-hover:border-accent/30 group-hover:bg-surface-2/60 transition-all duration-150 cursor-pointer"
        onClick={() => onSelectSymbol?.(a.symbol)}
      >
        <div className="flex justify-between items-center mb-1.5">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-text-primary group-hover:text-accent transition-colors">{a.symbol}</span>
            <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border ${dirBadge}`}>
              {a.direction}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[9px] text-text-faint font-medium px-1.5 py-0.5 bg-surface-3/80 rounded">
              {a.alert_type.replace(/_/g, " ")}
            </span>
            <span className="text-[9px] text-accent opacity-0 group-hover:opacity-100 transition-opacity">
              View →
            </span>
          </div>
        </div>
        <p className="text-[11px] text-text-muted leading-relaxed">{a.message}</p>
        {/* Action buttons */}
        {a.user_action == null && (a.direction === "BUY" || a.direction === "SHORT") && (
          <div className="flex gap-2 mt-2">
            <button
              onClick={(e) => { e.stopPropagation(); ack.mutate({ id: a.id, action: "took" }); }}
              className="rounded-md bg-bullish/15 px-3 py-1 text-[11px] font-semibold text-bullish-text hover:bg-bullish/25 transition-colors border border-bullish/20"
            >
              Took
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); ack.mutate({ id: a.id, action: "skipped" }); }}
              className="rounded-md bg-surface-4 px-3 py-1 text-[11px] font-semibold text-text-muted hover:bg-surface-3 transition-colors border border-border-subtle"
            >
              Skip
            </button>
          </div>
        )}
        {a.user_action && (
          <span className={`mt-2 inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded ${
            a.user_action === "took"
              ? "text-bullish-text bg-bullish/10 border border-bullish/20"
              : "text-text-muted bg-surface-3 border border-border-subtle"
          }`}>
            {a.user_action === "took" ? "Took" : "Skipped"}
          </span>
        )}
      </div>
    </div>
  );
}

/* ── Options Flow Panel ───────────────────────────────────────────── */

function OptionsFlowPanel({ symbols }: { symbols: string }) {
  const [collapsed, setCollapsed] = useState(true);
  const { data: flowItems, isLoading } = useOptionsFlow(symbols);

  const count = flowItems?.length ?? 0;

  return (
    <div className="border-b border-border-subtle">
      {/* Header — click to toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full px-4 py-2.5 flex items-center justify-between hover:bg-surface-2/40 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5 text-accent" />
          <span className="text-sm font-semibold text-text-primary">Options Flow</span>
          {count > 0 && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-accent/15 text-accent ring-1 ring-inset ring-accent/20">
              {count}
            </span>
          )}
        </div>
        <ChevronDown className={`h-3.5 w-3.5 text-text-faint transition-transform duration-200 ${collapsed ? "" : "rotate-180"}`} />
      </button>

      {/* Collapsible body */}
      {!collapsed && (
        <div className="px-3 pb-3 max-h-[280px] overflow-y-auto">
          {isLoading && (
            <div className="flex items-center justify-center py-4 gap-2">
              <Loader2 className="h-3 w-3 animate-spin text-text-faint" />
              <span className="text-xs text-text-faint">Scanning options chains...</span>
            </div>
          )}

          {!isLoading && count === 0 && (
            <p className="py-4 text-center text-xs text-text-faint">No unusual options activity detected</p>
          )}

          {!isLoading && flowItems && flowItems.length > 0 && (
            <div className="space-y-1.5">
              {flowItems.map((item, i) => (
                <div
                  key={`${item.symbol}-${item.type}-${item.strike}-${item.expiry}-${i}`}
                  className="flex items-center gap-2 px-2.5 py-2 rounded-lg bg-surface-2/40 border border-border-subtle/60 hover:border-accent/20 transition-colors"
                >
                  {/* Symbol */}
                  <span className="text-xs font-bold text-text-primary w-12 shrink-0">{item.symbol}</span>

                  {/* CALL/PUT badge */}
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 ${
                    item.type === "CALL"
                      ? "bg-bullish/10 text-bullish-text border border-bullish/20"
                      : "bg-bearish/10 text-bearish-text border border-bearish/20"
                  }`}>
                    {item.type}
                  </span>

                  {/* Strike + Expiry */}
                  <div className="flex flex-col flex-1 min-w-0">
                    <span className="font-mono text-xs text-text-secondary">${item.strike}</span>
                    <span className="text-[10px] text-text-faint">{item.expiry}</span>
                  </div>

                  {/* Volume */}
                  <div className="flex flex-col items-end shrink-0">
                    <span className="font-mono text-xs text-text-primary">{item.volume.toLocaleString()}</span>
                    <span className={`text-[10px] font-bold ${
                      item.volume_oi_ratio >= 10 ? "text-accent" : "text-text-muted"
                    }`}>
                      {item.volume_oi_ratio.toFixed(1)}x
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Collapsible Right Panel ──────────────────────────────────────── */

function RightPanel({
  selected,
  ohlcv,
  tfLabel,
  signals,
  todayAlerts,
  alertsError,
  symbolAlerts,
  onSelectSymbol,
}: {
  selected: SignalResult | null;
  ohlcv?: import("../api/hooks").OHLCBar[];
  tfLabel: string;
  signals: SignalResult[];
  todayAlerts?: Alert[];
  alertsError: unknown;
  symbolAlerts?: Alert[];
  onSelectSymbol: (sym: string) => void;
}) {
  const [coachOpen, setCoachOpen] = useState(true);
  const [signalFeedOpen, setSignalFeedOpen] = useState(true);

  const alertCount = todayAlerts?.length ?? 0;

  return (
    <aside className="hidden xl:flex w-[400px] bg-surface-0 border-l border-border-subtle flex-col shrink-0">
      {/* AI Coach (collapsible) */}
      <div className={`flex flex-col ${coachOpen ? "flex-1 min-h-[45%]" : ""} border-b border-border-subtle relative overflow-hidden`}>
        {/* Collapsible header */}
        <button
          onClick={() => setCoachOpen((v) => !v)}
          className="w-full px-4 py-2.5 flex items-center justify-between hover:bg-surface-2/40 transition-colors shrink-0"
        >
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-accent/20 border border-accent/30 flex items-center justify-center relative overflow-hidden ai-sweep-glow">
              <Brain className="h-3 w-3 text-accent relative z-10" />
            </div>
            <span className="text-sm font-semibold text-text-primary">AI Coach</span>
          </div>
          {coachOpen ? (
            <ChevronUp className="h-3.5 w-3.5 text-text-faint" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-text-faint" />
          )}
        </button>
        {coachOpen && (
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <AIPanel symbol={selected?.symbol ?? null} signal={selected} ohlcv={ohlcv} timeframe={tfLabel} />
            {/* Decorative glow */}
            <div className="absolute top-[-80px] right-[-80px] w-[160px] h-[160px] bg-accent/5 rounded-full blur-3xl pointer-events-none" />
          </div>
        )}
      </div>

      {/* Options Flow (collapsible — starts collapsed, has its own internal state) */}
      <OptionsFlowPanel symbols={signals.map((s) => s.symbol).slice(0, 10).join(",") || "SPY,QQQ,AAPL,NVDA,TSLA"} />

      {/* Signal Feed (collapsible) */}
      <div className={`flex flex-col ${signalFeedOpen ? "flex-1" : ""} min-h-0`}>
        <button
          onClick={() => setSignalFeedOpen((v) => !v)}
          className="w-full px-4 py-2.5 flex items-center justify-between border-b border-border-subtle hover:bg-surface-2/40 transition-colors shrink-0"
        >
          <div className="flex items-center gap-2">
            <Zap className="h-3.5 w-3.5 text-accent" />
            <span className="text-sm font-semibold text-text-primary">Signal Feed</span>
            {alertCount > 0 && (
              <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-bearish/15 text-bearish-text ring-1 ring-inset ring-bearish/20">
                {alertCount}
              </span>
            )}
            {todayAlerts && todayAlerts.length > 0 && (
              <span className="flex h-2 w-2 relative">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-bearish opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-bearish" />
              </span>
            )}
          </div>
          {signalFeedOpen ? (
            <ChevronUp className="h-3.5 w-3.5 text-text-faint" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-text-faint" />
          )}
        </button>

        {signalFeedOpen && (
          <div className="flex-1 overflow-y-auto px-3 relative">
            {/* Timeline line */}
            <div className="absolute left-[42px] top-4 bottom-0 w-px bg-border-subtle pointer-events-none" />

            {alertsError ? (
              <div className="py-8 text-center">
                <p className="text-xs text-bearish-text mb-2">Failed to load alerts</p>
                <button onClick={() => window.location.reload()} className="text-[10px] text-accent hover:text-accent-hover">Retry</button>
              </div>
            ) : symbolAlerts && symbolAlerts.length > 0 ? (
              symbolAlerts.map((a) => <AlertTimelineItem key={a.id} alert={a} onSelectSymbol={onSelectSymbol} />)
            ) : (
              <p className="py-8 text-center text-xs text-text-faint">No alerts fired today</p>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

/* ── Main Trading Page ─────────────────────────────────────────────── */

export default function TradingPage() {
  const { data: signals, isLoading, refetch, isFetching, error: scanError } = useScanner();
  const { data: todayAlerts, error: alertsError } = useAlertsToday();
  const { data: livePriceData } = useLivePrices();
  const livePrices = livePriceData?.prices ?? {};
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [tfIdx, setTfIdx] = useState(DEFAULT_TF);
  const [activeIndicators, setActiveIndicators] = useState<Set<string>>(DEFAULT_INDICATORS);
  const [showLevels, setShowLevels] = useState(true);
  const [hideWicks, setHideWicks] = useState(false);
  const [showRightPanel, setShowRightPanel] = useState(true);
  const [showLeftPanel, setShowLeftPanel] = useState(true);
  const [showIndicatorPanel, setShowIndicatorPanel] = useState(false);
  const indicatorPanelRef = useRef<HTMLDivElement>(null);

  // Trigger chart resize when panels toggle
  function toggleRightPanel() {
    setShowRightPanel((prev) => !prev);
    setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
  }
  function toggleLeftPanel() {
    setShowLeftPanel((prev) => !prev);
    setTimeout(() => window.dispatchEvent(new Event("resize")), 50);
  }
  const [searchFilter, setSearchFilter] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);
  const [sortMode, setSortMode] = useState<"score" | "az">("score");
  const queryClient = useQueryClient();

  // Watchlist ranking
  const { data: rankItems } = useWatchlistRank();
  const rankMap = new Map<string, WatchlistRankItem>();
  rankItems?.forEach((r) => rankMap.set(r.symbol, r));

  // Watchlist add/remove
  const { data: watchlistItems } = useWatchlist();
  const addSymbol = useAddSymbol();
  const removeSymbol = useRemoveSymbol();
  const watchlistSymbols = new Set(watchlistItems?.map((w) => w.symbol) ?? []);

  // Catalysts — upcoming earnings/ex-dividend for watchlist symbols
  const watchlistSymbolsCsv = watchlistItems?.map((w) => w.symbol).join(",") ?? "";
  const { data: catalysts } = useCatalysts(watchlistSymbolsCsv);

  // Determine if the search input looks like a symbol to add
  const searchUpper = searchFilter.trim().toUpperCase();
  const isValidTicker = /^[A-Z]{1,5}(-[A-Z]{3,4})?$/.test(searchUpper); // AAPL, BTC-USD
  const canAdd = isValidTicker && searchUpper.length >= 1 && !watchlistSymbols.has(searchUpper);

  function handleAddFromSearch() {
    if (!canAdd) return;
    addSymbol.mutate(searchUpper, {
      onSuccess: () => setSearchFilter(""),
    });
  }

  function handleRemoveSymbol(e: React.MouseEvent, symbol: string) {
    e.stopPropagation();
    removeSymbol.mutate(symbol);
  }

  function toggleIndicator(key: string) {
    setActiveIndicators((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const chartIndicators = ALL_INDICATORS
    .filter((ind) => activeIndicators.has(ind.key))
    .map(({ key, color }) => ({ key, color }));

  // Auto-select first signal
  if (!selectedSymbol && signals && signals.length > 0) {
    const entry = signals.find((s) => s.action_label === "Potential Entry");
    setSelectedSymbol(entry?.symbol ?? signals[0].symbol);
  }

  // Prefetch OHLCV for top symbols
  useEffect(() => {
    if (!signals) return;
    const tf = TIMEFRAMES[DEFAULT_TF];
    signals.slice(0, 5).forEach((s) => {
      queryClient.prefetchQuery({
        queryKey: ["ohlcv", s.symbol, tf.period, tf.interval],
        queryFn: () => api.get(`/charts/ohlcv/${s.symbol}?period=${tf.period}&interval=${tf.interval}`),
        staleTime: 15 * 60_000,
      });
    });
  }, [signals, queryClient]);

  // Close indicator popover on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (indicatorPanelRef.current && !indicatorPanelRef.current.contains(e.target as Node)) {
        setShowIndicatorPanel(false);
      }
    }
    if (showIndicatorPanel) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showIndicatorPanel]);

  const selected = signals?.find((s) => s.symbol === selectedSymbol) ?? null;
  const tf = TIMEFRAMES[tfIdx];
  const { data: ohlcv } = useOHLCV(selected?.symbol ?? "", tf.period, tf.interval);

  // Build chart levels
  const chartLevels = (() => {
    if (!selected) return [];
    const s = selected;
    const tradePrices = new Set(
      [s.entry, s.stop, s.target_1].filter((v): v is number => v != null).map((v) => Math.round(v * 100)),
    );
    const isDup = (p: number) => tradePrices.has(Math.round(p * 100));
    const lvls: Array<{ id: number; symbol: string; price: number; label: string; color: string }> = [];
    if (s.ref_day_high != null && !isDup(s.ref_day_high))
      lvls.push({ id: -1, symbol: s.symbol, price: s.ref_day_high, label: "Prior High", color: "#22c55e" });
    if (s.ref_day_low != null && !isDup(s.ref_day_low))
      lvls.push({ id: -2, symbol: s.symbol, price: s.ref_day_low, label: "Prior Low", color: "#ef4444" });
    if (s.nearest_support != null && !isDup(s.nearest_support)) {
      const isBroken = (s.close ?? 0) < s.nearest_support;
      lvls.push({ id: -3, symbol: s.symbol, price: s.nearest_support, label: isBroken ? "Resistance" : "Support", color: isBroken ? "#ef4444" : "#f59e0b" });
    }
    return lvls;
  })();

  // Show all alerts (consolidated feed, not filtered by selected symbol)
  const symbolAlerts = todayAlerts;

  // Filtered and sorted signals for watchlist
  const _gradeOrder: Record<string, number> = { "A+": 0, "A": 1, "A-": 2, "B+": 3, "B": 4, "B-": 5, "C": 6, "C-": 7 };
  const filteredSignals = signals
    ?.filter((s) => !searchFilter || s.symbol.toLowerCase().includes(searchFilter.toLowerCase()))
    ?.sort((a, b) => {
      if (sortMode === "az") return a.symbol.localeCompare(b.symbol);
      // Sort by tradeability score (desc), fallback to grade order
      const aScore = rankMap.get(a.symbol)?.score ?? 0;
      const bScore = rankMap.get(b.symbol)?.score ?? 0;
      if (aScore !== bScore) return bScore - aScore;
      return (_gradeOrder[a.grade] ?? 9) - (_gradeOrder[b.grade] ?? 9);
    });

  // Top pick = highest ranked symbol
  const topPickSymbol = filteredSignals?.[0]?.symbol ?? null;

  const potentialEntryCount = signals?.filter((s) => s.action_label === "Potential Entry").length ?? 0;

  return (
    <div className="flex h-full">
      {/* ── LEFT: Watchlist Panel (collapsible) ── */}
      {showLeftPanel && (
      <aside className="hidden lg:flex w-[240px] bg-surface-1 border-r border-border-subtle flex-col shrink-0">
        {/* Header */}
        <div className="h-14 px-4 flex items-center justify-between border-b border-border-subtle shrink-0">
          <h2 className="text-sm font-semibold tracking-wide text-text-primary">
            Watchlist
            <span className="text-text-faint font-normal ml-1.5 text-xs">{potentialEntryCount} setups</span>
          </h2>
          <div className="flex items-center gap-2">
            {/* Sort toggle */}
            <div className="flex items-center bg-surface-2/50 rounded text-[9px] font-semibold border border-border-subtle overflow-hidden">
              <button
                onClick={() => setSortMode("score")}
                className={`px-2 py-1 transition-colors ${
                  sortMode === "score" ? "bg-accent/15 text-accent" : "text-text-faint hover:text-text-muted"
                }`}
              >
                Score
              </button>
              <button
                onClick={() => setSortMode("az")}
                className={`px-2 py-1 transition-colors ${
                  sortMode === "az" ? "bg-accent/15 text-accent" : "text-text-faint hover:text-text-muted"
                }`}
              >
                A-Z
              </button>
            </div>
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-1 text-xs font-medium text-accent hover:text-accent-hover disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-3 w-3 ${isFetching ? "animate-spin" : ""}`} />
              Scan
            </button>
          </div>
        </div>

        {/* Search — filter existing OR add new symbols */}
        <div className="px-3 py-2.5 border-b border-border-subtle shrink-0">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-text-faint" />
            <input
              type="text"
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setTimeout(() => setSearchFocused(false), 150)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canAdd) handleAddFromSearch();
              }}
              placeholder="Search or add symbol..."
              className="w-full bg-surface-2/50 border border-border-subtle rounded-md py-1.5 pl-8 pr-8 text-xs text-text-primary placeholder:text-text-faint focus:outline-none focus:border-accent/50 transition-colors"
            />
            {searchFilter && (
              <button
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => setSearchFilter("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-faint hover:text-text-muted"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          {/* Add symbol prompt — shown when typing a symbol not in watchlist */}
          {searchFilter && canAdd && searchFocused && (
            <button
              onMouseDown={(e) => e.preventDefault()}
              onClick={handleAddFromSearch}
              disabled={addSymbol.isPending}
              className="mt-1.5 w-full flex items-center gap-2 px-3 py-2 rounded-md bg-accent/10 border border-accent/20 text-xs text-accent hover:bg-accent/20 transition-colors disabled:opacity-50"
            >
              {addSymbol.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Plus className="h-3 w-3" />
              )}
              Add <span className="font-bold">{searchUpper}</span> to watchlist
            </button>
          )}

          {/* Already in watchlist indicator */}
          {searchFilter && isValidTicker && watchlistSymbols.has(searchUpper) && searchFocused && (
            <div className="mt-1.5 flex items-center gap-2 px-3 py-1.5 text-[10px] text-text-faint">
              <span className="h-1.5 w-1.5 rounded-full bg-bullish" />
              {searchUpper} is in your watchlist
            </div>
          )}

          {addSymbol.error && (
            <p className="mt-1 text-[10px] text-bearish-text px-1">
              {addSymbol.error instanceof Error ? addSymbol.error.message : "Failed to add"}
            </p>
          )}
        </div>

        {/* Column headers */}
        <div className="flex px-4 py-1.5 text-[10px] uppercase font-semibold text-text-faint tracking-wider border-b border-border-subtle shrink-0">
          <div className="w-[52px]">Symbol</div>
          <div className="flex-1 text-right">Price</div>
          <div className="w-14 text-center ml-3">{sortMode === "score" ? "Score" : "Grade"}</div>
        </div>

        {/* Signal list */}
        <div className="flex-1 overflow-y-auto">
          {isLoading && <p className="p-4 text-xs text-text-faint">Scanning watchlist...</p>}
          {scanError && !isLoading && (
            <div className="p-4 text-center">
              <p className="text-xs text-bearish-text mb-1">Scan failed</p>
              <button onClick={() => refetch()} className="text-[10px] text-accent hover:text-accent-hover">Retry</button>
            </div>
          )}
          {filteredSignals?.map((s) => (
            <SignalRow
              key={s.symbol}
              signal={s}
              selected={selectedSymbol === s.symbol}
              onClick={() => setSelectedSymbol(s.symbol)}
              onRemove={watchlistSymbols.has(s.symbol) ? (e) => handleRemoveSymbol(e, s.symbol) : undefined}
              livePrice={livePrices[s.symbol]}
              rankItem={rankMap.get(s.symbol)}
              isTopPick={sortMode === "score" && s.symbol === topPickSymbol && (rankMap.get(s.symbol)?.score ?? 0) >= 50}
            />
          ))}
          {filteredSignals && filteredSignals.length === 0 && !isLoading && (
            <p className="p-4 text-xs text-text-faint text-center">No matches</p>
          )}
        </div>

        {/* Watchlist count */}
        <div className="px-4 py-2.5 border-t border-border-subtle shrink-0 flex items-center justify-between">
          <span className="text-[10px] text-text-faint">
            {watchlistItems?.length ?? 0} symbols
          </span>
          {removeSymbol.isPending && (
            <Loader2 className="h-3 w-3 animate-spin text-text-faint" />
          )}
        </div>
      </aside>
      )}

      {/* ── CENTER: Chart Canvas + Cockpit ── */}
      <section className="flex-1 flex flex-col min-w-0 bg-surface-0">
        {/* Chart header */}
        <header className="h-14 border-b border-border-subtle px-4 flex items-center justify-between shrink-0 bg-surface-1/50">
          {/* Left: watchlist toggle + symbol + price */}
          <div className="flex items-center gap-3">
            <button
              onClick={toggleLeftPanel}
              className={`hidden lg:flex w-7 h-7 items-center justify-center rounded transition-colors ${
                showLeftPanel ? "text-text-faint hover:text-text-muted" : "text-accent bg-accent/10"
              }`}
              title={showLeftPanel ? "Hide watchlist" : "Show watchlist"}
            >
              {showLeftPanel ? (
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>
              ) : (
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/><polyline points="14 9 17 12 14 15"/></svg>
              )}
            </button>
            <div className="flex items-baseline gap-3">
            {selected ? (
              <>
                <h1 className="text-2xl font-bold tracking-tight text-text-primary">{selected.symbol}</h1>
                <span className={`text-xl font-mono ${
                  livePrices[selected.symbol]
                    ? (livePrices[selected.symbol].change_pct >= 0 ? "text-bullish-text" : "text-bearish-text")
                    : ((selected.close ?? 0) >= (selected.entry ?? selected.close ?? 0) ? "text-bullish-text" : "text-bearish-text")
                }`}>
                  ${fmt(livePrices[selected.symbol]?.price ?? selected.close)}
                </span>
              </>
            ) : (
              <h1 className="text-lg font-bold text-text-muted">Select a symbol</h1>
            )}
            </div>
          </div>

          {/* Center: timeframes */}
          <div className="hidden sm:flex items-center bg-surface-2/50 p-0.5 rounded-lg border border-border-subtle">
            {TIMEFRAMES.map((t, i) => (
              <span key={t.label} className="flex items-center">
                {/* Subtle separator between intraday (1m-4H) and position (D-M) */}
                {i === 6 && <span className="w-px h-4 bg-border-default mx-0.5 shrink-0" />}
                <button
                  onClick={() => setTfIdx(i)}
                  className={`px-2 py-0.5 text-[11px] font-medium rounded transition-colors ${
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

          {/* Right: indicators popover + right panel toggle */}
          <div className="flex items-center gap-1">
            {/* Indicators popover button */}
            <div className="hidden md:block relative mr-2" ref={indicatorPanelRef}>
              <button
                onClick={() => setShowIndicatorPanel((v) => !v)}
                className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors border ${
                  showIndicatorPanel
                    ? "bg-accent/15 text-accent border-accent/30"
                    : "bg-surface-2/50 text-text-muted border-border-subtle hover:text-text-secondary hover:border-border-default"
                }`}
              >
                <SlidersHorizontal className="h-3.5 w-3.5" />
                Indicators ({activeIndicators.size + (showLevels ? 1 : 0) + (hideWicks ? 0 : 1)})
              </button>

              {/* Active indicator pills */}
              {activeIndicators.size > 0 && !showIndicatorPanel && (
                <div className="absolute top-full left-0 mt-1 flex items-center gap-0.5 flex-wrap max-w-[300px]">
                  {ALL_INDICATORS.filter((ind) => activeIndicators.has(ind.key)).map((ind) => (
                    <span
                      key={ind.key}
                      className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold"
                      style={{ backgroundColor: ind.color + "20", color: ind.color }}
                    >
                      {ind.label}
                    </span>
                  ))}
                </div>
              )}

              {/* Popover panel */}
              {showIndicatorPanel && (
                <div className="absolute top-full right-0 mt-1.5 w-[260px] bg-surface-2 border border-border-default rounded-lg shadow-elevated z-30 p-3 space-y-3">
                  {/* EMAs */}
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-text-faint mb-1.5">EMAs</p>
                    <div className="space-y-1">
                      {ALL_INDICATORS.filter((ind) => ind.group === "ema").map((ind) => (
                        <label key={ind.key} className="flex items-center gap-2 cursor-pointer px-1.5 py-1 rounded hover:bg-surface-3/50 transition-colors">
                          <input
                            type="checkbox"
                            checked={activeIndicators.has(ind.key)}
                            onChange={() => toggleIndicator(ind.key)}
                            className="sr-only"
                          />
                          <span
                            className={`w-3.5 h-3.5 rounded border-2 flex items-center justify-center transition-colors ${
                              activeIndicators.has(ind.key) ? "border-transparent" : "border-border-default"
                            }`}
                            style={{ backgroundColor: activeIndicators.has(ind.key) ? ind.color : "transparent" }}
                          >
                            {activeIndicators.has(ind.key) && (
                              <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 6l3 3 5-5" /></svg>
                            )}
                          </span>
                          <span className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: ind.color }} />
                          <span className="text-xs text-text-secondary">{ind.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* SMAs */}
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-text-faint mb-1.5">SMAs</p>
                    <div className="space-y-1">
                      {ALL_INDICATORS.filter((ind) => ind.group === "sma").map((ind) => (
                        <label key={ind.key} className="flex items-center gap-2 cursor-pointer px-1.5 py-1 rounded hover:bg-surface-3/50 transition-colors">
                          <input
                            type="checkbox"
                            checked={activeIndicators.has(ind.key)}
                            onChange={() => toggleIndicator(ind.key)}
                            className="sr-only"
                          />
                          <span
                            className={`w-3.5 h-3.5 rounded border-2 flex items-center justify-center transition-colors ${
                              activeIndicators.has(ind.key) ? "border-transparent" : "border-border-default"
                            }`}
                            style={{ backgroundColor: activeIndicators.has(ind.key) ? ind.color : "transparent" }}
                          >
                            {activeIndicators.has(ind.key) && (
                              <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 6l3 3 5-5" /></svg>
                            )}
                          </span>
                          <span className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: ind.color }} />
                          <span className="text-xs text-text-secondary">{ind.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Other */}
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-text-faint mb-1.5">Other</p>
                    <div className="space-y-1">
                      {/* VWAP */}
                      {ALL_INDICATORS.filter((ind) => ind.group === "other").map((ind) => (
                        <label key={ind.key} className="flex items-center gap-2 cursor-pointer px-1.5 py-1 rounded hover:bg-surface-3/50 transition-colors">
                          <input
                            type="checkbox"
                            checked={activeIndicators.has(ind.key)}
                            onChange={() => toggleIndicator(ind.key)}
                            className="sr-only"
                          />
                          <span
                            className={`w-3.5 h-3.5 rounded border-2 flex items-center justify-center transition-colors ${
                              activeIndicators.has(ind.key) ? "border-transparent" : "border-border-default"
                            }`}
                            style={{ backgroundColor: activeIndicators.has(ind.key) ? ind.color : "transparent" }}
                          >
                            {activeIndicators.has(ind.key) && (
                              <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 6l3 3 5-5" /></svg>
                            )}
                          </span>
                          <span className="w-2.5 h-0.5 rounded-full" style={{ backgroundColor: ind.color }} />
                          <span className="text-xs text-text-secondary">{ind.label}</span>
                        </label>
                      ))}
                      {/* Levels toggle */}
                      <label className="flex items-center gap-2 cursor-pointer px-1.5 py-1 rounded hover:bg-surface-3/50 transition-colors">
                        <input type="checkbox" checked={showLevels} onChange={() => setShowLevels(!showLevels)} className="sr-only" />
                        <span className={`w-3.5 h-3.5 rounded border-2 flex items-center justify-center transition-colors ${showLevels ? "bg-accent border-transparent" : "border-border-default"}`}>
                          {showLevels && <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 6l3 3 5-5" /></svg>}
                        </span>
                        <span className="text-xs text-text-secondary">Levels</span>
                      </label>
                      {/* Wicks toggle */}
                      <label className="flex items-center gap-2 cursor-pointer px-1.5 py-1 rounded hover:bg-surface-3/50 transition-colors">
                        <input type="checkbox" checked={!hideWicks} onChange={() => setHideWicks(!hideWicks)} className="sr-only" />
                        <span className={`w-3.5 h-3.5 rounded border-2 flex items-center justify-center transition-colors ${!hideWicks ? "bg-accent border-transparent" : "border-border-default"}`}>
                          {!hideWicks && <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"><path d="M2 6l3 3 5-5" /></svg>}
                        </span>
                        <span className="text-xs text-text-secondary">Wicks</span>
                      </label>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Toggle right panel */}
            <button
              onClick={toggleRightPanel}
              className={`hidden xl:flex w-8 h-8 items-center justify-center rounded transition-colors ${
                showRightPanel ? "text-accent bg-accent/10 border border-accent/20" : "text-text-muted hover:text-text-secondary"
              }`}
              title={showRightPanel ? "Hide AI panel" : "Show AI panel"}
            >
              {showRightPanel ? <PanelRightClose className="h-4 w-4" /> : <PanelRightOpen className="h-4 w-4" />}
            </button>
          </div>
        </header>

        {/* Catalyst warning banner */}
        {catalysts && catalysts.length > 0 && (
          <CatalystBanner catalysts={catalysts} onSelectSymbol={setSelectedSymbol} />
        )}

        {/* Mobile: horizontal symbol pills */}
        <div className="flex gap-1.5 overflow-x-auto px-3 py-2 lg:hidden shrink-0 no-scrollbar">
          {signals?.map((s) => (
            <button
              key={s.symbol}
              onClick={() => setSelectedSymbol(s.symbol)}
              className={`shrink-0 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                selectedSymbol === s.symbol
                  ? "bg-accent text-white"
                  : "bg-surface-3 text-text-muted"
              }`}
            >
              {s.symbol}
            </button>
          ))}
        </div>

        {/* Sector Rotation widget */}
        <SectorRotation />

        {/* Chart area */}
        <div className="flex-1 min-h-0 relative chart-grid-bg">
          {selected && ohlcv && ohlcv.length > 0 ? (
            <CandlestickChart
              data={ohlcv}
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
                /* Chart skeleton — shimmer bars */
                <div className="w-full h-full flex flex-col items-center justify-center gap-3 px-8">
                  <div className="flex items-end gap-1 h-32 w-full max-w-md">
                    {Array.from({ length: 30 }).map((_, i) => (
                      <div
                        key={i}
                        className="flex-1 bg-surface-3 rounded-sm animate-pulse"
                        style={{ height: `${20 + Math.sin(i * 0.5) * 40 + Math.random() * 30}%`, animationDelay: `${i * 30}ms` }}
                      />
                    ))}
                  </div>
                  <span className="text-xs text-text-faint">Loading chart...</span>
                </div>
              ) : (
                <div className="text-center">
                  <p className="text-sm text-text-muted">Select a symbol to view analysis</p>
                  <p className="text-xs text-text-faint mt-1">Click any symbol in the watchlist</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Context strip */}
        {selected && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 py-1.5 text-xs text-text-muted border-t border-border-subtle shrink-0 bg-surface-1/30">
            {selected.nearest_support != null && (
              <span>Support: <span className="font-mono text-text-secondary">${fmt(selected.nearest_support)}</span> {selected.support_label && `(${selected.support_label})`}</span>
            )}
            <span>{selected.support_status} · {selected.direction} · {selected.pattern}</span>
            {selected.bias && <span className="italic">{selected.bias}</span>}
          </div>
        )}

        {/* Cockpit trade plan */}
        {selected && <CockpitStrip signal={selected} />}
      </section>

      {/* ── RIGHT: AI Coach + Options Flow + Signal Feed (all collapsible) ── */}
      {showRightPanel && (
        <RightPanel
          selected={selected}
          ohlcv={ohlcv}
          tfLabel={tf.label}
          signals={signals ?? []}
          todayAlerts={todayAlerts}
          alertsError={alertsError}
          symbolAlerts={symbolAlerts}
          onSelectSymbol={setSelectedSymbol}
        />
      )}
    </div>
  );
}
