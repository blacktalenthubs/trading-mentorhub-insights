/** Landing Page — redesigned for launch (2026-07-05, specs/landing-redesign).
 *  Audience: busy professionals with a day job. Story: one platform to day-trade, swing,
 *  and find the next big winner — a rules-based SYSTEM fires the setups, AI AGENTS explain,
 *  triage, brief, and coach. Education-first, not financial advice. Routes to the apps.
 *  Positioning truth: alerts are systems (deterministic); agents (AI) are the insight layer.
 *  No synthetic win-rate claims — outcomes route to the live Performance / track record.
 */
import { useEffect, useState, type ReactNode } from "react";
import { Link, Navigate } from "react-router-dom";
import { useAuthStore } from "../stores/auth";
import StickyLandingCTA from "../components/StickyLandingCTA";
import {
  Crosshair, Menu, X, Zap, TrendingUp, LineChart, Sparkles,
  Clock, Target, Bell, Brain, Sunrise, Search, Satellite,
  BookOpen, Shield, Smartphone, Monitor, ArrowRight,
} from "lucide-react";

/* ── Live track record (real, scored — used only as a descriptive count, never a win-rate) ── */
interface TrackRecord { total_signals: number; wins: number; losses: number; win_rate: number }
function usePublicTrackRecord(): TrackRecord | null {
  const [data, setData] = useState<TrackRecord | null>(null);
  useEffect(() => {
    fetch("/api/v1/intel/public-track-record?days=90")
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => setData(null));
  }, []);
  return data;
}

