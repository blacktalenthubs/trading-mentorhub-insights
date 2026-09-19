/** P&L Calendar tab — month grid of realized daily P&L (full account history),
 *  click a day to drill into that day's trades, with a summary-stats strip.
 *  Reads matched_trades ∪ trades_1099 via /daily/calendar, /daily/day, /daily/stats
 *  (options already scaled ×100 server-side). Read-only. */

import { useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, TrendingUp, TrendingDown } from "lucide-react";
import {
  useDailyCalendar,
  useDayDetail,
  useTradeStats,
  type CalendarDay,
  type CalendarTrade,
  type StatsRange,
} from "../api/hooks";

const usd = (n: number) =>
  (n < 0 ? "-" : "") +
  Math.abs(n).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });

const usd2 = (n: number) =>
  (n < 0 ? "-" : "") +
  Math.abs(n).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  });

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function todayMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}
function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}
function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// Cell background for a day's P&L: two-tier heatmap using the app's bullish/bearish tokens.
function cellClasses(pnl: number, maxAbs: number, selected: boolean, isToday: boolean): string {
  const base =
    "relative flex flex-col justify-between rounded-lg border p-1.5 text-left transition " +
    "min-h-[54px] sm:min-h-[68px] focus:outline-none focus-visible:ring-2 focus-visible:ring-accent ";
  const ring = selected ? "ring-2 ring-accent " : isToday ? "ring-1 ring-accent/60 " : "";
  const strong = maxAbs > 0 && Math.abs(pnl) >= 0.55 * maxAbs;
  let tone: string;
  if (pnl > 0) tone = strong ? "bg-bullish border-transparent text-white" : "bg-bullish/15 border-transparent text-bullish-text";
  else if (pnl < 0) tone = strong ? "bg-bearish border-transparent text-white" : "bg-bearish/15 border-transparent text-bearish-text";
  else tone = "bg-surface-2 border-border-subtle text-text-faint";
  return base + ring + tone + " hover:brightness-110 cursor-pointer";
}

function StatCard({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg";
  sub?: string;
}) {
  const color = tone === "pos" ? "text-bullish-text" : tone === "neg" ? "text-bearish-text" : "text-text-primary";
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-1 px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-text-faint">{label}</div>
      <div className={`mt-0.5 font-mono text-lg font-semibold tabular-nums ${color}`}>{value}</div>
      {sub ? <div className="text-[11px] text-text-faint">{sub}</div> : null}
    </div>
  );
}

const RANGES: { key: StatsRange; label: string }[] = [
  { key: "month", label: "Month" },
  { key: "quarter", label: "Quarter" },
  { key: "year", label: "Year" },
  { key: "all", label: "All" },
];

