/** TodayEOD — the EOD-review surface (Performance · Today's EOD, #64 Sub-spec I).
 *  Lists YOUR open positions (mark-took trades not yet closed) with a close-out form,
 *  plus today's closed outcomes. Real R-multiple from your actual entry/exit — no
 *  synthetic P&L, no flawed target/stop-symbol heuristic.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useOpenTrades, useClosedTrades, useCloseTrade, useDeleteTrade, useClearOpenTrades } from "../api/hooks";
import type { RealTrade } from "../api/hooks";
import { formatSetup } from "../lib/alertFormat";
import { X, ChevronRight } from "lucide-react";

const px = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const todayStr = () => new Date().toISOString().slice(0, 10);

function isLong(t: RealTrade) {
  const d = (t.direction || "").toUpperCase();
  return d === "BUY" || d === "LONG";
}
function rOf(t: RealTrade): number | null {
  if (t.exit_price == null || t.stop_price == null || t.entry_price === t.stop_price) return null;
  const reward = isLong(t) ? t.exit_price - t.entry_price : t.entry_price - t.exit_price;
  return reward / Math.abs(t.entry_price - t.stop_price);
}

function Stat({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
      <div className="text-[10px] text-text-faint uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-2xl font-mono font-bold ${color ?? "text-text-primary"}`}>{value}</div>
    </div>
  );
}

function OpenRow({ t }: { t: RealTrade }) {
  const close = useCloseTrade();
  const dismiss = useDeleteTrade();
  const nav = useNavigate();
  const [exit, setExit] = useState("");
  const long = isLong(t);
  const submit = () => {
    const v = parseFloat(exit);
    if (isNaN(v) || v <= 0) return;
    close.mutate({ id: t.id, exit_price: v });
  };
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border-subtle bg-surface-1 px-3 py-2.5">
      <span className="font-display text-[13px] font-semibold text-text-primary">{t.symbol}</span>
      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${long ? "bg-bullish-subtle text-bullish-text" : "bg-bearish-subtle text-bearish-text"}`}>{long ? "LONG" : "SHORT"}</span>
      {t.alert_type && <button onClick={() => nav(`/pattern/${encodeURIComponent(t.alert_type as string)}`)} title="Learn this pattern" className="text-[10px] text-text-faint hover:text-accent hover:underline shrink-0">{formatSetup(t.alert_type)}</button>}
      <span className="font-mono text-[11px] text-text-muted tabular-nums">entry {px(t.entry_price)} · stop {t.stop_price != null ? px(t.stop_price) : "—"}</span>
      <div className="ml-auto flex items-center gap-2">
        <input value={exit} onChange={(e) => setExit(e.target.value)} inputMode="decimal" placeholder="exit price"
          className="w-28 rounded-md bg-surface-2 border border-border-default px-2 py-1 font-mono text-[12px] text-text-primary focus:border-accent outline-none" />
        <button onClick={submit} disabled={close.isPending}
          className="text-[12px] font-semibold px-3 py-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-60 transition-colors">
          {close.isPending ? "…" : "Close"}
        </button>
        <button onClick={() => dismiss.mutate(t.id)} disabled={dismiss.isPending} title="I didn't take this — remove"
          className="p-1 text-text-faint hover:text-bearish-text disabled:opacity-50 transition-colors"><X size={14} /></button>
      </div>
    </div>
  );
}

function dayLabel(d: string): string {
  if (d === todayStr()) return "Today";
  const y = new Date(); y.setDate(y.getDate() - 1);
  if (d === y.toISOString().slice(0, 10)) return "Yesterday";
  const dt = new Date(d + "T00:00:00");
  return isNaN(dt.getTime()) ? d : dt.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function ClosedRow({ t }: { t: RealTrade }) {
  const nav = useNavigate();
  const r = rOf(t);
  const win = (r ?? t.pnl ?? 0) >= 0;
  const long = isLong(t);
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border-subtle bg-surface-1 px-3 py-2.5">
      <span className="font-display text-[13px] font-semibold text-text-primary">{t.symbol}</span>
      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${long ? "bg-bullish-subtle text-bullish-text" : "bg-bearish-subtle text-bearish-text"}`}>{long ? "LONG" : "SHORT"}</span>
      {t.alert_type && <button onClick={() => nav(`/pattern/${encodeURIComponent(t.alert_type as string)}`)} title="Learn this pattern" className="text-[10px] text-text-faint hover:text-accent hover:underline shrink-0 hidden sm:inline">{formatSetup(t.alert_type)}</button>}
      <span className="font-mono text-[11px] text-text-muted tabular-nums">{px(t.entry_price)} → {t.exit_price != null ? px(t.exit_price) : "—"}</span>
      <span className={`ml-auto font-mono text-[12px] font-semibold tabular-nums ${win ? "text-bullish-text" : "text-bearish-text"}`}>
        {r != null ? `${win ? "Win" : "Loss"} ${r >= 0 ? "+" : ""}${r.toFixed(1)}R` : (win ? "Win" : "Loss")}
      </span>
    </div>
  );
}

export default function TodayEOD() {
  const { data: open } = useOpenTrades();
  const { data: closed } = useClosedTrades();
  const [selectedDay, setSelectedDay] = useState("");
  const [openCollapsed, setOpenCollapsed] = useState(false);
  const clearOpen = useClearOpenTrades();
  const openTrades = open ?? [];
  const clearAll = () => {
    if (openTrades.length && window.confirm(`Clear all ${openTrades.length} open position${openTrades.length > 1 ? "s" : ""}? Use this for trades you didn't actually take.`)) clearOpen.mutate();
  };
  const closedTrades = closed ?? [];
  const closedToday = closedTrades.filter((t) => t.session_date === todayStr());
  const won = closedToday.filter((t) => (rOf(t) ?? t.pnl ?? 0) > 0).length;
  const lost = closedToday.length - won;
  const days = [...new Set(closedTrades.map((t) => t.session_date))].sort((a, b) => b.localeCompare(a));
  const day = selectedDay && days.includes(selectedDay) ? selectedDay : (days[0] ?? "");
  const dayTrades = closedTrades.filter((t) => t.session_date === day);
  const dayWon = dayTrades.filter((t) => (rOf(t) ?? t.pnl ?? 0) > 0).length;
  const dayR = dayTrades.reduce((s, t) => s + (rOf(t) ?? 0), 0);

  return (
    <div className="space-y-6">
      <p className="text-[12px] text-text-muted">
        Close out the trades you took today — enter your exit and we record the real outcome. This is what feeds your Strategy Analysis.
      </p>

      <div className="grid grid-cols-3 gap-4">
        <Stat label="Open positions" value={openTrades.length} />
        <Stat label="Won today" value={won} color="text-bullish-text" />
        <Stat label="Lost today" value={lost} color="text-bearish-text" />
      </div>

      <section>
        <div className="flex items-center justify-between mb-2">
          <button onClick={() => setOpenCollapsed((c) => !c)} className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-text-faint hover:text-text-secondary">
            <ChevronRight size={12} className={`transition-transform ${openCollapsed ? "" : "rotate-90"}`} />
            Open positions{openTrades.length > 0 ? ` (${openTrades.length})` : ""}
          </button>
          {openTrades.length > 0 && (
            <button onClick={clearAll} disabled={clearOpen.isPending} className="text-[11px] text-text-faint hover:text-bearish-text disabled:opacity-50 transition-colors">Clear all</button>
          )}
        </div>
        {!openCollapsed && (openTrades.length > 0 ? (
          <div className="space-y-1.5">{openTrades.map((t) => <OpenRow key={t.id} t={t} />)}</div>
        ) : (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">
            No open positions. Tap “Took it” on a signal in Today to start tracking one.
          </div>
        ))}
      </section>

      {days.length > 0 && (
        <section>
          <div className="flex items-center justify-between gap-3 mb-2">
            <h3 className="text-[11px] font-semibold uppercase tracking-wider text-text-faint">Closed trades</h3>
            <div className="flex items-center gap-3">
              <span className="text-[11px] text-text-faint tabular-nums">
                {dayWon}/{dayTrades.length} won · <span className={dayR >= 0 ? "text-bullish-text" : "text-bearish-text"}>{dayR >= 0 ? "+" : ""}{dayR.toFixed(1)}R</span>
              </span>
              <select value={day} onChange={(e) => setSelectedDay(e.target.value)}
                className="bg-surface-2 border border-border-default rounded-md px-2.5 py-1 text-[12px] text-text-primary focus:border-accent outline-none cursor-pointer">
                {days.map((d) => <option key={d} value={d}>{dayLabel(d)}</option>)}
              </select>
            </div>
          </div>
          {dayTrades.length > 0 ? (
            <div className="space-y-1.5">{dayTrades.map((t) => <ClosedRow key={t.id} t={t} />)}</div>
          ) : (
            <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">No closed trades on {dayLabel(day)}.</div>
          )}
        </section>
      )}
    </div>
  );
}