/* ── Shared primitives (Sub-spec G) ─────────────────────────────────────────── */
function Section({ children, className = "", id }: { children: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={`border-t border-border-subtle py-16 sm:py-20 ${className}`}>
      <div className="mx-auto max-w-6xl px-5">{children}</div>
    </section>
  );
}
function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="mb-3 font-mono text-[11px] uppercase tracking-[0.16em] text-text-faint">{children}</div>;
}
function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-border-subtle bg-surface-1 p-6 ${className}`}>{children}</div>;
}
function Pill({ children }: { children: ReactNode }) {
  return <span className="inline-block rounded-lg border border-border-default bg-surface-3 px-2.5 py-1 text-xs text-text-secondary">{children}</span>;
}
function IconTile({ icon: Icon, tint }: { icon: typeof Zap; tint: string }) {
  return <div className={`mb-4 flex h-10 w-10 items-center justify-center rounded-xl ${tint}`}><Icon className="h-5 w-5" /></div>;
}
function PrimaryCTA({ children, to = "/register", className = "" }: { children: ReactNode; to?: string; className?: string }) {
  return <Link to={to} className={`inline-flex items-center justify-center gap-2 rounded-xl bg-bullish px-5 py-3 font-semibold text-surface-0 shadow-glow-bullish transition-colors hover:bg-bullish-text ${className}`}>{children}</Link>;
}
function SecondaryCTA({ children, to = "/track-record", className = "" }: { children: ReactNode; to?: string; className?: string }) {
  return <Link to={to} className={`inline-flex items-center justify-center gap-2 rounded-xl border border-border-default bg-surface-2 px-5 py-3 font-medium text-text-primary transition-colors hover:border-border-strong ${className}`}>{children}</Link>;
}

/* ── Nav (Sub-spec A) ───────────────────────────────────────────────────────── */
function LandingNav() {
  const [open, setOpen] = useState(false);
  const links = (
    <>
      <a href="#pillars" className="transition-colors hover:text-text-primary">How it works</a>
      <Link to="/learn" className="transition-colors hover:text-text-primary">Patterns</Link>
      <Link to="/track-record" className="transition-colors hover:text-text-primary">Track Record</Link>
      <a href="#pricing" className="transition-colors hover:text-text-primary">Pricing</a>
    </>
  );
  return (
    <div className="sticky top-0 z-40 border-b border-border-subtle bg-surface-0/80 backdrop-blur-md">
      <div className="mx-auto flex h-[62px] max-w-6xl items-center justify-between px-5">
        <Link to="/" className="flex items-center gap-2 font-bold">
          <Crosshair className="h-5 w-5 text-accent" />
          <span><span className="text-gradient-ai">Busy</span>TradersDesk</span>
        </Link>
        <div className="hidden items-center gap-6 text-sm text-text-muted md:flex">{links}</div>
        <div className="flex items-center gap-3">
          <Link to="/login" className="hidden text-sm font-medium text-text-primary transition-colors hover:text-accent sm:block">Sign in</Link>
          <PrimaryCTA className="!px-4 !py-2 text-sm">Start free</PrimaryCTA>
          <button onClick={() => setOpen((v) => !v)} className="text-text-muted md:hidden" aria-label="Menu">{open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}</button>
        </div>
      </div>
      {open && (
        <div className="flex flex-col gap-1 border-t border-border-subtle px-5 py-3 text-sm text-text-secondary md:hidden" onClick={() => setOpen(false)}>{links}</div>
      )}
    </div>
  );
}

/* ── Hero (Sub-spec A) ──────────────────────────────────────────────────────── */
function Hero() {
  return (
    <div className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(900px_400px_at_50%_-10%,rgba(59,130,246,0.13),transparent),radial-gradient(700px_380px_at_85%_10%,rgba(168,85,247,0.10),transparent)]" />
      <div className="relative mx-auto max-w-6xl px-5 py-16 text-center sm:py-20">
        <span className="inline-flex items-center gap-2 rounded-full border border-bullish/30 bg-bullish/10 px-3 py-1.5 text-xs font-semibold text-bullish-text">
          <span className="h-1.5 w-1.5 rounded-full bg-bullish shadow-[0_0_0_3px_rgba(34,197,94,0.2)]" /> Built for professionals with a day job
        </span>
        <h1 className="mx-auto mt-5 max-w-4xl text-4xl font-bold leading-[1.1] tracking-tight sm:text-[52px]">
          One platform to day-trade, swing, and find the next big winner — <span className="text-gradient-ai">without living on the charts.</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-[17px] text-text-secondary sm:text-[19px]">
          A disciplined, rules-based <b className="text-text-primary">system</b> watches your levels. The moment a setup fires you get the entry, stop, target — then an <b className="text-text-primary">AI agent explains the why</b>. Learn from every trade. Educational, never financial advice.
        </p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <PrimaryCTA>Start free — 3 days <ArrowRight className="h-4 w-4" /></PrimaryCTA>
          <SecondaryCTA>See a live daily report</SecondaryCTA>
        </div>
        <div className="mt-4 flex flex-wrap justify-center gap-2 text-sm">
          <a href="#apps" className="inline-flex items-center gap-1.5 rounded-lg border border-border-default bg-surface-2 px-3.5 py-2 text-text-secondary transition-colors hover:border-border-strong"><Smartphone className="h-4 w-4" /> iOS</a>
          <a href="#apps" className="inline-flex items-center gap-1.5 rounded-lg border border-border-default bg-surface-2 px-3.5 py-2 text-text-secondary transition-colors hover:border-border-strong"><Smartphone className="h-4 w-4" /> Android</a>
          <a href="#apps" className="inline-flex items-center gap-1.5 rounded-lg border border-border-default bg-surface-2 px-3.5 py-2 text-text-secondary transition-colors hover:border-border-strong"><Monitor className="h-4 w-4" /> Mac &amp; Windows</a>
        </div>
        <div className="mt-4 text-xs text-text-faint">No card required · For educational &amp; informational purposes only</div>

        {/* system fires → agent reads */}
        <div className="mx-auto mt-11 grid max-w-3xl gap-4 text-left sm:grid-cols-2">
          <Card className="!bg-surface-2">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-bold">NVDA <span className="ml-1.5 rounded-full border border-bullish/30 bg-bullish/10 px-2 py-0.5 text-[11px] font-semibold text-bullish-text">LONG · 4h reclaim</span></span>
              <span className="font-mono text-sm text-bullish-text">A+</span>
            </div>
            <div className="grid gap-1.5 font-mono text-[13px] text-text-secondary">
              <div className="flex justify-between"><span className="text-text-faint">Entry</span><span>182.40</span></div>
              <div className="flex justify-between"><span className="text-text-faint">Stop</span><span className="text-bearish-text">179.10</span></div>
              <div className="flex justify-between"><span className="text-text-faint">Target (+1R)</span><span className="text-bullish-text">185.70</span></div>
              <div className="mt-1 flex justify-between border-t border-border-subtle pt-1.5"><span className="text-text-faint">Why</span><span className="text-text-secondary">reclaimed the 4h low on vol</span></div>
            </div>
          </Card>
          <Card className="flex flex-col justify-center gap-3 !bg-surface-2">
            <Eyebrow>…then the AI reads it for you</Eyebrow>
            <div className="grid gap-2 font-mono text-[12.5px] text-text-secondary">
              <div><span className="text-bullish-text">thesis</span> — why it fired + what invalidates it</div>
              <div><span className="text-purple-400">triage</span> — high-conviction, or muted noise?</div>
              <div><span className="text-amber-400">brief</span> — the tape at 8:30, the recap at 4:05</div>
              <div><span className="text-accent">coach</span> — ask about any symbol, any time</div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

/* ── Problem ────────────────────────────────────────────────────────────────── */
function Problem() {
  const items = [
    { icon: Clock, tint: "bg-amber-500/12 text-amber-400", t: "No time to watch charts", d: "Real analysis takes hours you don't have between meetings." },
    { icon: Target, tint: "bg-accent/12 text-accent", t: "Setups fire mid-workday", d: "The move happens at 10:47am — you see it at 6pm, too late." },
    { icon: Bell, tint: "bg-bearish/12 text-bearish-text", t: "Most platforms sell noise", d: "Endless alerts, no reasoning, no idea which actually work." },
    { icon: Brain, tint: "bg-purple-500/12 text-purple-400", t: "Hard to learn live", d: "You know the patterns in a book — not the instant they form." },
  ];
  return (
    <Section>
      <Eyebrow>The problem</Eyebrow>
      <h2 className="max-w-2xl text-3xl font-bold tracking-tight">You've got a day job. The best setups don't wait for 5pm.</h2>
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((it) => (
          <Card key={it.t}><IconTile icon={it.icon} tint={it.tint} /><h3 className="font-bold">{it.t}</h3><p className="mt-1.5 text-sm text-text-muted">{it.d}</p></Card>
        ))}
      </div>
    </Section>
  );
}

/* ── Value pillars (Sub-spec B) ─────────────────────────────────────────────── */
function Pillars() {
  const items = [
    { icon: Zap, tint: "bg-accent/14 text-accent", t: "Day Trades", d: "A rules-based system watches your levels — 4h reclaims, opening-range breaks, prior-day highs/lows — and fires the second one triggers, entry / stop / target drawn. Every alert carries an AI thesis." },
    { icon: TrendingUp, tint: "bg-bullish/14 text-bullish-text", t: "Swing Trades", d: "Multi-day setups you can hold through a workday. Momentum + RSI-managed, so you're not glued to a screen to make it work." },
    { icon: LineChart, tint: "bg-bullish/14 text-bullish-text", t: "Performance", d: "See which setups actually work — every alert scored against real price. No synthetic win rates. Honest data you learn from, and can share." },
    { icon: Sparkles, tint: "bg-accent/14 text-accent", t: "The Agents = your analyst", d: "On top of the system: a thesis on each setup, triage to the high-conviction few, briefs at the open and close, and a coach on any symbol. The analyst a busy pro doesn't have time to be." },
  ];
  return (
    <Section className="bg-surface-1">
      <Eyebrow>One login. Every way you trade.</Eyebrow>
      <h2 className="max-w-3xl text-3xl font-bold tracking-tight">The system watches your levels. The agents explain, triage, and <span className="text-gradient-ai">coach.</span></h2>
      <div className="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((it) => (
          <Card key={it.t} className="!bg-surface-2"><IconTile icon={it.icon} tint={it.tint} /><h3 className="font-bold">{it.t}</h3><p className="mt-1.5 text-sm text-text-muted">{it.d}</p></Card>
        ))}
      </div>
    </Section>
  );
}

/* ── The playbook + Education (Sub-spec C) ──────────────────────────────────── */
function Playbook() {
  const groups = [
    { icon: Zap, tint: "bg-accent/14 text-accent", t: "Day trades", pills: ["MA bounce · 8/21/50/100/200", "PDL reclaim", "PDL held", "PDH breakout", "4h reclaim", "Opening-range break", "Gap-and-go"] },
    { icon: TrendingUp, tint: "bg-bullish/14 text-bullish-text", t: "Swing", pills: ["RSI-30 reclaim", "RSI-70 momentum", "5/20 EMA cross", "Weekly reclaim", "Multi-day double bottom", "10w / 30w hold"] },
    { icon: Satellite, tint: "bg-purple-500/14 text-purple-400", t: "Trend / position", pills: ["Monthly reclaim", "Monthly-box breakout (MoBO)", "Prior-month-low held", "Weekly-MA support"] },
  ];
  return (
    <Section>
      <Eyebrow>The playbook</Eyebrow>
      <h2 className="max-w-2xl text-3xl font-bold tracking-tight">Every setup we fire — and <span className="text-gradient-ai">teach you to see.</span></h2>
      <p className="mt-3.5 max-w-2xl text-[17px] text-text-secondary">Documented, structural patterns, grouped by how you trade them. We show you the setup and the reasoning — the honest, <b className="text-text-primary">scored</b> outcomes live on the Performance page. No invented win rates.</p>
      <div className="mt-8 grid items-start gap-4 sm:grid-cols-3">
        {groups.map((g) => (
          <Card key={g.t}>
            <div className="mb-3.5 flex items-center gap-2.5">
              <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${g.tint}`}><g.icon className="h-4 w-4" /></div>
              <h3 className="font-bold">{g.t}</h3>
            </div>
            <div className="flex flex-wrap gap-1.5">{g.pills.map((p) => <Pill key={p}>{p}</Pill>)}</div>
          </Card>
        ))}
      </div>
      <p className="mt-4 text-xs text-text-faint">Retired setups are archived, not sold — you only get what actually fires. Every live pattern has a free lesson: <Link to="/learn" className="text-accent hover:underline">what it is, why it works, when it fails →</Link></p>
    </Section>
  );
}

