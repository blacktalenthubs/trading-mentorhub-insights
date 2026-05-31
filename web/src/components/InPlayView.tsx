/** In-Play Volume Screener (spec 62) — professional, full-width screener table.
 *  Desktop: dense sortable table. Mobile: card rows. Real loading/empty/closed states.
 *  Lives as a tab inside Trade Ideas; rows open the symbol's chart.
 */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity, AlertTriangle, Zap, ChevronRight, ChevronUp, ChevronDown, Moon,
} from "lucide-react";
import { useInPlay } from "../api/hooks";
import { IN_PLAY_PRESETS, type InPlayEntry, type InPlayPreset } from "../pages/InPlay.types";

/* ── formatting ─────────────────────────────────────────────────────── */
function compact(n: number): string {
  if (!isFinite(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (a >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
}
const px = (n: number) => `$${n.toFixed(2)}`;

/* ── sort state ─────────────────────────────────────────────────────── */
type SortKey = "rank" | "symbol" | "last_price" | "pct_change" | "rvol" | "dollar_vol" | "market_cap";
const NUMERIC: SortKey[] = ["rank", "last_price", "pct_change", "rvol", "dollar_vol", "market_cap"];

const COLS: { key: SortKey; label: string; align: "left" | "right"; cls?: string }[] = [
  { key: "rank", label: "#", align: "left", cls: "w-10" },
  { key: "symbol", label: "Symbol", align: "left" },
  { key: "last_price", label: "Price", align: "right" },
  { key: "pct_change", label: "% Chg", align: "right" },
  { key: "rvol", label: "RVOL", align: "right" },
  { key: "dollar_vol", label: "$ Vol", align: "right" },
  { key: "market_cap", label: "Mkt Cap", align: "right" },
];

function SetupBadge({ e }: { e: InPlayEntry }) {
  if (!e.setup) return <span className="text-text-faint text-xs">—</span>;
  return (
    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-accent bg-accent/10 border border-accent/20 px-2 py-0.5 rounded-md whitespace-nowrap">
      <Zap className="h-3 w-3" />{e.setup.pattern || "Setup"}
    </span>
  );
}

function Pct({ v }: { v: number }) {
  const up = v >= 0;
  return <span className={`font-mono ${up ? "text-bullish-text" : "text-bearish-text"}`}>{up ? "+" : ""}{v.toFixed(2)}%</span>;
}

function RvolCell({ v, max }: { v: number; max: number }) {
  const w = Math.max(4, Math.min(100, (v / (max || 1)) * 100));
  const hot = v >= 2;
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="hidden lg:block w-16 h-1.5 rounded-full bg-surface-3 overflow-hidden">
        <div className={`h-full rounded-full ${hot ? "bg-accent" : "bg-text-faint/50"}`} style={{ width: `${w}%` }} />
      </div>
      <span className={`font-mono ${hot ? "text-accent" : "text-text-secondary"}`}>{v.toFixed(1)}x</span>
    </div>
  );
}

/* ── states ─────────────────────────────────────────────────────────── */
function EmptyState({ marketOpen, filtered }: { marketOpen: boolean; filtered: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-12 h-12 rounded-xl bg-surface-2 border border-border-subtle flex items-center justify-center mb-4">
        {marketOpen ? <Activity className="h-6 w-6 text-text-faint" /> : <Moon className="h-6 w-6 text-text-faint" />}
      </div>
      {marketOpen ? (
        <>
          <p className="text-text-secondary font-medium">No names match this view</p>
          <p className="text-text-faint text-sm mt-1">{filtered ? "Try a different preset or clear filters." : "The market's quiet — check back shortly."}</p>
        </>
      ) : (
        <>
          <p className="text-text-secondary font-medium">The desk is closed</p>
          <p className="text-text-faint text-sm mt-1">In-play movers refresh when the bell rings — 9:30&nbsp;AM&nbsp;ET, Mon–Fri.</p>
        </>
      )}
    </div>
  );
}

function SkeletonRows() {
  return (
    <div className="space-y-px">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-11 bg-surface-1/60 animate-pulse rounded" />
      ))}
    </div>
  );
}

