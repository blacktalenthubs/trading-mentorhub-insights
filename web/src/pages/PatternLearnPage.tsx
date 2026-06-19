/** PatternLearnPage — explains a single alert pattern (#64 Sub-spec K / C).
 *  Deep-linked from Strategy Analysis + the signal card's "Learn". Reads the registry:
 *  what it is, why it's an edge, how to trade it — plus a simple annotated diagram of
 *  the price action vs the level (the "chart" lite; a live per-symbol chart is a follow-up).
 */
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { patternFor } from "../lib/alertRegistry";

function shapeOf(code: string): "held" | "reclaim" | "break" | "rejection" | "flat" {
  const c = code.toLowerCase();
  if (/rc_?4h|rc4|_reclaim|^rc_?h|weekly_rc/.test(c)) return "reclaim";
  if (c.endsWith("_held") || c.includes("avwap_held") || c.includes("support")) return "held";
  if (c.endsWith("_break")) return "break";
  if (c.endsWith("_rejection") || c.includes("reject")) return "rejection";
  return "flat";
}

const PATHS: Record<string, { d: string; stroke: string }> = {
  held:      { d: "10,16 60,26 100,40 140,30 190,18", stroke: "var(--color-bullish)" },
  reclaim:   { d: "10,30 55,40 100,56 145,40 190,24", stroke: "var(--color-bullish)" },
  break:     { d: "10,56 70,50 110,40 150,27 190,16", stroke: "var(--color-bullish)" },
  rejection: { d: "10,56 60,48 100,40 140,48 190,58", stroke: "var(--color-bearish)" },
  flat:      { d: "10,40 60,30 100,44 140,28 190,34", stroke: "var(--color-bullish)" },
};

function Diagram({ code }: { code: string }) {
  const s = PATHS[shapeOf(code)];
  return (
    <div className="rounded-xl border border-border-subtle bg-surface-1 p-4">
      <svg viewBox="0 0 200 72" className="w-full h-32" preserveAspectRatio="none">
        {/* the level */}
        <line x1="0" y1="40" x2="200" y2="40" stroke="var(--color-text-faint)" strokeWidth="0.8" strokeDasharray="3 3" />
        <polyline points={s.d} fill="none" stroke={s.stroke} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      </svg>
      <div className="mt-1 flex justify-between text-[10px] text-text-faint">
        <span>price action</span>
        <span>— — the level</span>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-text-faint mb-1.5">{title}</h2>
      <p className="text-[14px] leading-relaxed text-text-secondary">{children}</p>
    </div>
  );
}

export default function PatternLearnPage() {
  const { code } = useParams<{ code: string }>();
  const nav = useNavigate();
  const p = patternFor(code);

  return (
    <div className="h-full overflow-y-auto bg-surface-0">
      <div className="mx-auto max-w-2xl px-4 sm:px-6 py-6 space-y-5 pb-16">
        <button onClick={() => nav(-1)} className="inline-flex items-center gap-1 text-[12px] text-text-muted hover:text-text-secondary">
          <ArrowLeft size={14} /> Back
        </button>

        {p ? (
          <>
            <div>
              <span className="text-[10px] uppercase tracking-wider text-text-faint">{p.group} setup</span>
              <h1 className="font-display text-2xl font-semibold text-text-primary mt-1">{p.label}</h1>
            </div>
            <Diagram code={p.code} />
            <Section title="What it is">{p.what}</Section>
            <Section title="Why it's an edge">{p.why}</Section>
            <Section title="How to trade it">{p.how}</Section>
            <p className="text-[11px] text-text-faint pt-2 border-t border-border-subtle">Annotated live-chart examples coming. This is the setup logic the alert fires on.</p>
          </>
        ) : (
          <div className="rounded-xl border border-border-subtle bg-surface-1 p-8 text-center text-[13px] text-text-faint">
            No lesson for <span className="font-mono">{code}</span> yet — it may be a retired alert type.
          </div>
        )}
      </div>
    </div>
  );
}
