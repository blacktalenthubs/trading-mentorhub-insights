/** Performance — which entry patterns actually work.
 *  Every delivered alert is replayed against price. DAY win = reached a real profit (+1R off
 *  the stop) BEFORE the stop hit (stopped out first = loss). SWING/LONG win = above entry
 *  with the stop (a daily close below the level) never hit. This page reads the
 *  precomputed report (/performance/report, published by the offline scorer) and, client
 *  side, ranks patterns and groups alerts by date across a Daily / Weekly / Monthly lens.
 *  (Replaces the old EOD/Strategy/Declined tabs entirely.)
 */
import { useMemo, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, ChevronLeft, ChevronRight, Search, X, Share2 } from "lucide-react";
import { toast } from "../components/Toast";
import { usePerformanceReport, usePerformanceShare, type ScoredAlert } from "../api/hooks";

type Gran = "daily" | "weekly" | "monthly";
type LbKey = "pattern" | "wr" | "ae" | "mfe" | "mae" | "n";
type AlKey = "symbol" | "pattern" | "entry" | "stop" | "intraday_high" | "intraday_low" | "eod_close" | "mfe_pct" | "max_dd_pct" | "result";

export function median(xs: number[]): number {
  const a = xs.filter((x) => x != null && !Number.isNaN(x)).sort((p, q) => p - q);
  return a.length ? a[Math.floor(a.length / 2)] : 0;
}
export function pct(x: number): string {
  return `${x >= 0 ? "+" : ""}${x.toFixed(1)}%`;
}
export function fmtDay(d: string): string {
  return new Date(d + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}
function fmtShort(d: string): string {
  return new Date(d + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
function mondayOf(d: string): string {
  const dt = new Date(d + "T00:00:00");
  const g = dt.getDay();
  dt.setDate(dt.getDate() + (g === 0 ? -6 : 1 - g));
  return dt.toISOString().slice(0, 10);
}
export function wrColor(wr: number): string {
  return wr >= 50 ? "#4ade80" : wr >= 38 ? "#e0a533" : "#f87171";
}

interface Period { label: string; dates: Set<string>; count: number; }
function buildPeriods(alerts: ScoredAlert[], gran: Gran): Period[] {
  const dates = Array.from(new Set(alerts.map((a) => a.session_date))).sort().reverse();
  const count = (ds: Set<string>) => alerts.filter((a) => ds.has(a.session_date)).length;
  if (gran === "daily") {
    return dates.map((d) => { const s = new Set([d]); return { label: fmtDay(d), dates: s, count: count(s) }; });
  }
  const groups = new Map<string, string[]>();
  for (const d of dates) {
    const key = gran === "weekly" ? mondayOf(d) : d.slice(0, 7);
    const arr = groups.get(key);
    if (arr) arr.push(d); else groups.set(key, [d]);
  }
  return Array.from(groups.entries())
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([key, ds]) => {
      const sorted = ds.slice().sort();
      const label = gran === "weekly"
        ? `Week of ${fmtShort(sorted[0])} – ${fmtShort(sorted[sorted.length - 1])}`
        : new Date(key + "-01T00:00:00").toLocaleDateString("en-US", { month: "long", year: "numeric" });
      const s = new Set(ds);
      return { label, dates: s, count: count(s) };
    });
}

export interface LbRow { pattern: string; style: string; n: number; wr: number; ae: number; mfe: number; mae: number; }
export function aggregate(alerts: ScoredAlert[]): LbRow[] {
  const byPat = new Map<string, ScoredAlert[]>();
  for (const a of alerts) { const arr = byPat.get(a.pattern); if (arr) arr.push(a); else byPat.set(a.pattern, [a]); }
  const rows: LbRow[] = [];
  byPat.forEach((items, pattern) => {
    const closed = items.filter((i) => !i.open);
    if (!closed.length) return;
    const wins = closed.filter((i) => i.result === "WIN").length;
    const ae = items.filter((i) => i.above_entry).length;
    rows.push({
      pattern, style: items[0].style, n: closed.length,
      wr: Math.round((wins * 100) / closed.length),
      ae: Math.round((ae * 100) / items.length),
      mfe: median(items.map((i) => i.mfe_pct)),
      mae: median(items.map((i) => i.mae_pct)),
    });
  });
  return rows.sort((a, b) => b.wr - a.wr || b.n - a.n);
}

export interface DateGroup { date: string; items: ScoredAlert[]; wr: number; mfe: number; }
export function groupByDate(alerts: ScoredAlert[]): DateGroup[] {
  const byd = new Map<string, ScoredAlert[]>();
  for (const a of alerts) { const arr = byd.get(a.session_date); if (arr) arr.push(a); else byd.set(a.session_date, [a]); }
  return Array.from(byd.entries())
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([date, items]) => {
      const closed = items.filter((i) => !i.open);
      const wins = closed.filter((i) => i.result === "WIN").length;
      return { date, items, wr: closed.length ? Math.round((wins * 100) / closed.length) : 0, mfe: median(items.map((i) => i.mfe_pct)) };
    });
}

const STYLE_TAG: Record<string, string> = { Day: "text-sky-400", Swing: "text-amber-400", Long: "text-bullish-text" };

export default function RealTradesPage() {
  const { data, isLoading, error } = usePerformanceReport();
  const navigate = useNavigate();
  const alerts = useMemo(() => data?.alerts ?? [], [data]);
  const share = usePerformanceShare();
  const [gran, setGran] = useState<Gran>("weekly");
  const [idx, setIdx] = useState(0);
  const [q, setQ] = useState("");
  const [styleF, setStyleF] = useState<"all" | "day" | "swing" | "crypto">("all");
  useEffect(() => { setIdx(0); }, [gran]);

  const periods = useMemo(() => buildPeriods(alerts, gran), [alerts, gran]);
  const period = periods.length ? periods[Math.min(idx, periods.length - 1)] : null;
  const inPeriod = useMemo(
    () => (period ? alerts.filter((a) => period.dates.has(a.session_date)) : []),
    [alerts, period],
  );
  // Share ONLY the period in view (the Daily/Weekly/Monthly selection) — so a
  // single Friday can be sent on its own. The backend scopes the snapshot to
  // [start, end] and stores the label for the public page's header.
  const onShare = async () => {
    try {
      const ds = period ? Array.from(period.dates).sort() : [];
      const body = ds.length
        ? { start: ds[0], end: ds[ds.length - 1], label: period!.label }
        : undefined;
      const { token, url: canonical } = await share.mutateAsync(body);
      // Prefer the canonical URL the backend builds (points at the primary app
      // domain that serves the report to logged-out visitors). Fall back to the
      // current origin only if an older backend omits it (e.g. local dev).
      const url = canonical || `${window.location.origin}/public/performance/${token}`;
      await navigator.clipboard.writeText(url);
      toast.success(period ? `Public link copied — ${period.label}` : "Public link copied to clipboard");
    } catch {
      toast.error("Could not create share link");
    }
  };
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    // Crypto (24/7, noisier) is NEVER merged with stocks — it lives in its own tab. Day/Swing/All
    // are stocks-only; the Crypto tab shows crypto only. Detected by the -USD pair suffix.
    return inPeriod.filter((a) => {
      const cr = a.symbol.includes("-USD");
      const ok =
        styleF === "crypto" ? cr
        : styleF === "day" ? (a.style === "Day" && !cr)
        : styleF === "swing" ? (a.style !== "Day" && !cr)
        : !cr;   // "all" = all STOCKS (crypto excluded)
      return ok && (!s || a.symbol.toLowerCase().includes(s));
    });
  }, [inPeriod, q, styleF]);
  const lb = useMemo(() => aggregate(filtered), [filtered]);
  const groups = useMemo(() => groupByDate(filtered), [filtered]);
  // recommendation — the period's best patterns to trade (enough sample + real win rate)
  const recommended = useMemo(() => lb.filter((r) => r.n >= 4 && r.wr >= 45).slice(0, 3), [lb]);

  // sortable leaderboard (default: win rate desc)
  const [lbSort, setLbSort] = useState<{ k: LbKey; d: 1 | -1 }>({ k: "wr", d: -1 });
  const sortedLb = useMemo(() => {
    const c = [...lb];
    c.sort((a, b) => {
      const av = a[lbSort.k]; const bv = b[lbSort.k];
      const r = typeof av === "string" ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return r * lbSort.d;
    });
    return c;
  }, [lb, lbSort]);
  const lbClick = (k: LbKey) => setLbSort((s) => (s.k === k ? { k, d: (s.d * -1) as 1 | -1 } : { k, d: k === "pattern" ? 1 : -1 }));
  const lbArrow = (k: LbKey) => (lbSort.k === k ? (lbSort.d < 0 ? " ↓" : " ↑") : "");

  // sortable alert list (within each date group; null = chronological as fired)
  const [alSort, setAlSort] = useState<{ k: AlKey; d: 1 | -1 } | null>(null);
  const alClick = (k: AlKey) => setAlSort((s) => (s && s.k === k ? { k, d: (s.d * -1) as 1 | -1 } : { k, d: k === "symbol" || k === "pattern" || k === "result" ? 1 : -1 }));
  const alArrow = (k: AlKey) => (alSort && alSort.k === k ? (alSort.d < 0 ? " ↓" : " ↑") : "");

  const closed = filtered.filter((a) => !a.open);
  const wins = closed.filter((a) => a.result === "WIN").length;
  const overallWr = closed.length ? Math.round((wins * 100) / closed.length) : 0;
  const medMfe = median(filtered.map((a) => a.mfe_pct));
  const medMae = median(filtered.map((a) => a.mae_pct));

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden p-4 md:p-6 space-y-4">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-mono text-sm tracking-[0.2em] uppercase text-amber-400 font-semibold">Performance</h1>
          <p className="text-xs text-text-faint mt-1">Which entry patterns actually work — scored against price. Day trades win if they hit a real profit before the stop; swings if they're holding above entry.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={onShare} disabled={share.isPending || !alerts.length} title={period ? `Create a public link for ${period.label} only` : "Create a public link"} className="flex items-center gap-1.5 rounded-lg border border-border-subtle px-3 py-1.5 text-xs font-medium text-text-muted transition-colors hover:border-accent hover:text-text-primary disabled:opacity-50"><Share2 className="h-3.5 w-3.5" /> {share.isPending ? "…" : "Share"}</button>
          <div className="flex gap-1 rounded-lg border border-border-subtle bg-surface-2 p-1">
            {(["daily", "weekly", "monthly"] as const).map((g) => (
              <button key={g} onClick={() => setGran(g)}
                className={`px-3 py-1.5 text-xs font-mono rounded-md capitalize transition-colors ${gran === g ? "bg-surface-3 text-text-primary" : "text-text-muted hover:text-text-primary"}`}>
                {g}
              </button>
            ))}
          </div>
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-text-muted text-sm py-10 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading performance…
        </div>
      )}
      {error && <div className="text-sm text-bearish-text bg-bearish-subtle rounded-lg p-3">{error.message}</div>}
      {!isLoading && !error && !alerts.length && (
        <div className="text-sm text-text-muted bg-surface-2 border border-border-subtle rounded-lg p-6 text-center">
          No scored alerts yet — the nightly scorer hasn't published a report.
        </div>
      )}

      {!!alerts.length && period && (
        <>
          <div className="flex items-center gap-3 bg-surface-2 border border-border-subtle rounded-lg px-3 py-2">
            <button disabled={idx >= periods.length - 1} onClick={() => setIdx((i) => Math.min(periods.length - 1, i + 1))}
              className="p-1.5 rounded-md bg-surface-3 text-text-muted disabled:opacity-30 hover:text-text-primary"><ChevronLeft className="h-4 w-4" /></button>
            <span className="font-mono text-sm font-semibold text-text-primary">{period.label}</span>
            <button disabled={idx <= 0} onClick={() => setIdx((i) => Math.max(0, i - 1))}
              className="p-1.5 rounded-md bg-surface-3 text-text-muted disabled:opacity-30 hover:text-text-primary"><ChevronRight className="h-4 w-4" /></button>
            {idx !== 0 && <button onClick={() => setIdx(0)} className="font-mono text-xs text-sky-400">Latest</button>}
            <span className="ml-auto font-mono text-xs text-text-faint">{filtered.length} alerts · {period.dates.size} session{period.dates.size > 1 ? "s" : ""} · {overallWr}% win</span>
          </div>

          {/* search + day/swing filter */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="relative flex-1 min-w-[180px] max-w-xs">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-faint pointer-events-none" />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a stock…"
                className="w-full bg-surface-2 border border-border-subtle rounded-lg pl-9 pr-8 py-2 text-sm text-text-primary placeholder:text-text-faint font-mono focus:outline-none focus:border-sky-500" />
              {q && <button onClick={() => setQ("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-text-faint hover:text-text-primary"><X className="h-4 w-4" /></button>}
            </div>
            <div className="flex gap-1 bg-surface-2 border border-border-subtle rounded-lg p-1">
              {([["all", "All stocks"], ["day", "Day trade"], ["swing", "Swing"], ["crypto", "Crypto"]] as const).map(([v, l]) => (
                <button key={v} onClick={() => setStyleF(v)}
                  className={`px-3 py-1.5 text-xs font-mono rounded-md transition-colors ${styleF === v ? "bg-surface-3 text-text-primary" : "text-text-muted hover:text-text-primary"}`}>{l}</button>
              ))}
            </div>
          </div>

          {recommended.length > 0 && !q && (
            <div className="bg-surface-2 border border-border-subtle rounded-lg px-4 py-3" style={{ borderLeft: "2px solid #4ade80" }}>
              <div className="text-[11px] font-mono uppercase tracking-wide text-bullish-text mb-2">★ Best patterns to trade · {period.label}</div>
              <div className="flex gap-2 flex-wrap">
                {recommended.map((r) => (
                  <div key={r.pattern} className="bg-surface-0 border border-border-subtle rounded-md px-3 py-1.5 text-xs">
                    <span className="font-semibold text-text-primary">{r.pattern}</span>
                    <span className="font-mono ml-2" style={{ color: wrColor(r.wr) }}>{r.wr}%</span>
                    <span className="font-mono text-text-faint ml-2">peak {pct(r.mfe)} · n={r.n}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="flex gap-6 flex-wrap bg-surface-0 border border-border-subtle rounded-lg px-4 py-3">
            {[
              { v: `${filtered.length}`, l: "alerts scored", c: "text-text-primary" },
              { v: `${lb.length}`, l: "entry patterns", c: "text-text-primary" },
              { v: `${overallWr}%`, l: "win (closed)", c: "text-bullish-text" },
              { v: pct(medMfe), l: "avg peak gain", c: "text-bullish-text" },
              { v: pct(medMae), l: "avg drop", c: "text-bearish-text" },
            ].map((m) => (
              <div key={m.l} className="flex flex-col">
                <span className={`font-mono text-lg font-semibold ${m.c}`}>{m.v}</span>
                <span className="text-[10px] uppercase tracking-wide text-text-faint mt-0.5">{m.l}</span>
              </div>
            ))}
          </div>

          <SectionTitle>Entry patterns, ranked · by win rate</SectionTitle>
          <p className="text-[11px] text-text-faint -mt-2">Day-trade win = reached a real profit (1× the risk to the stop) BEFORE the stop was hit — stopped out first is a loss, so the stop counts. Swing win = above entry with the stop (a daily close below the level) never hit. "Above" = intraday high cleared entry. n≥1, closed only.</p>
          <div className="bg-surface-2 border border-border-subtle rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[560px]">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wide text-text-faint select-none">
                    <th className="text-center px-3 py-2.5 font-semibold w-8">#</th>
                    <th onClick={() => lbClick("pattern")} className="text-left px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Entry pattern{lbArrow("pattern")}</th>
                    <th onClick={() => lbClick("wr")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Win rate{lbArrow("wr")}</th>
                    <th onClick={() => lbClick("ae")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Above{lbArrow("ae")}</th>
                    <th onClick={() => lbClick("mfe")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Peak Gain{lbArrow("mfe")}</th>
                    <th onClick={() => lbClick("mae")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Max Drop{lbArrow("mae")}</th>
                    <th onClick={() => lbClick("n")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Alerts{lbArrow("n")}</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedLb.map((r, i) => (
                    <tr key={r.pattern} className="border-t border-border-subtle hover:bg-surface-3/40">
                      <td className="text-center px-3 py-3 font-mono text-text-faint">{i + 1}</td>
                      <td className="px-3 py-3 font-semibold text-text-primary">{r.pattern}</td>
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-2 justify-end">
                          <div className="w-24 h-2 bg-surface-0 rounded-full overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${Math.max(4, r.wr)}%`, background: wrColor(r.wr) }} />
                          </div>
                          <span className="font-mono text-sm font-semibold w-9 text-right" style={{ color: wrColor(r.wr) }}>{r.wr}%</span>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right font-mono text-text-muted">{r.ae}%</td>
                      <td className="px-3 py-3 text-right font-mono text-bullish-text">{pct(r.mfe)}</td>
                      <td className="px-3 py-3 text-right font-mono text-bearish-text">{pct(r.mae)}</td>
                      <td className="px-3 py-3 text-right font-mono text-text-muted">{r.n} <span className={`text-[10px] ${STYLE_TAG[r.style] ?? "text-text-faint"}`}>{r.style === "Day" ? "DAY" : r.style === "Swing" ? "SW" : "LT"}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <SectionTitle>Alerts, grouped by date</SectionTitle>
          <div className="bg-surface-2 border border-border-subtle rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[720px]">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wide text-text-faint select-none">
                    <th onClick={() => alClick("symbol")} className="text-left px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Sym{alArrow("symbol")}</th>
                    <th onClick={() => alClick("pattern")} className="text-left px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Setup{alArrow("pattern")}</th>
                    <th onClick={() => alClick("entry")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Entry{alArrow("entry")}</th>
                    <th onClick={() => alClick("stop")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Stop{alArrow("stop")}</th>
                    <th onClick={() => alClick("intraday_high")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Hi{alArrow("intraday_high")}</th>
                    <th onClick={() => alClick("intraday_low")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Lo{alArrow("intraday_low")}</th>
                    <th onClick={() => alClick("eod_close")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">EOD{alArrow("eod_close")}</th>
                    <th onClick={() => alClick("mfe_pct")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Peak{alArrow("mfe_pct")}</th>
                    <th onClick={() => alClick("max_dd_pct")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Max Drop{alArrow("max_dd_pct")}</th>
                    <th onClick={() => alClick("result")} className="text-right px-3 py-2.5 font-semibold cursor-pointer hover:text-text-muted">Result{alArrow("result")}</th>
                  </tr>
                </thead>
                <tbody>
                  {groups.map((g) => (
                    <GroupRows key={g.date} g={g} sort={alSort} onSym={(sym) => navigate(`/trading?symbol=${encodeURIComponent(sym)}`)} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-[10px] text-text-faint font-mono leading-relaxed pt-2">
            Every trade is scored only on price AFTER the alert fired — the time under Entry is when it fired, under Hi is when the high printed, so a move before entry never counts. Day trades scored on the session (5-min bars). Swing/long scored to now (daily bars). "Peak Gain" = the most it ran above entry · "Max Drop" = the most it fell below. Your watchlist, delivered alerts only. As of {data?.as_of ?? "—"}.
          </p>
        </>
      )}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 mt-4">
      <span className="font-mono text-[11px] tracking-[0.14em] uppercase text-amber-400">{children}</span>
      <span className="flex-1 h-px bg-border-subtle" />
    </div>
  );
}

function GroupRows({ g, sort, onSym }: { g: DateGroup; sort: { k: AlKey; d: 1 | -1 } | null; onSym: (s: string) => void }) {
  const items = useMemo(() => {
    if (!sort) return g.items;
    const c = [...g.items];
    c.sort((a, b) => {
      const av = a[sort.k]; const bv = b[sort.k];
      const r = typeof av === "string" && typeof bv === "string" ? av.localeCompare(bv) : (av as number) - (bv as number);
      return r * sort.d;
    });
    return c;
  }, [g.items, sort]);
  return (
    <>
      <tr className="bg-surface-0">
        <td colSpan={10} className="px-3 py-2 font-mono text-xs font-semibold text-text-primary border-t border-border-subtle">
          {fmtDay(g.date)}
          <span className="ml-3 font-normal text-text-faint">
            <span className="text-bullish-text font-semibold">{g.wr}% win</span> · {g.items.length} alerts · peak {pct(g.mfe)}
          </span>
        </td>
      </tr>
      {items.map((a, i) => {
        const win = a.result === "WIN";
        return (
          <tr key={`${a.symbol}-${a.session_date}-${i}`} className="border-t border-border-subtle hover:bg-surface-3/40 font-mono">
            <td onClick={() => onSym(a.symbol)} className="px-3 py-2 text-left font-bold text-text-primary cursor-pointer hover:text-sky-400">{a.symbol}</td>
            <td className="px-3 py-2 text-left text-text-muted text-[11px] font-sans">{a.pattern}</td>
            <td className="px-3 py-2 text-right">{a.entry.toFixed(2)}{a.alert_et && <span className="block text-[9px] text-text-faint">{a.alert_et}</span>}</td>
            <td className="px-3 py-2 text-right text-text-muted">{a.stop != null ? a.stop.toFixed(2) : "—"}</td>
            <td className={`px-3 py-2 text-right ${a.mfe_pct > 0 ? "text-bullish-text" : ""}`}>{a.intraday_high.toFixed(2)}{a.hi_et && <span className="block text-[9px] text-text-faint">@ {a.hi_et}</span>}</td>
            <td className={`px-3 py-2 text-right ${a.mae_pct < -0.5 ? "text-bearish-text" : ""}`}>{a.intraday_low.toFixed(2)}{a.lo_et && <span className="block text-[9px] text-text-faint">@ {a.lo_et}</span>}</td>
            <td className="px-3 py-2 text-right">{a.eod_close.toFixed(2)}{a.eod_et && <span className="block text-[9px] text-text-faint">{a.eod_et}</span>}</td>
            <td className="px-3 py-2 text-right text-bullish-text">{pct(a.mfe_pct)}</td>
            <td className="px-3 py-2 text-right text-bearish-text">{pct(a.max_dd_pct)}</td>
            <td className={`px-3 py-2 text-right text-[11px] font-semibold ${win ? "text-bullish-text" : "text-bearish-text"}`}>
              {a.open ? "· open" : win ? "✓ WIN" : `✗ LOSS ${a.realized_stop_pct != null ? pct(a.realized_stop_pct) : ""}`}
            </td>
          </tr>
        );
      })}
    </>
  );
}