function Education() {
  const items = [
    { icon: BookOpen, t: "Documented patterns", d: "taught with real, live examples — free, no account" },
    { icon: Brain, t: "The reasoning on every alert", d: "why it fired, what invalidates it, where the risk is" },
    { icon: Shield, t: "Risk-first, always", d: "a stop on every setup — survival before being right" },
  ];
  return (
    <Section>
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <div>
          <Eyebrow>Education-first · not financial advice</Eyebrow>
          <h2 className="text-3xl font-bold tracking-tight">Learn the <span className="text-gradient-ai">why</span>, not just the what.</h2>
          <p className="mt-4 text-[17px] text-text-secondary">Every alert is built on documented chart structure — and teaches it. A free pattern library, the reasoning on every setup, risk and stops first. You leave a better trader, not just a busier one.</p>
          <p className="mt-4 text-xs text-text-faint">We surface structural observations with entry, stop and target levels — you decide whether and how to act. Nothing here is investment advice.</p>
          <SecondaryCTA to="/learn" className="mt-5">Explore the pattern library <ArrowRight className="h-4 w-4" /></SecondaryCTA>
        </div>
        <div className="grid gap-3">
          {items.map((it) => (
            <Card key={it.t} className="flex items-center gap-4"><it.icon className="h-6 w-6 shrink-0 text-accent" /><div><b>{it.t}</b><div className="text-xs text-text-faint">{it.d}</div></div></Card>
          ))}
        </div>
      </div>
    </Section>
  );
}

