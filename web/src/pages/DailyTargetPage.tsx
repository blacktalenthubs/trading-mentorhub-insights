/** Daily Target — self-reporting discipline page (gated to one account for now).
 *
 * Log the day's trades (setup, instrument, entry/exit, P/L), watch the running total climb
 * toward your target, and CLOSE THE DAY once you hit it. "Make your number, then stop" — the
 * guard against overtrading and giving it back. */

import { useState, useMemo } from "react";
import { Plus, Trash2, Lock, Check, Pencil } from "lucide-react";
import { useAuthStore } from "../stores/auth";
import {
  useDailySummary,
  useSetDailyTarget,
  useAddDailyTrade,
  useDeleteDailyTrade,
  useCloseDay,
  useReopenDay,
  useWatchlist,
  useSectorsWatchlist,
  type DailyTradeInput,
} from "../api/hooks";

const OWNER_EMAIL = "vbolofinde@gmail.com";

// Entry mechanisms (your rules) — levels + SMA.
const SETUPS = [
  "PDH break",
  "PDL held",
  "PDL reclaim",
  "8 SMA reclaim",
  "21 SMA reclaim",
  "50 SMA support",
  "100 SMA support",
  "200 SMA support",
  "Level reclaim",
  "Level reject",
  "Weekly breakout (PWH)",
  "Monthly breakout (PMH)",
  "Open bracket",
  "Gap and go",
  "Pivot breakout",
  "Other",
];

const EXIT_REASONS = [
  "Target hit",
  "Stop",
  "Into resistance",
  "Give-back / trailed out",
  "Time cutoff",
  "Changed mind",
  "Other",
];

