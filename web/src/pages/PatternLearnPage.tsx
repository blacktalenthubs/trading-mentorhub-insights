/** PatternLearnPage — explains a single alert pattern (#64 Sub-spec K / C).
 *  Deep-linked from Strategy Analysis, the Declined page, and the signal card's "Learn".
 *  Reads the registry: what it is, why it's an edge, and the structured trade plan
 *  (entry / stop / target) — plus an annotated anatomy diagram of the price action vs the
 *  level, with the target/stop guides and the entry marked. The education promise, made real.
 */
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Target, Ban, LogIn, type LucideIcon } from "lucide-react";
import { type ReactNode } from "react";
import { patternFor, type PatternInfo } from "../lib/alertRegistry";
import { useAlertConfig } from "../api/hooks";

type Shape = "held" | "reclaim" | "break" | "rejection" | "flat";
function shapeOf(code: string): Shape {
  const c = code.toLowerCase();
  if (/ma_rejection/.test(c) || c.endsWith("_rejection") || c.includes("reject")) return "rejection";
  if (c.includes("bounce") || c.endsWith("_held") || c.includes("support") || c.includes("pullback") || /rc_?4h/.test(c)) return "held";
  if (c.endsWith("_reclaim") || /weekly_rc|rc_?h\b/.test(c) || c.includes("oversold")) return "reclaim";
  if (c.endsWith("_break") || c.includes("gap_up") || c.includes("cross")) return "break";
  return "flat";
}

const SHAPES: Record<Shape, { pts: string; entry: [number, number] }> = {
  held:      { pts: "20,40 70,48 120,52 170,40 220,28", entry: [120, 52] },
  reclaim:   { pts: "20,46 70,56 120,64 165,48 220,30", entry: [165, 48] },
  break:     { pts: "20,68 70,62 120,52 170,38 220,24", entry: [120, 52] },
  rejection: { pts: "20,72 70,62 120,52 170,62 220,74", entry: [120, 52] },
  flat:      { pts: "20,50 70,44 120,54 170,44 220,50", entry: [120, 52] },
};

