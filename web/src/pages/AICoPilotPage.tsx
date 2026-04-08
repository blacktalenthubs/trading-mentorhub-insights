/** AI CoPilot — chart analysis with structured trade plans. */

import { useState, useCallback, useRef } from "react";
import { Capacitor } from "@capacitor/core";
import { useAuthStore } from "../stores/auth";
import { useWatchlist, useOHLCV, useLivePrices } from "../api/hooks";
import type { OHLCBar } from "../api/hooks";
import CandlestickChart from "../components/CandlestickChart";
import TradePlanCard, { type TradePlan } from "../components/ai/TradePlanCard";
import AnalysisHistory from "../components/ai/AnalysisHistory";
import { Brain, Loader2, StopCircle, TrendingUp, TrendingDown } from "lucide-react";

const API_HOST = Capacitor.isNativePlatform()
  ? String(import.meta.env.VITE_API_URL || "https://api.aicopilottrader.com")
  : "";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1H", "4H", "D", "W"] as const;

const TF_MAP: Record<string, { period: string; interval: string }> = {
  "1m": { period: "1d", interval: "1m" },
  "5m": { period: "5d", interval: "5m" },
  "15m": { period: "5d", interval: "15m" },
  "30m": { period: "5d", interval: "30m" },
  "1H": { period: "5d", interval: "60m" },
  "4H": { period: "1mo", interval: "60m" },
  "D": { period: "1y", interval: "1d" },
  "W": { period: "2y", interval: "1wk" },
};

/* ── Helpers ──────────────────────────────────────────────────────── */

function parsePlanFromText(text: string): TradePlan | null {
  const clean = text.replace(/\*\*/g, "");
  const getField = (name: string): string | null => {
    const re = new RegExp(`${name}:\\s*(.+?)(?:\\n|$)`, "i");
    const m = clean.match(re);
    return m ? m[1].trim() : null;
  };
  const getNum = (name: string): number | null => {
    const v = getField(name);
    if (!v || v.toUpperCase() === "N/A") return null;
    const n = parseFloat(v.replace(/[$,]/g, ""));
    return isNaN(n) ? null : n;
  };
  const direction = getField("DIRECTION");
  if (!direction) return null;
  return {
    setup: getField("SETUP") ?? null,
    direction: direction.toUpperCase().replace(/\s+/g, "_"),
    entry: getNum("ENTRY"),
    stop: getNum("STOP"),
    target_1: getNum("TARGET_1"),
    target_2: getNum("TARGET_2"),
    rr_ratio: getNum("RR_RATIO"),
    confidence: (() => {
      const v = getField("CONFIDENCE");
      if (!v || v.toUpperCase() === "N/A") return null;
      return v.toUpperCase().replace(/[^A-Z]/g, "");
    })(),
    confluence_score: (() => {
      const v = getField("CONFLUENCE_SCORE");
      if (!v) return null;
      const n = parseInt(v);
      return isNaN(n) ? null : Math.min(10, Math.max(0, n));
    })(),
    timeframe_fit: getField("TIMEFRAME_FIT"),
    key_levels: (() => {
      const v = getField("KEY_LEVELS");
      if (!v || v.toUpperCase() === "N/A") return [];
      return v.split(",").map((s) => s.trim()).filter(Boolean);
    })(),
    historical_ref: null,
  };
}

function extractReasoning(text: string): { reasoning: string; higherTf: string } {
  const clean = text.replace(/\*\*/g, "");
  const rMatch = clean.match(/REASONING:\s*\n?([\s\S]*?)(?=HIGHER_TF|$)/i);
  let reasoning = rMatch?.[1]?.replace(/---+/g, "").trim() || "";
  const hMatch = clean.match(/HIGHER_TF_SUMMARY:\s*\n?([\s\S]*?)$/i);
  const higherTf = hMatch?.[1]?.replace(/---+/g, "").trim() || "";
  return { reasoning, higherTf };
}