const usd = (n: number) =>
  (n < 0 ? "-" : "") +
  Math.abs(n).toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export default function DailyTargetPage() {
  const user = useAuthStore((s) => s.user);
  const isOwner = (user?.email || "").toLowerCase() === OWNER_EMAIL;

  const { data, isLoading } = useDailySummary();
  const setTarget = useSetDailyTarget();
  const addTrade = useAddDailyTrade();
  const delTrade = useDeleteDailyTrade();
  const closeDay = useCloseDay();
  const reopenDay = useReopenDay();

  // Symbol typeahead — the master (Editor's Picks) universe + your own watchlist, deduped.
  const { data: masterWl } = useSectorsWatchlist();
  const { data: myWl } = useWatchlist();
  const symbolOptions = useMemo(() => {
    const set = new Set<string>();
    (masterWl ?? []).forEach((w) => set.add(w.symbol));
    (myWl ?? []).forEach((w) => set.add(w.symbol));
    return Array.from(set).sort();
  }, [masterWl, myWl]);

  // trade form
  const [symbol, setSymbol] = useState("");
  const [instrument, setInstrument] = useState("stock");
  const [tradeType, setTradeType] = useState("day");
  const [setup, setSetup] = useState(SETUPS[0]);
  const [direction, setDirection] = useState("long");
  const [entry, setEntry] = useState("");
  const [exit, setExit] = useState("");
  const [qty, setQty] = useState("");
  const [size, setSize] = useState("");
  const [pnl, setPnl] = useState("");
  const [exitReason, setExitReason] = useState(EXIT_REASONS[0]);
  const [note, setNote] = useState("");

  // target editor
  const [editingTarget, setEditingTarget] = useState(false);
  const [targetDraft, setTargetDraft] = useState("");

  if (!isOwner) {
    return (
      <div className="h-full overflow-y-auto overflow-x-hidden p-5">
        <div className="max-w-5xl mx-auto">
          <div className="bg-surface-1 border border-border-subtle rounded-xl p-6 text-center text-text-muted">
            This page isn't enabled for your account.
          </div>
        </div>
      </div>
    );
  }

  const target = data?.target ?? 4000;
  const total = data?.total_pnl ?? 0;
  const hit = data?.hit ?? false;
  const closed = data?.closed ?? false;
  const pct = target > 0 ? Math.max(0, Math.min(100, (total / target) * 100)) : 0;
  const trades = data?.trades ?? [];

  const submitTrade = (e: React.FormEvent) => {
    e.preventDefault();
    if (!symbol.trim() || pnl.trim() === "") return;
    const body: DailyTradeInput = {
      symbol: symbol.trim().toUpperCase(),
      instrument,
      trade_type: tradeType,
      setup,
      direction,
      entry_price: entry.trim() === "" ? null : Number(entry),
      exit_price: exit.trim() === "" ? null : Number(exit),
      quantity: qty.trim() === "" ? null : Number(qty),
      position_size: size.trim() === "" ? null : Number(size),
      pnl: Number(pnl),
      exit_reason: exitReason,
      note: note.trim() || null,
    };
    addTrade.mutate(body, {
      onSuccess: () => {
        setSymbol("");
        setEntry("");
        setExit("");
        setQty("");
        setSize("");
        setPnl("");
        setNote("");
      },
    });
  };

  const inputCls =
    "rounded-md border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:ring-1 focus:ring-accent/30 focus:outline-none disabled:opacity-50";

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden p-5">
      <div className="max-w-5xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="font-display text-xl font-bold text-text-primary">Daily Target</h1>
            <p className="mt-1 text-[11px] text-text-faint">{data?.date ?? "today"} · make your number, then stop</p>
          </div>
        </div>

        {/* Scoreboard */}
        <div className="bg-surface-1 border border-border-subtle rounded-xl p-5 space-y-4">
          <div className="flex items-end justify-between gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-wide text-text-faint">Realized today</div>
              <div className={`font-display text-4xl font-bold ${total < 0 ? "text-bearish-text" : "text-bullish-text"}`}>
                {usd(total)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[11px] uppercase tracking-wide text-text-faint">Target</div>
              {editingTarget ? (
                <div className="flex items-center gap-1.5 mt-1">
                  <input
                    autoFocus
                    type="number"
                    value={targetDraft}
                    onChange={(e) => setTargetDraft(e.target.value)}
                    className={`${inputCls} w-28 text-right`}
                  />
                  <button
                    onClick={() => {
                      const v = Number(targetDraft);
                      if (!Number.isNaN(v) && v >= 0) setTarget.mutate(v);
                      setEditingTarget(false);
                    }}
                    className="inline-flex items-center gap-1 rounded-lg border border-accent/40 bg-accent/10 px-2.5 py-2 text-[13px] font-semibold text-accent hover:bg-accent/20"
                  >
                    <Check className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => {
                    setTargetDraft(String(target));
                    setEditingTarget(true);
                  }}
                  className="inline-flex items-center gap-1.5 font-display text-2xl font-bold text-text-primary hover:text-accent"
                >
                  {usd(target)}
                  <Pencil className="h-3.5 w-3.5 text-text-faint" />
                </button>
              )}
            </div>
          </div>

          {/* Progress */}
          <div>
            <div className="h-2.5 w-full rounded-full bg-surface-3 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${hit ? "bg-bullish" : total < 0 ? "bg-bearish" : "bg-accent"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="mt-2 flex items-center gap-4 text-[11px] text-text-faint">
              <span>{trades.length} trades</span>
              <span className="text-bullish-text">{data?.wins ?? 0}W</span>
              <span className="text-bearish-text">{data?.losses ?? 0}L</span>
              <span className="ml-auto">{Math.round(pct)}% of target</span>
            </div>
          </div>

          {/* Status banner + close/reopen */}
          {closed ? (
            <div className="flex items-center justify-between gap-3 rounded-lg border border-border-subtle bg-surface-2 px-4 py-3">
              <div className="flex items-center gap-2 text-text-primary font-semibold">
                <Lock className="h-4 w-4 text-text-muted" /> Day closed — done trading.
              </div>
              <button
                onClick={() => reopenDay.mutate()}
                className="rounded-md border border-border-subtle bg-surface-3 px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary"
              >
                Reopen
              </button>
            </div>
          ) : (
            <div
              className={`flex items-center justify-between gap-3 rounded-lg border px-4 py-3 ${
                hit ? "border-bullish/30 bg-bullish/10" : "border-border-subtle bg-surface-2"
              }`}
            >
              <div className={`font-semibold ${hit ? "text-bullish-text" : "text-text-secondary"}`}>
                {hit ? "🎯 Target hit — close the day. Don't give it back." : `${usd(Math.max(0, target - total))} to go`}
              </div>
              <button
                onClick={() => closeDay.mutate()}
                className={`rounded-lg px-3.5 py-2 text-[13px] font-semibold transition-colors ${
                  hit
                    ? "border border-bullish/40 bg-bullish/20 text-bullish-text hover:bg-bullish/30"
                    : "border border-border-subtle bg-surface-3 text-text-secondary hover:text-text-primary"
                }`}
              >
                Close the day
              </button>
            </div>
          )}
        </div>

        {/* Log a trade */}
        {!closed && (
          <form onSubmit={submitTrade} className="bg-surface-1 border border-border-subtle rounded-xl p-5 space-y-3">
            <div className="font-semibold text-text-primary">Log a trade</div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <input
                className={`${inputCls} font-mono uppercase`}
                placeholder="Symbol"
                list="daily-symbols"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
              />
              <datalist id="daily-symbols">
                {symbolOptions.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
              <select className={inputCls} value={instrument} onChange={(e) => setInstrument(e.target.value)}>
                <option value="stock">Stock</option>
                <option value="option">Option</option>
              </select>
              <select className={inputCls} value={tradeType} onChange={(e) => setTradeType(e.target.value)}>
                <option value="day">Day</option>
                <option value="swing">Swing</option>
              </select>
              <select className={inputCls} value={setup} onChange={(e) => setSetup(e.target.value)}>
                {SETUPS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <select className={inputCls} value={direction} onChange={(e) => setDirection(e.target.value)}>
                <option value="long">Long</option>
                <option value="short">Short</option>
              </select>
              <input
                className={inputCls}
                type="number"
                step="any"
                placeholder="Entry"
                value={entry}
                onChange={(e) => setEntry(e.target.value)}
              />
              <input
                className={inputCls}
                type="number"
                step="any"
                placeholder="Exit"
                value={exit}
                onChange={(e) => setExit(e.target.value)}
              />
              <input
                className={inputCls}
                type="number"
                step="any"
                placeholder={instrument === "option" ? "Contracts" : "Shares"}
                value={qty}
                onChange={(e) => setQty(e.target.value)}
              />
              <input
                className={inputCls}
                type="number"
                step="any"
                placeholder="Size $"
                value={size}
                onChange={(e) => setSize(e.target.value)}
              />
              <input
                className={`${inputCls} font-semibold`}
                type="number"
                step="any"
                placeholder="P/L $"
                value={pnl}
                onChange={(e) => setPnl(e.target.value)}
              />
              <select className={inputCls} value={exitReason} onChange={(e) => setExitReason(e.target.value)}>
                {EXIT_REASONS.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <input
              className={`${inputCls} w-full`}
              placeholder="Note (optional)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={addTrade.isPending || !symbol.trim() || pnl.trim() === ""}
                className="inline-flex items-center gap-1.5 rounded-lg border border-accent/40 bg-accent/10 px-4 py-2 text-[13px] font-semibold text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
              >
                <Plus className="h-4 w-4" /> Add trade
              </button>
            </div>
          </form>
        )}

        {/* Trades table */}
        <div className="bg-surface-1 border border-border-subtle rounded-xl overflow-hidden">
          {isLoading ? (
            <div className="p-5 text-sm text-text-muted">Loading…</div>
          ) : trades.length === 0 ? (
            <div className="p-5 text-sm text-text-muted">No trades logged yet today.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wide text-text-faint">
                    <th className="text-left font-medium px-4 py-2.5">Symbol</th>
                    <th className="text-left font-medium px-3 py-2.5">Setup</th>
                    <th className="text-left font-medium px-3 py-2.5">Dir</th>
                    <th className="text-right font-medium px-3 py-2.5">Entry</th>
                    <th className="text-right font-medium px-3 py-2.5">Exit</th>
                    <th className="text-right font-medium px-3 py-2.5">Size</th>
                    <th className="text-right font-medium px-3 py-2.5">P/L</th>
                    <th className="text-left font-medium px-3 py-2.5">Exit</th>
                    <th className="px-3 py-2.5"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle/40">
                  {trades.map((t) => (
                    <tr key={t.id} className="text-text-secondary">
                      <td className="px-4 py-2.5">
                        <span className="font-mono font-semibold text-text-primary">{t.symbol}</span>
                        <span className="ml-1.5 text-[10px] uppercase text-text-faint">{t.instrument}</span>
                      </td>
                      <td className="px-3 py-2.5">{t.setup || "—"}</td>
                      <td className="px-3 py-2.5 uppercase text-[11px]">
                        {t.direction || "—"}
                        <span className="ml-1 lowercase text-text-faint">{t.trade_type === "swing" ? "· swing" : "· day"}</span>
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono">{t.entry_price ?? "—"}</td>
                      <td className="px-3 py-2.5 text-right font-mono">{t.exit_price ?? "—"}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-[12px] text-text-muted">
                        {t.quantity ?? "—"}
                        {t.position_size ? ` · ${usd(t.position_size)}` : ""}
                      </td>
                      <td
                        className={`px-3 py-2.5 text-right font-mono font-semibold ${
                          t.pnl < 0 ? "text-bearish-text" : "text-bullish-text"
                        }`}
                      >
                        {usd(t.pnl)}
                      </td>
                      <td className="px-3 py-2.5 text-[12px]">{t.exit_reason || "—"}</td>
                      <td className="px-3 py-2.5 text-right">
                        <button
                          onClick={() => delTrade.mutate(t.id)}
                          className="text-text-faint hover:text-bearish-text"
                          aria-label="Delete trade"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