function Anatomy({ p }: { p: PatternInfo }) {
  const s = SHAPES[shapeOf(p.code)];
  const short = p.dir === "short";
  const targetY = short ? 88 : 16;
  const stopY = short ? 16 : 88;
  const stroke = short ? "var(--color-bearish)" : "var(--color-bullish)";
  return (
    <div className="rounded-2xl border border-border-subtle bg-surface-1 p-5">
      <div className="text-[10px] uppercase tracking-wider text-text-faint mb-2">Anatomy</div>
      <svg viewBox="0 0 285 104" className="w-full h-40">
        <line x1="0" y1={targetY} x2="240" y2={targetY} stroke="var(--color-bullish)" strokeWidth="0.7" strokeDasharray="2 3" opacity="0.65" />
        <text x="244" y={targetY + 3} fontSize="8" fill="var(--color-bullish)">target</text>
        <line x1="0" y1="52" x2="240" y2="52" stroke="var(--color-text-faint)" strokeWidth="0.9" strokeDasharray="3 3" />
        <text x="244" y="55" fontSize="8" fill="var(--color-text-faint)">level</text>
        <line x1="0" y1={stopY} x2="240" y2={stopY} stroke="var(--color-bearish)" strokeWidth="0.7" strokeDasharray="2 3" opacity="0.65" />
        <text x="244" y={stopY + 3} fontSize="8" fill="var(--color-bearish)">stop</text>
        <polyline points={s.pts} fill="none" stroke={stroke} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
        <text x={s.entry[0]} y={s.entry[1] - 9} fontSize="8" fill="var(--color-text-secondary)" textAnchor="middle">entry</text>
        <circle cx={s.entry[0]} cy={s.entry[1]} r="4" fill={stroke} stroke="var(--color-surface-1)" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

function PlanItem({ icon: Icon, label, text, tone }: { icon: LucideIcon; label: string; text: string; tone: "entry" | "stop" | "target" }) {
  const tones: Record<string, string> = {
    entry: "text-accent bg-accent-subtle",
    stop: "text-bearish-text bg-bearish-subtle",
    target: "text-bullish-text bg-bullish-subtle",
  };
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border-subtle bg-surface-1 px-4 py-3">
      <span className={`grid place-items-center w-7 h-7 rounded-lg shrink-0 ${tones[tone]}`}><Icon size={15} /></span>
      <div className="min-w-0">
        <div className="text-[10px] uppercase tracking-wider text-text-faint">{label}</div>
        <div className="text-[13px] text-text-secondary leading-snug">{text}</div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-text-faint mb-1.5">{title}</h2>
      <p className="text-[14px] leading-relaxed text-text-secondary">{children}</p>
    </div>
  );
}

/** Sibling browser — other live setups in the same group, so a lesson isn't a dead-end.
 *  Catalog (live codes) × registry (label/group); dedupes by label, caps at 8. */
function RelatedSetups({ current }: { current: PatternInfo }) {
  const nav = useNavigate();
  const { data: config } = useAlertConfig();
  const seen = new Set<string>([current.label]);
  const related: PatternInfo[] = [];
  for (const c of config ?? []) {
    const info = patternFor(c.alert_type);
    if (!info || info.group !== current.group || info.code === current.code || seen.has(info.label)) continue;
    seen.add(info.label);
    related.push(info);
    if (related.length >= 8) break;
  }
  if (related.length === 0) return null;
  return (
    <div className="pt-3 border-t border-border-subtle">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-text-faint mb-2">More {current.group} setups</h2>
      <div className="flex flex-wrap gap-2">
        {related.map((r) => (
          <button
            key={r.code}
            onClick={() => nav(`/pattern/${encodeURIComponent(r.code)}`)}
            className="text-[12px] text-accent bg-accent-subtle/40 hover:bg-accent-subtle rounded-lg px-3 py-1.5 transition-colors"
          >
            {r.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function PatternLearnPage() {
  const { code } = useParams<{ code: string }>();
  const nav = useNavigate();
  const p = patternFor(code);

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden bg-surface-0">
      <div className="mx-auto max-w-2xl px-4 sm:px-6 py-6 space-y-6 pb-20">
        <button onClick={() => nav(-1)} className="inline-flex items-center gap-1 text-[12px] text-text-muted hover:text-text-secondary">
          <ArrowLeft size={14} /> Back
        </button>

        {p ? (
          <>
            {/* hero */}
            <div className="flex items-start justify-between gap-3">
              <div>
                <span className="text-[10px] uppercase tracking-wider text-text-faint">{p.group} setup</span>
                <h1 className="font-display text-2xl font-semibold text-text-primary mt-1">{p.label}</h1>
              </div>
              {p.dir && (
                <span className={`text-[11px] font-bold px-2 py-1 rounded shrink-0 ${p.dir === "long" ? "bg-bullish-subtle text-bullish-text" : "bg-bearish-subtle text-bearish-text"}`}>
                  {p.dir.toUpperCase()}
                </span>
              )}
            </div>

            <Anatomy p={p} />

            <Section title="What it is">{p.what}</Section>
            <Section title="Why it's an edge">{p.why}</Section>

            <div>
              <h2 className="text-[11px] font-semibold uppercase tracking-wider text-text-faint mb-2">How to trade it</h2>
              {p.entry ? (
                <div className="space-y-2">
                  <PlanItem icon={LogIn} label="Entry" text={p.entry} tone="entry" />
                  <PlanItem icon={Ban} label="Stop" text={p.stop ?? "—"} tone="stop" />
                  <PlanItem icon={Target} label="Target" text={p.target ?? "—"} tone="target" />
                </div>
              ) : (
                <p className="text-[14px] leading-relaxed text-text-secondary">{p.how}</p>
              )}
            </div>

            <RelatedSetups current={p} />

            <p className="text-[11px] text-text-faint pt-2">
              Annotated live-chart examples coming. This is the setup logic the alert fires on — not financial advice.
            </p>
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
