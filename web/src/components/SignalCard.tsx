/** Expandable signal card — clean collapsed row, expanded shows trade plan + full chart. */

import { useState } from "react";
import type { SignalResult } from "../types";
import { useOHLCV } from "../api/hooks";
import CandlestickChart from "./CandlestickChart";
import Badge from "./ui/Badge";
import { ChevronDown, ChevronUp } from "lucide-react";

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

const DEFAULT_PORTFOLIO = 150_000;

const TIMEFRAMES = [
  { label: "1m",  period: "1d",  interval: "1m" },
  { label: "5m",  period: "5d",  interval: "5m" },
  { label: "10m", period: "5d",  interval: "5m" },
  { label: "15m", period: "5d",  interval: "15m" },
  { label: "30m", period: "5d",  interval: "30m" },
  { label: "1H",  period: "5d",  interval: "60m" },
  { label: "4H",  period: "1mo", interval: "60m" },
  { label: "D",   period: "3mo", interval: "1d" },
  { label: "W",   period: "1y",  interval: "1wk" },
  { label: "M",   period: "5y",  interval: "1mo" },
] as const;

const DEFAULT_TF = 7; // Daily

interface Props {
  signal: SignalResult;
}

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

export default function SignalCard({ signal: s }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [tfIdx, setTfIdx] = useState(DEFAULT_TF);
  const tf = TIMEFRAMES[tfIdx];
  const { data: ohlcv } = useOHLCV(expanded ? s.symbol : "", tf.period, tf.interval);

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
    <div className="overflow-hidden rounded-lg border border-border-subtle bg-surface-2 shadow-card">
      {/* Collapsed row */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-surface-3/50 active:scale-[0.995]"
      >
        <div className="flex items-center gap-3">
          <span className="text-base font-bold text-text-primary">{s.symbol}</span>
          <Badge variant={ACTION_VARIANT[s.action_label] || "neutral"}>
            {s.action_label}
          </Badge>
          <span className={`font-mono text-sm font-bold ${GRADE_COLORS[s.grade] || "text-text-faint"}`}>
            {s.grade} ({s.score})
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="font-mono text-base font-semibold text-text-primary">${fmt(s.close)}</p>
            {s.entry != null && (
              <p className="font-mono text-xs text-text-muted">
                R:R {fmt(s.rr_ratio, 1)}:1
              </p>
            )}
          </div>
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-text-muted" />
          ) : (
            <ChevronDown className="h-4 w-4 text-text-muted" />
          )}
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-border-subtle px-4 py-4 space-y-4">
          {/* Trade Plan — compact row above chart */}
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

          {/* Chart — full width, tall */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">{s.symbol}</h3>
              <div className="flex flex-wrap gap-1">
                {TIMEFRAMES.map((t, i) => (
                  <button
                    key={t.label}
                    onClick={() => setTfIdx(i)}
                    className={`rounded px-1.5 py-0.5 text-[11px] font-medium transition-colors ${
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
                height={500}
              />
            ) : (
              <div className="flex h-[500px] items-center justify-center rounded-lg bg-surface-3 text-sm text-text-faint">
                Loading chart...
              </div>
            )}
          </div>

          {/* Context + Position sizing — single compact row */}
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
      )}
    </div>
  );
}
