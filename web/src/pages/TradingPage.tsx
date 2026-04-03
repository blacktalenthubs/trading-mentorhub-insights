/** Trading — the ONE page traders live on all day.
 *
 *  Left sidebar: Watchlist with signal status + score
 *  Center: Chart with entry/stop/target overlays + trade plan
 *  Bottom: Today's alert stream (real-time)
 */

import { useState, useRef, useEffect } from "react";
import { useScanner, useOHLCV, useAlertsToday, useAckAlert, useDailyAnalysis } from "../api/hooks";
import { useCoachStream } from "../hooks/useCoachStream";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { SignalResult, Alert } from "../types";
import CandlestickChart from "../components/CandlestickChart";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import WatchlistBar from "../components/WatchlistBar";
import { RefreshCw, ChevronDown, ChevronUp, Check, X, Brain, Send, MessageSquare } from "lucide-react";

/* ── constants ────────────────────────────────────────────────────── */

const GRADE_COLORS: Record<string, string> = {
  "A+": "text-bullish-text",
  A: "text-bullish-text",
  B: "text-warning-text",
  C: "text-text-faint",
};

const ACTION_VARIANT: Record<string, "bullish" | "warning" | "bearish" | "neutral"> = {
  "Potential Entry": "bullish",
  Watch: "warning",
  "No Setup": "neutral",
};

const TIMEFRAMES = [
  { label: "1m", period: "1d", interval: "1m" },
  { label: "5m", period: "5d", interval: "5m" },
  { label: "15m", period: "5d", interval: "15m" },
  { label: "30m", period: "5d", interval: "30m" },
  { label: "1H", period: "5d", interval: "60m" },
  { label: "4H", period: "1mo", interval: "60m" },
  { label: "D", period: "3mo", interval: "1d" },
  { label: "W", period: "1y", interval: "1wk" },
  { label: "M", period: "5y", interval: "1mo" },
] as const;

const DEFAULT_TF = 6; // Daily
const DEFAULT_PORTFOLIO = 150_000;

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

/* ── Signal row (watchlist sidebar) ──────────────────────────────── */

