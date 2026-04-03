import { useState } from "react";
import {
  useOpenTrades,
  useClosedTrades,
  useRealTradeStats,
  useOpenRealTrade,
  useCloseRealTrade,
  useUpdateTradeNotes,
  useRealTradeEquityCurve,
  useOpenOptionsTrades,
  useClosedOptionsTrades,
  useOptionsTradeStats,
} from "../api/hooks";
import EquityCurve from "../components/EquityCurve";
import Card from "../components/ui/Card";

type Tab = "stocks" | "options";

function StatBox({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Card padding="sm">
      <p className="text-xs text-text-muted">{label}</p>
      <p className={`mt-1 font-mono text-lg font-bold ${color || "text-text-primary"}`}>{value}</p>
    </Card>
  );
}

export default function RealTradesPage() {
  const [tab, setTab] = useState<Tab>("stocks");

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <h1 className="font-display text-2xl font-bold">Trades</h1>
        <div className="flex gap-1">
          <button
            onClick={() => setTab("stocks")}
            className={`rounded px-3 py-1 text-xs font-medium ${tab === "stocks" ? "bg-accent text-white" : "bg-surface-3 text-text-muted"}`}
          >
            Stocks
          </button>
          <button
            onClick={() => setTab("options")}
            className={`rounded px-3 py-1 text-xs font-medium ${tab === "options" ? "bg-accent text-white" : "bg-surface-3 text-text-muted"}`}
          >
            Options
          </button>
        </div>
      </div>

      {tab === "stocks" ? <StocksTab /> : <OptionsTab />}
    </div>
  );
}