/* ── Find the next big winner (Sub-spec D) ──────────────────────────────────── */
function Discovery() {
  const items = [
    { icon: Sunrise, tint: "bg-amber-500/14 text-amber-400", t: "Morning Focus", d: "Each morning, the names sitting on a monthly breakout — a locked multi-month base (MoBO) or a prior-month high about to reclaim. The MU-off-$96 setup, before it ran." },
    { icon: Search, tint: "bg-purple-500/14 text-purple-400", t: "Trade Ideas", d: "Five screens working for you — In-Play volume, Swing setups, Conviction leaders, Growth leaders, Early-Turn — ranked, so you start with a shortlist, not a blank chart." },
    { icon: Satellite, tint: "bg-accent/14 text-accent", t: "Long Term Finders", d: "The ETF technique: names showing up across multiple thematic ETFs — the next RKLB/AST before the crowd — each with a plain-English dossier (Moonshot · Emerging Leader · Compounder)." },
  ];
  return (
    <Section className="bg-surface-1">
      <Eyebrow>Find the next big winner</Eyebrow>
      <h2 className="max-w-2xl text-3xl font-bold tracking-tight">How you'd have caught <span className="text-gradient-ai">MU or SNDK</span> early.</h2>
      <p className="mt-3.5 max-w-2xl text-[17px] text-text-secondary">Momentum isn't luck — it's a search you can run every day. Three layers, from this morning's breakout to the multi-year hold.</p>
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {items.map((it) => (
          <Card key={it.t} className="!bg-surface-2"><IconTile icon={it.icon} tint={it.tint} /><h3 className="font-bold">{it.t}</h3><p className="mt-1.5 text-sm text-text-muted">{it.d}</p></Card>
        ))}
      </div>
    </Section>
  );
}