export default function PnLCalendarView() {
  const [month, setMonth] = useState<string>(todayMonth());
  const [selected, setSelected] = useState<string | null>(null);
  const [range, setRange] = useState<StatsRange>("all");

  const cal = useDailyCalendar(month);
  const stats = useTradeStats(range);
  const day = useDayDetail(selected);

  const byDate = useMemo(() => {
    const m: Record<string, CalendarDay> = {};
    for (const d of cal.data?.days ?? []) m[d.date] = d;
    return m;
  }, [cal.data]);

  const maxAbs = useMemo(() => {
    let x = 0;
    for (const d of cal.data?.days ?? []) x = Math.max(x, Math.abs(d.pnl));
    return x;
  }, [cal.data]);

  // Build the Mon–Sun grid for the month: leading blanks + each day + trailing blanks.
  const [yy, mm] = month.split("-").map(Number);
  const monthTotal = (cal.data?.days ?? []).reduce((s, d) => s + d.pnl, 0);
  const cells = useMemo(() => {
    const first = new Date(yy, mm - 1, 1);
    const lead = (first.getDay() + 6) % 7; // days since Monday
    const daysInMonth = new Date(yy, mm, 0).getDate();
    const out: (string | null)[] = [];
    for (let i = 0; i < lead; i++) out.push(null);
    for (let d = 1; d <= daysInMonth; d++)
      out.push(`${yy}-${String(mm).padStart(2, "0")}-${String(d).padStart(2, "0")}`);
    while (out.length % 7 !== 0) out.push(null);
    return out;
  }, [yy, mm]);

  const iso = todayISO();

  return (
    <div className="space-y-4">
      {/* Range toggle + stats strip */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-text-primary">Performance</h3>
        <div className="flex gap-1 rounded-lg bg-surface-2 p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                range === r.key ? "bg-surface-3 text-accent" : "text-text-faint hover:text-text-secondary"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatCard
          label="Realized"
          value={stats.data ? usd(stats.data.realized) : "—"}
          tone={stats.data && stats.data.realized < 0 ? "neg" : "pos"}
          sub={stats.data ? `${stats.data.trade_count} trades · ${stats.data.trading_days} days` : undefined}
        />
        <StatCard
          label="Win rate"
          value={stats.data ? `${Math.round(stats.data.win_rate * 100)}%` : "—"}
          sub={stats.data ? `${stats.data.wins}W / ${stats.data.losses}L` : undefined}
        />
        <StatCard
          label="Avg win / loss"
          value={stats.data ? `${usd(stats.data.avg_win)} / ${usd(stats.data.avg_loss)}` : "—"}
          sub={stats.data ? `PF ${stats.data.profit_factor ?? "∞"}` : undefined}
        />
        <StatCard
          label="Best / worst day"
          value={stats.data && stats.data.best_day ? `${usd(stats.data.best_day.pnl)} / ${usd(stats.data.worst_day?.pnl ?? 0)}` : "—"}
          sub={
            stats.data && stats.data.streak.count > 0
              ? `${stats.data.streak.count}-day ${stats.data.streak.type} streak`
              : undefined
          }
        />
      </div>

      {/* Month navigation */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setMonth(shiftMonth(month, -1)); setSelected(null); }}
            className="rounded-md border border-border-subtle bg-surface-1 p-1.5 text-text-secondary hover:text-text-primary"
            aria-label="Previous month"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <div className="min-w-[9rem] text-center text-sm font-semibold text-text-primary">
            {MONTHS[mm - 1]} {yy}
          </div>
          <button
            onClick={() => { setMonth(shiftMonth(month, 1)); setSelected(null); }}
            className="rounded-md border border-border-subtle bg-surface-1 p-1.5 text-text-secondary hover:text-text-primary"
            aria-label="Next month"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        <div className={`font-mono text-sm font-semibold tabular-nums ${monthTotal >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
          {monthTotal >= 0 ? "+" : ""}{usd(monthTotal)}
        </div>
      </div>

      {/* Calendar grid */}
      <div>
        <div className="mb-1 grid grid-cols-7 gap-1.5">
          {DOW.map((d) => (
            <div key={d} className="text-center text-[10px] font-medium uppercase tracking-wide text-text-faint">
              {d}
            </div>
          ))}
        </div>
        {cal.isLoading ? (
          <div className="py-10 text-center text-sm text-text-faint">Loading…</div>
        ) : (
          <div className="grid grid-cols-7 gap-1.5">
            {cells.map((date, i) => {
              if (!date) return <div key={`b${i}`} className="min-h-[54px] rounded-lg sm:min-h-[68px]" />;
              const d = byDate[date];
              const dayNum = Number(date.slice(8, 10));
              const isToday = date === iso;
              if (!d) {
                return (
                  <button
                    key={date}
                    onClick={() => setSelected(date)}
                    className={cellClasses(0, maxAbs, selected === date, isToday)}
                  >
                    <span className="text-[10px] tabular-nums">{dayNum}</span>
                  </button>
                );
              }
              return (
                <button
                  key={date}
                  onClick={() => setSelected(date)}
                  className={cellClasses(d.pnl, maxAbs, selected === date, isToday)}
                  title={`${date}: ${usd2(d.pnl)} · ${d.trades} trade${d.trades === 1 ? "" : "s"}`}
                >
                  <span className="text-[10px] tabular-nums opacity-80">
                    {dayNum}{d.hit ? " ✓" : ""}
                  </span>
                  <span className="truncate font-mono text-[11px] font-semibold tabular-nums sm:text-xs">
                    {d.pnl >= 0 ? "+" : ""}{usd(d.pnl)}
                  </span>
                  <span className="text-[9px] opacity-70">{d.trades}t · {d.wins}/{d.losses}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Day drill-down */}
      {selected && (
        <DayDrawer date={selected} detail={day.data} loading={day.isLoading} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

function DayDrawer({
  date,
  detail,
  loading,
  onClose,
}: {
  date: string;
  detail: import("../api/hooks").DayDetail | undefined;
  loading: boolean;
  onClose: () => void;
}) {
  const heading = new Date(date + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  const total = detail?.total ?? 0;
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-3 sm:p-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold text-text-primary">{heading}</span>
          {detail && (
            <span className={`font-mono text-sm font-semibold tabular-nums ${total >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
              {total >= 0 ? "+" : ""}{usd2(total)} · {detail.trade_count} · {detail.wins}W/{detail.losses}L
            </span>
          )}
        </div>
        <button onClick={onClose} className="text-xs text-text-faint hover:text-text-secondary">Close</button>
      </div>
      {loading ? (
        <div className="py-6 text-center text-sm text-text-faint">Loading…</div>
      ) : !detail || detail.trades.length === 0 ? (
        <div className="py-6 text-center text-sm text-text-faint">No closed trades on this day.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-border-subtle text-[10px] uppercase tracking-wide text-text-faint">
                <th className="py-1.5 pr-2 font-semibold">Symbol</th>
                <th className="py-1.5 pr-2 font-semibold">Type</th>
                <th className="py-1.5 pr-2 font-semibold">Qty</th>
                <th className="py-1.5 pr-2 font-semibold">Entry→Exit</th>
                <th className="py-1.5 pr-2 font-semibold">Hold</th>
                <th className="py-1.5 pl-2 text-right font-semibold">P&amp;L</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {detail.trades.map((t, i) => (
                <TradeRow key={i} t={t} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TradeRow({ t }: { t: CalendarTrade }) {
  const isOpt = t.asset_type === "option";
  const typeLabel = (t.trade_type || "").replace("_", " ") || (isOpt ? "option" : "stock");
  const hold =
    t.holding_days == null ? "—" : t.holding_days === 0 ? "intraday" : `${t.holding_days}d`;
  return (
    <tr className="border-b border-border-subtle/60 last:border-0">
      <td className="py-1.5 pr-2">
        <span className="font-sans font-semibold text-text-primary">{t.symbol}</span>
        {isOpt && (
          <span className="ml-1 rounded bg-surface-3 px-1 py-0.5 font-sans text-[9px] text-text-muted">opt</span>
        )}
        {isOpt && t.contract && (
          <div className="font-sans text-[10px] text-text-faint">{t.contract}</div>
        )}
      </td>
      <td className="py-1.5 pr-2 font-sans text-text-secondary">
        <span className="inline-flex items-center gap-1">
          {t.pnl >= 0 ? <TrendingUp className="h-3 w-3 text-bullish-text" /> : <TrendingDown className="h-3 w-3 text-bearish-text" />}
          {typeLabel}
        </span>
      </td>
      <td className="py-1.5 pr-2 text-text-secondary">{t.quantity ?? "—"}</td>
      <td className="py-1.5 pr-2 text-text-secondary">
        {t.entry_price != null ? usd2(t.entry_price) : "—"}
        {t.exit_price != null ? ` → ${usd2(t.exit_price)}` : ""}
      </td>
      <td className="py-1.5 pr-2 text-text-faint">{hold}</td>
      <td className={`py-1.5 pl-2 text-right font-semibold ${t.pnl >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
        {t.pnl >= 0 ? "+" : ""}{usd2(t.pnl)}
      </td>
    </tr>
  );
}