function StocksTab() {
  const { data: openTrades } = useOpenTrades();
  const { data: closedTrades } = useClosedTrades();
  const { data: stats } = useRealTradeStats();
  const { data: equityCurve } = useRealTradeEquityCurve();
  const openTrade = useOpenRealTrade();
  const closeTrade = useCloseRealTrade();
  const updateNotes = useUpdateTradeNotes();

  const [symbol, setSymbol] = useState("");
  const [entryPrice, setEntryPrice] = useState("");
  const [stopPrice, setStopPrice] = useState("");
  const [targetPrice, setTargetPrice] = useState("");
  const [closingId, setClosingId] = useState<number | null>(null);
  const [exitPrice, setExitPrice] = useState("");
  const [editingNotesId, setEditingNotesId] = useState<number | null>(null);
  const [notesText, setNotesText] = useState("");

  function handleOpen(e: React.FormEvent) {
    e.preventDefault();
    openTrade.mutate(
      {
        symbol: symbol.toUpperCase(),
        entry_price: parseFloat(entryPrice),
        stop_price: stopPrice ? parseFloat(stopPrice) : undefined,
        target_price: targetPrice ? parseFloat(targetPrice) : undefined,
      },
      { onSuccess: () => { setSymbol(""); setEntryPrice(""); setStopPrice(""); setTargetPrice(""); } },
    );
  }

  function handleClose() {
    if (closingId === null || !exitPrice) return;
    closeTrade.mutate(
      { id: closingId, exit_price: parseFloat(exitPrice) },
      { onSuccess: () => { setClosingId(null); setExitPrice(""); } },
    );
  }

  function handleSaveNotes() {
    if (editingNotesId === null) return;
    updateNotes.mutate(
      { id: editingNotesId, notes: notesText },
      { onSuccess: () => { setEditingNotesId(null); setNotesText(""); } },
    );
  }

  return (
    <>
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatBox
            label="Total P&L"
            value={`$${stats.total_pnl.toFixed(2)}`}
            color={stats.total_pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}
          />
          <StatBox label="Win Rate" value={`${stats.win_rate}%`} />
          <StatBox label="Trades" value={`${stats.total_trades}`} />
          <StatBox
            label="Expectancy"
            value={`$${stats.expectancy.toFixed(2)}`}
            color={stats.expectancy >= 0 ? "text-bullish-text" : "text-bearish-text"}
          />
        </div>
      )}

      {/* Equity Curve */}
      {equityCurve && equityCurve.length > 1 && (
        <Card title="Equity Curve" padding="sm">
          <EquityCurve data={equityCurve} height={180} />
        </Card>
      )}

      {/* Open Trade Form */}
      <Card title="Open New Trade">
        <form onSubmit={handleOpen} className="flex flex-wrap gap-2">
          <input type="text" value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="Symbol" required className="w-24 rounded border border-border-subtle bg-surface-3 px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none" />
          <input type="number" step="0.01" value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} placeholder="Entry $" required className="w-28 rounded border border-border-subtle bg-surface-3 px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none" />
          <input type="number" step="0.01" value={stopPrice} onChange={(e) => setStopPrice(e.target.value)} placeholder="Stop $" className="w-28 rounded border border-border-subtle bg-surface-3 px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none" />
          <input type="number" step="0.01" value={targetPrice} onChange={(e) => setTargetPrice(e.target.value)} placeholder="Target $" className="w-28 rounded border border-border-subtle bg-surface-3 px-2 py-1.5 text-sm text-text-primary focus:border-accent focus:outline-none" />
          <button type="submit" disabled={openTrade.isPending} className="rounded bg-bullish px-4 py-1.5 text-sm font-medium text-white hover:opacity-80 disabled:opacity-50">Open</button>
        </form>
      </Card>

      {/* Open Positions */}
      {openTrades && openTrades.length > 0 && (
        <div>
          <h2 className="mb-2 font-display text-sm font-semibold text-text-secondary">Open Positions</h2>
          <div className="space-y-2">
            {openTrades.map((t) => (
              <div key={t.id} className="rounded-lg border border-border-subtle bg-surface-2 px-4 py-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-medium text-text-primary">{t.symbol}</span>
                    <span className="ml-2 text-sm text-text-muted">{t.shares} shares @ ${t.entry_price.toFixed(2)}</span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setEditingNotesId(t.id); setNotesText(t.notes || ""); }}
                      className="rounded bg-surface-4 px-2 py-1 text-xs text-text-muted hover:text-text-secondary"
                    >
                      Notes
                    </button>
                    <button onClick={() => setClosingId(t.id)} className="rounded bg-bearish px-3 py-1 text-xs font-medium text-white hover:opacity-80">Close</button>
                  </div>
                </div>
                {t.notes && <p className="mt-1 text-xs text-text-muted">{t.notes}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Close modal */}
      {closingId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-[calc(100%-2rem)] max-w-80 space-y-4 rounded-lg border border-border-subtle bg-surface-2 p-6">
            <h3 className="font-display font-bold text-text-primary">Close Trade</h3>
            <input type="number" step="0.01" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} placeholder="Exit Price $" className="w-full rounded border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none" autoFocus />
            <div className="flex gap-2">
              <button onClick={handleClose} className="flex-1 rounded bg-bearish py-2 text-sm font-medium text-white hover:opacity-80">Confirm Close</button>
              <button onClick={() => setClosingId(null)} className="flex-1 rounded bg-surface-4 py-2 text-sm text-text-muted hover:bg-surface-3">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Notes modal */}
      {editingNotesId !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-[calc(100%-2rem)] max-w-96 space-y-4 rounded-lg border border-border-subtle bg-surface-2 p-6">
            <h3 className="font-display font-bold text-text-primary">Trade Notes</h3>
            <textarea
              value={notesText}
              onChange={(e) => setNotesText(e.target.value)}
              rows={4}
              className="w-full rounded border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
              autoFocus
            />
            <div className="flex gap-2">
              <button onClick={handleSaveNotes} className="flex-1 rounded bg-accent py-2 text-sm font-medium text-white hover:bg-accent-hover">Save</button>
              <button onClick={() => setEditingNotesId(null)} className="flex-1 rounded bg-surface-4 py-2 text-sm text-text-muted hover:bg-surface-3">Cancel</button>
            </div>
          </div>
        </div>
      )}

      {/* Closed Trades */}
      {closedTrades && closedTrades.length > 0 && (
        <div>
          <h2 className="mb-2 font-display text-sm font-semibold text-text-secondary">Recent Closed</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted">
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2">Entry</th>
                  <th className="pb-2">Exit</th>
                  <th className="pb-2">Shares</th>
                  <th className="pb-2">P&L</th>
                  <th className="pb-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {closedTrades.map((t) => (
                  <tr key={t.id} className="border-t border-border-subtle">
                    <td className="py-2 font-medium text-text-primary">{t.symbol}</td>
                    <td className="py-2 font-mono text-text-secondary">${t.entry_price.toFixed(2)}</td>
                    <td className="py-2 font-mono text-text-secondary">${t.exit_price?.toFixed(2)}</td>
                    <td className="py-2 text-text-secondary">{t.shares}</td>
                    <td className={`py-2 font-mono font-medium ${(t.pnl ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                      ${t.pnl?.toFixed(2)}
                    </td>
                    <td className="py-2 text-text-muted">{t.session_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

function OptionsTab() {
  const { data: openOptions } = useOpenOptionsTrades();
  const { data: closedOptions } = useClosedOptionsTrades();
  const { data: stats } = useOptionsTradeStats();

  return (
    <>
      {/* Options Stats */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatBox
            label="Total P&L"
            value={`$${stats.total_pnl.toFixed(2)}`}
            color={stats.total_pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}
          />
          <StatBox label="Win Rate" value={`${stats.win_rate.toFixed(1)}%`} />
          <StatBox label="Trades" value={`${stats.total_trades}`} />
          <StatBox
            label="Expectancy"
            value={`$${stats.expectancy.toFixed(2)}`}
            color={stats.expectancy >= 0 ? "text-bullish-text" : "text-bearish-text"}
          />
        </div>
      )}

      {/* Open Options */}
      {openOptions && openOptions.length > 0 && (
        <div>
          <h2 className="mb-2 font-display text-sm font-semibold text-text-secondary">Open Options</h2>
          <div className="space-y-2">
            {openOptions.map((t) => (
              <div key={t.id} className="flex items-center justify-between rounded-lg border border-border-subtle bg-surface-2 px-4 py-3">
                <div>
                  <span className="font-medium text-text-primary">{t.symbol}</span>
                  <span className="ml-2 text-sm text-text-muted">
                    {t.option_type.toUpperCase()} ${t.strike} exp {t.expiration}
                  </span>
                  <span className="ml-2 text-sm text-text-muted">
                    {t.contracts}x @ ${t.premium_per_contract.toFixed(2)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Closed Options */}
      {closedOptions && closedOptions.length > 0 && (
        <div>
          <h2 className="mb-2 font-display text-sm font-semibold text-text-secondary">Closed Options</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-text-muted">
                  <th className="pb-2">Symbol</th>
                  <th className="pb-2">Type</th>
                  <th className="pb-2">Strike</th>
                  <th className="pb-2">Contracts</th>
                  <th className="pb-2">Premium</th>
                  <th className="pb-2">Exit</th>
                  <th className="pb-2">P&L</th>
                </tr>
              </thead>
              <tbody>
                {closedOptions.map((t) => (
                  <tr key={t.id} className="border-t border-border-subtle">
                    <td className="py-2 font-medium text-text-primary">{t.symbol}</td>
                    <td className="py-2 text-text-secondary">{t.option_type}</td>
                    <td className="py-2 font-mono text-text-secondary">${t.strike.toFixed(2)}</td>
                    <td className="py-2 text-text-secondary">{t.contracts}</td>
                    <td className="py-2 font-mono text-text-secondary">${t.premium_per_contract.toFixed(2)}</td>
                    <td className="py-2 font-mono text-text-secondary">{t.exit_premium ? `$${t.exit_premium.toFixed(2)}` : "—"}</td>
                    <td className={`py-2 font-mono font-medium ${(t.pnl ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                      {t.pnl != null ? `$${t.pnl.toFixed(2)}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(!openOptions || openOptions.length === 0) && (!closedOptions || closedOptions.length === 0) && (
        <p className="text-sm text-text-faint">No options trades recorded yet.</p>
      )}
    </>
  );
}
