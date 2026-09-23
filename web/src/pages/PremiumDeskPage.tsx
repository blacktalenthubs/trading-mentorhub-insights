/**
 * Premium Desk (Spec S3) — the ranked feed of leveraged-ETF premium-selling candidates.
 *
 * Reads the S2 scan output from market_reports(kind='premium_desk') via usePremiumDesk().
 * Groups by risk tier (low / med / high), splits qualifying-now from the watch list, and
 * shows each candidate's trade (sell put ≤ strike) with its factor chips + rationale.
 * Tap a card to preview the S4 hand-off (strike, % OTM, est. credit, 30%/50% exit targets).
 *
 * "Risk" here is directional — how safe is the floor under a cash-secured put. While IV
 * history is warming (<20 sessions) the rank is neutralized and flagged, so the desk works
 * from day one on real trend/RSI. Educational, not financial advice. Verify the live chain
 * in-broker before selling — nothing here places an order.
 */
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { usePremiumDesk, type PremiumDeskReport, type PremiumDeskRow } from "../api/hooks";

type Tier = "low" | "med" | "high";
type Filter = "qual" | "watch" | "all";

const TIER = {
  low: {
    label: "Low risk", desc: "Clear floor — a put you'd take assignment on",
    edge: "border-l-bullish-text", card: "border-bullish-text/30",
    badge: "bg-bullish-text/15 text-bullish-text", accent: "text-bullish-text",
  },
  med: {
    label: "Medium", desc: "Sellable, with attention",
    edge: "border-l-warning-text", card: "border-warning-text/30",
    badge: "bg-warning-text/15 text-warning-text", accent: "text-warning-text",
  },
  high: {
    label: "High", desc: "Rich for a bad reason — far OTM only",
    edge: "border-l-bearish-text", card: "border-bearish-text/30",
    badge: "bg-bearish-text/15 text-bearish-text", accent: "text-bearish-text",
  },
} as const;

const TIER_ORDER: Tier[] = ["low", "med", "high"];

// Illustrative credit only — S4 pulls the live quote. ≈ strike·100·IV·√(dte/365)·0.4.
const estCredit = (r: PremiumDeskRow) =>
  Math.round(r.strike * 100 * (r.iv / 100) * Math.sqrt(r.dte / 365) * 0.4);


