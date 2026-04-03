import { useState } from "react";
import { Link } from "react-router-dom";
import { useScanner, useOHLCV } from "../api/hooks";
import type { SignalResult } from "../types";
import CandlestickChart from "../components/CandlestickChart";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import WatchlistBar from "../components/WatchlistBar";
import { Settings2 } from "lucide-react";

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
  { label: "1m",  period: "1d",  interval: "1m" },
  { label: "5m",  period: "5d",  interval: "5m" },
  { label: "15m", period: "5d",  interval: "15m" },
  { label: "30m", period: "5d",  interval: "30m" },
  { label: "1H",  period: "5d",  interval: "60m" },
  { label: "4H",  period: "1mo", interval: "60m" },
  { label: "D",   period: "3mo", interval: "1d" },
  { label: "W",   period: "1y",  interval: "1wk" },
  { label: "M",   period: "5y",  interval: "1mo" },
] as const;

const DEFAULT_TF = 6; // Daily
const DEFAULT_PORTFOLIO = 150_000;

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

/* ── Signal list item (compact row) ───────────────────────────────── */

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
      <div className="flex items-center gap-2.5 min-w-0">
        <span className="text-sm font-bold text-text-primary">{s.symbol}</span>
        <Badge variant={ACTION_VARIANT[s.action_label] || "neutral"}>
          {s.action_label}
        </Badge>
        <span className={`hidden font-mono text-xs font-bold sm:inline ${GRADE_COLORS[s.grade] || "text-text-faint"}`}>
          {s.grade}
        </span>
      </div>
      <div className="text-right shrink-0">
        <p className="font-mono text-sm font-semibold text-text-primary">${fmt(s.close)}</p>
        {s.rr_ratio != null && (
          <p className="font-mono text-[10px] text-text-muted">{fmt(s.rr_ratio, 1)}:1</p>
        )}
      </div>
    </button>
  );
}

/* ── Detail panel (selected symbol) ───────────────────────────────── */

