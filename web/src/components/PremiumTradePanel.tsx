/**
 * Premium Desk — trade sizing/detail panel (Spec S4), reusable.
 *
 * Renders the live-chain strike picker, capital slider, sizing (contracts / collateral /
 * credit / RoC / annualized), the 30% / 50% exit plan, greeks + levels, and the earnings
 * landmine warning for one candidate. Used both as the desktop side panel (variant="panel")
 * and as the mobile /premium-desk/:sym route (variant="page"). READ-ONLY — no orders.
 */
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  usePremiumDesk, usePremiumChain, useLogPremiumTrade,
  type PremiumDeskReport, type PremiumDeskRow, type PremiumChainRow,
} from "../api/hooks";

const TIER_BADGE = {
  low: "bg-bullish-text/15 text-bullish-text",
  med: "bg-warning-text/15 text-warning-text",
  high: "bg-bearish-text/15 text-bearish-text",
} as const;

const CAPITAL_PRESETS = [5000, 10000, 25000, 50000];
const estMarkPerShare = (r: PremiumDeskRow) => (r.strike * (r.iv / 100) * Math.sqrt(r.dte / 365) * 0.4);
const usd = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });
const pctf = (n: number) => (n * 100).toFixed(1) + "%";

export default function PremiumTradePanel({ sym, candidate, variant = "panel" }: {
  sym: string; candidate?: PremiumDeskRow; variant?: "panel" | "page";
}) {
  const symU = (sym || "").toUpperCase();
  const nav = useNavigate();

  const { data: feed } = usePremiumDesk();
  const cand = useMemo<PremiumDeskRow | undefined>(() => {
    if (candidate) return candidate;
    const body = feed?.premium_desk?.body;
    if (!body) return undefined;
    try { return (JSON.parse(body) as PremiumDeskReport).rows.find((r) => r.sym === symU); }
    catch { return undefined; }
  }, [candidate, feed, symU]);

  const { data: chain, isLoading: chainLoading } = usePremiumChain(symU || undefined);
  const live = chain?.available ? chain.rows : [];
  const dte = chain?.dte ?? cand?.dte ?? 30;

  const [strike, setStrike] = useState<number | null>(null);
  const [capital, setCapital] = useState(10000);
  const logTrade = useLogPremiumTrade();

  // New symbol → drop the old strike pick (capital stays); avoids a stale coincidental match.
  useEffect(() => { setStrike(null); }, [symU]);

  // Reset the strike selection when the symbol changes (panel reuse across rows).
  const chosen = useMemo(() => {
    if (live.length) {
      let row: PremiumChainRow = live[Math.floor(live.length / 2)];
      if (strike != null && live.some((r) => r.strike === strike)) {
        row = live.find((r) => r.strike === strike)!;
      } else if (cand?.strike) {
        row = live.reduce((a, b) => (Math.abs(b.strike - cand.strike) < Math.abs(a.strike - cand.strike) ? b : a));
      } else {
        row = live.reduce((a, b) => (Math.abs(Math.abs(b.delta) - 0.3) < Math.abs(Math.abs(a.delta) - 0.3) ? b : a));
      }
      return { strike: row.strike, mark: row.mark, delta: row.delta, iv: row.iv, theta: row.theta, live: true };
    }
    if (cand) return { strike: cand.strike, mark: estMarkPerShare(cand), delta: -0.3, iv: cand.iv, theta: 0, live: false };
    return null;
  }, [live, strike, cand]);

  const calc = useMemo(() => {
    if (!chosen) return null;
    const collPer = chosen.strike * 100;
    const contracts = Math.max(0, Math.floor(capital / collPer));
    const collateral = contracts * collPer;
    const creditPer = chosen.mark * 100;
    const totalCredit = creditPer * contracts;
    const roc = collateral > 0 ? totalCredit / collateral : 0;
    return { collPer, contracts, collateral, creditPer, totalCredit, roc, annualized: roc * (365 / dte) };
  }, [chosen, capital, dte]);

  const takeAndLog = () => {
    if (!chosen || !calc || calc.contracts === 0) return;
    logTrade.mutate({
      symbol: symU, theme: cand?.theme ?? null, tier: cand?.tier ?? null,
      strike: chosen.strike, expiration: chain?.expiration ?? null, dte,
      contracts: calc.contracts, credit_per_contract: calc.creditPer, collateral: calc.collateral,
    }, { onSuccess: () => nav("/premium-desk/positions") });
  };

  if (!symU) return <div className="grid h-full place-items-center p-8 text-center text-[12.5px] text-text-faint">Select a candidate to size a trade.</div>;
  if (!cand && !chosen && !chainLoading) return <div className="grid h-full place-items-center p-8 text-center text-[12.5px] text-text-faint">No data for {symU}. Open it from the feed.</div>;

  const assignOdds = chosen ? Math.round(Math.abs(chosen.delta) * 100) : null;
  const otmPct = chosen && cand ? Math.round((1 - chosen.strike / cand.price) * 100) : 0;

  return (
    <div className={variant === "page" ? "mx-auto max-w-lg px-4 py-5 pb-24" : "p-4"}>
      {variant === "page" && (
        <button onClick={() => nav("/premium-desk")} className="mb-3 text-[12.5px] text-text-muted hover:text-accent">← Premium Desk</button>
      )}

      {/* Header */}
      <div className="flex items-start gap-2.5">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-xl font-extrabold tracking-tight text-text-primary">{symU}</span>
            {cand && <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${TIER_BADGE[cand.tier]}`}>{cand.tier}</span>}
          </div>
          <div className="mt-0.5 text-[11.5px] text-text-muted">{cand?.theme ?? "Cash-secured put"} · put · ~{dte}d</div>
        </div>
        {cand && <div className="ml-auto text-right"><div className="font-mono text-[17px] font-bold text-text-primary">${cand.price.toFixed(2)}</div><div className="text-[9.5px] uppercase tracking-wide text-text-faint">underlying</div></div>}
      </div>

      {cand && (
        <p className="mt-2.5 text-[12px] leading-snug text-text-muted">
          {cand.rationale?.[0]}. {cand.above_200 ? "Above the 200-day — a dip inside an uptrend." : "Below the 200-day — weaker structure; keep the strike well OTM."}
        </p>
      )}

      {cand?.earnings_warn && (
        <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-bearish-text/40 bg-bearish-subtle p-3">
          <span className="text-[15px] leading-tight">⚠️</span>
          <p className="text-[11.5px] leading-snug text-text-secondary"><b className="text-bearish-text">Earnings in {cand.earnings_days} days</b> — inside this ~{dte}d expiry. Gap &amp; IV-crush risk; use a shorter expiry that closes before it, or skip.</p>
        </div>
      )}

      {chosen && calc && (
        <>
          {/* Strike */}
          <div className="mt-4 rounded-xl border border-border-subtle bg-surface-1 p-3.5">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Strike {chosen.live ? "· live chain" : "· suggested"}</span>
              {assignOdds != null && <span className="font-mono text-[10.5px] text-text-faint">Δ{Math.abs(chosen.delta).toFixed(2)} · ~{assignOdds}% assign</span>}
            </div>
            {live.length > 0 ? (
              <div className="flex gap-1.5 overflow-x-auto pb-1">
                {live.map((r) => (
                  <button key={r.strike} onClick={() => setStrike(r.strike)}
                    className={`flex min-w-[58px] flex-col items-center rounded-lg border px-2 py-1.5 ${r.strike === chosen.strike ? "border-accent bg-accent-subtle" : "border-border-subtle bg-surface-0 hover:border-border-strong"}`}>
                    <span className="font-mono text-[12.5px] font-bold text-text-primary">${r.strike}</span>
                    <span className="font-mono text-[9px] text-text-faint">Δ{Math.abs(r.delta).toFixed(2)}</span>
                    <span className="font-mono text-[9px] text-bullish-text">{r.mark.toFixed(2)}</span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-warning-text/30 bg-warning-subtle px-3 py-2 text-[11px] text-text-secondary">Live chain unavailable{chain?.reason ? ` (${chain.reason})` : ""} — suggested strike + illustrative credit. Verify in-broker.</div>
            )}
          </div>

          {/* Capital + sizing */}
          <div className="mt-3 rounded-xl border border-border-subtle bg-surface-1 p-3.5">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Capital{otmPct ? ` · ${otmPct}% OTM` : ""}</span>
              <span className="font-mono text-[15px] font-bold text-text-primary">${usd(capital)}</span>
            </div>
            <input type="range" min={1000} max={100000} step={1000} value={capital} onChange={(e) => setCapital(Number(e.target.value))} className="w-full accent-accent" />
            <div className="mt-2 flex gap-1.5">
              {CAPITAL_PRESETS.map((p) => (
                <button key={p} onClick={() => setCapital(p)} className={`rounded-md px-2.5 py-1 text-[11px] font-semibold ${capital === p ? "bg-accent text-white" : "bg-surface-2 text-text-muted hover:text-text-secondary"}`}>${usd(p)}</button>
              ))}
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Kpi k="Contracts" v={String(calc.contracts)} sub={`$${usd(calc.collateral)} collateral`} />
              <Kpi k="Credit" v={`$${usd(calc.totalCredit)}`} sub={`$${calc.creditPer.toFixed(0)}/ct`} g />
              <Kpi k="Return on capital" v={pctf(calc.roc)} sub="to expiry" g />
              <Kpi k="Annualized" v={pctf(calc.annualized)} sub={`~${dte}d`} />
            </div>
            {calc.contracts === 0 && <p className="mt-2 text-center text-[11px] text-warning-text">Capital below one contract (${usd(calc.collPer)}).</p>}
          </div>

          {/* Exits */}
          <div className="mt-3 rounded-xl border border-border-subtle bg-surface-1 p-3.5">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-text-muted">Profit-take plan</div>
            {[0.3, 0.5].map((p) => (
              <div key={p} className="mb-1.5 flex items-center justify-between rounded-lg bg-surface-0 px-3 py-2 last:mb-0">
                <span className="text-[12.5px] font-semibold text-text-primary">Close at {p * 100}%</span>
                <span className="flex gap-3 font-mono text-[11px] tabular-nums text-text-muted">
                  <span>~${(chosen.mark * (1 - p)).toFixed(2)}</span>
                  <b className="text-bullish-text">+${usd(calc.totalCredit * p)}</b>
                  <span>{pctf(calc.collateral > 0 ? (calc.totalCredit * p) / calc.collateral : 0)}</span>
                </span>
              </div>
            ))}
          </div>

          {/* Read */}
          <div className="mt-3 flex flex-wrap gap-1.5">
            <Chip k="IV" v={`${chosen.iv.toFixed(0)}%`} />
            <Chip k="exp move" v={cand ? `±${cand.exp_move_pct || (cand.iv / 15.874).toFixed(1)}%` : "—"} />
            <Chip k="Δ" v={Math.abs(chosen.delta).toFixed(2)} />
            {cand && <Chip k="RSI" v={`${cand.rsi_d}/${cand.rsi_w}`} />}
            {cand && cand.sma200 > 0 && <Chip k="200-SMA" v={cand.above_200 ? "below spot" : "above spot"} />}
          </div>

          {/* Actions */}
          <div className="mt-4 flex gap-2">
            <button onClick={() => nav(`/trading?symbol=${encodeURIComponent(symU)}`)} className="flex-1 rounded-xl border border-border-subtle py-2.5 text-[13px] font-semibold text-text-secondary hover:border-accent">View chart</button>
            <button onClick={takeAndLog} disabled={calc.contracts === 0 || logTrade.isPending} className="flex-1 rounded-xl bg-accent py-2.5 text-[13px] font-semibold text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-accent/40">{logTrade.isPending ? "Logging…" : "Take & Log →"}</button>
          </div>
          <p className="mt-2.5 text-center text-[10px] text-text-faint">Educational · verify the live chain in-broker · read-only, no orders</p>
        </>
      )}
    </div>
  );
}

function Kpi({ k, v, sub, g }: { k: string; v: string; sub?: string; g?: boolean }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-0 p-2.5">
      <div className="text-[9.5px] font-semibold uppercase tracking-wide text-text-faint">{k}</div>
      <div className={`mt-0.5 font-mono text-[17px] font-bold ${g ? "text-bullish-text" : "text-text-primary"}`}>{v}</div>
      {sub && <div className="text-[9.5px] text-text-faint">{sub}</div>}
    </div>
  );
}
function Chip({ k, v }: { k: string; v: string }) {
  return <span className="rounded-md bg-surface-3 px-2 py-0.5 font-mono text-[10.5px] text-text-muted">{k} <b className="text-text-primary">{v}</b></span>;
}