export default function PremiumDeskPage() {
  const nav = useNavigate();
  const goChart = (s: string) => nav(`/trading?symbol=${encodeURIComponent(s)}`);
  const goDetail = (s: string) => nav(`/premium-desk/${encodeURIComponent(s)}`);
  const { data, isLoading } = usePremiumDesk();

  const rep = useMemo<PremiumDeskReport | null>(() => {
    const body = data?.premium_desk?.body;
    if (!body) return null;
    try { return JSON.parse(body) as PremiumDeskReport; } catch { return null; }
  }, [data]);

  const [filter, setFilter] = useState<Filter>("qual");
  const [openCards, setOpenCards] = useState<Set<string>>(new Set());
  const [closedGroups, setClosedGroups] = useState<Set<string>>(new Set());

  const rows = rep?.rows ?? [];
  const qual = rows.filter((r) => r.qualifies);
  const watch = rows.filter((r) => !r.qualifies);
  const warming = rows.some((r) => r.iv_warming);
  const shown = filter === "qual" ? qual : filter === "watch" ? watch : rows;

  const toggleCard = (k: string) =>
    setOpenCards((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const toggleGroup = (k: string) =>
    setClosedGroups((p) => { const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const asOf = data?.premium_desk?.session_date;

  return (
    <div className="mx-auto max-w-2xl px-4 py-5 pb-24">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-extrabold tracking-tight text-text-primary">
            <span className="inline-block h-2.5 w-2.5 rotate-45 rounded-sm bg-accent" />
            Premium Desk
          </h1>
          <p className="mt-1 text-[12px] leading-snug text-text-muted">
            Selling premium on mega-cap leveraged-ETF options, ranked by risk. Educational — verify the live chain before selling.
          </p>
        </div>
        <button
          onClick={() => nav("/premium-desk/positions")}
          className="whitespace-nowrap rounded-lg border border-border-subtle px-2.5 py-1.5 text-[12px] font-semibold text-text-secondary transition-colors hover:border-accent"
        >P&amp;L →</button>
      </div>
      {asOf && <div className="mt-1 font-mono text-[10.5px] text-text-faint">as of {asOf}</div>}

      {isLoading && <div className="mt-8 text-center text-[13px] text-text-faint">Loading the desk…</div>}
      {!isLoading && !rep && (
        <div className="mt-6 rounded-xl border border-border-subtle bg-surface-1 p-6 text-center">
          <div className="text-[13px] font-semibold text-text-secondary">The desk is warming up.</div>
          <div className="mx-auto mt-1.5 max-w-sm text-[12px] leading-snug text-text-faint">
            Ranked candidates will appear here shortly. Check back in a moment.
          </div>
        </div>
      )}

      {rep && (
        <>
          {/* Tally */}
          <div className="mt-4 grid grid-cols-3 gap-2">
            {TIER_ORDER.map((t) => (
              <div key={t} className="rounded-xl border border-border-subtle bg-surface-1 p-2.5 text-center">
                <div className={`text-lg font-extrabold leading-none ${TIER[t].accent}`}>
                  {qual.filter((r) => r.tier === t).length}
                </div>
                <div className="mt-1 text-[9.5px] font-semibold uppercase tracking-wide text-text-muted">{TIER[t].label}</div>
              </div>
            ))}
          </div>

          {/* Filter */}
          <div className="mt-3 flex gap-1 rounded-xl border border-border-subtle bg-surface-0 p-1">
            {([["qual", "Qualifying", qual.length], ["watch", "Watch", watch.length], ["all", "All", rows.length]] as const).map(
              ([f, label, n]) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  aria-pressed={filter === f}
                  className={`flex flex-1 flex-col items-center gap-0.5 rounded-lg px-2 py-1.5 text-[12.5px] font-semibold transition-colors ${
                    filter === f ? "bg-surface-2 text-text-primary shadow-sm" : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {label}
                  <span className={`font-mono text-[10px] ${filter === f ? "text-accent" : "text-text-faint"}`}>{n}</span>
                </button>
              ),
            )}
          </div>

          {/* Warming strip */}
          {warming && (
            <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-warning-text/30 bg-warning-subtle p-3">
              <span className="text-[15px] leading-tight">🌱</span>
              <p className="text-[12px] leading-snug text-text-secondary">
                <b className="text-warning-text">IV history is warming.</b> The 1-year IV range just started building, so
                tiers ride real trend &amp; RSI today — IV rank sharpens the order as it fills (IVR·30d → 1y).
              </p>
            </div>
          )}

          {/* Feed */}
          <div className="mt-2">
            {shown.length === 0 && (
              <div className="mt-4 rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12.5px] text-text-faint">
                Nothing here right now.
              </div>
            )}
            {TIER_ORDER.map((tier) => {
              const items = shown
                .filter((r) => r.tier === tier)
                .sort((a, b) => b.score - a.score);
              if (items.length === 0) return null;
              const gkey = tier + filter;
              const isClosed = closedGroups.has(gkey);
              return (
                <div key={tier} className="mt-4">
                  <button
                    onClick={() => toggleGroup(gkey)}
                    className="flex w-full items-center gap-2 pb-2 text-left"
                  >
                    <span className={`rounded-md px-2.5 py-1 text-[10.5px] font-semibold uppercase tracking-wide ${TIER[tier].badge}`}>
                      {TIER[tier].label}
                    </span>
                    <span className="flex-1 text-[11.5px] text-text-muted">{TIER[tier].desc}</span>
                    <span className={`text-text-faint transition-transform ${isClosed ? "-rotate-90" : ""}`}>▾</span>
                  </button>
                  {!isClosed && (
                    <div className="space-y-2.5">
                      {items.map((r) => (
                        <Card key={r.sym} r={r} open={openCards.has(r.sym)} onToggle={() => toggleCard(r.sym)} onChart={goChart} onDetail={goDetail} />
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <p className="mt-8 border-t border-border-subtle pt-3 text-[10.5px] leading-relaxed text-text-faint">
            Ranked by the S2 scoring engine: IV rank + RSI + moving-average reclaims → risk tier. Credit estimates are
            illustrative; S4 pulls the live chain, delta &amp; exact credit. Read-only — nothing here places an order.
          </p>
        </>
      )}
    </div>
  );
}

function Card({ r, open, onToggle, onChart, onDetail }: {
  r: PremiumDeskRow; open: boolean; onToggle: () => void; onChart: (s: string) => void; onDetail: (s: string) => void;
}) {
  const t = TIER[r.tier];
  const otmPct = Math.round((1 - r.strike / r.price) * 100);
  const credit = estCredit(r);
  const posDot = (on: boolean) =>
    `inline-block h-1.5 w-1.5 rounded-sm ${on ? "bg-bullish-text" : "bg-bearish-text/50"}`;

  return (
    <div className={`overflow-hidden rounded-2xl border border-l-[3px] bg-surface-1 ${t.card} ${t.edge}`}>
      {/* Tap target */}
      <button onClick={onToggle} className="w-full text-left">
        <div className="flex items-center gap-3 px-4 pb-2.5 pt-3.5">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="font-mono text-[16px] font-extrabold leading-none text-text-primary">{r.sym}</span>
              {!r.qualifies && (
                <span className="rounded border border-border-subtle px-1.5 py-0.5 text-[8.5px] font-semibold uppercase tracking-wide text-text-faint">watch</span>
              )}
            </div>
            <div className="mt-1 truncate text-[11.5px] text-text-muted">{r.theme}</div>
          </div>
          <div className="ml-auto text-right">
            <div className="font-mono text-[9.5px] uppercase tracking-wide text-text-muted">Sell put ≤</div>
            <div className="text-[15px] font-bold text-text-primary">
              ${r.strike.toFixed(2)} <span className="text-[11px] font-semibold text-text-muted">· {r.dte}d</span>
            </div>
          </div>
        </div>
        {/* Factor chips */}
        <div className="flex flex-wrap gap-1.5 px-4 pb-2.5">
          {r.iv_warming ? (
            <span className="rounded-md bg-warning-text/15 px-2 py-0.5 font-mono text-[10.5px] text-warning-text">🌱 IVR warming</span>
          ) : (
            <span className="rounded-md bg-surface-3 px-2 py-0.5 font-mono text-[10.5px] text-text-muted">
              IVR <b className="text-accent">{r.iv_rank}</b>
            </span>
          )}
          <span className={`rounded-md bg-surface-3 px-2 py-0.5 font-mono text-[10.5px] text-text-muted`}>
            RSI <b className={r.rsi_d > 70 ? "text-bearish-text" : "text-text-primary"}>{r.rsi_d}</b>/{r.rsi_w}
          </span>
          <span className="flex items-center gap-1 rounded-md bg-surface-3 px-2 py-0.5 font-mono text-[10.5px] text-text-muted">
            <span className="flex items-center gap-0.5">
              <span className={posDot(r.above_20)} title="20 SMA" />
              <span className={posDot(r.above_50)} title="50 SMA" />
              <span className={posDot(r.above_200)} title="200 SMA" />
            </span>
            MA
          </span>
          <span className="rounded-md bg-surface-3 px-2 py-0.5 font-mono text-[10.5px] text-text-muted">
            score <b className="text-text-primary">{r.score.toFixed(1)}</b>
          </span>
        </div>
        <div className="px-4 pb-3 text-[11.5px] leading-snug text-text-muted">{r.rationale.join(" · ")}</div>
      </button>

      {/* Next-session planning — the value off-hours; prices don't move after close. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border-subtle px-4 py-2 font-mono text-[10.5px] text-text-muted">
        {r.exp_move_pct > 0 && (
          <span title="Expected 1-day move implied by ATM IV">±{r.exp_move_pct}% <span className="text-text-faint">(${r.exp_move_usd}) exp. move</span></span>
        )}
        {r.sma200 > 0 && (
          <span title="Distance from spot down to the 200-day SMA — the floor under the strike">
            200-floor ${r.sma200} <span className={r.floor_dist_pct >= 0 ? "text-text-faint" : "text-bearish-text"}>({r.floor_dist_pct >= 0 ? "+" : ""}{r.floor_dist_pct}%)</span>
          </span>
        )}
        {r.earnings_days != null && (
          <span className={`ml-auto rounded px-1.5 py-0.5 ${r.earnings_warn ? "bg-warning-text/15 text-warning-text" : "text-text-faint"}`}
            title={r.earnings_warn ? "Earnings falls inside the option's expiry window — gap + IV-crush risk" : "Days to the underlying's next earnings"}>
            {r.earnings_warn ? "⚠ " : ""}earnings {r.earnings_days}d
          </span>
        )}
      </div>

      {/* Expand — S4 preview */}
      {open && (
        <div className="border-t border-dashed border-border-subtle bg-surface-2/40 px-4 pb-4 pt-3">
          <Row k="Underlying" v={`$${r.price.toFixed(2)}`} />
          <Row k="Suggested strike" v={`$${r.strike.toFixed(2)} · ${otmPct}% OTM`} />
          <Row k="Est. credit (illustrative)" v={`~$${credit}/contract`} />
          <Row k="IV rank" v={r.iv_warming ? "warming" : `${r.iv_rank} (IV ${r.iv.toFixed(0)}%, n=${r.iv_n})`} />
          <Row k="30% / 50% target" v={`$${Math.round(credit * 0.7)} / $${Math.round(credit * 0.5)} to close`} />
          <div className="mt-3 flex gap-2">
            <button
              onClick={() => onChart(r.sym)}
              className="flex-1 rounded-xl border border-border-subtle py-2.5 text-[13px] font-semibold text-text-secondary transition-colors hover:border-accent"
            >
              View chart
            </button>
            <button
              onClick={() => onDetail(r.sym)}
              className="flex-1 rounded-xl bg-accent py-2.5 text-[13px] font-semibold text-white transition-colors hover:bg-accent-hover"
            >
              Set up trade →
            </button>
          </div>
          <p className="mt-2.5 text-center text-[10px] text-text-faint">
            S4 pulls the live chain, delta &amp; exact credit · read-only, no orders
          </p>
        </div>
      )}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border-subtle py-1.5 text-[12.5px] last:border-0">
      <span className="text-text-muted">{k}</span>
      <span className="font-mono font-medium text-text-secondary">{v}</span>
    </div>
  );
}
