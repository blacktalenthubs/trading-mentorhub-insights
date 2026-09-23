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

import { usePremiumDesk, type PremiumDeskReport, type PremiumDeskRow } from "../api/hooks";
import PremiumTradePanel from "../components/PremiumTradePanel";

type Tier = "low" | "med" | "high";
type Filter = "qual" | "watch" | "all";

const TIER = {
  low: { label: "Low risk", desc: "A real dip — the entry you wait for", badge: "bg-bullish-text/15 text-bullish-text", accent: "text-bullish-text", stripe: "shadow-[inset_3px_0_0_var(--color-bullish-text)]" },
  med: { label: "Medium", desc: "Neutral middle — fine, nothing special", badge: "bg-warning-text/15 text-warning-text", accent: "text-warning-text", stripe: "shadow-[inset_3px_0_0_var(--color-warning-text)]" },
  high: { label: "High", desc: "Extended or broken — far OTM only", badge: "bg-bearish-text/15 text-bearish-text", accent: "text-bearish-text", stripe: "shadow-[inset_3px_0_0_var(--color-bearish-text)]" },
} as const;
const TIER_ORDER: Tier[] = ["low", "med", "high"];

export default function PremiumDeskPage() {
  const nav = useNavigate();
  const { data, isLoading } = usePremiumDesk();

  const rep = useMemo<PremiumDeskReport | null>(() => {
    const body = data?.premium_desk?.body;
    if (!body) return null;
    try { return JSON.parse(body) as PremiumDeskReport; } catch { return null; }
  }, [data]);

  const [filter, setFilter] = useState<Filter>("qual");
  const [selected, setSelected] = useState<string | null>(null);

  const rows = rep?.rows ?? [];
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
              <span className="h-2 w-2 rounded-full bg-accent" />Premium Desk
            </h1>
            <p className="mt-0.5 max-w-2xl text-[12px] text-text-muted">Selling premium on mega-cap leveraged-ETF options, ranked by entry quality. Educational — verify the live chain before selling.</p>
            {asOf && <p className="mt-0.5 font-mono text-[10.5px] text-text-faint">as of {asOf}</p>}
          </div>
          <button onClick={() => nav("/premium-desk/positions")} className="ml-auto shrink-0 rounded-lg border border-border-default bg-surface-1 px-3 py-2 text-[12px] font-semibold text-text-secondary hover:border-accent hover:text-text-primary">Positions &amp; P&amp;L →</button>
        </div>
        {rep && (
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
            {warming && <span className="ml-auto hidden items-center gap-1.5 rounded-lg border border-warning-text/30 bg-warning-subtle px-2.5 py-1 text-[11px] text-warning-text md:flex">🌱 IV warming — tiers ride real entry signals; IV rank sharpens as history fills</span>}
          </div>
        )}
      </header>

      {isLoading && <div className="grid flex-1 place-items-center text-[13px] text-text-faint">Loading the desk…</div>}
      {!isLoading && !rep && (
        <div className="grid flex-1 place-items-center px-6 text-center">
          <div>
            <div className="text-[14px] font-semibold text-text-secondary">The desk is warming up.</div>
            <div className="mx-auto mt-1.5 max-w-sm text-[12px] text-text-faint">Ranked candidates will appear here shortly.</div>
          </div>
        </div>
      )}

      {rep && (
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
            <td className="px-3 py-2.5"><div className="font-mono text-[13px] font-semibold text-text-primary">{r.sym}</div><div className="text-[11px] text-text-muted">{r.theme}</div></td>
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
