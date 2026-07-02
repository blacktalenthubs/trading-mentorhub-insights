// Premarket signals rendered as a feed panel — its own ISOLATED channel (data comes
// from the market_reports premarket_signals report, not the RTH alert feed). Shown as
// the "Premarket" panel in the Signals feed during premarket.

export type PmSignal = {
  symbol: string; alert_type: string; entry: number; level: number;
  stop: number; note: string; price: number; gap_pct: number;
};

const PM_LABEL: Record<string, string> = {
  cml_reclaim: "reclaimed month low", cml_held: "held month low",
  staged_pdl_held: "held prior-day low", staged_pwl_held: "held prior-week low",
  staged_pml_held: "held prior-month low", staged_pdh_break: "broke prior-day high",
  staged_pwh_break: "broke prior-week high", weekly_10w_held: "held 10-week MA",
  weekly_30w_held: "held 30-week MA",
};

function Card({ s, onSelect }: { s: PmSignal; onSelect: (x: string) => void }) {
  return (
    <button
      onClick={() => onSelect(s.symbol)}
      className="text-left rounded-lg border border-border-subtle bg-surface-1 p-2.5 hover:border-accent transition-colors"
    >
      <div className="flex items-center justify-between">
        <span className="text-[12px] font-bold text-text-secondary">{s.symbol}</span>
        <span className={`text-[10px] font-semibold ${s.gap_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
          {s.gap_pct >= 0 ? "+" : ""}{s.gap_pct}%
        </span>
      </div>
      <div className="mt-0.5 text-[11px] text-text-muted">{PM_LABEL[s.alert_type] ?? s.alert_type}</div>
      <div className="mt-0.5 text-[11px] text-text-faint">entry ${s.entry} · level ${s.level} · stop ${s.stop}</div>
    </button>
  );
}

export function PremarketPanel({ signals, onSelectSymbol }: { signals: PmSignal[]; onSelectSymbol: (s: string) => void }) {
  if (!signals || signals.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center px-4">
        <p className="text-xs text-text-faint text-center">
          No Focus name is at a key level premarket right now. Signals appear here 7:00–9:30 AM ET, refreshed every 15 min.
        </p>
      </div>
    );
  }
  const breakouts = signals.filter((s) => s.alert_type.includes("break"));
  const support = signals.filter((s) => !s.alert_type.includes("break"));
  return (
    <div className="flex-1 overflow-y-auto px-3 py-2 space-y-3">
      {breakouts.length > 0 && (
        <section className="space-y-1.5">
          <h3 className="text-[10px] font-bold uppercase tracking-wide text-text-muted">Breaking out · through resistance</h3>
          <div className="grid grid-cols-1 gap-1.5">{breakouts.map((s) => <Card key={s.symbol + s.alert_type} s={s} onSelect={onSelectSymbol} />)}</div>
        </section>
      )}
      {support.length > 0 && (
        <section className="space-y-1.5">
          <h3 className="text-[10px] font-bold uppercase tracking-wide text-text-muted">At support · reclaiming a level</h3>
          <div className="grid grid-cols-1 gap-1.5">{support.map((s) => <Card key={s.symbol + s.alert_type} s={s} onSelect={onSelectSymbol} />)}</div>
        </section>
      )}
    </div>
  );
}
