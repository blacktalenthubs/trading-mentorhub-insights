/** StartHerePage — onboarding + education hub (redesign).
 *  Left: a 4-step checklist (pick a style → add symbols → connect Telegram → learn the
 *  setups). Right rail: progress, the day's workflow, and a live "your alerts right now"
 *  read. All from existing data (alert config · watchlist · Telegram status). Nothing is
 *  on by default; this page remembers where you left off. Own scroll root.
 */
import { useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  Zap, TrendingUp, CalendarDays, Sparkles, Check, ChevronRight, Settings as Cog,
  Send, Star, GraduationCap, ArrowRight,
} from "lucide-react";
import {
  useAlertConfig, useToggleAllAlertConfig, useToggleAlertConfig,
  useWatchlist, useAddSymbol, useTelegramStatus, useTelegramLink,
} from "../api/hooks";

/* ── Step 1: trading styles ──────────────────────────────────────── */
type Style = { id: string; group?: string; starter?: string[]; icon: ReactNode; tag: string; tagCls: string; title: string; blurb: string; examples: string };
const STARTER = ["staged_pdl_reclaim", "rc_4h", "weekly_ma_held"];
const STYLES: Style[] = [
  { id: "day", group: "Day Trade", icon: <Zap className="h-4 w-4" />, tag: "DAY", tagCls: "bg-warning-subtle text-warning-text",
    title: "Day trader", blurb: "Intraday — in and out the same day, stop at nearby structure.",
    examples: "PDH/PDL held + reclaim · 4h RC · gap-and-go" },
  { id: "swing", group: "Swing Trade", icon: <TrendingUp className="h-4 w-4" />, tag: "SWING", tagCls: "bg-accent/15 text-accent",
    title: "Swing trader", blurb: "Daily chart, hold days — buy the dip, target RSI 70.",
    examples: "RSI oversold · 5/20 EMA cross · daily MA bounce" },
  { id: "long", group: "Long Term", icon: <CalendarDays className="h-4 w-4" />, tag: "LT", tagCls: "bg-violet-400/15 text-violet-400",
    title: "Long-term / position", blurb: "Weekly chart, hold weeks-months — Weinstein Stage-2 entries.",
    examples: "Weekly 10w/30w MA held / reclaim · weekly RC" },
  { id: "new", starter: STARTER, icon: <Sparkles className="h-4 w-4" />, tag: "NEW", tagCls: "bg-bullish-subtle text-bullish-text",
    title: "I'm new to this", blurb: "Start with a simple, high-quality 3-pack and learn as you go.",
    examples: "PDL reclaim · 4h RC · weekly MA held" },
];

/* ── Step 4: setup lessons (static education) ────────────────────── */
function Diagram({ kind }: { kind: "reclaim" | "break" | "hold" }) {
  const d = kind === "reclaim" ? "M2,14 L20,14 L34,31 L54,31 L74,10 L98,7"
    : kind === "break" ? "M2,29 L30,27 L54,25 L74,12 L98,5"
    : "M2,27 L24,22 L44,20 L48,25 L70,17 L98,11";
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className="h-9 w-full">
      <line x1="0" y1="20" x2="100" y2="20" stroke="currentColor" strokeDasharray="2 2" strokeWidth="0.75" className="text-text-faint" />
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" className="text-bullish-text" />
    </svg>
  );
}
const LESSONS: { title: string; kind: "reclaim" | "break" | "hold"; text: string }[] = [
  { title: "PDL reclaim", kind: "reclaim", text: "Price loses yesterday's low, then takes it back — a swept-low bounce. Stop = the sweep low." },
  { title: "PDH break", kind: "break", text: "A confirmed close above yesterday's high on volume — continuation. Stop = back below PDH." },
  { title: "4-hour reclaim", kind: "reclaim", text: "Dips under the prior 4h low and reclaims it — bounce off support. Stop = the retest low." },
  { title: "Weekly MA held", kind: "hold", text: "Tags a rising 10/30-week MA and holds — long-term trend support. Position-size entry." },
];

