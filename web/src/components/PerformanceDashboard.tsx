import { usePerformanceByStrategy, usePerformanceSummary } from "../api/hooks";
import type { StrategyPerformance } from "../api/hooks";

function WinRateBar({ rate }: { rate: number }) {
  const color = rate >= 60 ? "bg-bullish" : rate >= 40 ? "bg-warning" : "bg-bearish";
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1.5 bg-surface-3 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(rate, 100)}%` }} />
      </div>
      <span className={`text-[10px] font-bold tabular-nums ${
        rate >= 60 ? "text-bullish-text" : rate >= 40 ? "text-warning-text" : "text-bearish-text"
      }`}>
        {rate}%
      </span>
    </div>
  );
}

function StrategyRow({ strategy: s }: { strategy: StrategyPerformance }) {
  const _resolved = s.wins + s.losses; void _resolved;
  return (
    <div className="flex items-center gap-3 px-3 py-2 hover:bg-surface-2/30 transition-colors rounded-lg">
      <div className="flex-1 min-w-0">
        <div className="text-xs font-medium text-text-primary truncate">
          {s.alert_type.replace(/_/g, " ")}
        </div>
        <div className="text-[10px] text-text-faint mt-0.5">
          {s.total} alerts · {s.wins}W / {s.losses}L{s.no_outcome > 0 ? ` / ${s.no_outcome} pending` : ""}
        </div>
      </div>
      <div className="w-24 shrink-0">
        <WinRateBar rate={s.win_rate} />
      </div>
      <div className="w-10 text-center shrink-0">
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
          s.avg_score >= 70 ? "bg-bullish/15 text-bullish-text border-bullish/25"
            : s.avg_score >= 40 ? "bg-warning/15 text-warning-text border-warning/25"
            : "bg-surface-3 text-text-faint border-border-subtle"
        }`}>
          {s.avg_score}
        </span>
      </div>
    </div>
  );
}

export default function PerformanceDashboard() {
  const { data: strategies, isLoading: stratLoading } = usePerformanceByStrategy();
  const { data: summary, isLoading: sumLoading } = usePerformanceSummary();

  return (
    <div className="space-y-4">
      {/* Summary stats */}
      {summary && !sumLoading && (
        <div className="grid grid-cols-4 gap-3">
          {[
            { label: "Total Alerts", value: summary.total_alerts },
            { label: "T1 Hits", value: summary.t1_hits },
            { label: "Stopped", value: summary.stops },
            { label: "Trading Days", value: summary.trading_days },
          ].map((s) => (
            <div key={s.label} className="bg-surface-2/50 rounded-lg px-3 py-2 border border-border-subtle">
              <div className="text-lg font-bold text-text-primary tabular-nums">{s.value}</div>
              <div className="text-[10px] text-text-faint uppercase tracking-wider">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Strategy breakdown */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-text-primary">Win Rate by Strategy</h3>
          <span className="text-[10px] text-text-faint">min 2 alerts to appear</span>
        </div>

        {/* Header */}
        <div className="flex items-center gap-3 px-3 py-1 text-[9px] uppercase font-semibold text-text-faint tracking-wider">
          <div className="flex-1">Strategy</div>
          <div className="w-24 shrink-0">Win Rate</div>
          <div className="w-10 text-center shrink-0">Score</div>
        </div>

        {stratLoading ? (
          <p className="px-3 py-4 text-xs text-text-faint">Loading performance data...</p>
        ) : strategies && strategies.length > 0 ? (
          <div className="space-y-0.5">
            {strategies.map((s) => (
              <StrategyRow key={s.alert_type} strategy={s} />
            ))}
          </div>
        ) : (
          <p className="px-3 py-4 text-xs text-text-faint text-center">
            Not enough data yet. Performance stats appear after 2+ alerts per strategy.
          </p>
        )}
      </div>
    </div>
  );
}
