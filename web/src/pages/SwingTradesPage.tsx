import {
  useSpyRegime,
  useSwingCategories,
  useActiveSwingTrades,
  useSwingTradesHistory,
  useTriggerSwingScan,
} from "../api/hooks";
import Badge from "../components/ui/Badge";
import Card from "../components/ui/Card";
import { useFeatureGate } from "../hooks/useFeatureGate";

export default function SwingTradesPage() {
  const { data: regime } = useSpyRegime();
  const { data: categories } = useSwingCategories();
  const { data: activeTrades } = useActiveSwingTrades();
  const { data: history } = useSwingTradesHistory();
  const triggerScan = useTriggerSwingScan();
  const { isPro } = useFeatureGate();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Swing Trades</h1>
        {isPro && (
          <button
            onClick={() => triggerScan.mutate()}
            disabled={triggerScan.isPending}
            className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {triggerScan.isPending ? "Scanning..." : "Run EOD Scan"}
          </button>
        )}
      </div>

      {/* SPY Regime */}
      {regime && (
        <Card title="SPY Regime">
          <div className="flex items-center gap-4">
            <Badge variant={regime.regime_bullish ? "bullish" : "bearish"}>
              {regime.regime_bullish ? "BULLISH" : "BEARISH"}
            </Badge>
            <span className="text-sm text-text-muted">
              SPY: <span className="font-mono text-text-primary">${regime.spy_close?.toFixed(2)}</span>
            </span>
            {regime.spy_ema20 && (
              <span className="text-sm text-text-muted">
                EMA20: <span className="font-mono text-text-primary">${regime.spy_ema20.toFixed(2)}</span>
              </span>
            )}
            {regime.spy_rsi != null && (
              <span className="text-sm text-text-muted">
                RSI: <span className={`font-mono ${regime.spy_rsi > 70 ? "text-bearish-text" : regime.spy_rsi < 30 ? "text-bullish-text" : "text-text-primary"}`}>
                  {regime.spy_rsi}
                </span>
              </span>
            )}
          </div>
        </Card>
      )}

      {/* Swing Categories (RSI heatmap-style) */}
      {categories && categories.length > 0 && (
        <Card title="Watchlist Categories">
          <div className="flex flex-wrap gap-2">
            {categories.map((c) => (
              <div
                key={c.symbol}
                className="rounded border border-border-subtle bg-surface-3 px-3 py-2"
              >
                <p className="text-sm font-medium text-text-primary">{c.symbol}</p>
                <p className="text-xs text-text-muted">{c.category}</p>
                {c.rsi != null && (
                  <p className={`font-mono text-xs ${c.rsi > 70 ? "text-bearish-text" : c.rsi < 30 ? "text-bullish-text" : "text-text-muted"}`}>
                    RSI: {c.rsi.toFixed(1)}
                  </p>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Active Swing Trades */}
      <div>
        <h2 className="mb-2 font-display text-sm font-semibold text-text-secondary">Active Trades</h2>
        {activeTrades && activeTrades.length > 0 ? (
          <div className="space-y-2">
            {activeTrades.map((t) => (
              <div
                key={t.id}
                className="flex items-center justify-between rounded-lg border border-border-subtle bg-surface-2 px-4 py-3"
              >
                <div>
                  <span className="font-medium text-text-primary">{t.symbol}</span>
                  <span className="ml-2 text-sm text-text-muted">
                    @ ${t.entry_price.toFixed(2)}
                  </span>
                  {t.current_price && (
                    <span className={`ml-2 font-mono text-sm ${(t.current_price - t.entry_price) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                      ${t.current_price.toFixed(2)}
                    </span>
                  )}
                </div>
                <div className="text-right text-xs text-text-muted">
                  {t.opened_date}
                  {t.current_rsi != null && (
                    <span className="ml-2">RSI: {t.current_rsi.toFixed(1)}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-text-faint">No active swing trades</p>
        )}
      </div>

      {/* History */}
      {history && history.length > 0 && (
        <div>
          <h2 className="mb-2 font-display text-sm font-semibold text-text-secondary">Closed Trades</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted">
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2">Entry</th>
                  <th className="pb-2">Exit</th>
                  <th className="pb-2">P&L</th>
                  <th className="pb-2">Opened</th>
                  <th className="pb-2">Closed</th>
                </tr>
              </thead>
              <tbody>
                {history.map((t) => (
                  <tr key={t.id} className="border-t border-border-subtle">
                    <td className="py-2 font-medium text-text-primary">{t.symbol}</td>
                    <td className="py-2 font-mono text-text-secondary">${t.entry_price.toFixed(2)}</td>
                    <td className="py-2 font-mono text-text-secondary">{t.exit_price ? `$${t.exit_price.toFixed(2)}` : "—"}</td>
                    <td className={`py-2 font-mono font-medium ${(t.pnl ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                      {t.pnl != null ? `$${t.pnl.toFixed(2)}` : "—"}
                    </td>
                    <td className="py-2 text-text-muted">{t.opened_date}</td>
                    <td className="py-2 text-text-muted">{t.closed_date ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
