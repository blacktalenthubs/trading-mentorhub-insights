import {
  useActiveSwingTrades,
  useSwingTradesHistory,
  useTriggerSwingScan,
} from "../api/hooks";
import Badge from "../components/ui/Badge";
import { useFeatureGate } from "../hooks/useFeatureGate";
import { toast } from "../components/Toast";
import type { SwingTrade } from "../types";

function fmt(n: number | null | undefined): string {
  return n != null ? `$${n.toFixed(2)}` : "—";
}

function TradeRow({ t }: { t: SwingTrade }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-2 px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="font-medium text-text-primary">{t.symbol}</span>
          <Badge variant="neutral">{t.setup}</Badge>
          {t.conviction && (
            <span className="text-xs uppercase text-text-faint">{t.conviction}</span>
          )}
        </div>
        <span className="text-xs text-text-muted">{t.opened_date}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-sm">
        <span className="text-text-secondary">Entry {fmt(t.entry)}</span>
        <span className="text-bearish-text">Stop {fmt(t.stop)}</span>
        <span className="text-bullish-text">T1 {fmt(t.target_1)}</span>
        <span className="text-bullish-text">T2 {fmt(t.target_2)}</span>
      </div>
    </div>
  );
}

export default function SwingTradesPage() {
  const { data: activeTrades } = useActiveSwingTrades();
  const { data: history } = useSwingTradesHistory();
  const triggerScan = useTriggerSwingScan();
  const { isPro } = useFeatureGate();

  function runScan() {
    triggerScan.mutate(undefined, {
      onSuccess: (data) => {
        const n = data?.alerts_fired ?? 0;
        toast.success(
          n > 0
            ? `Scan complete — ${n} new swing setup${n === 1 ? "" : "s"}`
            : "Scan complete — no setups qualified today"
        );
      },
      onError: () => toast.error("Scan failed — try again"),
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Swing Trades</h1>
        {isPro && (
          <button
            onClick={runScan}
            disabled={triggerScan.isPending}
            className="rounded bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {triggerScan.isPending ? "Scanning..." : "Run Scan Now"}
          </button>
        )}
      </div>

      <p className="text-xs text-text-faint">
        Runs the daily-bar swing rules across your watchlist: MA bounces (21,
        50, 200), 8/21 cross, golden-cross retest, 52-week-high retest,
        5-day-low reclaim, RSI-30 recovery. Toggle delivery per pattern in
        Settings → Alert Types. Setups appear here even when notifications
        are off — for end-of-day review.
      </p>

      {/* Active swing trades */}
      <div>
        <h2 className="mb-2 font-display text-sm font-semibold text-text-secondary">
          Active Trades
        </h2>
        {activeTrades && activeTrades.length > 0 ? (
          <div className="space-y-2">
            {activeTrades.map((t) => (
              <TradeRow key={t.id} t={t} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-text-faint">No active swing trades</p>
        )}
      </div>

      {/* History */}
      {history && history.length > 0 && (
        <div>
          <h2 className="mb-2 font-display text-sm font-semibold text-text-secondary">
            Closed Trades
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted">
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2">Setup</th>
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
                    <td className="py-2 text-text-muted">{t.setup}</td>
                    <td className="py-2 font-mono text-text-secondary">{fmt(t.entry)}</td>
                    <td className="py-2 font-mono text-text-secondary">{fmt(t.exit_price)}</td>
                    <td
                      className={`py-2 font-mono font-medium ${
                        (t.pnl_pct ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"
                      }`}
                    >
                      {t.pnl_pct != null ? `${t.pnl_pct.toFixed(2)}%` : "—"}
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
