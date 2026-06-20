/** StartHerePage — "pick how you trade" onboarding (recommendations / Sub-spec N).
 *  Everything ships OFF by default; this turns the 45-toggle wall into a 30-second
 *  guided setup: pick one or more trade styles → we bulk-enable that style's alert
 *  types (trade_group bulk endpoint) → add symbols. Re-openable from Settings.
 *  Own scroll root (AppLayout <main> is overflow-hidden).
 */
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  Zap, TrendingUp, CalendarDays, Sparkles, Check, ChevronRight,
  Star, BellRing, SlidersHorizontal,
} from "lucide-react";
import { useAlertConfig, useToggleAllAlertConfig, useToggleAlertConfig } from "../api/hooks";

type Tint = "day" | "swing" | "long" | "new";
type Style = {
  id: Tint;
  group?: string;        // trade_group to bulk-enable in one shot
  starter?: string[];    // explicit alert_types for the "I'm new" 3-pack
  icon: ReactNode;
  title: string;
  blurb: string;
  examples: string[];
  recommended?: boolean;
};

// The simplest high-quality 3-pack for beginners (rule names — no tv_ prefix).
const STARTER = ["staged_pdl_reclaim", "rc_4h", "weekly_ma_held"];

// Per-style colour — only CONFIRMED design tokens so classes never render blank.
const TINT: Record<Tint, { icon: string; ring: string; dot: string }> = {
  day:   { icon: "bg-bullish-subtle text-bullish-text", ring: "border-bullish-text/50 bg-bullish-subtle/30", dot: "text-bullish-text" },
  swing: { icon: "bg-accent/15 text-accent",            ring: "border-accent/60 bg-accent/10",               dot: "text-accent" },
  long:  { icon: "bg-warning-subtle text-warning-text", ring: "border-warning-text/50 bg-warning-subtle/30", dot: "text-warning-text" },
  new:   { icon: "bg-accent/15 text-accent",            ring: "border-accent/60 bg-accent/10",               dot: "text-accent" },
};

const STYLES: Style[] = [
  {
    id: "day", group: "Day Trade", icon: <Zap className="h-5 w-5" />,
    title: "Day trader",
    blurb: "Intraday — in and out the same day, stop at nearby structure.",
    examples: ["PDH/PDL held + reclaim", "4h RC / RC-H", "ORL held", "gap-and-go"],
  },
  {
    id: "swing", group: "Swing Trade", icon: <TrendingUp className="h-5 w-5" />,
    title: "Swing trader",
    blurb: "Daily chart, hold days — buy the dip, target RSI 70.",
    examples: ["RSI oversold reclaim", "5/20 EMA cross", "daily MA bounce"],
  },
  {
    id: "long", group: "Long Term", icon: <CalendarDays className="h-5 w-5" />,
    title: "Long-term / position",
    blurb: "Weekly chart, hold weeks-to-months — Weinstein Stage-2 entries.",
    examples: ["Weekly 10w/30w MA", "weekly RC"],
  },
  {
    id: "new", starter: STARTER, icon: <Sparkles className="h-5 w-5" />,
    title: "I'm new to this",
    blurb: "A simple, high-quality 3-pack to start — learn the rest as you go.",
    examples: ["PDL reclaim", "4h RC", "weekly MA held"],
    recommended: true,
  },
];

function StepLabel({ n, title, hint }: { n: number; title: string; hint?: string }) {
  return (
    <div className="mb-3 flex items-center gap-2.5">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-3 text-[11px] font-bold text-text-secondary">
        {n}
      </span>
      <h2 className="font-display text-[15px] font-semibold text-text-primary">{title}</h2>
      {hint && <span className="text-[11.5px] text-text-faint">· {hint}</span>}
    </div>
  );
}