function SignalDetail({ signal: s }: { signal: SignalResult }) {
  const [tfIdx, setTfIdx] = useState(DEFAULT_TF);
  const tf = TIMEFRAMES[tfIdx];
  const { data: ohlcv } = useOHLCV(s.symbol, tf.period, tf.interval);

  const risk = s.risk_per_share ?? (s.entry && s.stop ? s.entry - s.stop : null);
  const shares = risk && risk > 0 ? Math.floor(DEFAULT_PORTFOLIO * 0.01 / risk) : null;
  const dollarRisk = shares && risk ? shares * risk : null;
  const dollarReward = shares && s.entry != null && s.target_1 != null
    ? shares * (s.target_1 - s.entry)
    : null;

  // Build chart levels — deduplicate against entry/stop/target
  const chartLevels = (() => {
    const tradePrices = new Set(
      [s.entry, s.stop, s.target_1].filter((v): v is number => v != null).map((v) => Math.round(v * 100))
    );
    const isDup = (p: number) => tradePrices.has(Math.round(p * 100));
    const lvls: Array<{ id: number; symbol: string; price: number; label: string; color: string }> = [];
    if (s.ref_day_high != null && !isDup(s.ref_day_high))
      lvls.push({ id: -1, symbol: s.symbol, price: s.ref_day_high, label: "Prior High", color: "#22c55e" });
    if (s.ref_day_low != null && !isDup(s.ref_day_low))
      lvls.push({ id: -2, symbol: s.symbol, price: s.ref_day_low, label: "Prior Low", color: "#ef4444" });
    if (s.nearest_support != null && !isDup(s.nearest_support)
      && (s.ref_day_low == null || Math.round(s.nearest_support * 100) !== Math.round(s.ref_day_low * 100)))
      lvls.push({ id: -3, symbol: s.symbol, price: s.nearest_support, label: "Support", color: "#f59e0b" });
    return lvls;
  })();

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold text-text-primary">{s.symbol}</h2>
          <Badge variant={ACTION_VARIANT[s.action_label] || "neutral"}>
            {s.action_label}
          </Badge>
          <span className={`font-mono text-sm font-bold ${GRADE_COLORS[s.grade] || "text-text-faint"}`}>
            {s.grade} ({s.score})
          </span>
        </div>
        <p className="font-mono text-xl font-bold text-text-primary">${fmt(s.close)}</p>
      </div>

      {/* Trade Plan */}
      {s.entry != null && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
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
            <p className="text-[10px] text-text-faint">Risk</p>
            <p className="font-mono text-sm font-semibold text-bearish-text">${fmt(risk)}</p>
          </div>
        </div>
      )}

      {/* Chart */}
      <div>
        <div className="mb-2 flex items-center justify-end">
          <div className="flex flex-wrap gap-1">
            {TIMEFRAMES.map((t, i) => (
              <button
                key={t.label}
                onClick={() => setTfIdx(i)}
                className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
                  i === tfIdx
                    ? "bg-accent text-white"
                    : "bg-surface-4 text-text-muted hover:text-text-secondary"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
        {ohlcv && ohlcv.length > 0 ? (
          <CandlestickChart
            data={ohlcv}
            entry={s.entry ?? undefined}
            stop={s.stop ?? undefined}
            target={s.target_1 ?? undefined}
            levels={chartLevels}
            height={520}
          />
        ) : (
          <div className="flex h-[520px] items-center justify-center rounded-lg bg-surface-3 text-sm text-text-faint">
            Loading chart...
          </div>
        )}
      </div>

      {/* Context row */}
      <div className="flex flex-wrap items-start gap-x-6 gap-y-2 text-sm">
        {s.nearest_support != null && (
          <span className="text-text-secondary">
            Support: <span className="font-mono font-medium text-text-primary">${fmt(s.nearest_support)}</span>
            {s.support_label && <span className="text-text-muted"> ({s.support_label})</span>}
            {s.distance_pct != null && <span className="text-text-muted"> {fmt(s.distance_pct, 1)}%</span>}
          </span>
        )}
        <span className="text-text-secondary">
          <span className="font-medium text-text-primary">{s.support_status}</span>
          {" · "}
          <span className="font-medium text-text-primary">{s.direction}</span>
          {" · "}
          <span className="font-medium text-text-primary">{s.pattern}</span>
        </span>
        {shares != null && (
          <span className="text-text-secondary">
            <span className="font-mono font-semibold text-text-primary">{shares}</span> shares
            {" · "}
            Risk <span className="font-mono font-semibold text-bearish-text">{dollarRisk != null ? `$${fmt(dollarRisk, 0)}` : "—"}</span>
            {" · "}
            Reward <span className="font-mono font-semibold text-bullish-text">{dollarReward != null ? `$${fmt(dollarReward, 0)}` : "—"}</span>
          </span>
        )}
        {s.bias && <span className="text-text-muted italic">{s.bias}</span>}
      </div>
    </div>
  );
}

/* ── Scanner page ─────────────────────────────────────────────────── */

export default function ScannerPage() {
  const { data: signals, isLoading, refetch, isFetching } = useScanner();
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  const selected = signals?.find((s) => s.symbol === selectedSymbol) ?? null;

  const potentialEntryCount = signals?.filter((s) => s.action_label === "Potential Entry").length ?? 0;
  const avgScore = signals && signals.length > 0
    ? Math.round(signals.reduce((sum, s) => sum + (s.score ?? 0), 0) / signals.length)
    : 0;
  const topGradeCount = signals?.filter((s) => s.grade === "A+" || s.grade === "A").length ?? 0;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Scanner</h1>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50 active:scale-95"
        >
          {isFetching ? "Scanning..." : "Refresh"}
        </button>
      </div>

      {/* Watchlist bar */}
      <Card padding="sm">
        <div className="flex items-center justify-between">
          <div className="min-w-0 flex-1">
            <WatchlistBar compact />
          </div>
          <Link
            to="/watchlist"
            className="ml-3 flex shrink-0 items-center gap-1 rounded-md bg-surface-4 px-2.5 py-1.5 text-xs font-medium text-text-muted transition-colors hover:bg-surface-3 hover:text-text-secondary"
          >
            <Settings2 className="h-3.5 w-3.5" />
            Manage
          </Link>
        </div>
      </Card>

      {/* KPI row */}
      {signals && signals.length > 0 && (
        <div className="grid grid-cols-4 gap-3">
          <Card padding="sm">
            <p className="text-[10px] uppercase text-text-muted">Scanned</p>
            <p className="font-mono text-lg font-bold text-text-primary">{signals.length}</p>
          </Card>
          <Card padding="sm">
            <p className="text-[10px] uppercase text-text-muted">Entries</p>
            <p className="font-mono text-lg font-bold text-bullish-text">{potentialEntryCount}</p>
          </Card>
          <Card padding="sm">
            <p className="text-[10px] uppercase text-text-muted">Avg Score</p>
            <p className="font-mono text-lg font-bold text-info-text">{avgScore}</p>
          </Card>
          <Card padding="sm">
            <p className="text-[10px] uppercase text-text-muted">A+ / A</p>
            <p className="font-mono text-lg font-bold text-info-text">{topGradeCount}</p>
          </Card>
        </div>
      )}

      {isLoading && <p className="text-sm text-text-faint">Loading scanner results...</p>}

      {/* Main content: signal list + detail */}
      {signals && signals.length > 0 && (
        <>
          {/* Signal list — horizontal scroll on mobile, vertical sidebar on desktop */}
          <div className="flex gap-1.5 overflow-x-auto pb-1 md:hidden">
            {signals.map((s) => (
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
                <span className={`ml-1.5 text-xs ${selectedSymbol === s.symbol ? "text-white/70" : GRADE_COLORS[s.grade] || "text-text-faint"}`}>
                  {s.grade}
                </span>
              </button>
            ))}
          </div>

          <div className="flex gap-4">
            {/* Left: signal list (desktop only) */}
            <div className="hidden w-64 shrink-0 space-y-1 rounded-lg border border-border-subtle bg-surface-2 p-2 md:block">
              {signals.map((s) => (
                <SignalRow
                  key={s.symbol}
                  signal={s}
                  selected={selectedSymbol === s.symbol}
                  onClick={() => setSelectedSymbol(s.symbol)}
                />
              ))}
            </div>

            {/* Right: detail panel */}
            <div className="min-w-0 flex-1 rounded-lg border border-border-subtle bg-surface-2 p-3 md:p-4">
              {selected ? (
                <SignalDetail signal={selected} />
              ) : (
                <div className="flex h-48 items-center justify-center text-text-faint md:h-96">
                  <p>Select a symbol to view analysis</p>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {signals && signals.length === 0 && !isLoading && (
        <div className="flex flex-col items-center gap-3 py-12 text-center">
          <p className="text-text-muted">No signals. Add symbols to your watchlist to start scanning.</p>
          <Link
            to="/watchlist"
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover"
          >
            Manage Watchlist
          </Link>
        </div>
      )}
    </div>
  );
}
