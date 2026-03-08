/** Expandable signal card — collapsed shows key info, expanded shows full trade plan + chart. */

import { useState } from "react";
import type { SignalResult } from "../types";
import { useOHLCV } from "../api/hooks";
import CandlestickChart from "./CandlestickChart";

const GRADE_COLORS: Record<string, string> = {
  "A+": "text-green-400",
  A: "text-green-400",
  B: "text-yellow-400",
  C: "text-gray-500",
};

const ACTION_COLORS: Record<string, string> = {
  "Potential Entry": "bg-green-900 text-green-300",
  "Watch": "bg-yellow-900 text-yellow-300",
  "No Setup": "bg-red-900 text-red-300",
};

const PATTERN_COLORS: Record<string, string> = {
  inside: "bg-purple-900 text-purple-300",
  outside: "bg-orange-900 text-orange-300",
  normal: "bg-gray-800 text-gray-400",
};

const DEFAULT_PORTFOLIO = 150_000;

interface Props {
  signal: SignalResult;
}

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

export default function SignalCard({ signal: s }: Props) {
  const [expanded, setExpanded] = useState(false);
  const { data: ohlcv } = useOHLCV(expanded ? s.symbol : "", "1mo");

  const risk = s.risk_per_share ?? (s.entry && s.stop ? s.entry - s.stop : null);
  const shares = risk && risk > 0 ? Math.floor(DEFAULT_PORTFOLIO * 0.01 / risk) : null;
  const dollarRisk = shares && risk ? shares * risk : null;
  const dollarReward = shares && s.entry != null && s.target_1 != null
    ? shares * (s.target_1 - s.entry)
    : null;

  const maAboveBelow = (label: string, ma: number | null) => {
    if (ma == null || s.close == null) return null;
    return `${label}: $${fmt(ma)} (${s.close >= ma ? "above" : "below"})`;
  };

  return (
    <div className="rounded-lg bg-gray-900 overflow-hidden">
      {/* Collapsed row */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 text-left hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-lg font-bold">{s.symbol}</span>
            <span
              className={`rounded px-2 py-0.5 text-xs font-bold ${
                ACTION_COLORS[s.action_label] || "bg-gray-800 text-gray-400"
              }`}
            >
              {s.action_label}
            </span>
            <span className={`text-sm font-bold ${GRADE_COLORS[s.grade] || "text-gray-400"}`}>
              {s.grade} ({s.score})
            </span>
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                PATTERN_COLORS[s.pattern] || "bg-gray-800 text-gray-400"
              }`}
            >
              {s.pattern}
            </span>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-lg font-medium">${fmt(s.close)}</p>
              {s.entry != null && (
                <p className="text-xs text-gray-500">
                  E: ${fmt(s.entry)} / S: ${fmt(s.stop)} / T1: ${fmt(s.target_1)} / R:R {fmt(s.rr_ratio, 1)}:1
                </p>
              )}
            </div>
            <span className="text-gray-500 text-sm">{expanded ? "▲" : "▼"}</span>
          </div>
        </div>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-gray-800 px-4 py-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Left column: Trade Plan + Support + Position Sizing + MA */}
            <div className="space-y-4">
              {/* Trade Plan */}
              <div>
                <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Trade Plan</h3>
                <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
                  <div>
                    <span className="text-gray-500">Entry </span>
                    <span className="font-medium text-green-400">${fmt(s.entry)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Stop </span>
                    <span className="font-medium text-red-400">${fmt(s.stop)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">T1 </span>
                    <span className="font-medium text-blue-400">${fmt(s.target_1)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">T2 </span>
                    <span className="font-medium text-blue-300">${fmt(s.target_2)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Re-entry Stop </span>
                    <span className="font-medium text-red-300">${fmt(s.reentry_stop)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">R:R </span>
                    <span className="font-medium">{fmt(s.rr_ratio, 1)}:1</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Risk/Share </span>
                    <span className="font-medium text-red-400">${fmt(risk)}</span>
                  </div>
                </div>
              </div>

              {/* Support & Context */}
              <div>
                <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">Support & Context</h3>
                <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
                  <div>
                    <span className="text-gray-500">Nearest Support </span>
                    <span className="font-medium">${fmt(s.nearest_support)}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Label </span>
                    <span className="font-medium">{s.support_label || "—"}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Distance </span>
                    <span className="font-medium">{fmt(s.distance_pct, 1)}%</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Status </span>
                    <span className="font-medium">{s.support_status}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Pattern </span>
                    <span className="font-medium">{s.pattern}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Direction </span>
                    <span className="font-medium">{s.direction}</span>
                  </div>
                </div>
                {s.bias && (
                  <p className="mt-2 text-sm text-gray-400 italic">{s.bias}</p>
                )}
              </div>

              {/* Position Sizing */}
              <div>
                <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
                  Position Sizing <span className="text-gray-600 normal-case">(${(DEFAULT_PORTFOLIO / 1000).toFixed(0)}k portfolio)</span>
                </h3>
                <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
                  <div>
                    <span className="text-gray-500">Shares </span>
                    <span className="font-medium">{shares ?? "—"}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">$ Risk </span>
                    <span className="font-medium text-red-400">{dollarRisk != null ? `$${fmt(dollarRisk, 0)}` : "—"}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">$ Reward </span>
                    <span className="font-medium text-green-400">{dollarReward != null ? `$${fmt(dollarReward, 0)}` : "—"}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Day Range </span>
                    <span className="font-medium">${fmt(s.day_range)}</span>
                  </div>
                </div>
              </div>

              {/* MA Context */}
              <div>
                <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">MA Context</h3>
                <p className="text-sm text-gray-300">
                  Close: ${fmt(s.close)}
                  {" | "}
                  {maAboveBelow("MA20", s.ma20) ?? "MA20: —"}
                  {" | "}
                  {maAboveBelow("MA50", s.ma50) ?? "MA50: —"}
                  {" | "}
                  Vol: {fmt(s.volume_ratio, 1)}x avg
                </p>
              </div>
            </div>

            {/* Right column: Mini Chart */}
            <div>
              <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">30-Day Chart</h3>
              {ohlcv && ohlcv.length > 0 ? (
                <CandlestickChart
                  data={ohlcv}
                  entry={s.entry ?? undefined}
                  stop={s.stop ?? undefined}
                  target={s.target_1 ?? undefined}
                  levels={
                    s.nearest_support != null
                      ? [{ id: 0, symbol: s.symbol, price: s.nearest_support, label: s.support_label || "Support", color: "#f59e0b" }]
                      : []
                  }
                  height={280}
                />
              ) : (
                <div className="flex h-[280px] items-center justify-center rounded-lg bg-gray-950 text-sm text-gray-600">
                  Loading chart...
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