function SignalRow({
  signal: s,
  selected,
  onClick,
}: {
  signal: SignalResult;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left transition-colors ${
        selected
          ? "bg-accent/10 border border-accent/30"
          : "hover:bg-surface-3/50 border border-transparent"
      }`}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-sm font-bold text-text-primary">{s.symbol}</span>
        <Badge variant={ACTION_VARIANT[s.action_label] || "neutral"}>
          {s.action_label === "Potential Entry" ? "Entry" : s.action_label}
        </Badge>
      </div>
      <div className="text-right shrink-0">
        <p className="font-mono text-sm font-semibold text-text-primary">${fmt(s.close)}</p>
        <p className={`font-mono text-[10px] font-bold ${GRADE_COLORS[s.grade] || "text-text-faint"}`}>
          {s.grade} · {fmt(s.rr_ratio, 1)}R
        </p>
      </div>
    </button>
  );
}

/* ── Trade plan bar ──────────────────────────────────────────────── */

function TradePlan({ signal: s }: { signal: SignalResult }) {
  const risk = s.risk_per_share ?? (s.entry && s.stop ? s.entry - s.stop : null);
  const shares = risk && risk > 0 ? Math.floor(DEFAULT_PORTFOLIO * 0.01 / risk) : null;

  if (s.entry == null) return null;

  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-7">
      <div className="rounded-md bg-surface-3 p-2 text-center">
        <p className="text-[10px] text-text-faint">Entry</p>
        <p className="font-mono text-sm font-semibold text-bullish-text">${fmt(s.entry)}</p>
      </div>
      <div className="rounded-md bg-surface-3 p-2 text-center">
        <p className="text-[10px] text-text-faint">Stop</p>
        <p className="font-mono text-sm font-semibold text-bearish-text">${fmt(s.stop)}</p>
      </div>
      <div className="rounded-md bg-surface-3 p-2 text-center">
        <p className="text-[10px] text-text-faint">T1</p>
        <p className="font-mono text-sm font-semibold text-info-text">${fmt(s.target_1)}</p>
      </div>
      <div className="rounded-md bg-surface-3 p-2 text-center">
        <p className="text-[10px] text-text-faint">T2</p>
        <p className="font-mono text-sm font-semibold text-info-text">${fmt(s.target_2)}</p>
      </div>
      <div className="rounded-md bg-surface-3 p-2 text-center">
        <p className="text-[10px] text-text-faint">R:R</p>
        <p className="font-mono text-sm font-semibold text-text-primary">{fmt(s.rr_ratio, 1)}:1</p>
      </div>
      <div className="rounded-md bg-surface-3 p-2 text-center">
        <p className="text-[10px] text-text-faint">Risk/sh</p>
        <p className="font-mono text-sm font-semibold text-bearish-text">${fmt(risk)}</p>
      </div>
      <div className="rounded-md bg-surface-3 p-2 text-center">
        <p className="text-[10px] text-text-faint">Shares</p>
        <p className="font-mono text-sm font-semibold text-text-primary">{shares ?? "—"}</p>
      </div>
    </div>
  );
}

/* ── Alert stream item ───────────────────────────────────────────── */

function AlertRow({ alert: a }: { alert: Alert }) {
  const ack = useAckAlert();
  const time = new Date(a.created_at).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const dirColor =
    a.direction === "BUY" ? "text-bullish-text" :
    a.direction === "SHORT" ? "text-bearish-text" :
    a.direction === "SELL" ? "text-warning-text" : "text-text-muted";

  return (
    <div className="flex items-center gap-3 rounded-md bg-surface-3/50 px-3 py-2 text-sm">
      <span className="shrink-0 font-mono text-xs text-text-faint">{time}</span>
      <span className={`shrink-0 font-bold ${dirColor}`}>{a.direction}</span>
      <span className="font-semibold text-text-primary">{a.symbol}</span>
      <span className="min-w-0 flex-1 truncate text-text-muted">
        {a.alert_type.replace(/_/g, " ")}
      </span>
      <span className="shrink-0 font-mono text-text-secondary">${fmt(a.price)}</span>
      {a.user_action == null && (a.direction === "BUY" || a.direction === "SHORT") && (
        <div className="flex shrink-0 gap-1">
          <button
            onClick={() => ack.mutate({ alert_id: a.id, action: "took" })}
            className="rounded bg-bullish/20 p-1 text-bullish-text hover:bg-bullish/30"
            title="Took it"
          >
            <Check className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => ack.mutate({ alert_id: a.id, action: "skipped" })}
            className="rounded bg-surface-4 p-1 text-text-muted hover:bg-surface-3"
            title="Skipped"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      {a.user_action && (
        <Badge variant={a.user_action === "took" ? "bullish" : "neutral"}>
          {a.user_action === "took" ? "Took" : "Skip"}
        </Badge>
      )}
    </div>
  );
}

/* ── Main Trading Page ───────────────────────────────────────────── */

/* ── AI Coach Panel ──────────────────────────────────────────────── */

function AIPanel({ symbol, signal }: { symbol: string | null; signal: SignalResult | null }) {
  const { data: analysis } = useDailyAnalysis(symbol ?? "");
  const { messages, streaming, sendMessage, stopStreaming, clearMessages } = useCoachStream();
  const [input, setInput] = useState("");
  const [lastAutoSymbol, setLastAutoSymbol] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-analyze when symbol changes — send context-aware prompt automatically
  useEffect(() => {
    if (!symbol || symbol === lastAutoSymbol || streaming) return;
    setLastAutoSymbol(symbol);
    clearMessages();

    // Build a rich context prompt from the signal data
    const parts = [`Analyze ${symbol} for me.`];
    if (signal) {
      if (signal.action_label === "Potential Entry") {
        parts.push(`Signal: ${signal.action_label} (score ${signal.score}, grade ${signal.grade}).`);
        if (signal.entry) parts.push(`Entry ${signal.entry}, Stop ${signal.stop}, T1 ${signal.target_1}, T2 ${signal.target_2}.`);
        if (signal.rr_ratio) parts.push(`R:R ${signal.rr_ratio.toFixed(1)}:1.`);
        parts.push("What's the setup quality? Should I take this trade? What's the risk?");
      } else if (signal.action_label === "Watch") {
        parts.push(`Status: Watch (score ${signal.score}). What would make this actionable? What levels to watch?`);
      } else {
        parts.push(`No setup currently. What's the overall picture? When might a setup develop?`);
      }
      if (signal.support_status) parts.push(`Support status: ${signal.support_status}.`);
      if (signal.bias) parts.push(`Bias: ${signal.bias}`);
    }

    sendMessage(parts.join(" "));
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSend() {
    if (!input.trim()) return;
    const prompt = symbol
      ? `[Looking at ${symbol}] ${input.trim()}`
      : input.trim();
    sendMessage(prompt);
    setInput("");
  }

  return (
    <div className="flex h-full flex-col rounded-lg border border-border-subtle bg-surface-2">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-subtle px-3 py-2">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-accent" />
          <span className="text-sm font-semibold text-text-primary">AI Coach</span>
        </div>
        {messages.length > 0 && (
          <button onClick={() => { clearMessages(); setLastAutoSymbol(null); }} className="text-[10px] text-text-faint hover:text-text-muted">
            Clear
          </button>
        )}
      </div>

      {/* Quick prompts */}
      {messages.length === 0 && symbol && (
        <div className="border-b border-border-subtle px-3 py-2 space-y-1">
          <p className="text-[10px] font-semibold uppercase text-text-faint">Ask about {symbol}</p>
          {[
            "What's the best entry strategy here?",
            "Where should I set my stop?",
            "Is this setup high conviction?",
            "What could invalidate this trade?",
          ].map((q) => (
            <button
              key={q}
              onClick={() => { sendMessage(`[Looking at ${symbol}] ${q}`); }}
              className="block w-full rounded-md bg-surface-3/50 px-2 py-1.5 text-left text-xs text-text-muted hover:bg-surface-3 hover:text-text-secondary transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {/* Chat messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {messages.map((m, i) => (
          <div key={i} className={`text-xs leading-relaxed ${m.role === "user" ? "text-accent" : "text-text-secondary"}`}>
            {m.role === "user" ? (
              <p className="font-medium">{m.content}</p>
            ) : (
              <p className="whitespace-pre-wrap">{m.content}</p>
            )}
          </div>
        ))}
        {streaming && (
          <div className="flex items-center gap-1 text-xs text-text-faint">
            <span className="animate-pulse">Thinking...</span>
            <button onClick={stopStreaming} className="text-bearish-text hover:text-bearish text-[10px]">Stop</button>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-border-subtle p-2">
        <div className="flex gap-1.5">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
            placeholder={symbol ? `Ask about ${symbol}...` : "Ask the AI coach..."}
            disabled={streaming}
            className="flex-1 rounded-md border border-border-subtle bg-surface-3 px-2.5 py-1.5 text-xs text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={streaming || !input.trim()}
            className="rounded-md bg-accent px-2.5 py-1.5 text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── Available indicators ─────────────────────────────────────────── */

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

const DEFAULT_INDICATORS = new Set(["ema20", "ema50"]);

export default function TradingPage() {
  const { data: signals, isLoading, refetch, isFetching } = useScanner();
  const { data: todayAlerts } = useAlertsToday();
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [tfIdx, setTfIdx] = useState(DEFAULT_TF);
  const [alertsExpanded, setAlertsExpanded] = useState(false);
  const [activeIndicators, setActiveIndicators] = useState<Set<string>>(DEFAULT_INDICATORS);
  const [showLevels, setShowLevels] = useState(true);
  const [showAI, setShowAI] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);

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

  const queryClient = useQueryClient();

  // Auto-select first symbol or first "Potential Entry" if none selected
  if (!selectedSymbol && signals && signals.length > 0) {
    const entry = signals.find((s) => s.action_label === "Potential Entry");
    setSelectedSymbol(entry?.symbol ?? signals[0].symbol);
  }

  // Prefetch OHLCV for top symbols so chart switching is instant
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

  const selected = signals?.find((s) => s.symbol === selectedSymbol) ?? null;
  const tf = TIMEFRAMES[tfIdx];
  const { data: ohlcv } = useOHLCV(
    selected?.symbol ?? "",
    tf.period,
    tf.interval,
  );

  // Build chart levels for selected symbol
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
    if (s.nearest_support != null && !isDup(s.nearest_support))
      lvls.push({ id: -3, symbol: s.symbol, price: s.nearest_support, label: "Support", color: "#f59e0b" });
    return lvls;
  })();

  // Filter alerts for selected symbol
  const symbolAlerts = todayAlerts?.filter((a) =>
    selected ? a.symbol === selected.symbol : true,
  );

  const potentialEntryCount = signals?.filter((s) => s.action_label === "Potential Entry").length ?? 0;

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col gap-2 md:h-[calc(100vh-3rem)]">
      {/* Top bar: title + refresh + watchlist */}
      <div className="flex items-center justify-between shrink-0">
        <h1 className="font-display text-2xl font-bold">Trading</h1>
        <div className="flex items-center gap-3">
          {signals && (
            <span className="text-xs text-text-muted">
              {potentialEntryCount} setups · {signals.length} symbols
            </span>
          )}
          <button
            onClick={() => setShowAI(!showAI)}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              showAI ? "bg-accent text-white" : "bg-surface-3 text-text-muted hover:text-text-secondary"
            }`}
          >
            <Brain className="h-3.5 w-3.5" />
            AI Coach
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            Scan
          </button>
        </div>
      </div>

      {/* Main content: sidebar + chart */}
      <div className="flex min-h-0 flex-1 gap-2">
        {/* Left: Collapsible Watchlist / Signal list */}
        {showSidebar ? (
          <div className="hidden w-56 shrink-0 flex-col rounded-lg border border-border-subtle bg-surface-2 md:flex">
            <div className="flex items-center justify-between border-b border-border-subtle px-2 py-1.5">
              <WatchlistBar compact />
              <button
                onClick={() => setShowSidebar(false)}
                className="ml-1 rounded p-0.5 text-text-faint hover:text-text-muted"
                title="Collapse watchlist"
              >
                <ChevronDown className="h-3.5 w-3.5 -rotate-90" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-1 space-y-0.5">
              {isLoading && <p className="p-3 text-xs text-text-faint">Scanning...</p>}
              {signals?.map((s) => (
                <SignalRow
                  key={s.symbol}
                  signal={s}
                  selected={selectedSymbol === s.symbol}
                  onClick={() => setSelectedSymbol(s.symbol)}
                />
              ))}
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowSidebar(true)}
            className="hidden shrink-0 items-center rounded-lg border border-border-subtle bg-surface-2 px-1 py-2 text-text-faint hover:text-text-muted md:flex"
            title="Expand watchlist"
          >
            <ChevronDown className="h-4 w-4 rotate-90" />
          </button>
        )}

        {/* Mobile: horizontal symbol pills */}
        <div className="flex gap-1.5 overflow-x-auto pb-1 md:hidden shrink-0">
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

        {/* Center: Chart + Trade Plan */}
        <div className="flex min-w-0 flex-1 flex-col gap-3">
          {selected ? (
            <>
              {/* Symbol header */}
              <div className="flex items-center justify-between shrink-0">
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-bold text-text-primary">{selected.symbol}</h2>
                  <Badge variant={ACTION_VARIANT[selected.action_label] || "neutral"}>
                    {selected.action_label}
                  </Badge>
                  <span className={`font-mono text-sm font-bold ${GRADE_COLORS[selected.grade] || "text-text-faint"}`}>
                    {selected.grade} ({selected.score})
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <p className="font-mono text-xl font-bold text-text-primary">${fmt(selected.close)}</p>
                  {/* Timeframe picker */}
                  <div className="flex gap-0.5">
                    {TIMEFRAMES.map((t, i) => (
                      <button
                        key={t.label}
                        onClick={() => setTfIdx(i)}
                        className={`rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors ${
                          i === tfIdx
                            ? "bg-accent text-white"
                            : "text-text-muted hover:text-text-secondary"
                        }`}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Trade plan */}
              <div className="shrink-0">
                <TradePlan signal={selected} />
              </div>

              {/* Indicator toggles */}
              <div className="flex flex-wrap items-center gap-1.5 shrink-0">
                {/* Levels toggle */}
                <button
                  onClick={() => setShowLevels(!showLevels)}
                  className={`rounded px-2 py-0.5 text-[10px] font-semibold transition-colors ${
                    showLevels ? "bg-accent/20 text-accent" : "bg-surface-4 text-text-faint"
                  }`}
                >
                  Levels
                </button>
                <span className="text-[10px] text-text-faint">|</span>
                {/* EMA toggles */}
                {ALL_INDICATORS.filter((i) => i.group === "ema").map((ind) => (
                  <button
                    key={ind.key}
                    onClick={() => toggleIndicator(ind.key)}
                    className={`rounded px-2 py-0.5 text-[10px] font-semibold transition-colors`}
                    style={{
                      backgroundColor: activeIndicators.has(ind.key) ? ind.color + "30" : undefined,
                      color: activeIndicators.has(ind.key) ? ind.color : "#475569",
                    }}
                  >
                    {ind.label}
                  </button>
                ))}
                <span className="text-[10px] text-text-faint">|</span>
                {/* SMA toggles */}
                {ALL_INDICATORS.filter((i) => i.group === "sma").map((ind) => (
                  <button
                    key={ind.key}
                    onClick={() => toggleIndicator(ind.key)}
                    className="rounded px-2 py-0.5 text-[10px] font-semibold transition-colors"
                    style={{
                      backgroundColor: activeIndicators.has(ind.key) ? ind.color + "30" : undefined,
                      color: activeIndicators.has(ind.key) ? ind.color : "#475569",
                    }}
                  >
                    {ind.label}
                  </button>
                ))}
                <span className="text-[10px] text-text-faint">|</span>
                {/* VWAP */}
                {ALL_INDICATORS.filter((i) => i.group === "other").map((ind) => (
                  <button
                    key={ind.key}
                    onClick={() => toggleIndicator(ind.key)}
                    className="rounded px-2 py-0.5 text-[10px] font-semibold transition-colors"
                    style={{
                      backgroundColor: activeIndicators.has(ind.key) ? ind.color + "30" : undefined,
                      color: activeIndicators.has(ind.key) ? ind.color : "#475569",
                    }}
                  >
                    {ind.label}
                  </button>
                ))}
              </div>

              {/* Chart */}
              <div className="min-h-0 flex-1">
                {ohlcv && ohlcv.length > 0 ? (
                  <CandlestickChart
                    data={ohlcv}
                    entry={showLevels ? (selected.entry ?? undefined) : undefined}
                    stop={showLevels ? (selected.stop ?? undefined) : undefined}
                    target={showLevels ? (selected.target_1 ?? undefined) : undefined}
                    levels={showLevels ? chartLevels : []}
                    indicators={chartIndicators}
                    height={400}
                  />
                ) : (
                  <div className="flex h-full items-center justify-center rounded-lg bg-surface-3 text-sm text-text-faint">
                    Loading chart...
                  </div>
                )}
              </div>

              {/* Context */}
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted shrink-0">
                {selected.nearest_support != null && (
                  <span>Support: <span className="font-mono text-text-secondary">${fmt(selected.nearest_support)}</span> {selected.support_label && `(${selected.support_label})`}</span>
                )}
                <span>{selected.support_status} · {selected.direction} · {selected.pattern}</span>
                {selected.bias && <span className="italic">{selected.bias}</span>}
              </div>
            </>
          ) : (
            <div className="flex flex-1 items-center justify-center text-text-faint">
              <p>Select a symbol to view analysis</p>
            </div>
          )}
        </div>

        {/* Right: AI Coach Panel */}
        {showAI && (
          <div className="hidden w-64 shrink-0 md:block">
            <AIPanel symbol={selected?.symbol ?? null} signal={selected} />
          </div>
        )}
      </div>

      {/* Bottom: Today's Alert Stream */}
      <div className="shrink-0 rounded-lg border border-border-subtle bg-surface-2">
        <button
          onClick={() => setAlertsExpanded(!alertsExpanded)}
          className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium text-text-secondary hover:text-text-primary"
        >
          <span>
            Today's Alerts
            {todayAlerts && (
              <span className="ml-2 text-text-muted">({todayAlerts.length})</span>
            )}
          </span>
          {alertsExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
        </button>
        {alertsExpanded && (
          <div className="max-h-48 overflow-y-auto border-t border-border-subtle px-2 py-1.5 space-y-1">
            {symbolAlerts && symbolAlerts.length > 0 ? (
              symbolAlerts.map((a) => <AlertRow key={a.id} alert={a} />)
            ) : (
              <p className="py-2 text-center text-xs text-text-faint">No alerts yet today</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