export default function StartHerePage() {
  const nav = useNavigate();
  const { data: types } = useAlertConfig();
  const bulk = useToggleAllAlertConfig();
  const one = useToggleAlertConfig();
  const [picked, setPicked] = useState<Set<Tint>>(new Set());
  const busy = bulk.isPending || one.isPending;

  const totalOn = useMemo(() => (types ?? []).filter((t) => t.enabled).length, [types]);
  const onByGroup = useMemo(() => {
    const m: Record<string, number> = {};
    for (const t of types ?? []) if (t.enabled) m[t.trade_group] = (m[t.trade_group] ?? 0) + 1;
    return m;
  }, [types]);

  async function pick(s: Style) {
    if (busy) return;
    if (s.group) {
      await bulk.mutateAsync({ enabled: true, trade_group: s.group });
    } else if (s.starter) {
      for (const at of s.starter) {
        if ((types ?? []).some((t) => t.alert_type === at)) {
          await one.mutateAsync({ alert_type: at, enabled: true });
        }
      }
    }
    setPicked((p) => new Set(p).add(s.id));
  }

  return (
    <div className="h-full overflow-y-auto bg-surface-0">
      <div className="mx-auto max-w-3xl px-4 sm:px-6 py-8 pb-20">
        {/* hero */}
        <header className="mb-8">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-accent/10 px-2.5 py-1 text-[11px] font-semibold text-accent">
            <Sparkles className="h-3 w-3" /> 30-second setup
          </span>
          <h1 className="mt-3 font-display text-2xl font-bold tracking-tight text-text-primary">
            Set up your alerts
          </h1>
          <p className="mt-1.5 max-w-xl text-[13.5px] leading-relaxed text-text-muted">
            Nothing is on by default — no noise. Tell us how you trade and we'll switch on
            the right alerts for you. You can fine-tune anything later in Settings.
          </p>
        </header>

        {/* step 1 — pick style */}
        <section className="mb-8">
          <StepLabel n={1} title="What do you trade?" hint="pick one or more" />
          <div className="grid gap-3 sm:grid-cols-2">
            {STYLES.map((s) => {
              const t = TINT[s.id];
              const count = s.group ? onByGroup[s.group] ?? 0 : 0;
              const isOn = picked.has(s.id) || count > 0;
              return (
                <button
                  key={s.id}
                  onClick={() => pick(s)}
                  disabled={busy}
                  aria-pressed={isOn}
                  className={`group relative flex flex-col gap-2.5 rounded-2xl border p-4 text-left transition-all disabled:opacity-60 ${
                    isOn ? t.ring + " shadow-sm" : "border-border-subtle bg-surface-1 hover:bg-surface-2 hover:border-border-subtle/80"
                  }`}
                >
                  {s.recommended && !isOn && (
                    <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-surface-3 px-2 py-0.5 text-[10px] font-semibold text-text-secondary">
                      <Star className="h-2.5 w-2.5" /> Beginner
                    </span>
                  )}
                  <div className="flex items-center gap-3">
                    <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-colors ${isOn ? "bg-accent/20 text-accent" : t.icon}`}>
                      {isOn ? <Check className="h-5 w-5" /> : s.icon}
                    </span>
                    <div className="min-w-0">
                      <p className="font-display text-[14.5px] font-semibold text-text-primary">{s.title}</p>
                      {isOn ? (
                        <p className={`text-[11.5px] font-semibold ${t.dot}`}>
                          {count > 0 ? `${count} alert${count > 1 ? "s" : ""} on` : "Enabled ✓"}
                        </p>
                      ) : (
                        <p className="text-[11.5px] text-text-faint">Tap to turn on</p>
                      )}
                    </div>
                  </div>
                  <p className="text-[12.5px] leading-snug text-text-secondary">{s.blurb}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {s.examples.map((e) => (
                      <span key={e} className="rounded-md bg-surface-2 px-1.5 py-0.5 text-[10.5px] text-text-faint">{e}</span>
                    ))}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        {/* live summary */}
        {totalOn > 0 && (
          <div className="mb-8 flex items-center gap-3 rounded-2xl border border-accent/30 bg-accent/[0.07] p-4">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent/15 text-accent">
              <BellRing className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[13.5px] font-semibold text-text-primary">
                {totalOn} alert{totalOn > 1 ? "s" : ""} on — you're set
              </p>
              <p className="text-[12px] text-text-muted">One more step: add the symbols you want them to fire on.</p>
            </div>
          </div>
        )}

        {/* step 2 — symbols */}
        <section className="mb-8">
          <StepLabel n={2} title="Add your symbols" hint="alerts fire only for names you watch" />
          <button
            onClick={() => nav("/watchlist")}
            className="flex w-full items-center gap-3 rounded-2xl border border-border-subtle bg-surface-1 p-4 text-left transition-colors hover:bg-surface-2"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface-3 text-text-secondary">
              <Star className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[13.5px] font-semibold text-text-primary">Build your watchlist</p>
              <p className="text-[12px] text-text-muted">Add the tickers you trade — that's the universe your alerts watch.</p>
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-text-faint" />
          </button>
        </section>

        {/* advanced */}
        <button
          onClick={() => nav("/settings")}
          className="flex w-full items-center gap-2.5 rounded-xl px-4 py-3 text-left text-text-muted transition-colors hover:bg-surface-1 hover:text-text-secondary"
        >
          <SlidersHorizontal className="h-4 w-4 shrink-0" />
          <span className="flex-1 text-[12.5px]">
            <span className="font-semibold">Advanced</span> — fine-tune every alert type, grouped by style
          </span>
          <ChevronRight className="h-4 w-4 shrink-0" />
        </button>
      </div>
    </div>
  );
}