function cleanText(text: string): string {
  return text.replace(/\*\*/g, "").replace(/^#{1,3}\s+/gm, "").replace(/^---+$/gm, "").replace(/\n{3,}/g, "\n\n").trim();
}

/* ── Symbol Picker Button ─────────────────────────────────────────── */

function SymbolPicker({
  symbols,
  active,
  prices,
  onSelect,
}: {
  symbols: string[];
  active: string;
  prices: Record<string, { price: number; change_pct: number }>;
  onSelect: (s: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 bg-surface-3 border border-border-subtle rounded-lg px-3 py-1.5 hover:border-accent/50 transition-colors"
      >
        <span className="text-sm font-bold text-text-primary">{active || "Select"}</span>
        {prices[active] && (
          <span className={`text-xs font-mono ${prices[active].change_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
            ${prices[active].price.toFixed(2)}
            <span className="ml-1 text-[10px]">
              {prices[active].change_pct >= 0 ? "+" : ""}{prices[active].change_pct.toFixed(1)}%
            </span>
          </span>
        )}
        <svg className={`h-3 w-3 text-text-faint transition-transform ${open ? "rotate-180" : ""}`} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 5l3 3 3-3" /></svg>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute top-full left-0 mt-1 z-50 w-56 max-h-64 overflow-y-auto rounded-lg border border-border-subtle bg-surface-2 shadow-xl">
            {symbols.length === 0 ? (
              <div className="px-3 py-4 text-xs text-text-faint text-center">
                Add symbols in Settings → Watchlist
              </div>
            ) : (
              symbols.map((s) => {
                const p = prices[s];
                const isActive = s === active;
                return (
                  <button
                    key={s}
                    onClick={() => { onSelect(s); setOpen(false); }}
                    className={`w-full flex items-center justify-between px-3 py-2 text-left hover:bg-surface-3/60 transition-colors ${isActive ? "bg-accent/10" : ""}`}
                  >
                    <span className={`text-sm font-semibold ${isActive ? "text-accent" : "text-text-primary"}`}>{s}</span>
                    {p && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-mono text-text-secondary">${p.price.toFixed(2)}</span>
                        <span className={`flex items-center text-[10px] font-semibold ${p.change_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                          {p.change_pct >= 0 ? <TrendingUp className="h-2.5 w-2.5 mr-0.5" /> : <TrendingDown className="h-2.5 w-2.5 mr-0.5" />}
                          {p.change_pct >= 0 ? "+" : ""}{p.change_pct.toFixed(1)}%
                        </span>
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ── Main Page ────────────────────────────────────────────────────── */

export default function AICoPilotPage() {
  const { data: watchlist } = useWatchlist();
  const { data: pricesData } = useLivePrices();
  const prices = pricesData?.prices ?? {};
  const symbols = watchlist?.map((w) => w.symbol) ?? [];

  const [selectedSymbol, setSelectedSymbol] = useState("");
  const [timeframe, setTimeframe] = useState("15m");

  const tf = TF_MAP[timeframe] ?? TF_MAP["15m"];
  const activeSymbol = selectedSymbol || symbols[0] || "";
  const { data: ohlcv, isLoading: chartLoading } = useOHLCV(activeSymbol, tf.period, tf.interval);

  const [plan, setPlan] = useState<TradePlan | null>(null);
  const [reasoning, setReasoning] = useState("");
  const [higherTfSummary, setHigherTfSummary] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [remaining, setRemaining] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  if (!selectedSymbol && symbols.length > 0) {
    setSelectedSymbol(symbols[0]);
  }

  const analyzeChart = useCallback(async () => {
    const token = useAuthStore.getState().accessToken;
    if (!token || !activeSymbol) return;

    setPlan(null);
    setReasoning("");
    setHigherTfSummary("");
    setError("");
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;
    const lastBars: OHLCBar[] = ohlcv?.slice(-60) ?? [];

    try {
      const res = await fetch(`${API_HOST}/api/v1/intel/analyze-chart`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          symbol: activeSymbol,
          timeframe,
          ohlcv_bars: lastBars.map((b) => ({ timestamp: b.timestamp, open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume })),
        }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (res.status === 429) throw new Error("Daily analysis limit reached. Upgrade for more.");
        throw new Error(typeof err.detail === "string" ? err.detail : "Analysis request failed");
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let fullText = "";
      let currentEvent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (line.startsWith("event:")) { currentEvent = line.slice(6).trim(); continue; }
          if (!line.startsWith("data:")) continue;
          const dataStr = line.slice(5).trim();
          if (!dataStr) continue;
          try {
            const parsed = JSON.parse(dataStr);
            if (currentEvent === "plan" || parsed.event === "plan") {
              const d = parsed.data || parsed;
              setPlan({ setup: d.setup ?? null, direction: d.direction ?? null, entry: d.entry ?? null, stop: d.stop ?? null, target_1: d.target_1 ?? null, target_2: d.target_2 ?? null, rr_ratio: d.rr_ratio ?? null, confidence: d.confidence ?? null, confluence_score: d.confluence_score ?? null, timeframe_fit: d.timeframe_fit ?? null, key_levels: d.key_levels ?? [], historical_ref: d.historical_ref ?? null });
            } else if (currentEvent === "reasoning" || parsed.event === "reasoning") {
              setReasoning(parsed.data?.text || parsed.text || "");
            } else if (currentEvent === "higher_tf" || parsed.event === "higher_tf") {
              setHigherTfSummary(parsed.data?.text || parsed.text || "");
            } else if (currentEvent === "done" || parsed.event === "done") {
              const r = parsed.data?.remaining ?? parsed.remaining;
              if (r != null) setRemaining(r);
            } else if (currentEvent === "chunk" || parsed.text) {
              fullText += parsed.text || "";
              const livePlan = parsePlanFromText(fullText);
              if (livePlan) setPlan(livePlan);
              const { reasoning: r, higherTf: h } = extractReasoning(fullText);
              if (r) setReasoning(r);
              if (h) setHigherTfSummary(h);
            }
          } catch { /* skip */ }
          currentEvent = "";
        }
      }
      if (fullText && !plan) {
        const finalPlan = parsePlanFromText(fullText);
        if (finalPlan) setPlan(finalPlan);
        const { reasoning: r, higherTf: h } = extractReasoning(fullText);
        if (r) setReasoning(r);
        if (h) setHigherTfSummary(h);
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") setError((err as Error).message);
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }, [activeSymbol, timeframe, ohlcv]);

  return (
    <div className="h-full overflow-y-auto p-4 md:p-5">
      <div className="max-w-6xl mx-auto space-y-4">
        {/* ── Controls bar ── */}
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border-subtle bg-surface-1 px-3 py-2.5">
          <Brain className="h-5 w-5 text-accent shrink-0" />
          <span className="font-display text-sm font-bold text-text-primary">AI CoPilot</span>

          <SymbolPicker symbols={symbols} active={activeSymbol} prices={prices} onSelect={setSelectedSymbol} />

          <div className="flex gap-0.5 bg-surface-3/50 rounded-lg p-0.5">
            {TIMEFRAMES.map((t) => (
              <button
                key={t}
                onClick={() => setTimeframe(t)}
                className={`px-2.5 py-1 text-[11px] font-semibold rounded-md transition-all ${
                  timeframe === t
                    ? "bg-accent text-white shadow-sm"
                    : "text-text-muted hover:text-text-primary"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <div className="flex-1" />

          {remaining != null && (
            <span className="text-[10px] text-text-faint">{remaining} left today</span>
          )}

          {streaming ? (
            <button onClick={() => abortRef.current?.abort()} className="flex items-center gap-1.5 bg-bearish/10 hover:bg-bearish/20 border border-bearish/20 text-bearish-text font-semibold text-xs px-3 py-1.5 rounded-lg transition-colors">
              <StopCircle className="h-3.5 w-3.5" /> Stop
            </button>
          ) : (
            <button onClick={analyzeChart} disabled={!activeSymbol || chartLoading} className="flex items-center gap-1.5 bg-accent hover:bg-accent-hover text-white font-semibold text-xs px-4 py-1.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-glow-accent">
              <Brain className="h-3.5 w-3.5" /> Analyze
            </button>
          )}
        </div>

        {/* ── Chart ── */}
        <div className="rounded-xl border border-border-subtle bg-surface-1 p-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-semibold text-text-primary">
              {activeSymbol} <span className="text-text-faint">{timeframe}</span>
            </span>
            {chartLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-text-muted" />}
          </div>
          {ohlcv && ohlcv.length > 0 ? (
            <CandlestickChart data={ohlcv} height={420} entry={plan?.entry ?? undefined} stop={plan?.stop ?? undefined} target={plan?.target_1 ?? undefined} />
          ) : !chartLoading ? (
            <div className="flex items-center justify-center h-[400px] text-xs text-text-faint">
              {activeSymbol ? "No chart data" : "Select a symbol"}
            </div>
          ) : (
            <div className="flex items-center justify-center h-[400px]">
              <Loader2 className="h-5 w-5 animate-spin text-accent" />
            </div>
          )}
        </div>

        {/* ── Loading state ── */}
        {streaming && !plan && !reasoning && (
          <div className="rounded-xl border border-accent/20 bg-accent/5 p-4 flex items-center gap-3">
            <Loader2 className="h-5 w-5 animate-spin text-accent shrink-0" />
            <div>
              <p className="text-sm font-semibold text-text-primary">Analyzing {activeSymbol} on {timeframe}...</p>
              <p className="text-xs text-text-muted">Checking setups, levels, and multi-timeframe alignment</p>
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-bearish/20 bg-bearish/5 p-4">
            <p className="text-sm text-bearish-text">{error}</p>
          </div>
        )}

        {/* ── Results: Plan card + Analysis text ── */}
        {plan && (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
            <div className="lg:col-span-2">
              <TradePlanCard plan={plan} />
            </div>
            <div className="lg:col-span-3 rounded-xl border border-border-subtle bg-surface-1 p-5 space-y-4">
              <h3 className="text-sm font-semibold text-text-primary flex items-center gap-1.5">
                <Brain className="h-4 w-4 text-accent" />
                AI Analysis
                {streaming && <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />}
              </h3>
              {reasoning ? (
                <p className="text-[13px] text-text-secondary leading-relaxed whitespace-pre-line">{cleanText(reasoning)}</p>
              ) : streaming ? (
                <p className="text-sm text-text-muted italic">Generating analysis...</p>
              ) : (
                <p className="text-sm text-text-muted italic">No reasoning available.</p>
              )}
              {higherTfSummary && (
                <div className="border-t border-border-subtle/50 pt-3">
                  <h4 className="text-[10px] font-bold text-text-faint uppercase tracking-wider mb-1.5">Higher Timeframes</h4>
                  <p className="text-[13px] text-text-secondary leading-relaxed">{cleanText(higherTfSummary)}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Streaming preview (before plan parsed) ── */}
        {streaming && !plan && reasoning && (
          <div className="rounded-xl border border-accent/20 bg-surface-1 p-5">
            <h3 className="text-sm font-semibold text-text-primary flex items-center gap-1.5 mb-2">
              <Brain className="h-4 w-4 text-accent" />
              Analyzing...
              <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
            </h3>
            <p className="text-[13px] text-text-secondary leading-relaxed">{cleanText(reasoning)}</p>
          </div>
        )}

        {/* ── History ── */}
        <AnalysisHistory />
      </div>
    </div>
  );
}
