/** Sector Rotation — compact collapsible widget showing sector ETF flows.
 *
 *  Collapsed: horizontal grid of 11 sectors with 1d change, color-coded.
 *  Expanded: table with 5d/20d details.
 */

import { useState } from "react";
import { ChevronDown, ChevronUp, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { useSectorRotation } from "../api/hooks";
import type { SectorRotationItem } from "../api/hooks";

const FLOW_CONFIG = {
  INFLOW: { icon: TrendingUp, color: "text-bullish-text", bg: "bg-bullish/10", border: "border-bullish/20" },
  OUTFLOW: { icon: TrendingDown, color: "text-bearish-text", bg: "bg-bearish/10", border: "border-bearish/20" },
  NEUTRAL: { icon: Minus, color: "text-text-muted", bg: "bg-surface-3", border: "border-border-subtle" },
} as const;

function MomentumArrow({ value }: { value: number }) {
  if (value > 0.3) return <TrendingUp className="h-2.5 w-2.5 text-bullish-text" />;
  if (value < -0.3) return <TrendingDown className="h-2.5 w-2.5 text-bearish-text" />;
  return <Minus className="h-2.5 w-2.5 text-text-faint" />;
}

function SectorTile({ sector }: { sector: SectorRotationItem }) {
  const cfg = FLOW_CONFIG[sector.flow];
  return (
    <div className={`flex flex-col items-center gap-0.5 px-2 py-1.5 rounded-md border ${cfg.bg} ${cfg.border} transition-colors`}>
      <span className="text-[9px] font-semibold text-text-secondary truncate w-full text-center">
        {sector.name}
      </span>
      <div className="flex items-center gap-1">
        <span className={`text-xs font-mono font-bold ${cfg.color}`}>
          {sector.change_1d >= 0 ? "+" : ""}{sector.change_1d.toFixed(1)}%
        </span>
        <MomentumArrow value={sector.change_5d} />
      </div>
    </div>
  );
}

export default function SectorRotation() {
  const [expanded, setExpanded] = useState(false);
  const { data: sectors, isLoading, error } = useSectorRotation();

  if (isLoading) {
    return (
      <div className="px-4 py-2 border-b border-border-subtle bg-surface-1/30">
        <div className="flex items-center gap-2">
          <div className="h-3 w-20 bg-surface-3 rounded animate-pulse" />
          <div className="flex-1 flex gap-1.5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-10 w-16 bg-surface-3 rounded animate-pulse" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (error || !sectors || sectors.length === 0) return null;

  const inflows = sectors.filter((s) => s.flow === "INFLOW").length;
  const outflows = sectors.filter((s) => s.flow === "OUTFLOW").length;

  return (
    <div className="border-b border-border-subtle bg-surface-1/30">
      {/* Header + toggle */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-1.5 flex items-center justify-between hover:bg-surface-2/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-text-faint">
            Sectors
          </span>
          <span className="text-[9px] font-mono text-bullish-text bg-bullish/10 px-1.5 py-0.5 rounded">
            {inflows} in
          </span>
          <span className="text-[9px] font-mono text-bearish-text bg-bearish/10 px-1.5 py-0.5 rounded">
            {outflows} out
          </span>
        </div>
        {expanded ? (
          <ChevronUp className="h-3.5 w-3.5 text-text-faint" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 text-text-faint" />
        )}
      </button>

      {/* Collapsed: compact tile grid */}
      {!expanded && (
        <div className="px-4 pb-2 flex gap-1.5 overflow-x-auto no-scrollbar">
          {sectors.map((s) => (
            <SectorTile key={s.symbol} sector={s} />
          ))}
        </div>
      )}

      {/* Expanded: detailed table */}
      {expanded && (
        <div className="px-4 pb-3">
          <div className="rounded-lg border border-border-subtle overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-surface-2/50 text-text-faint text-[10px] uppercase tracking-wider">
                  <th className="text-left px-3 py-1.5 font-semibold">Sector</th>
                  <th className="text-right px-2 py-1.5 font-semibold">Price</th>
                  <th className="text-right px-2 py-1.5 font-semibold">1D</th>
                  <th className="text-right px-2 py-1.5 font-semibold">5D</th>
                  <th className="text-right px-2 py-1.5 font-semibold">20D</th>
                  <th className="text-center px-2 py-1.5 font-semibold">Flow</th>
                </tr>
              </thead>
              <tbody>
                {sectors.map((s) => {
                  const cfg = FLOW_CONFIG[s.flow];
                  const FlowIcon = cfg.icon;
                  return (
                    <tr key={s.symbol} className="border-t border-border-subtle/50 hover:bg-surface-2/30 transition-colors">
                      <td className="px-3 py-1.5">
                        <div className="flex flex-col">
                          <span className="font-semibold text-text-primary">{s.name}</span>
                          <span className="text-[10px] text-text-faint">{s.symbol}</span>
                        </div>
                      </td>
                      <td className="text-right px-2 py-1.5 font-mono text-text-secondary">
                        ${s.price.toFixed(2)}
                      </td>
                      <td className={`text-right px-2 py-1.5 font-mono font-bold ${s.change_1d >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                        {s.change_1d >= 0 ? "+" : ""}{s.change_1d.toFixed(2)}%
                      </td>
                      <td className={`text-right px-2 py-1.5 font-mono ${s.change_5d >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                        {s.change_5d >= 0 ? "+" : ""}{s.change_5d.toFixed(2)}%
                      </td>
                      <td className={`text-right px-2 py-1.5 font-mono ${s.change_20d >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                        {s.change_20d >= 0 ? "+" : ""}{s.change_20d.toFixed(2)}%
                      </td>
                      <td className="text-center px-2 py-1.5">
                        <span className={`inline-flex items-center gap-1 text-[9px] font-bold px-1.5 py-0.5 rounded ${cfg.bg} ${cfg.color} border ${cfg.border}`}>
                          <FlowIcon className="h-2.5 w-2.5" />
                          {s.flow}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
