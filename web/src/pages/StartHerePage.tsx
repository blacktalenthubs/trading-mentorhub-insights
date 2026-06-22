/** StartHerePage — "pick how you trade" onboarding (recommendations / Sub-spec N).
 *  Everything ships OFF by default; this turns the 45-toggle wall into one tap:
 *  pick Day / Swing / Long-term / New and we bulk-enable that style's alert types
 *  via the trade_group bulk endpoint. Re-openable any time from Settings.
 *  Own scroll root (AppLayout <main> is overflow-hidden).
 */
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Zap, TrendingUp, CalendarDays, Sparkles, Check, ChevronRight, Settings as Cog } from "lucide-react";
import { useAlertConfig, useToggleAllAlertConfig, useToggleAlertConfig } from "../api/hooks";

type Style = {
  id: string;
  group?: string;        // trade_group to bulk-enable in one shot
  starter?: string[];    // explicit alert_types for the "I'm new" 3-pack
  icon: ReactNode;
  title: string;
  blurb: string;
  examples: string;
};

// The simplest high-quality 3-pack for beginners (rule names — no tv_ prefix).
const STARTER = ["staged_pdl_reclaim", "rc_4h", "weekly_ma_held"];

const STYLES: Style[] = [
  {
    id: "day", group: "Day Trade", icon: <Zap className="h-5 w-5" />,
    title: "Day trader",
    blurb: "Intraday — in and out the same day, stop at nearby structure.",
    examples: "PDH/PDL held + reclaim · 4h RC · ORL held · gap-and-go",
  },
  {
    id: "swing", group: "Swing Trade", icon: <TrendingUp className="h-5 w-5" />,
    title: "Swing trader",
    blurb: "Daily chart, hold days — buy the dip, target RSI 70.",
    examples: "RSI oversold · 5/20 EMA cross · daily MA bounce",
  },
  {
    id: "long", group: "Long Term", icon: <CalendarDays className="h-5 w-5" />,
    title: "Long-term / position",
    blurb: "Weekly chart, hold weeks-months — Weinstein Stage-2 entries.",
    examples: "Weekly 10w/30w MA held / reclaim · weekly RC",
  },
  {
    id: "new", starter: STARTER, icon: <Sparkles className="h-5 w-5" />,
    title: "I'm new to this",
    blurb: "Start with a simple, high-quality 3-pack and learn as you go.",
    examples: "PDL reclaim · 4h RC · weekly MA held",
  },
];

export default function StartHerePage() {
  const nav = useNavigate();
  const { data: types } = useAlertConfig();
  const bulk = useToggleAllAlertConfig();
  const one = useToggleAlertConfig();
  const [done, setDone] = useState<string | null>(null);
  const busy = bulk.isPending || one.isPending;

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
    setDone(s.id);
  }

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden bg-surface-0">
      <div className="mx-auto max-w-3xl px-4 sm:px-6 py-8 pb-16">
        <header className="mb-6">
          <h1 className="font-display text-xl font-semibold text-text-primary">Start here</h1>
          <p className="mt-1 text-[13px] text-text-muted">
            Nothing is on by default. Pick how you trade and we'll switch on the right
            alerts — you can fine-tune anything later in Settings.
          </p>
        </header>

        <div className="grid gap-3 sm:grid-cols-2">
          {STYLES.map((s) => {
            const count = s.group ? onByGroup[s.group] ?? 0 : 0;
            const isDone = done === s.id;
            return (
              <button
                key={s.id}
                onClick={() => pick(s)}
                disabled={busy}
                className={`flex flex-col gap-2 rounded-2xl border p-4 text-left transition-colors disabled:opacity-60 ${
                  isDone
                    ? "border-accent/60 bg-accent/10"
                    : "border-border-subtle bg-surface-1 hover:bg-surface-2"
                }`}
              >
                <div className="flex items-center gap-2.5">
                  <span className={`shrink-0 rounded-xl p-2 ${isDone ? "bg-accent/20 text-accent" : "bg-surface-3 text-text-secondary"}`}>
                    {isDone ? <Check className="h-5 w-5" /> : s.icon}
                  </span>
                  <div className="min-w-0">
                    <p className="font-display text-[14px] font-semibold text-text-primary">{s.title}</p>
                    {s.group && count > 0 && (
                      <p className="text-[11px] font-semibold text-accent">{count} alert{count > 1 ? "s" : ""} on</p>
                    )}
                  </div>
                </div>
                <p className="text-[12.5px] leading-snug text-text-secondary">{s.blurb}</p>
                <p className="text-[11px] text-text-faint">{s.examples}</p>
                {isDone && (
                  <p className="mt-0.5 text-[11.5px] font-medium text-accent">
                    Enabled ✓ — add your symbols next so they fire.
                  </p>
                )}
              </button>
            );
          })}
        </div>

        {/* next steps */}
        <div className="mt-6 space-y-2">
          <button
            onClick={() => nav("/watchlist")}
            className="flex w-full items-center justify-between rounded-xl border border-border-subtle bg-surface-1 px-4 py-3 text-left hover:bg-surface-2"
          >
            <div>
              <p className="text-[13px] font-semibold text-text-primary">Add your symbols</p>
              <p className="text-[11.5px] text-text-muted">Alerts only fire for names on your watchlist.</p>
            </div>
            <ChevronRight className="h-4 w-4 text-text-faint" />
          </button>
          <button
            onClick={() => nav("/settings")}
            className="flex w-full items-center justify-between rounded-xl border border-border-subtle bg-surface-1 px-4 py-3 text-left hover:bg-surface-2"
          >
            <div className="flex items-center gap-2">
              <Cog className="h-4 w-4 text-text-faint" />
              <div>
                <p className="text-[13px] font-semibold text-text-primary">Advanced — all alert toggles</p>
                <p className="text-[11.5px] text-text-muted">Every type, grouped by trade style.</p>
              </div>
            </div>
            <ChevronRight className="h-4 w-4 text-text-faint" />
          </button>
        </div>
      </div>
    </div>
  );
}
