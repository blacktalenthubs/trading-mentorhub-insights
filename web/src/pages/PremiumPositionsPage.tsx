/**
 * Premium Desk — Positions & standalone P&L (Spec S5).
 *
 * The premium-selling book the user logs themselves (NOT broker-integrated): open
 * positions with the credit at risk, and closed trades with realized P&L. Closing a
 * position records the buyback debit (0 = expired worthless) and books realized =
 * credit collected − buyback cost. Educational; read-only — no orders.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { usePremiumPositions, useClosePremiumTrade, type PremiumTrade } from "../api/hooks";

const usd = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });
const signed = (n: number) => (n >= 0 ? "+" : "−") + "$" + usd(Math.abs(n));

export default function PremiumPositionsPage() {
  const nav = useNavigate();
  const { data, isLoading } = usePremiumPositions();
  const s = data?.summary;
  const pnlColor = (s?.realized_pnl ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text";

  return (
    <div className="mx-auto h-full max-w-3xl overflow-y-auto px-4 py-5 pb-24">
      <div className="flex items-center justify-between">
        <button onClick={() => nav("/premium-desk")} className="text-[12.5px] text-text-muted hover:text-accent">← Premium Desk</button>
      </div>
      <h1 className="mt-2 text-xl font-extrabold tracking-tight text-text-primary">Premium P&amp;L</h1>
      <p className="mt-1 text-[12px] text-text-muted">Your logged premium-selling book — separate from the broker. Educational, not financial advice.</p>

      {isLoading && <div className="mt-8 text-center text-[13px] text-text-faint">Loading…</div>}

      {data && (
        <>
          {/* Summary */}
          <div className="mt-4 rounded-2xl border border-border-subtle bg-surface-1 p-4">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-text-muted">Realized P&amp;L</div>
            <div className={`mt-0.5 text-3xl font-extrabold ${pnlColor}`}>{signed(s?.realized_pnl ?? 0)}</div>
            <div className="mt-3 grid grid-cols-3 gap-2 border-t border-border-subtle pt-3">
              <Mini label="Win rate" value={s?.win_rate != null ? `${s.win_rate}%` : "—"} />
              <Mini label="Open" value={String(s?.open_count ?? 0)} />
              <Mini label="Credit at risk" value={`$${usd(s?.credit_at_risk ?? 0)}`} />
            </div>
          </div>

          {/* Open */}
          <SectionTitle>Open · {data.open.length}</SectionTitle>
          {data.open.length === 0 ? (
            <Empty>No open positions. Log one from a trade’s detail view.</Empty>
          ) : (
            <div className="space-y-2.5">
              {data.open.map((t) => <OpenCard key={t.id} t={t} />)}
            </div>
          )}

          {/* Closed */}
          {data.closed.length > 0 && (
            <>
              <SectionTitle>Closed · {data.closed.length}</SectionTitle>
              <div className="space-y-1.5">
                {data.closed.map((t) => (
                  <div key={t.id} className="flex items-center justify-between rounded-lg border border-border-subtle bg-surface-1 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[13px] font-bold text-text-primary">{t.symbol}</span>
                      <span className="font-mono text-[11px] text-text-muted">{t.contracts}× ${t.strike} put</span>
                    </div>
                    <span className={`font-mono text-[13px] font-bold ${(t.realized_pnl ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                      {signed(t.realized_pnl ?? 0)}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}

          <p className="mt-8 border-t border-border-subtle pt-3 text-[10.5px] leading-relaxed text-text-faint">
            Log trades you placed in your own broker; this is a standalone tally, not a brokerage account. Read-only — nothing here places or closes a real order.
          </p>
        </>
      )}
    </div>
  );
}

function OpenCard({ t }: { t: PremiumTrade }) {
  const close = useClosePremiumTrade();
  const [closing, setClosing] = useState(false);
  const [buyback, setBuyback] = useState("0");

  const doClose = () => {
    close.mutate({ id: t.id, close_price: Math.max(0, Number(buyback) || 0) },
      { onSuccess: () => setClosing(false) });
  };

  return (
    <div className="overflow-hidden rounded-2xl border border-border-subtle bg-surface-1">
      <div className="flex items-center gap-3 px-4 pt-3.5 pb-2.5">
        <div>
          <div className="font-mono text-[15px] font-bold text-text-primary">{t.symbol}</div>
          <div className="mt-0.5 text-[11px] text-text-muted">{t.theme ?? "put"}{t.expiration ? ` · exp ${t.expiration}` : ""}</div>
        </div>
        <div className="ml-auto text-right">
          <div className="font-mono text-[9.5px] uppercase tracking-wide text-text-muted">Credit</div>
          <div className="text-[15px] font-bold text-bullish-text">+${usd(t.total_credit)}</div>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 px-4 pb-3 font-mono text-[10.5px] text-text-muted">
        <span className="rounded-md bg-surface-3 px-2 py-0.5">{t.contracts}× ${t.strike} put</span>
        {t.dte != null && <span className="rounded-md bg-surface-3 px-2 py-0.5">~{t.dte}d</span>}
        {t.collateral != null && <span className="rounded-md bg-surface-3 px-2 py-0.5">${usd(t.collateral)} collateral</span>}
        {t.tier && <span className="rounded-md bg-surface-3 px-2 py-0.5">{t.tier}</span>}
      </div>
      {!closing ? (
        <button onClick={() => setClosing(true)} className="w-full border-t border-border-subtle py-2.5 text-[12.5px] font-semibold text-text-secondary transition-colors hover:text-accent">
          Close position
        </button>
      ) : (
        <div className="border-t border-dashed border-border-subtle bg-surface-2/40 px-4 py-3">
          <label className="text-[11px] font-semibold uppercase tracking-wide text-text-muted">Buyback price / share</label>
          <div className="mt-1.5 flex items-center gap-2">
            <input
              type="number" step="0.01" min="0" value={buyback}
              onChange={(e) => setBuyback(e.target.value)}
              className="w-24 rounded-lg border border-border-subtle bg-surface-0 px-2.5 py-1.5 font-mono text-[13px] text-text-primary"
            />
            <button onClick={() => setBuyback("0")} className="rounded-md bg-surface-2 px-2.5 py-1.5 text-[11px] font-semibold text-text-muted hover:text-text-secondary">Expired $0</button>
            <div className="ml-auto text-right font-mono text-[11px] text-text-muted">
              P&amp;L {signed(t.total_credit - Math.max(0, Number(buyback) || 0) * 100 * t.contracts)}
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <button onClick={() => setClosing(false)} className="flex-1 rounded-lg border border-border-subtle py-2 text-[12.5px] font-semibold text-text-muted">Cancel</button>
            <button onClick={doClose} disabled={close.isPending} className="flex-1 rounded-lg bg-accent py-2 text-[12.5px] font-semibold text-white disabled:bg-accent/40">
              {close.isPending ? "Closing…" : "Confirm close"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-center">
      <div className="text-lg font-bold text-text-primary">{value}</div>
      <div className="mt-0.5 text-[9.5px] font-semibold uppercase tracking-wide text-text-muted">{label}</div>
    </div>
  );
}
function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="mb-2 mt-6 text-[11px] font-semibold uppercase tracking-wide text-text-muted">{children}</div>;
}
function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12.5px] text-text-faint">{children}</div>;
}
