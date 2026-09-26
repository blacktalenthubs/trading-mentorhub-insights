/**
 * Premium Desk (Spec S3) — the ranked feed, desktop-grade terminal layout.
 *
 * Full-height, full-width: a dense ranked TABLE on the left (grouped by risk tier,
 * aligned columns, tabular numbers) and a sticky trade-sizing PANEL on the right that
 * follows the selected row. On mobile it collapses to the table alone and a row opens
 * the /premium-desk/:sym detail route. Reads market_reports[premium_desk] (the S2 scan).
 * Educational — verify the live chain before selling. READ-ONLY.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { usePremiumDesk, useLeapDesk, type PremiumDeskReport, type PremiumDeskRow, type LeapDeskReport, type LeapDeskRow } from "../api/hooks";
import PremiumTradePanel from "../components/PremiumTradePanel";

type Desk = "premium" | "leap";
type Tier = "low" | "med" | "high";
type Filter = "qual" | "watch" | "all";
type InstrFilter = "all" | "direct" | "lev";

const TIER = {
  low: { label: "Low risk", desc: "A real dip — the entry you wait for", badge: "bg-bullish-text/15 text-bullish-text", accent: "text-bullish-text", stripe: "shadow-[inset_3px_0_0_var(--color-bullish-text)]" },
  med: { label: "Medium", desc: "Neutral middle — fine, nothing special", badge: "bg-warning-text/15 text-warning-text", accent: "text-warning-text", stripe: "shadow-[inset_3px_0_0_var(--color-warning-text)]" },
  high: { label: "High", desc: "Extended or broken — far OTM only", badge: "bg-bearish-text/15 text-bearish-text", accent: "text-bearish-text", stripe: "shadow-[inset_3px_0_0_var(--color-bearish-text)]" },
} as const;
const TIER_ORDER: Tier[] = ["low", "med", "high"];

export default function PremiumDeskPage() {
  const nav = useNavigate();
  const [desk, setDesk] = useState<Desk>("premium");
  const { data, isLoading } = usePremiumDesk();

  const rep = useMemo<PremiumDeskReport | null>(() => {
    const body = data?.premium_desk?.body;
    if (!body) return null;
    try { return JSON.parse(body) as PremiumDeskReport; } catch { return null; }
  }, [data]);

  const [filter, setFilter] = useState<Filter>("qual");
  const [instr, setInstr] = useState<InstrFilter>("all");
  const [selected, setSelected] = useState<string | null>(null);

  const allRows = rep?.rows ?? [];
  // Direct (leverage 1× — the stock/ETF itself, e.g. a GOOGL put) vs Leveraged (2×/3×).
  const rows = instr === "direct" ? allRows.filter((r) => r.leverage <= 1)
    : instr === "lev" ? allRows.filter((r) => r.leverage > 1) : allRows;
  const qual = rows.filter((r) => r.qualifies);
  const watch = rows.filter((r) => !r.qualifies);
  const warming = rows.some((r) => r.iv_warming);
  const shown = filter === "qual" ? qual : filter === "watch" ? watch : rows;
  const sorted = [...shown].sort((a, b) => TIER_ORDER.indexOf(a.tier) - TIER_ORDER.indexOf(b.tier) || b.score - a.score);

  // Keep a valid selection as data/filter changes.
  useEffect(() => {
    if (sorted.length && !sorted.some((r) => r.sym === selected)) setSelected(sorted[0].sym);
  }, [sorted, selected]);

  const selectedRow = rows.find((r) => r.sym === selected);
  const asOf = data?.premium_desk?.session_date;

  const openRow = (sym: string) => {
    if (window.matchMedia("(min-width: 1024px)").matches) setSelected(sym);
    else nav(`/premium-desk/${encodeURIComponent(sym)}`);
  };

  return (
    <div className="flex h-full flex-col bg-surface-0">
      {/* Header toolbar */}
      <header className="shrink-0 space-y-3 border-b border-border-subtle px-4 py-3 lg:px-6">
        <div className="flex items-start gap-4">
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 text-[19px] font-extrabold tracking-tight text-text-primary">
              <span className="h-2 w-2 rounded-full bg-accent" />{desk === "leap" ? "LEAP Desk" : "Premium Desk"}
            </h1>
            <p className="mt-0.5 max-w-2xl text-[12px] text-text-muted">{desk === "leap"
              ? "Deep-oversold entries on strong companies (+ index ETFs) for long-dated ITM calls. The rare, generational shot — quality-gated. Educational; verify the live chain before buying."
              : "Selling premium on mega-cap leveraged-ETF options, ranked by entry quality. Educational — verify the live chain before selling."}</p>
            {desk === "premium" && asOf && <p className="mt-0.5 font-mono text-[10.5px] text-text-faint">as of {asOf}</p>}
          </div>
          {/* Desk switch — Premium (sell puts) | LEAP (buy long-dated calls) */}
          <div className="ml-auto flex gap-0.5 rounded-lg border border-border-subtle bg-surface-1 p-0.5">
            {([["premium", "Premium"], ["leap", "LEAP"]] as const).map(([d, label]) => (
              <button key={d} onClick={() => setDesk(d)} aria-pressed={desk === d}
                className={`rounded-md px-3 py-1.5 text-[12px] font-semibold ${desk === d ? "bg-surface-3 text-text-primary" : "text-text-muted hover:text-text-secondary"}`}>{label}</button>
            ))}
          </div>
          {desk === "premium" && <button onClick={() => nav("/premium-desk/positions")} className="shrink-0 rounded-lg border border-border-default bg-surface-1 px-3 py-2 text-[12px] font-semibold text-text-secondary hover:border-accent hover:text-text-primary">Positions &amp; P&amp;L →</button>}
        </div>
        {desk === "premium" && rep && (
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex gap-2">
              {TIER_ORDER.map((t) => (
                <div key={t} className="flex items-baseline gap-1.5 rounded-lg border border-border-subtle bg-surface-1 px-3 py-1.5">
                  <b className={`text-[15px] font-extrabold ${TIER[t].accent}`}>{qual.filter((r) => r.tier === t).length}</b>
                  <span className="text-[9.5px] font-semibold uppercase tracking-wide text-text-faint">{TIER[t].label}</span>
                </div>
              ))}
            </div>
            <div className="flex gap-0.5 rounded-lg border border-border-subtle bg-surface-1 p-0.5">
              {([["qual", "Qualifying", qual.length], ["watch", "Watch", watch.length], ["all", "All", rows.length]] as const).map(([f, label, n]) => (
                <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-semibold ${filter === f ? "bg-surface-3 text-text-primary" : "text-text-muted hover:text-text-secondary"}`}>
                  {label}<span className={`font-mono text-[10px] ${filter === f ? "text-accent" : "text-text-faint"}`}>{n}</span>
                </button>
              ))}
            </div>
            {/* Direct (the stock/ETF itself — e.g. a GOOGL put) vs Leveraged (2×/3×) */}
            <div className="flex gap-0.5 rounded-lg border border-border-subtle bg-surface-1 p-0.5">
              {([["all", "All"], ["direct", "Direct"], ["lev", "Leveraged"]] as const).map(([f, label]) => (
                <button key={f} onClick={() => setInstr(f)} aria-pressed={instr === f}
                  className={`rounded-md px-3 py-1.5 text-[12px] font-semibold ${instr === f ? "bg-surface-3 text-text-primary" : "text-text-muted hover:text-text-secondary"}`}>{label}</button>
              ))}
            </div>
            {warming && <span className="ml-auto hidden items-center gap-1.5 rounded-lg border border-warning-text/30 bg-warning-subtle px-2.5 py-1 text-[11px] text-warning-text md:flex">🌱 IV warming — tiers ride real entry signals; IV rank sharpens as history fills</span>}
          </div>
        )}
      </header>

      {desk === "leap" && <LeapDeskView />}

      {desk === "premium" && isLoading && <div className="grid flex-1 place-items-center text-[13px] text-text-faint">Loading the desk…</div>}
      {desk === "premium" && !isLoading && !rep && (
        <div className="grid flex-1 place-items-center px-6 text-center">
          <div>
            <div className="text-[14px] font-semibold text-text-secondary">The desk is warming up.</div>
            <div className="mx-auto mt-1.5 max-w-sm text-[12px] text-text-faint">Ranked candidates will appear here shortly.</div>
          </div>
        </div>
      )}

      {desk === "premium" && rep && (
        <div className="flex min-h-0 flex-1">
          {/* List */}
          <div className="min-w-0 flex-1 overflow-y-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="sticky top-0 z-10 bg-surface-0">
                  {["ETF", "Entry — why now", "RSI d/w", "IVR", "Exp move", "Earnings", "Sell put ≤", "Score"].map((h, i) => (
                    <th key={h} className={`border-b border-border-subtle px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-text-faint ${i >= 2 ? "text-right" : "text-left"} whitespace-nowrap`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.length === 0 && <tr><td colSpan={8} className="px-4 py-10 text-center text-[12.5px] text-text-faint">Nothing here right now.</td></tr>}
                {TIER_ORDER.map((tier) => {
                  const items = sorted.filter((r) => r.tier === tier);
                  if (!items.length) return null;
                  return (
                    <TierGroup key={tier} tier={tier} items={items} selected={selected} onOpen={openRow} />
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Detail panel (desktop) */}
          <div className="hidden w-[384px] shrink-0 overflow-y-auto border-l border-border-subtle bg-surface-0 lg:block">
            {selectedRow ? <PremiumTradePanel sym={selectedRow.sym} candidate={selectedRow} /> : <div className="grid h-full place-items-center p-8 text-[12.5px] text-text-faint">Select a candidate.</div>}
          </div>
        </div>
      )}
    </div>
  );
}

function TierGroup({ tier, items, selected, onOpen }: {
  tier: Tier; items: PremiumDeskRow[]; selected: string | null; onOpen: (s: string) => void;
}) {
  return (
    <>
      <tr>
        <td colSpan={8} className="border-b border-border-subtle bg-surface-1 px-3 py-1.5">
          <span className={`mr-2 rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${TIER[tier].badge}`}>{TIER[tier].label}</span>
          <span className="text-[11px] text-text-faint">{TIER[tier].desc}</span>
        </td>
      </tr>
      {items.map((r) => {
        const sel = r.sym === selected;
        const rsiCls = r.rsi_d >= 65 ? "text-bearish-text" : r.rsi_d < 40 ? "text-bullish-text" : "text-text-primary";
        return (
          <tr key={r.sym} onClick={() => onOpen(r.sym)}
            className={`cursor-pointer border-b border-border-subtle ${sel ? `bg-accent-subtle ${TIER[tier].stripe}` : "hover:bg-surface-1"}`}>
            <td className="px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <span className="font-mono text-[13px] font-semibold text-text-primary">{r.sym}</span>
                {r.leverage > 1 && <span className="rounded bg-purple-muted/40 px-1 py-0.5 font-mono text-[9px] font-semibold text-purple-text">{r.leverage}×</span>}
              </div>
              <div className="text-[11px] text-text-muted">{r.theme}</div>
            </td>
            <td className="px-3 py-2.5"><span className="block max-w-[240px] text-[12px] text-text-secondary">{r.rationale?.[0] ?? ""}</span></td>
            <td className="px-3 py-2.5 text-right font-mono text-[12px]"><span className={rsiCls}>{r.rsi_d}</span><span className="text-text-faint">/{r.rsi_w}</span></td>
            <td className="px-3 py-2.5 text-right font-mono text-[11px] text-text-faint">{r.iv_warming ? "warming" : r.iv_rank}</td>
            <td className="px-3 py-2.5 text-right font-mono text-[12px] text-text-secondary">{r.exp_move_pct > 0 ? `±${r.exp_move_pct}%` : "—"}</td>
            <td className="px-3 py-2.5 text-right font-mono text-[12px]">{r.earnings_days == null ? <span className="text-text-faint">—</span> : <span className={r.earnings_warn ? "text-bearish-text" : "text-text-muted"}>{r.earnings_warn ? "⚠ " : ""}{r.earnings_days}d</span>}</td>
            <td className="px-3 py-2.5 text-right font-mono text-[12px] font-semibold text-text-primary">${r.strike.toFixed(2)}</td>
            <td className="px-3 py-2.5 text-right font-mono text-[12px] text-text-secondary">{r.score.toFixed(1)}</td>
          </tr>
        );
      })}
    </>
  );
}

// ── LEAP Desk view — buying long-dated ITM calls on deep-oversold strong names ──
type LeapTier = "prime" | "strong" | "watch";
const LEAP_TIER = {
  prime: { label: "Prime", desc: "Generational — weekly oversold at the 200-day", badge: "bg-bullish-text/15 text-bullish-text", accent: "text-bullish-text", stripe: "shadow-[inset_3px_0_0_var(--color-bullish-text)]" },
  strong: { label: "Strong", desc: "A qualified oversold entry on a strong name", badge: "bg-accent/15 text-accent", accent: "text-accent", stripe: "shadow-[inset_3px_0_0_var(--color-accent)]" },
  watch: { label: "Watch", desc: "Approaching the entry zone — not there yet", badge: "bg-warning-text/15 text-warning-text", accent: "text-warning-text", stripe: "shadow-[inset_3px_0_0_var(--color-warning-text)]" },
} as const;
const LEAP_ORDER: LeapTier[] = ["prime", "strong", "watch"];
// Fundamentals letter grade (A best → D weakest that still passed the gate).
const GRADE_CLS: Record<string, string> = {
  A: "bg-bullish-text/15 text-bullish-text",
  B: "bg-accent/15 text-accent",
  C: "bg-warning-text/15 text-warning-text",
  D: "bg-bearish-text/15 text-bearish-text",
};

function fmtCap(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(0)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}

function LeapDeskView() {
  const nav = useNavigate();
  const { data, isLoading } = useLeapDesk();
  const openChart = (sym: string) => nav(`/trading?symbol=${encodeURIComponent(sym)}`);
  const rep = useMemo<LeapDeskReport | null>(() => {
    const body = data?.leap_desk?.body;
    if (!body) return null;
    try { return JSON.parse(body) as LeapDeskReport; } catch { return null; }
  }, [data]);
  const [filter, setFilter] = useState<Filter>("qual");
  const [kind, setKind] = useState<"all" | "index" | "stock">("all");
  const [sortKey, setSortKey] = useState<"tier" | "grade" | "rsi_d" | "dist" | "sym">("tier");
  const [dir, setDir] = useState<"asc" | "desc">("desc");
  const asOf = data?.leap_desk?.session_date;
  // Default direction per column: grade best-first, RSI most-oversold-first, distance nearest-first.
  const clickSort = (k: typeof sortKey) => {
    if (k === sortKey) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(k); setDir(k === "grade" ? "desc" : "asc"); }
  };

  const allRows = rep?.rows ?? [];
  const rows = kind === "all" ? allRows : allRows.filter((r) => r.kind === kind);
  const qual = rows.filter((r) => r.qualifies);
  const watch = rows.filter((r) => !r.qualifies);
  const shown = filter === "qual" ? qual : filter === "watch" ? watch : rows;
  const sorted = [...shown].sort((a, b) => LEAP_ORDER.indexOf(a.tier) - LEAP_ORDER.indexOf(b.tier) || b.quality_score - a.quality_score);

  if (isLoading) return <div className="grid flex-1 place-items-center text-[13px] text-text-faint">Loading the LEAP desk…</div>;
  if (!rep) return (
    <div className="grid flex-1 place-items-center px-6 text-center">
      <div>
        <div className="text-[14px] font-semibold text-text-secondary">No LEAP setups on the board.</div>
        <div className="mx-auto mt-1.5 max-w-sm text-[12px] text-text-faint">That's the point — these are the 2–3 generational entries a year. The desk stays quiet until a strong name is deeply oversold.</div>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-border-subtle px-4 py-2.5 lg:px-6">
        <div className="flex gap-2">
          {LEAP_ORDER.map((t) => (
            <div key={t} className="flex items-baseline gap-1.5 rounded-lg border border-border-subtle bg-surface-1 px-3 py-1.5">
              <b className={`text-[15px] font-extrabold ${LEAP_TIER[t].accent}`}>{qual.filter((r) => r.tier === t).length}</b>
              <span className="text-[9.5px] font-semibold uppercase tracking-wide text-text-faint">{LEAP_TIER[t].label}</span>
            </div>
          ))}
        </div>
        <div className="flex gap-0.5 rounded-lg border border-border-subtle bg-surface-1 p-0.5">
          {([["qual", "Qualifying", qual.length], ["watch", "Watch", watch.length], ["all", "All", rows.length]] as const).map(([f, label, n]) => (
            <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[12px] font-semibold ${filter === f ? "bg-surface-3 text-text-primary" : "text-text-muted hover:text-text-secondary"}`}>
              {label}<span className={`font-mono text-[10px] ${filter === f ? "text-accent" : "text-text-faint"}`}>{n}</span>
            </button>
          ))}
        </div>
        <div className="flex gap-0.5 rounded-lg border border-border-subtle bg-surface-1 p-0.5">
          {([["all", "All"], ["index", "Index"], ["stock", "Stocks"]] as const).map(([k, label]) => (
            <button key={k} onClick={() => setKind(k)} aria-pressed={kind === k}
              className={`rounded-md px-3 py-1.5 text-[12px] font-semibold ${kind === k ? "bg-surface-3 text-text-primary" : "text-text-muted hover:text-text-secondary"}`}>{label}</button>
          ))}
        </div>
        {asOf && <span className="ml-auto font-mono text-[10.5px] text-text-faint">as of {asOf}</span>}
      </div>
      <div className="min-w-0 flex-1 overflow-y-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="sticky top-0 z-10 bg-surface-0">
              {([["Symbol", "sym", "left"], ["Entry — why now", null, "left"], ["RSI d/w", "rsi_d", "right"], ["vs 200d", "dist", "right"], ["Grade", "grade", "right"], ["IV", null, "right"], ["Call: ITM · target", null, "right"]] as const).map(([label, key, align]) => (
                <th key={label} className={`border-b border-border-subtle px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-text-faint ${align === "right" ? "text-right" : "text-left"} whitespace-nowrap`}>
                  {key ? (
                    <button onClick={() => clickSort(key)} className={`inline-flex items-center gap-1 uppercase tracking-wide hover:text-text-secondary ${sortKey === key ? "text-text-primary" : ""}`}>
                      {label}<span className="text-[8px]">{sortKey === key ? (dir === "asc" ? "▲" : "▼") : "↕"}</span>
                    </button>
                  ) : label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={7} className="px-4 py-10 text-center text-[12.5px] text-text-faint">Nothing in this bucket right now.</td></tr>}
            {sortKey === "tier"
              ? LEAP_ORDER.map((tier) => {
                  const items = sorted.filter((r) => r.tier === tier);
                  if (!items.length) return null;
                  return <LeapTierGroup key={tier} tier={tier} items={items} onChart={openChart} />;
                })
              : [...shown].sort((a, b) => {
                  let c = 0;
                  if (sortKey === "grade") c = a.quality_score - b.quality_score;
                  else if (sortKey === "rsi_d") c = (a.rsi_d ?? 999) - (b.rsi_d ?? 999);
                  else if (sortKey === "dist") c = (a.dist_200_pct ?? 999) - (b.dist_200_pct ?? 999);
                  else if (sortKey === "sym") c = a.sym.localeCompare(b.sym);
                  return dir === "asc" ? c : -c;
                }).map((r) => <LeapRow key={r.sym} r={r} onChart={openChart} />)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LeapTierGroup({ tier, items, onChart }: { tier: LeapTier; items: LeapDeskRow[]; onChart: (s: string) => void }) {
  return (
    <>
      <tr>
        <td colSpan={7} className="border-b border-border-subtle bg-surface-1 px-3 py-1.5">
          <span className={`mr-2 rounded px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${LEAP_TIER[tier].badge}`}>{LEAP_TIER[tier].label}</span>
          <span className="text-[11px] text-text-faint">{LEAP_TIER[tier].desc}</span>
        </td>
      </tr>
      {items.map((r) => <LeapRow key={r.sym} r={r} onChart={onChart} />)}
    </>
  );
}

function LeapRow({ r, onChart }: { r: LeapDeskRow; onChart: (s: string) => void }) {
  const rsiCls = r.rsi_d == null ? "text-text-faint" : r.rsi_d < 40 ? "text-bullish-text" : r.rsi_d >= 65 ? "text-bearish-text" : "text-text-primary";
  const distCls = r.dist_200_pct == null ? "text-text-faint" : r.dist_200_pct <= 1 ? "text-bullish-text" : "text-text-muted";
  return (
          <tr className="border-b border-border-subtle hover:bg-surface-1">
            <td className="px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <button onClick={() => onChart(r.sym)} title={`Open ${r.sym} chart`}
                  className="font-mono text-[13px] font-semibold text-text-primary underline decoration-transparent underline-offset-2 hover:text-accent hover:decoration-accent">{r.sym}</button>
                {r.kind === "index" && <span className="rounded bg-purple-muted/40 px-1 py-0.5 font-mono text-[9px] font-semibold text-purple-text">IDX</span>}
                {r.breadth && <span title="Breadth washout — this index is oversold vs cap-weight SPY (the average stock got flushed)" className="rounded bg-bullish-text/15 px-1 py-0.5 text-[9px] font-semibold text-bullish-text">BREADTH</span>}
              </div>
              <div className="text-[11px] capitalize text-text-muted">{r.quality_warming ? "quality warming" : r.quality_tier}</div>
            </td>
            <td className="px-3 py-2.5"><span className="block max-w-[260px] text-[12px] text-text-secondary">{r.rationale?.[0] ?? ""}</span></td>
            <td className="px-3 py-2.5 text-right font-mono text-[12px]"><span className={rsiCls}>{r.rsi_d ?? "—"}</span><span className="text-text-faint">/{r.rsi_w ?? "—"}</span></td>
            <td className={`px-3 py-2.5 text-right font-mono text-[12px] ${distCls}`}>{r.dist_200_pct == null ? "—" : `${r.dist_200_pct > 0 ? "+" : ""}${r.dist_200_pct}%`}</td>
            <td className="px-3 py-2.5 text-right">
              <span className="group relative inline-flex cursor-default items-center gap-1.5">
                {r.quality_warming
                  ? <span className="font-mono text-[11px] text-text-faint">warming</span>
                  : <><span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${GRADE_CLS[r.grade] ?? "bg-surface-2 text-text-muted"}`}>{r.grade}</span><span className="font-mono text-[12px] text-text-secondary">{r.quality_score}</span></>}
                {/* Fundamentals hover card */}
                <span className="pointer-events-none absolute right-0 top-full z-30 mt-1 hidden w-56 rounded-lg border border-border-default bg-surface-0 p-2.5 text-left shadow-xl group-hover:block">
                  <span className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-text-faint">{r.sym} · fundamentals</span>
                  {r.quality_warming ? (
                    <span className="block text-[11px] text-text-muted">Not yet loaded — the nightly refresh hasn't graded this name.</span>
                  ) : (
                    <span className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[11px]">
                      <span className="text-text-faint">Market cap</span><span className="text-right text-text-secondary">{fmtCap(r.market_cap)}</span>
                      <span className="text-text-faint">Rev growth</span><span className="text-right text-text-secondary">{r.rev_growth == null ? "—" : `${r.rev_growth > 0 ? "+" : ""}${r.rev_growth}%`}</span>
                      <span className="text-text-faint">Net margin</span><span className="text-right text-text-secondary">{r.net_margin == null ? "—" : `${r.net_margin}%`}</span>
                      <span className="text-text-faint">Gross margin</span><span className="text-right text-text-secondary">{r.gross_margin == null ? "—" : `${r.gross_margin}%`}</span>
                      <span className="text-text-faint">EPS growth</span><span className="text-right text-text-secondary">{r.eps_growth == null ? "—" : `${r.eps_growth > 0 ? "+" : ""}${r.eps_growth}%`}</span>
                      <span className="text-text-faint">Analysts</span><span className="text-right capitalize text-text-secondary">{r.consensus ?? "—"}</span>
                    </span>
                  )}
                </span>
              </span>
            </td>
            <td className="px-3 py-2.5 text-right font-mono text-[11px]">{r.iv_warming || r.iv_rank == null ? <span className="text-text-faint">—</span> : <span className={r.iv_note.startsWith("cheap") ? "text-bullish-text" : r.iv_note.startsWith("rich") ? "text-bearish-text" : "text-text-muted"}>{r.iv_rank}{r.iv_note ? ` ${r.iv_note}` : ""}</span>}</td>
            <td className="px-3 py-2.5 text-right font-mono text-[12px] whitespace-nowrap"
                title={`ITM ~0.8Δ (stock replacement, high probability / low theta) vs a TARGET call at the nearest overhead resistance — the ${r.target_basis} — more leverage, more theta/IV risk. ~18mo expiry (${r.expiry}).`}>
              <span className="text-text-muted">${r.strike_itm.toFixed(0)}</span>
              <span className="text-text-faint"> · </span>
              <span className="font-semibold text-accent">${r.strike_target.toFixed(0)}</span>
              <span className="ml-1 text-[9px] text-text-faint">→{r.target_basis}</span>
            </td>
          </tr>
  );
}