/* ── small pieces ────────────────────────────────────────────────── */
const SH = ({ children }: { children: ReactNode }) => (
  <div className="mb-2 font-mono text-[11px] font-bold uppercase tracking-wider text-amber-400/80">{children}</div>
);
function StepHead({ n, done, title, hint }: { n: number; done: boolean; title: string; hint?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold ${done ? "bg-bullish-text text-surface-0" : "bg-surface-3 text-text-secondary"}`}>
        {done ? <Check className="h-3.5 w-3.5" /> : n}
      </span>
      <span className="font-display text-[15px] font-semibold text-text-primary">{title}</span>
      {hint && <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold ${done ? "bg-bullish-subtle text-bullish-text" : "bg-warning-subtle text-warning-text"}`}>{hint}</span>}
    </div>
  );
}

const QUICK_ADD = ["SPY", "QQQ", "NVDA", "AAPL", "TSLA", "BTC-USD"];

export default function StartHerePage() {
  const nav = useNavigate();
  const { data: types } = useAlertConfig();
  const { data: watchlist } = useWatchlist();
  const { data: tg } = useTelegramStatus();
  const bulk = useToggleAllAlertConfig();
  const one = useToggleAlertConfig();
  const addSym = useAddSymbol();
  const tgLink = useTelegramLink();
  const [pickedStyle, setPickedStyle] = useState<string | null>(null);
  const [symInput, setSymInput] = useState("");
  const busy = bulk.isPending || one.isPending;

  const onByGroup = useMemo(() => {
    const m: Record<string, number> = {};
    for (const t of types ?? []) if (t.enabled) m[t.trade_group] = (m[t.trade_group] ?? 0) + 1;
    return m;
  }, [types]);
  const enabledCount = (types ?? []).filter((t) => t.enabled).length;
  const owned = useMemo(() => new Set((watchlist ?? []).map((w) => w.symbol.toUpperCase())), [watchlist]);
  const dominantStyle = useMemo(() => Object.entries(onByGroup).sort((a, b) => b[1] - a[1])[0]?.[0] ?? null, [onByGroup]);

  const styleDone = enabledCount > 0;
  const symbolsDone = (watchlist?.length ?? 0) > 0;
  const tgDone = !!tg?.linked;
  const doneCount = [styleDone, symbolsDone, tgDone].filter(Boolean).length;

  async function pickStyle(s: Style) {
    if (busy) return;
    if (s.group) await bulk.mutateAsync({ enabled: true, trade_group: s.group });
    else if (s.starter) for (const at of s.starter) if ((types ?? []).some((t) => t.alert_type === at)) await one.mutateAsync({ alert_type: at, enabled: true });
    setPickedStyle(s.id);
  }
  function addFromInput() {
    const s = symInput.trim().toUpperCase();
    if (!s) return;
    setSymInput("");
    if (!owned.has(s)) addSym.mutate(s);
  }
  async function linkTelegram() {
    try {
      const res = await tgLink.mutateAsync();
      if (res?.deep_link) window.open(res.deep_link, "_blank");
    } catch { /* toast handled in hook */ }
  }

  const DAY = [
    { t: "8:30a", label: "Morning notes", desc: "premarket gappers + the Gap & Go queue", to: "/premarket" },
    { t: "8:55a", label: "Today's Focus", desc: "the day's curated setups", to: "/today" },
    { t: "9:30a", label: "Live signals", desc: "alerts fire on your watchlist", to: "/trading" },
    { t: "4:10p", label: "EOD recap", desc: "how the day went", to: "/today" },
    { t: "Anytime", label: "Ideas & research", desc: "graded ideas + AI briefs", to: "/trade-ideas" },
  ];

  const panel = "rounded-2xl border border-border-subtle bg-surface-1 p-4";

  return (
    <div className="h-full overflow-y-auto overflow-x-hidden bg-surface-0">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 py-8 pb-16">
        <header className="mb-4">
          <h1 className="font-display text-xl font-semibold text-text-primary">Start here</h1>
          <p className="mt-1 text-[13px] text-text-muted">Three steps and the desk is live. Come back any time — this page remembers where you left off.</p>
        </header>

        {/* Disclaimer */}
        <div className="mb-5 flex items-start gap-2 rounded-xl border border-warning/25 bg-warning/5 p-3 text-[12px] leading-relaxed text-text-muted">
          <span className="text-[15px]">⚖️</span>
          <span><b className="text-text-secondary">Educational tool — not financial advice.</b> Signals are patterns, not recommendations. Nothing here is a trade plan. Paper-trade first and manage your own risk.</span>
        </div>

        <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
          {/* ── Left: the steps ── */}
          <div className="space-y-4">
            {/* Step 1 — style */}
            <div className={panel}>
              <StepHead n={1} done={styleDone} title="Choose how you trade" hint={styleDone ? "done" : undefined} />
              <p className="mt-1.5 mb-3 text-[12px] text-text-muted">Nothing is on by default. Pick a style and we switch on the right alerts — fine-tune later in Settings.</p>
              <div className="grid gap-2.5 sm:grid-cols-2">
                {STYLES.map((s) => {
                  const count = s.group ? onByGroup[s.group] ?? 0 : 0;
                  const isPicked = pickedStyle === s.id || (s.group && count > 0);
                  return (
                    <button key={s.id} onClick={() => pickStyle(s)} disabled={busy}
                      className={`flex flex-col gap-1.5 rounded-xl border p-3 text-left transition-colors disabled:opacity-60 ${isPicked ? "border-accent/60 bg-accent/[0.07]" : "border-border-subtle bg-surface-2/40 hover:bg-surface-2"}`}>
                      <div className="flex items-center gap-2">
                        <span className={`rounded px-1.5 py-0.5 text-[8.5px] font-bold ${s.tagCls}`}>{s.tag}</span>
                        <span className="font-display text-[13.5px] font-semibold text-text-primary">{s.title}</span>
                        {s.group && count > 0 && <span className="ml-auto text-[10px] font-semibold text-accent">{count} on</span>}
                      </div>
                      <p className="text-[12px] leading-snug text-text-secondary">{s.blurb}</p>
                      <p className="font-mono text-[10px] text-text-faint">{s.examples}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Step 2 — symbols */}
            <div className={panel}>
              <StepHead n={2} done={symbolsDone} title="Add your symbols" hint={symbolsDone ? "done" : undefined} />
              <p className="mt-1.5 mb-3 text-[12px] text-text-muted">Alerts only fire for names on your watchlist. Add a few — or grab a whole sector list on the Watchlist page.</p>
              <div className="mb-2 flex gap-2">
                <input value={symInput} onChange={(e) => setSymInput(e.target.value.toUpperCase())}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addFromInput(); } }}
                  placeholder="Add a ticker (e.g. NVDA)"
                  className="flex-1 rounded-lg border border-border-subtle bg-surface-2 px-3 py-2 text-[13px] text-text-primary placeholder:text-text-faint outline-none focus:border-accent" />
                <button onClick={addFromInput} disabled={!symInput.trim() || addSym.isPending}
                  className="rounded-lg bg-accent px-3 py-2 text-[12px] font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-40">Add</button>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {QUICK_ADD.map((s) => {
                  const on = owned.has(s);
                  return (
                    <button key={s} onClick={() => !on && addSym.mutate(s)} disabled={on || addSym.isPending}
                      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 font-mono text-[11px] transition-colors ${on ? "border-bullish/40 bg-bullish/10 text-bullish-text" : "border-border-subtle bg-surface-2 text-text-secondary hover:border-accent"}`}>
                      {on && <Check className="h-3 w-3" />}{s}
                    </button>
                  );
                })}
                <button onClick={() => nav("/watchlist")} className="inline-flex items-center gap-1 rounded-full border border-dashed border-border-subtle px-2.5 py-1 text-[11px] text-accent hover:border-accent">
                  <Star className="h-3 w-3" /> Sector lists →
                </button>
              </div>
            </div>

            {/* Step 3 — telegram */}
            <div className={panel}>
              <StepHead n={3} done={tgDone} title="Connect Telegram" hint={tgDone ? "connected" : "1 tap left"} />
              {tgDone ? (
                <p className="mt-1.5 text-[12px] text-text-muted">✅ Linked — alerts, morning notes, and the EOD recap deliver to your Telegram.</p>
              ) : (
                <>
                  <p className="mt-1.5 mb-3 text-[12px] text-text-muted">Link Telegram and your first alerts can reach you today. Not into Telegram? Alerts still record in-app.</p>
                  <div className="flex flex-wrap gap-2">
                    <button onClick={linkTelegram} disabled={tgLink.isPending}
                      className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-[12px] font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-40">
                      <Send className="h-3.5 w-3.5" /> Open the bot & link
                    </button>
                    <button onClick={() => nav("/settings")} className="rounded-lg border border-border-subtle px-3 py-2 text-[12px] font-medium text-text-secondary hover:bg-surface-2">Skip — set up later</button>
                  </div>
                </>
              )}
            </div>

            {/* Step 4 — learn (optional) */}
            <div className={panel}>
              <StepHead n={4} done={false} title="Learn the setups" hint="optional" />
              <p className="mt-1.5 mb-3 text-[12px] text-text-muted">Every alert is a level event — a break or a reclaim. The anatomy of the ones you'll see most:</p>
              <div className="grid gap-2.5 sm:grid-cols-2">
                {LESSONS.map((l) => (
                  <div key={l.title} className="rounded-xl border border-border-subtle bg-surface-2/40 p-3">
                    <div className="mb-1 flex items-center gap-1.5">
                      <GraduationCap className="h-3.5 w-3.5 text-accent" />
                      <span className="font-mono text-[12px] font-bold text-text-primary">{l.title}</span>
                    </div>
                    <Diagram kind={l.kind} />
                    <p className="mt-1.5 text-[11.5px] leading-snug text-text-muted">{l.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* ── Right rail ── */}
          <div className="space-y-4 lg:sticky lg:top-2 lg:self-start">
            {/* progress */}
            <div className={panel}>
              <div className="flex items-baseline justify-between">
                <SH>Setup progress</SH>
                <span className="font-mono text-[11px] text-text-secondary">{doneCount} of 3</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
                <div className="h-full rounded-full bg-bullish-text transition-all" style={{ width: `${(doneCount / 3) * 100}%` }} />
              </div>
              <p className="mt-2 text-[11.5px] text-text-muted">
                {doneCount === 3 ? "You're live — alerts can reach you." : !tgDone ? "Link Telegram and your first alerts can reach you today." : "Add your symbols so alerts have names to scan."}
              </p>
            </div>

            {/* your day */}
            <div className={panel}>
              <SH>Your day with the desk</SH>
              <div className="space-y-0.5">
                {DAY.map((d) => (
                  <button key={d.t} onClick={() => nav(d.to)} className="flex w-full items-start gap-2.5 rounded-lg px-1.5 py-1.5 text-left transition-colors hover:bg-surface-2">
                    <span className="w-12 shrink-0 font-mono text-[10px] text-text-faint">{d.t}</span>
                    <span className="min-w-0 flex-1">
                      <span className="text-[12px] font-semibold text-text-secondary">{d.label}</span>
                      <span className="block text-[11px] text-text-faint">{d.desc}</span>
                    </span>
                    <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-text-faint" />
                  </button>
                ))}
              </div>
            </div>

            {/* alerts right now */}
            <div className={panel}>
              <SH>Your alerts right now</SH>
              <dl className="space-y-2 text-[12px]">
                <div className="flex items-start justify-between gap-2">
                  <dt className="text-text-faint">Style</dt>
                  <dd className="text-right text-text-secondary">{enabledCount > 0 ? `${dominantStyle ?? "Mixed"} — ${enabledCount} types on` : "None yet"}</dd>
                </div>
                <div className="flex items-start justify-between gap-2">
                  <dt className="text-text-faint">Names</dt>
                  <dd className="text-right text-text-secondary">{watchlist?.length ? `${watchlist.length} scanned every ~3 min` : "No symbols yet"}</dd>
                </div>
                <div className="flex items-start justify-between gap-2">
                  <dt className="text-text-faint">Delivery</dt>
                  <dd className={`text-right ${tgDone ? "text-bullish-text" : "text-warning-text"}`}>{tgDone ? "Telegram connected" : "Not connected — recorded, can't reach you yet"}</dd>
                </div>
              </dl>
              <button onClick={() => nav("/settings")} className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-border-subtle px-3 py-2 text-[12px] font-medium text-text-secondary hover:bg-surface-2">
                <Cog className="h-3.5 w-3.5" /> Tune every alert <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