/* ── Apps download (Sub-spec E) — TODO: swap in real store/installer URLs when live ── */
function Apps() {
  const apps = [
    { icon: Smartphone, t: "iPhone & iPad", d: "App Store" },
    { icon: Smartphone, t: "Android", d: "Google Play" },
    { icon: Monitor, t: "Mac & Windows", d: "Desktop app" },
  ];
  return (
    <Section className="bg-surface-1">
      <div className="text-center">
        <Eyebrow>Your desk, everywhere</Eyebrow>
        <h2 className="text-3xl font-bold tracking-tight">Alerts on your phone. Full charting on your desktop.</h2>
        <p className="mx-auto mt-3.5 max-w-2xl text-[17px] text-text-secondary">One account, every screen. Get pinged the instant a setup fires while you're in a meeting; sit down at the desktop app to study the chart and the levels.</p>
        <div className="mx-auto mt-8 grid max-w-3xl gap-4 sm:grid-cols-3">
          {apps.map((a) => (
            <Link key={a.t} to="/register" className="rounded-2xl border border-border-subtle bg-surface-2 p-6 transition-colors hover:border-border-strong">
              <a.icon className="mx-auto h-7 w-7 text-text-secondary" /><h3 className="mt-2 font-bold">{a.t}</h3><p className="text-sm text-text-muted">{a.d}</p>
            </Link>
          ))}
        </div>
      </div>
    </Section>
  );
}

/* ── How it works ───────────────────────────────────────────────────────────── */
function HowItWorks() {
  const steps = [
    { n: "01", c: "text-accent", t: "Build your watchlist", d: "Pick your names — or start from Trade Ideas and Long Term Finders." },
    { n: "02", c: "text-purple-400", t: "The system watches, all day", d: "Levels, momentum, reversals, 24/7 crypto — the rules engine never blinks." },
    { n: "03", c: "text-bullish-text", t: "You get the setup + the AI read", d: "A clean alert with entry/stop/target — plus the AI thesis. Act, or learn — your call." },
  ];
  return (
    <Section>
      <Eyebrow>How it works</Eyebrow>
      <h2 className="text-3xl font-bold tracking-tight">Three steps. Then get on with your day.</h2>
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {steps.map((s) => (
          <Card key={s.n}><div className={`font-mono text-sm ${s.c}`}>{s.n}</div><h3 className="mt-2 font-bold">{s.t}</h3><p className="mt-1.5 text-sm text-text-muted">{s.d}</p></Card>
        ))}
      </div>
    </Section>
  );
}

/* ── Proof (Sub-spec F) — descriptive stats only, never a headline win-rate ─── */
function Proof({ track }: { track: TrackRecord | null }) {
  const stats = [
    { v: "A/B/C", l: "graded on volume + VWAP" },
    { v: "Public", l: "daily reports & track record" },
    { v: track ? `${track.total_signals}` : "Scored", l: track ? "signals scored (90d)" : "vs real price — not synthetic" },
    { v: "Shareable", l: "your performance, one link" },
  ];
  return (
    <Section className="bg-surface-1">
      <div className="text-center">
        <Eyebrow>Transparent by default</Eyebrow>
        <h2 className="text-3xl font-bold tracking-tight">Every alert. Every outcome. Public.</h2>
        <p className="mx-auto mt-3.5 max-w-2xl text-[17px] text-text-secondary">We publish a daily report and a Performance page that scores real setups against real price — and you can share your own results with a public link. No cherry-picked win rate.</p>
        <div className="mt-8 flex flex-wrap justify-center gap-x-10 gap-y-6">
          {stats.map((s) => (
            <div key={s.l}><div className="text-3xl font-bold tracking-tight">{s.v}</div><div className="mt-1 text-xs text-text-faint">{s.l}</div></div>
          ))}
        </div>
        <SecondaryCTA className="mt-8">See the live track record <ArrowRight className="h-4 w-4" /></SecondaryCTA>
      </div>
    </Section>
  );
}

