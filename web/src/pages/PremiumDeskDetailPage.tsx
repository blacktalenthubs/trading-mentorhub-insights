/**
 * Premium Desk — Trade Detail (Spec S4).
 *
 * Opened from a feed card. Turns a candidate into a sized, real-numbers trade:
 * pick a put strike from the LIVE ~30-DTE chain, set the capital to allocate, and see
 * contracts, collateral, credit, return on capital, and the 30% / 50% profit-take exit
 * math. Falls back to the illustrative estimate when the live chain is unavailable.
 *
 * Educational, not financial advice. READ-ONLY — nothing here places an order; "Take &
 * Log" (S5) records a trade you placed yourself in the broker.
 */
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

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

// Illustrative fallback credit/share when the live chain is unavailable.
const estMarkPerShare = (r: PremiumDeskRow) => (r.strike * (r.iv / 100) * Math.sqrt(r.dte / 365) * 0.4);

export default function PremiumDeskDetailPage() {
  const { sym = "" } = useParams();
  const nav = useNavigate();
  const symU = sym.toUpperCase();

  const { data: feed } = usePremiumDesk();
  const cand = useMemo<PremiumDeskRow | undefined>(() => {
    const body = feed?.premium_desk?.body;
    if (!body) return undefined;
    try { return (JSON.parse(body) as PremiumDeskReport).rows.find((r) => r.sym === symU); }
    catch { return undefined; }
  }, [feed, symU]);

  const { data: chain, isLoading: chainLoading } = usePremiumChain(symU);
  const live = chain?.available ? chain.rows : [];
  const dte = chain?.dte ?? cand?.dte ?? 30;

  // Strike selection — default to the candidate's suggested strike (nearest live strike),
  // else the ~0.30-delta put (a standard CSP), else the candidate strike.
  const [strike, setStrike] = useState<number | null>(null);
  const chosen = useMemo<{ strike: number; mark: number; delta: number; iv: number; theta: number; live: boolean } | null>(() => {
    if (live.length) {
      const target = strike ?? cand?.strike ?? live[Math.floor(live.length / 2)].strike;
      let row: PremiumChainRow = live[0];
      if (strike != null) {
        row = live.find((r) => r.strike === strike) ?? live[0];
      } else if (cand?.strike) {
        row = live.reduce((a, b) => (Math.abs(b.strike - target) < Math.abs(a.strike - target) ? b : a));
      } else {
        row = live.reduce((a, b) => (Math.abs(Math.abs(b.delta) - 0.30) < Math.abs(Math.abs(a.delta) - 0.30) ? b : a));
      }
      return { strike: row.strike, mark: row.mark, delta: row.delta, iv: row.iv, theta: row.theta, live: true };
    }
    if (cand) return { strike: cand.strike, mark: estMarkPerShare(cand), delta: -0.3, iv: cand.iv, theta: 0, live: false };
    return null;
  }, [live, strike, cand]);

  const [capital, setCapital] = useState(10000);
  const logTrade = useLogPremiumTrade();

  const takeAndLog = () => {
    if (!chosen || !calc || calc.contracts === 0) return;
    logTrade.mutate(
      {
        symbol: symU, theme: cand?.theme ?? null, tier: cand?.tier ?? null,
        strike: chosen.strike, expiration: chain?.expiration ?? null, dte,
        contracts: calc.contracts, credit_per_contract: calc.creditPer,
        collateral: calc.collateral,
      },
      { onSuccess: () => nav("/premium-desk/positions") },
    );
  };

  const calc = useMemo(() => {
    if (!chosen) return null;
    const collPer = chosen.strike * 100;
    const contracts = Math.max(0, Math.floor(capital / collPer));
    const collateral = contracts * collPer;
    const creditPer = chosen.mark * 100;
    const totalCredit = creditPer * contracts;
    const roc = collateral > 0 ? (totalCredit / collateral) : 0;
    const annualized = roc * (365 / dte);
    const exits = [0.3, 0.5].map((pct) => ({
      pct,
      profit: totalCredit * pct,
      buyback: chosen.mark * (1 - pct),
      roc: collateral > 0 ? (totalCredit * pct) / collateral : 0,
    }));
    return { collPer, contracts, collateral, creditPer, totalCredit, roc, annualized, exits };
  }, [chosen, capital, dte]);

  const assignOdds = chosen ? Math.round(Math.abs(chosen.delta) * 100) : null;
  const usd = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  const pct = (n: number) => (n * 100).toFixed(1) + "%";

  return (
    <div className="mx-auto max-w-2xl px-4 py-5 pb-24">
      <button onClick={() => nav("/premium-desk")} className="mb-3 text-[12.5px] text-text-muted hover:text-accent">← Premium Desk</button>

      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 font-mono text-2xl font-extrabold tracking-tight text-text-primary">
            {symU}
            {cand && <span className={`rounded-md px-2 py-0.5 text-[10.5px] font-semibold uppercase tracking-wide ${TIER_BADGE[cand.tier]}`}>{cand.tier}</span>}
          </h1>
          <p className="mt-1 text-[12.5px] text-text-muted">{cand?.theme ?? "Cash-secured put"} · sell put · ~{dte}d</p>
        </div>
        <span className={`whitespace-nowrap rounded-full px-2.5 py-1 text-[10px] font-semibold ${chosen?.live ? "bg-bullish-text/15 text-bullish-text" : "bg-warning-text/15 text-warning-text"}`}>
          {chainLoading ? "loading chain…" : chosen?.live ? "● live chain" : "estimate"}
        </span>
      </div>

      {/* Earnings landmine — never be short a put through an earnings event. */}
      {cand?.earnings_warn && (
        <div className="mt-3 flex items-start gap-2.5 rounded-xl border border-bearish-text/40 bg-bearish-subtle p-3">
          <span className="text-[15px] leading-tight">⚠️</span>
          <p className="text-[12px] leading-snug text-text-secondary">
            <b className="text-bearish-text">Earnings in {cand.earnings_days} days</b> — inside this ~{dte}d expiry. Selling a put through earnings adds gap &amp; IV-crush risk. Consider a shorter expiry that closes before the report, or skip it.
          </p>
        </div>
      )}

      {!chosen && !chainLoading && (
        <div className="mt-6 rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[13px] text-text-faint">
          No candidate or live chain for {symU}. Open it from the feed.
        </div>
      )}

      {chosen && calc && (
        <>
          {/* Strike selector */}
          <div className="mt-5">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Strike {chosen.live ? "" : "(suggested)"}</span>
              {assignOdds != null && (
                <span className="font-mono text-[11px] text-text-faint">Δ{Math.abs(chosen.delta).toFixed(2)} · ~{assignOdds}% assignment odds</span>
              )}
            </div>
            {live.length > 0 ? (
              <div className="flex gap-1.5 overflow-x-auto pb-1">
                {live.map((r) => (
                  <button
                    key={r.strike}
                    onClick={() => setStrike(r.strike)}
                    className={`flex min-w-[64px] flex-col items-center rounded-lg border px-2 py-1.5 transition-colors ${
                      r.strike === chosen.strike ? "border-accent bg-accent-subtle" : "border-border-subtle bg-surface-1 hover:border-border-strong"
                    }`}
                  >
                    <span className="font-mono text-[13px] font-bold text-text-primary">${r.strike}</span>
                    <span className="font-mono text-[9.5px] text-text-faint">Δ{Math.abs(r.delta).toFixed(2)}</span>
                    <span className="font-mono text-[9.5px] text-bullish-text">{r.mark.toFixed(2)}</span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-warning-text/30 bg-warning-subtle px-3 py-2 text-[11.5px] text-text-secondary">
                Live chain unavailable{chain?.reason ? ` (${chain.reason})` : ""} — showing the suggested strike with an illustrative credit. Verify in-broker.
              </div>
            )}
          </div>

          {/* Capital */}
          <div className="mt-5">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Capital to allocate</span>
              <span className="font-mono text-[15px] font-bold text-text-primary">${usd(capital)}</span>
            </div>
            <input
              type="range" min={1000} max={100000} step={1000} value={capital}
              onChange={(e) => setCapital(Number(e.target.value))}
              className="w-full accent-accent"
            />
            <div className="mt-2 flex gap-1.5">
              {CAPITAL_PRESETS.map((p) => (
                <button
                  key={p}
                  onClick={() => setCapital(p)}
                  className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                    capital === p ? "bg-accent text-white" : "bg-surface-2 text-text-muted hover:text-text-secondary"
                  }`}
                >${usd(p)}</button>
              ))}
            </div>
          </div>

          {/* Sizing result */}
          <div className="mt-5 grid grid-cols-2 gap-2.5">
            <Stat label="Contracts" value={String(calc.contracts)} sub={`${usd(calc.collateral)} collateral`} />
            <Stat label="Credit collected" value={`$${usd(calc.totalCredit)}`} sub={`$${calc.creditPer.toFixed(0)}/contract`} accent="bullish" />
            <Stat label="Return on capital" value={pct(calc.roc)} sub={`if held to expiry`} accent="bullish" />
            <Stat label="Annualized" value={pct(calc.annualized)} sub={`~${dte}d basis`} />
          </div>
          {calc.contracts === 0 && (
            <p className="mt-2 text-center text-[11px] text-warning-text">Capital below one contract’s collateral (${usd(calc.collPer)}). Raise it or pick a lower strike.</p>
          )}

          {/* Exit plan */}
          <div className="mt-5 rounded-xl border border-border-subtle bg-surface-1 p-3.5">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-muted">Profit-take plan</div>
            <div className="space-y-2">
              {calc.exits.map((e) => (
                <div key={e.pct} className="flex items-center justify-between rounded-lg bg-surface-2/50 px-3 py-2">
                  <span className="text-[13px] font-semibold text-text-primary">Close at {Math.round(e.pct * 100)}%</span>
                  <div className="flex items-center gap-3 font-mono text-[11.5px] tabular-nums text-text-muted">
                    <span>buy-back ~${e.buyback.toFixed(2)}</span>
                    <span className="font-semibold text-bullish-text">+${usd(e.profit)}</span>
                    <span className="text-text-secondary">{pct(e.roc)} RoC</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-2 text-[10.5px] text-text-faint">Standard CSP management: buy to close after capturing part of the credit rather than holding to expiry.</p>
          </div>

          {/* Greeks + rationale */}
          <div className="mt-4 flex flex-wrap gap-1.5">
            <Chip k="mark" v={`$${chosen.mark.toFixed(2)}`} />
            <Chip k="Δ" v={Math.abs(chosen.delta).toFixed(2)} />
            <Chip k="IV" v={`${chosen.iv.toFixed(0)}%`} />
            {chosen.theta !== 0 && <Chip k="θ/day" v={chosen.theta.toFixed(2)} />}
            {cand && <Chip k="score" v={cand.score.toFixed(1)} />}
          </div>
          {cand && <p className="mt-3 text-[12px] leading-snug text-text-muted">{cand.rationale.join(" · ")}</p>}

          {/* Actions */}
          <div className="mt-5 flex gap-2">
            <button
              onClick={() => nav(`/trading?symbol=${encodeURIComponent(symU)}`)}
              className="flex-1 rounded-xl border border-border-subtle py-3 text-[13.5px] font-semibold text-text-secondary transition-colors hover:border-accent"
            >View chart</button>
            <button
              onClick={takeAndLog}
              disabled={calc.contracts === 0 || logTrade.isPending}
              className="flex-1 rounded-xl bg-accent py-3 text-[13.5px] font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-accent/40"
            >{logTrade.isPending ? "Logging…" : "Take & Log →"}</button>
          </div>
          <p className="mt-6 border-t border-border-subtle pt-3 text-[10.5px] leading-relaxed text-text-faint">
            Educational, not financial advice. Numbers are for sizing a cash-secured put; the live chain moves — confirm bid/ask, delta and collateral in your broker before selling. Read-only: nothing here places an order.
          </p>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: "bullish" }) {
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-3">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">{label}</div>
      <div className={`mt-1 text-xl font-extrabold ${accent === "bullish" ? "text-bullish-text" : "text-text-primary"}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[10.5px] text-text-faint">{sub}</div>}
    </div>
  );
}

function Chip({ k, v }: { k: string; v: string }) {
  return (
    <span className="rounded-md bg-surface-3 px-2 py-0.5 font-mono text-[10.5px] text-text-muted">
      {k} <b className="text-text-primary">{v}</b>
    </span>
  );
}
