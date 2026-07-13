/** ResearchCard — the shared symbol research dossier.
 *
 *  The full research card extracted from the Watchlist › Research tab so it can
 *  be reused verbatim on the Universe / Research page (in a modal). Renders the
 *  key numbers, where the name is trading (vs 50/200-day MA + 52-week range),
 *  the analyst street, and the AI investment brief. Nothing here is a trade
 *  plan — levels live on the Trading page.
 */

import {
  RefreshCw, Loader2, Sparkles, ArrowRight,
} from "lucide-react";
import type { FundamentalsItem, AIBrief } from "../api/hooks";

/** AI brief: regenerating it costs LLM, so only the admin who pays for it can. */
export const AI_ADMIN_EMAIL = "vbolofinde@gmail.com";

/* ── formatters ──────────────────────────────────────────────────── */
export const pctText = (v: number | null | undefined) => (v != null ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : "—");
export const money = (v: number | null | undefined) => (v != null ? `$${v.toFixed(2)}` : "—");
export function fmtAge(iso: string | null): string {
  if (!iso) return "never";
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6;
  if (h < 1) return "just now";
  if (h < 24) return `${Math.round(h)}h ago`;
  return `${Math.round(h / 24)}d ago`;
}
export function fmtMarketCap(v: number | null): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toFixed(0)}`;
}
export const growthColor = (g: number | null | undefined) =>
  g == null ? "text-text-faint" : g > 0 ? "text-bullish-text" : g < 0 ? "text-bearish-text" : "text-text-muted";
export function consensusBadge(c: string | null): string {
  if (c === "Buy") return "bg-bullish-subtle text-bullish-text";
  if (c === "Sell") return "bg-bearish-subtle text-bearish-text";
  if (c === "Hold") return "bg-warning-subtle text-warning-text";
  return "bg-surface-3 text-text-faint";
}
export function gradeBadge(g: string | null | undefined): string {
  if (g?.startsWith("A")) return "bg-bullish-subtle text-bullish-text";
  if (g?.startsWith("B")) return "bg-accent/15 text-accent";
  return "bg-surface-3 text-text-muted";
}
/** Freshness of the numbers: green ≤6h, amber older, empty ring = never fetched. */
export function freshDot(iso: string | null): string {
  if (!iso) return "border border-text-faint/50";
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6;
  return h <= 6 ? "bg-bullish-text" : "bg-amber-400";
}

/* ── small pieces ────────────────────────────────────────────────── */
function Tile({ k, v, sub, tone }: { k: string; v: string; sub?: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-border-subtle bg-surface-1 p-2.5">
      <div className="font-mono text-[8.5px] uppercase tracking-wide text-text-faint">{k}</div>
      <div className={`font-mono text-[16px] font-bold ${tone ?? "text-text-primary"}`}>{v}</div>
      {sub && <div className="text-[9.5px] text-text-faint">{sub}</div>}
    </div>
  );
}

function KeyNumbers({ it }: { it: FundamentalsItem }) {
  const m = it.metrics;
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <Tile k="EPS ttm" v={money(it.trailing_eps)} />
      <Tile k="EPS fwd" v={money(it.forward_eps)} />
      <Tile k="EPS growth" v={pctText(it.eps_growth_pct)} tone={growthColor(it.eps_growth_pct)} />
      <Tile k="P/E" v={it.pe_ratio != null ? it.pe_ratio.toFixed(1) : "—"} sub="trailing" />
      <Tile k="Rev growth" v={pctText(m?.revenue_growth_pct)} tone={growthColor(m?.revenue_growth_pct)} />
      <Tile k="Margins" v={m?.net_margin_pct != null ? `${m.net_margin_pct.toFixed(0)}%` : "—"} sub="net" />
    </div>
  );
}

function vsMa(last: number | null | undefined, ma: number | null | undefined) {
  if (last == null || ma == null) return null;
  const pct = ((last - ma) / ma) * 100;
  return { above: last >= ma, txt: `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%` };
}

function WhereTrading({ it }: { it: FundamentalsItem }) {
  const m = it.metrics;
  if (!m) return null;
  const ma50 = vsMa(m.last_price, m.ma50);
  const ma200 = vsMa(m.last_price, m.ma200);
  const hi = m.week52_high, lo = m.week52_low, px = m.last_price;
  const pct = hi != null && lo != null && px != null && hi > lo ? Math.max(0, Math.min(100, ((px - lo) / (hi - lo)) * 100)) : null;
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
      <Tile k="vs 50-day MA" v={ma50 ? ma50.txt : "—"} tone={ma50 ? (ma50.above ? "text-bullish-text" : "text-bearish-text") : undefined} sub={ma50 ? (ma50.above ? "above" : "below") : undefined} />
      <Tile k="vs 200-day MA" v={ma200 ? ma200.txt : "—"} tone={ma200 ? (ma200.above ? "text-bullish-text" : "text-bearish-text") : undefined} sub={ma200 ? (ma200.above ? "above" : "below") : undefined} />
      <div className="rounded-lg border border-border-subtle bg-surface-1 p-2.5">
        <div className="flex items-baseline justify-between">
          <span className="font-mono text-[8.5px] uppercase tracking-wide text-text-faint">52-week range</span>
          {pct != null && <span className="font-mono text-[10px] text-text-muted">{Math.round(pct)}%</span>}
        </div>
        <div className="relative mt-2 h-1.5 rounded-full bg-gradient-to-r from-bearish-text/60 via-amber-400/50 to-bullish-text/60">
          {pct != null && <span className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface-0 bg-text-primary" style={{ left: `${pct}%` }} />}
        </div>
        <div className="mt-1 flex justify-between font-mono text-[9px] text-text-faint">
          <span>L {money(lo)}</span>
          <span className="text-text-secondary">{money(px)}</span>
          <span>H {money(hi)}</span>
        </div>
      </div>
    </div>
  );
}

function TheStreet({ it }: { it: FundamentalsItem }) {
  const sb = it.rec_strong_buy ?? 0, b = it.rec_buy ?? 0, h = it.rec_hold ?? 0, s = it.rec_sell ?? 0, ss = it.rec_strong_sell ?? 0;
  const total = sb + b + h + s + ss;
  if (total === 0) return <p className="text-[11px] text-text-faint">No analyst coverage.</p>;
  const seg = (n: number, cls: string) => (n > 0 ? <div className={cls} style={{ width: `${(n / total) * 100}%` }} /> : null);
  return (
    <div className="space-y-1.5">
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-surface-3">
        {seg(sb, "bg-bullish")}{seg(b, "bg-bullish/55")}{seg(h, "bg-warning/70")}{seg(s, "bg-bearish/55")}{seg(ss, "bg-bearish")}
      </div>
      <div className="flex items-center justify-between font-mono text-[10px] text-text-faint">
        <span className="text-text-muted">Strong buy {sb} · Buy {b} · Hold {h} · Sell {s + ss}</span>
        <span>{total} analysts</span>
      </div>
    </div>
  );
}

/* ── AI investment brief — thesis + case grid + bull/risk + verdict ── */
function BriefBox({ label, text, accent }: { label: string; text: string; accent?: "bull" | "risk" | "verdict" }) {
  const border = accent === "bull" ? "border-bullish/30" : accent === "risk" ? "border-bearish/30" : accent === "verdict" ? "border-accent/30" : "border-border-subtle";
  const lab = accent === "bull" ? "text-bullish-text" : accent === "risk" ? "text-bearish-text" : accent === "verdict" ? "text-accent" : "text-text-muted";
  return (
    <div className={`rounded-lg border ${border} bg-surface-1 p-3`}>
      <div className={`mb-1 font-mono text-[9.5px] uppercase tracking-wide ${lab}`}>{label}</div>
      <p className="text-[11.5px] leading-relaxed text-text-secondary">{text}</p>
    </div>
  );
}

function BriefView({ brief }: { brief: AIBrief }) {
  return (
    <div className="space-y-3">
      {brief.summary && <p className="max-w-[72ch] text-[13px] font-medium leading-relaxed text-text-primary">{brief.summary}</p>}
      <div className="grid gap-2 sm:grid-cols-2">
        {brief.business && <BriefBox label="Business & moat" text={brief.business} />}
        {brief.growth && <BriefBox label="Growth & margins" text={brief.growth} />}
        {brief.valuation && <BriefBox label="Valuation" text={brief.valuation} />}
        {brief.analyst && <BriefBox label="Analyst take" text={brief.analyst} />}
      </div>
      {(brief.bull_case || brief.risks) && (
        <div className="grid gap-2 sm:grid-cols-2">
          {brief.bull_case && <BriefBox label="🟢 Bull case" text={brief.bull_case} accent="bull" />}
          {brief.risks && <BriefBox label="🔴 Key risks" text={brief.risks} accent="risk" />}
        </div>
      )}
      {(brief.short_term || brief.long_term) && (
        <div className="grid gap-2 sm:grid-cols-2">
          {brief.short_term && <BriefBox label="⏱ Short-term (weeks)" text={brief.short_term} accent="verdict" />}
          {brief.long_term && <BriefBox label="🗓 Long-term (quarters+)" text={brief.long_term} accent="verdict" />}
        </div>
      )}
    </div>
  );
}

/* ── The research dossier for the selected symbol ──────────────────── */
export default function ResearchCard({
  it, isAdmin, onOpen, onRefresh, refreshing, onGenerate, generating,
}: {
  it: FundamentalsItem; isAdmin: boolean; onOpen: () => void;
  onRefresh: () => void; refreshing: boolean; onGenerate: () => void; generating: boolean;
}) {
  const fetched = it.fetched_at != null;
  const px = it.metrics?.last_price;
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="rounded-xl border border-border-subtle bg-surface-1 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[24px] font-bold text-text-primary">{it.symbol}</span>
              {px != null && <span className="font-mono text-[16px] text-text-secondary">{money(px)}</span>}
              {it.consensus && <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${consensusBadge(it.consensus)}`}>{it.consensus}</span>}
            </div>
            <div className="mt-0.5 text-[12px] text-text-muted">
              {it.company_name || "—"}
              {it.sector && <span className="text-text-faint"> · {it.sector}</span>}
              <span className="text-text-faint"> · {fmtMarketCap(it.market_cap)}</span>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <button onClick={onRefresh} disabled={refreshing} className="flex items-center gap-1 rounded-md bg-surface-3 px-2 py-1 text-[10px] font-medium text-text-secondary transition-colors hover:bg-surface-4 disabled:opacity-40">
              {refreshing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />} Numbers
            </button>
            {isAdmin && (
              <button onClick={onGenerate} disabled={generating} className="flex items-center gap-1 rounded-md bg-accent/15 px-2 py-1 text-[10px] font-medium text-accent transition-colors hover:bg-accent/25 disabled:opacity-40">
                {generating ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />} {it.ai_brief ? "Regenerate" : "Generate"} brief
              </button>
            )}
            <button onClick={onOpen} className="flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 text-[10px] font-semibold text-white transition-colors hover:bg-accent-hover">
              Open in Trading <ArrowRight className="h-3 w-3" />
            </button>
          </div>
        </div>
        <p className="mt-2 font-mono text-[10px] text-text-faint">
          Numbers {fmtAge(it.fetched_at)} · Brief {it.ai_generated_at ? fmtAge(it.ai_generated_at) : "not generated"} · nothing here is a trade plan — levels live on the Trading page.
        </p>
      </div>

      {!fetched ? (
        <div className="rounded-xl border border-border-subtle bg-surface-1 p-6 text-center text-[12px] text-text-faint">
          Not fetched yet — tap <b className="text-text-secondary">Numbers</b> to load fundamentals, analyst ratings, and metrics.
        </div>
      ) : (
        <>
          <section className="space-y-2">
            <h3 className="font-mono text-[10px] uppercase tracking-wide text-text-faint">Key numbers</h3>
            <KeyNumbers it={it} />
          </section>
          <section className="space-y-2">
            <h3 className="font-mono text-[10px] uppercase tracking-wide text-text-faint">Where it's trading</h3>
            <WhereTrading it={it} />
          </section>
          <section className="space-y-2">
            <h3 className="font-mono text-[10px] uppercase tracking-wide text-text-faint">The Street</h3>
            <div className="rounded-xl border border-border-subtle bg-surface-1 p-3"><TheStreet it={it} /></div>
          </section>
          <section className="space-y-2">
            <h3 className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-wide text-accent">
              <Sparkles className="h-3 w-3" /> Investment brief — AI-generated · verify before acting
            </h3>
            {it.ai_brief ? (
              <BriefView brief={it.ai_brief} />
            ) : (
              <div className="rounded-xl border border-border-subtle bg-surface-1 p-5 text-center text-[12px] text-text-faint">
                {isAdmin ? "No brief yet — tap Generate brief (Sonnet)." : "AI brief not generated yet — it'll appear here once it's run."}
              </div>
            )}
          </section>
          {it.description && (
            <details className="rounded-xl border border-border-subtle bg-surface-1 p-3">
              <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-wide text-text-muted">About {it.company_name || it.symbol}</summary>
              <p className="mt-2 max-w-[78ch] text-[12px] leading-relaxed text-text-muted">{it.description}</p>
            </details>
          )}
        </>
      )}
    </div>
  );
}