/* ── Pricing (Sub-spec F) ───────────────────────────────────────────────────── */
function Pricing() {
  return (
    <Section>
      <div className="text-center">
        <Eyebrow>Pricing</Eyebrow>
        <h2 className="text-3xl font-bold tracking-tight">Start free. Upgrade when it earns its keep.</h2>
        <div className="mx-auto mt-8 grid max-w-3xl gap-4 text-left sm:grid-cols-2">
          <Card>
            <h3 className="font-bold">Free</h3>
            <div className="my-1.5 text-4xl font-bold tracking-tight">$0</div>
            <p className="mb-4 text-sm text-text-muted">5 symbols · top setups preview · pattern library · public reports.</p>
            <SecondaryCTA to="/register" className="w-full">Get started</SecondaryCTA>
          </Card>
          <Card className="!border-accent shadow-glow-accent">
            <div className="flex items-center justify-between">
              <h3 className="font-bold">Pro</h3>
              <span className="rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 text-xs font-semibold text-accent">Most popular</span>
            </div>
            <div className="my-1.5 text-4xl font-bold tracking-tight">$49<span className="text-base text-text-faint">/mo</span></div>
            <p className="mb-4 text-sm text-text-muted">Unlimited watchlist · all agents · real-time alerts · Long Term Finders · Performance · apps.</p>
            <PrimaryCTA to="/register" className="w-full">Try free for 3 days</PrimaryCTA>
          </Card>
        </div>
        <div className="mt-4 text-xs text-text-faint">No card required · cancel anytime</div>
      </div>
    </Section>
  );
}

/* ── Final CTA + Footer ─────────────────────────────────────────────────────── */
function FinalCTA() {
  return (
    <Section className="bg-[radial-gradient(700px_300px_at_50%_120%,rgba(34,197,94,0.12),transparent)] text-center">
      <h2 className="mx-auto max-w-2xl text-4xl font-bold tracking-tight">Stop staring at charts.<br /><span className="text-gradient-ai">Let the desk watch for you.</span></h2>
      <div className="mt-6 flex justify-center"><PrimaryCTA>Start free — 3 days <ArrowRight className="h-4 w-4" /></PrimaryCTA></div>
      <div className="mt-3.5 text-xs text-text-faint">No card required · For educational &amp; informational purposes only</div>
    </Section>
  );
}
function Footer() {
  return (
    <div className="border-t border-border-subtle bg-surface-0 py-9">
      <div className="mx-auto max-w-6xl px-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2 font-bold"><Crosshair className="h-4 w-4 text-accent" /><span><span className="text-gradient-ai">Busy</span>TradersDesk</span></div>
          <div className="flex flex-wrap gap-5 text-xs text-text-faint">
            <Link to="/learn" className="hover:text-text-muted">Pattern Library</Link>
            <Link to="/track-record" className="hover:text-text-muted">Reports</Link>
            <a href="#pricing" className="hover:text-text-muted">Pricing</a>
            <Link to="/privacy" className="hover:text-text-muted">Privacy</Link>
          </div>
        </div>
        <p className="mt-5 max-w-4xl text-[11.5px] leading-relaxed text-text-faint">
          <b className="text-text-secondary">Important disclosures.</b> BusyTradersDesk is a research and education platform for self-directed investors. All content and alerts are for educational and informational purposes only and do not constitute investment advice, a recommendation, or an offer to buy or sell any security. Past performance does not guarantee future results. Trading involves risk of loss.
        </p>
      </div>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────────────────────────── */
export default function LandingPage() {
  const user = useAuthStore((s) => s.user);
  const track = usePublicTrackRecord();
  // Restored session → straight into the app (Capacitor cold-start lands at "/").
  if (user) return <Navigate to="/trading" replace />;
  return (
    <div className="min-h-screen overflow-x-hidden bg-surface-0 text-text-primary">
      <LandingNav />
      <Hero />
      <Problem />
      <div id="pillars"><Pillars /></div>
      <Playbook />
      <Discovery />
      <Education />
      <div id="apps"><Apps /></div>
      <HowItWorks />
      <Proof track={track} />
      <div id="pricing"><Pricing /></div>
      <FinalCTA />
      <Footer />
      <StickyLandingCTA />
    </div>
  );
}