/* ── main ───────────────────────────────────────────────────────────── */
export default function InPlayView() {
  const [preset, setPreset] = useState<InPlayPreset>("any");
  const [hasSetup, setHasSetup] = useState(false);
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "rank", dir: "asc" });
  const { data, isLoading, isError } = useInPlay(preset, hasSetup);
  const navigate = useNavigate();
  const openChart = (s: string) => navigate(`/trading?symbol=${encodeURIComponent(s)}`);

  const rows = useMemo(() => {
    const list = [...(data?.entries ?? [])];
    list.sort((a, b) => {
      const dir = sort.dir === "asc" ? 1 : -1;
      if (sort.key === "symbol") return a.symbol.localeCompare(b.symbol) * dir;
      return ((a[sort.key] as number) - (b[sort.key] as number)) * dir;
    });
    return list;
  }, [data, sort]);

  const maxRvol = useMemo(() => Math.max(1, ...rows.map((r) => r.rvol)), [rows]);
  const captured = data?.captured_at ? new Date(`${data.captured_at}Z`) : null;

  function toggleSort(key: SortKey) {
    setSort((s) =>
      s.key === key
        ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
        : { key, dir: NUMERIC.includes(key) ? "desc" : "asc" });
  }

  return (
    <div className="space-y-4">
      {/* Title + status */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-bold text-text-primary flex items-center gap-2">
            <Activity className="h-4 w-4 text-accent" /> Top movers
            <span className="text-text-faint font-normal text-sm">· by relative volume</span>
          </h2>
          <p className="text-[11px] text-text-faint mt-0.5">
            What the whole market is doing on volume right now — not just your watchlist.
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-text-faint">
          {data?.market_open ? (
            <span className="inline-flex items-center gap-1.5 text-bullish-text">
              <span className="w-1.5 h-1.5 rounded-full bg-bullish animate-pulse" /> Live
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5"><Moon className="h-3 w-3" /> Closed</span>
          )}
          {captured && <span>· {captured.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</span>}
          {rows.length > 0 && <span>· {rows.length} names</span>}
          {data?.stale && (
            <span className="inline-flex items-center gap-1 text-amber-400"><AlertTriangle className="h-3 w-3" /> delayed</span>
          )}
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex flex-wrap gap-1.5">
          {IN_PLAY_PRESETS.map((p) => (
            <button
              key={p.id}
              onClick={() => setPreset(p.id)}
              className={`text-xs px-3 py-1.5 rounded-lg border font-medium transition-colors ${
                preset === p.id
                  ? "bg-accent/15 text-accent border-accent/30"
                  : "bg-surface-2 text-text-muted border-border-subtle hover:text-text-primary hover:border-border-default"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-xs text-text-muted cursor-pointer select-none">
          <input type="checkbox" checked={hasSetup} onChange={(e) => setHasSetup(e.target.checked)} className="accent-accent" />
          Has setup
        </label>
      </div>

      {/* Body */}
      <div className="bg-surface-1 border border-border-subtle rounded-xl overflow-hidden">
        {isLoading ? (
          <div className="p-3"><SkeletonRows /></div>
        ) : isError ? (
          <div className="py-16 text-center text-sm text-bearish-text">Couldn't load the in-play list. Retrying…</div>
        ) : rows.length === 0 ? (
          <EmptyState marketOpen={!!data?.market_open} filtered={preset !== "any" || hasSetup} />
        ) : (
          <>
            {/* Desktop table */}
            <table className="hidden md:table w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wider text-text-faint">
                  {COLS.map((c) => {
                    const active = sort.key === c.key;
                    return (
                      <th
                        key={c.key}
                        onClick={() => toggleSort(c.key)}
                        className={`py-2.5 px-3 font-semibold cursor-pointer select-none hover:text-text-secondary ${c.align === "right" ? "text-right" : "text-left"} ${c.cls ?? ""}`}
                      >
                        <span className={`inline-flex items-center gap-1 ${c.align === "right" ? "justify-end" : ""}`}>
                          {c.label}
                          {active && (sort.dir === "asc" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />)}
                        </span>
                      </th>
                    );
                  })}
                  <th className="py-2.5 px-3 text-left font-semibold">Setup</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr
                    key={e.symbol}
                    onClick={() => openChart(e.symbol)}
                    className="border-b border-border-subtle/40 last:border-0 hover:bg-surface-2/50 cursor-pointer transition-colors"
                  >
                    <td className="py-2.5 px-3 font-mono text-text-faint">{e.rank}</td>
                    <td className="py-2.5 px-3">
                      <span className="font-bold text-text-primary">{e.symbol}</span>
                      {e.sector && <span className="text-text-faint text-[11px] ml-2 hidden xl:inline">{e.sector}</span>}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-text-primary">{px(e.last_price)}</td>
                    <td className="py-2.5 px-3 text-right"><Pct v={e.pct_change} /></td>
                    <td className="py-2.5 px-3"><RvolCell v={e.rvol} max={maxRvol} /></td>
                    <td className="py-2.5 px-3 text-right font-mono text-text-secondary">{compact(e.dollar_vol)}</td>
                    <td className="py-2.5 px-3 text-right font-mono text-text-secondary">{compact(e.market_cap)}</td>
                    <td className="py-2.5 px-3"><SetupBadge e={e} /></td>
                    <td className="py-2.5 px-2 text-right"><ChevronRight className="h-4 w-4 text-text-faint" /></td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Mobile cards */}
            <div className="md:hidden divide-y divide-border-subtle/40">
              {rows.map((e) => (
                <button key={e.symbol} onClick={() => openChart(e.symbol)} className="w-full text-left px-4 py-3 hover:bg-surface-2/40 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-mono text-xs text-text-faint w-4">{e.rank}</span>
                      <span className="font-bold text-text-primary">{e.symbol}</span>
                      <Pct v={e.pct_change} />
                      <SetupBadge e={e} />
                    </div>
                    <span className="font-mono text-sm text-text-primary">{px(e.last_price)}</span>
                  </div>
                  <div className="flex items-center gap-3 mt-1.5 pl-6 text-[11px] text-text-muted font-mono">
                    <span className={e.rvol >= 2 ? "text-accent" : ""}>RVOL {e.rvol.toFixed(1)}x</span>
                    <span>{compact(e.dollar_vol)}</span>
                    <span>{compact(e.market_cap)} cap</span>
                  </div>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
