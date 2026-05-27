/** Landing Page — Research toolkit for self-directed investors.
 *  Repositioned 2026-05-27: three pillars (AI Market Analysis, Pattern
 *  Education, Public EOD Reports). Dark terminal aesthetic. Mobile-first.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Crosshair, Brain, Send, BarChart3, Play,
  Check, Zap, Clock,
  ArrowRight, BookOpen,
  Scan, Target, ChevronRight,
} from "lucide-react";

/* ── Live track record hook ───────────────────────────────────────── */

interface TrackRecord {
  total_signals: number;
  wins: number;
  losses: number;
  win_rate: number;
}

function usePublicTrackRecord(): TrackRecord | null {
  const [data, setData] = useState<TrackRecord | null>(null);
  useEffect(() => {
    fetch("/api/v1/intel/public-track-record?days=90")
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, []);
  return data;
}

/* ── Shared components ────────────────────────────────────────────── */

function Badge({ children, variant = "default" }: { children: React.ReactNode; variant?: "default" | "green" | "blue" }) {
  const styles = {
    default: "bg-surface-3 text-text-secondary border-border-subtle",
    green: "bg-bullish/10 text-bullish-text border-bullish/20",
    blue: "bg-accent/10 text-accent border-accent/20",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border ${styles[variant]}`}>
      {children}
    </span>
  );
}

/* ── Nav ──────────────────────────────────────────────────────────── */

function LandingNav() {
  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 bg-surface-0/80 backdrop-blur-lg border-b border-border-subtle/50"
      style={{ paddingTop: "env(safe-area-inset-top)" }}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-purple flex items-center justify-center">
            <Crosshair className="h-4 w-4 text-white" />
          </div>
          <span className="font-bold text-lg text-text-primary">
            <span className="text-accent">Trade</span>CoPilot
          </span>
        </div>

        <div className="hidden md:flex items-center gap-8 text-sm text-text-muted">
          <a href="#pillars" className="hover:text-text-primary transition-colors">Toolkit</a>
          <a href="#pricing" className="hover:text-text-primary transition-colors">Pricing</a>
          <Link to="/learn" className="hover:text-text-primary transition-colors">Pattern Library</Link>
          <Link to="/track-record" className="hover:text-text-primary transition-colors">Track Record</Link>
        </div>

        <div className="flex items-center gap-3">
          <Link to="/login" className="text-sm font-medium text-text-primary hover:text-accent transition-colors px-3 py-2 rounded-lg border border-border-subtle hover:border-accent">
            Sign in
          </Link>
          <Link
            to="/register"
            className="bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            Get Started
          </Link>
        </div>
      </div>
    </nav>
  );
}

/* ── Hero Section ─────────────────────────────────────────────────── */

function Hero({ track: _track }: { track: TrackRecord | null }) {
  return (
    <section className="relative pt-32 pb-16 flex flex-col items-center px-6 overflow-hidden">
      {/* Background grid + glow */}
      <div className="absolute inset-0 opacity-[0.03]" style={{
        backgroundImage: "radial-gradient(circle, #fff 1px, transparent 1px)",
        backgroundSize: "32px 32px",
      }} />
      <div className="absolute top-[-20%] left-[20%] w-[600px] h-[600px] bg-accent/8 rounded-full blur-[150px] pointer-events-none" />
      <div className="absolute bottom-[-10%] right-[10%] w-[400px] h-[400px] bg-bullish/5 rounded-full blur-[120px] pointer-events-none" />

      {/* Content */}
      <div className="relative z-10 max-w-4xl mx-auto text-center">
        <Badge variant="green">
          <div className="w-1.5 h-1.5 rounded-full bg-bullish animate-pulse" />
          Built for self-directed investors with day jobs
        </Badge>

        <h1 className="mt-8 text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight text-text-primary leading-[1.08]">
          Market research
          <br />
          <span className="text-gradient-ai">for people with day jobs.</span>
        </h1>

        <p className="mt-6 text-lg sm:text-xl text-text-secondary max-w-2xl mx-auto leading-relaxed">
          A research toolkit that scans your watchlist during market hours, maps every
          setup to a documented pattern, and publishes transparent daily reports so you
          can study what worked — and what didn't.
        </p>

        {/* CTA */}
        <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            to="/register"
            className="inline-flex items-center justify-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold text-base px-8 py-4 rounded-xl transition-all shadow-[0_0_30px_rgba(34,197,94,0.25)] hover:shadow-[0_0_40px_rgba(34,197,94,0.35)]"
          >
            Try free for 3 days
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/track-record"
            className="inline-flex items-center justify-center gap-2 bg-surface-2 hover:bg-surface-3 text-text-primary font-medium text-base px-8 py-4 rounded-xl border border-border-subtle transition-colors"
          >
            See yesterday's EOD report
          </Link>
        </div>

        <p className="mt-4 text-xs text-text-faint">
          No card required · For educational and informational purposes only
        </p>

        {/* What the toolkit covers */}
        <div className="mt-16 flex flex-wrap justify-center gap-6 sm:gap-10">
          {[
            { label: "Documented patterns", value: "14", color: "text-accent" },
            { label: "Daily EOD reports", value: "Public", color: "text-bullish-text" },
            { label: "Coverage", value: "Stocks + Crypto", color: "text-text-primary" },
          ].map((m) => (
            <div key={m.label} className="flex flex-col items-center">
              <span className={`font-mono text-2xl sm:text-3xl font-bold ${m.color}`}>{m.value}</span>
              <span className="text-xs text-text-faint uppercase tracking-wider mt-1">{m.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Hero visual — AI Scan alert card */}
      <div className="relative z-10 mt-16 max-w-3xl mx-auto w-full px-4">
        <div className="bg-surface-1 border border-border-subtle rounded-2xl p-6 shadow-elevated relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-0.5 bg-bullish" />
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center">
                <Scan className="h-5 w-5 text-accent" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-text-primary">ETH-USD</span>
                  <span className="bg-bullish/10 text-bullish-text text-[10px] font-bold px-2 py-0.5 rounded border border-bullish/20">LONG</span>
                  <span className="text-[8px] font-bold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded">SETUP</span>
                </div>
                <span className="text-xs text-text-muted">PDL Bounce -- Prior Day Low held with volume</span>
              </div>
            </div>
            <span className="font-mono text-xl font-bold text-text-primary">$2,285</span>
          </div>

          <div className="bg-surface-0 rounded-lg p-3 border border-border-subtle/50 mb-4">
            <p className="text-sm text-text-secondary leading-relaxed">
              <Zap className="inline h-3.5 w-3.5 text-accent mr-1" />
              Session low tested PDL at $2,277 and held. Volume 1.3x average on bounce candle.
              VWAP reclaimed. Next resistance at session high $2,298.
            </p>
          </div>

          <div className="grid grid-cols-4 gap-3 bg-surface-0 rounded-lg p-3 border border-border-subtle/50">
            <div>
              <span className="text-[9px] text-text-faint uppercase">Entry</span>
              <p className="font-mono text-sm font-medium text-text-primary">$2,277.60</p>
            </div>
            <div>
              <span className="text-[9px] text-bearish-text uppercase">Stop</span>
              <p className="font-mono text-sm font-medium text-bearish-text">$2,270.00</p>
            </div>
            <div>
              <span className="text-[9px] text-bullish-text uppercase">Target 1</span>
              <p className="font-mono text-sm font-medium text-bullish-text">$2,298.00</p>
            </div>
            <div>
              <span className="text-[9px] text-text-faint uppercase">Conviction</span>
              <p className="font-mono text-sm font-medium text-accent">HIGH</p>
            </div>
          </div>
        </div>
        {/* Fade out at bottom */}
        <div className="absolute bottom-0 left-0 w-full h-20 bg-gradient-to-t from-surface-0 to-transparent pointer-events-none" />
      </div>
    </section>
  );
}

/* ── The Problem ──────────────────────────────────────────────────── */

function Problem() {
  return (
    <section className="py-24 px-6">
      <div className="max-w-4xl mx-auto text-center">
        <Badge>The problem</Badge>
        <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
          You can't watch charts <span className="italic text-text-secondary">9-to-5.</span>
          <br />
          You don't want to either.
        </h2>
        <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 gap-6 text-left">
          {[
            { icon: Clock, text: "Real chart analysis takes hours — scanning multiple symbols across timeframes is a full-time job, and you already have one." },
            { icon: Target, text: "Setups form during meetings. The pattern you studied last weekend triggers at 11:30 AM Tuesday while you're heads-down at work." },
            { icon: Send, text: "Most platforms sell noise. 'ETH crossed $2,280' tells you nothing useful — you need context, structure, and a record of what worked." },
            { icon: Brain, text: "You learn patterns on YouTube but struggle to recognize them live. Education and analysis live in separate apps." },
          ].map((item, i) => (
            <div key={i} className="bg-surface-1 border border-border-subtle rounded-xl p-5 flex gap-4">
              <div className="shrink-0 w-10 h-10 rounded-lg bg-bearish/10 border border-bearish/20 flex items-center justify-center">
                <item.icon className="h-5 w-5 text-bearish-text" />
              </div>
              <p className="text-sm text-text-secondary leading-relaxed">{item.text}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── 5 AI Pillars ────────────────────────────────────────────────── */

function AIPillars() {
  // Three-pillar repositioning (2026-05-27): AI Analysis / Education /
  // Public Strategy Evaluation. Replaces the old "5 AI capabilities" framing
  // which leaned too hard on the "alert service" positioning.
  const pillars = [
    {
      icon: Scan,
      title: "AI Market Analysis",
      subtitle: "Automated scanning during market hours",
      color: "accent",
      desc: "Pattern recognition runs on your watchlist while you work. Results delivered in plain English — observations with entry, stop, target levels. You make the call.",
      bullets: [
        "Scans across stocks + crypto with multi-timeframe context",
        "Maps every observation to a documented pattern",
        "Volume + structure context built into every setup",
        "Position-aware — won't duplicate setups you're already in",
      ],
    },
    {
      icon: BookOpen,
      title: "Pattern Education",
      subtitle: "14 documented setups, taught with real data",
      color: "purple-400",
      desc: "Every signal links to a teachable pattern. Study the structure, see real historical examples, and replay any past setup bar-by-bar.",
      bullets: [
        "14 patterns from beginner to advanced",
        "Each one: what it is, why it works, risk management",
        "Replay any past setup to study the structure",
        "Free pattern library at /learn — no account required",
      ],
    },
    {
      icon: Play,
      title: "Public EOD Reports",
      subtitle: "Transparent strategy evaluation",
      color: "bullish-text",
      desc: "Daily reports published after market close. See what triggered, what worked, what didn't — with full data, not curated highlights. Learn from transparent outcomes.",
      bullets: [
        "Published daily — every signal, every outcome",
        "Filter by pattern, symbol, or your own took/skipped decisions",
        "Build a personal track record over time",
        "Public archive at /track-record — no login required",
      ],
    },
  ];

  const colorMap: Record<string, { bg: string; border: string; text: string }> = {
    "accent": { bg: "bg-accent/10", border: "border-accent/20", text: "text-accent" },
    "purple-400": { bg: "bg-purple-500/10", border: "border-purple-500/20", text: "text-purple-400" },
    "bullish-text": { bg: "bg-bullish/10", border: "border-bullish/20", text: "text-bullish-text" },
  };

  return (
    <section id="pillars" className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="blue">Three pillars</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Analysis. Education. Transparency.
          </h2>
          <p className="mt-4 text-text-secondary max-w-2xl mx-auto">
            A toolkit built around what serious self-directed investors actually need —
            not another inbox of buy/sell calls.
          </p>
        </div>

        <div className="space-y-6">
          {pillars.map((p) => {
            const c = colorMap[p.color];
            return (
              <div key={p.title} className="bg-surface-1 border border-border-subtle rounded-2xl p-6 md:p-8 hover:border-border-default transition-colors">
                <div className="flex flex-col md:flex-row gap-6">
                  {/* Left: title + description */}
                  <div className="md:w-2/5">
                    <div className="flex items-center gap-3 mb-3">
                      <div className={`w-10 h-10 rounded-lg ${c.bg} ${c.border} border flex items-center justify-center`}>
                        <p.icon className={`h-5 w-5 ${c.text}`} />
                      </div>
                      <div>
                        <h3 className="text-lg font-bold text-text-primary">{p.title}</h3>
                        <p className={`text-xs font-medium ${c.text}`}>{p.subtitle}</p>
                      </div>
                    </div>
                    <p className="text-sm text-text-secondary leading-relaxed">{p.desc}</p>
                  </div>

                  {/* Right: bullet points */}
                  <div className="md:w-3/5">
                    <ul className="space-y-2.5">
                      {p.bullets.map((b, i) => (
                        <li key={i} className="flex items-start gap-2.5 text-sm text-text-secondary">
                          <Check className={`h-4 w-4 ${c.text} shrink-0 mt-0.5`} />
                          <span>{b}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ── How It Works ─────────────────────────────────────────────────── */

function HowItWorks() {
  const steps = [
    {
      num: "01",
      title: "Build your watchlist",
      desc: "Add the names you actually follow — stocks, ETFs, crypto. The platform monitors price action across multiple timeframes while you work.",
      icon: Crosshair,
    },
    {
      num: "02",
      title: "Setups surface with full context",
      desc: "When price interacts with a key structural level, you get an observation: entry zone, stop reference, target levels, and which pattern it matches. You make the call.",
      icon: Scan,
    },
    {
      num: "03",
      title: "Review the public EOD report",
      desc: "Daily report shows every observation, outcome, and your own took/skipped decisions. Replay any setup bar-by-bar. Learn the structure from real data.",
      icon: BarChart3,
    },
  ];

  return (
    <section className="py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="green">How it works</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Build your watchlist, watch the analysis, learn from the data
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {steps.map((step) => (
            <div key={step.num} className="relative">
              <div className="flex items-center gap-3 mb-4">
                <span className="font-mono text-3xl font-bold text-border-strong">{step.num}</span>
                <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center">
                  <step.icon className="h-5 w-5 text-accent" />
                </div>
              </div>
              <h3 className="text-lg font-bold text-text-primary mb-2">{step.title}</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{step.desc}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── AI vs Manual Comparison ─────────────────────────────────────── */

function AIvsManual() {
  const rows = [
    { aspect: "Time spent scanning", manual: "Hours every day", ai: "Automated during market hours" },
    { aspect: "Setups while you work", manual: "You miss them", ai: "Surfaced when they happen" },
    { aspect: "Entry context", manual: "Gut feel, chasing", ai: "Structural level with pattern match" },
    { aspect: "Stop reference", manual: "Arbitrary %", ai: "Below structure (suggested, not mandated)" },
    { aspect: "Signal noise", manual: "100+ generic alerts/day", ai: "Filtered to documented setups" },
    { aspect: "Outcome tracking", manual: "Spreadsheets, memory", ai: "Took/Skipped logged automatically" },
    { aspect: "Pattern learning", manual: "YouTube + trial and error", ai: "Every setup linked to library" },
    { aspect: "Track record visibility", manual: "\"Trust me, I'm a trader\"", ai: "Public daily EOD reports" },
  ];

  return (
    <section className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <Badge>Why a toolkit</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            DIY analysis vs an analytical toolkit
          </h2>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left py-3 px-4 text-text-muted font-medium w-1/3"></th>
                <th className="py-3 px-4 text-text-faint font-medium w-1/3">Manual / DIY</th>
                <th className="py-3 px-4 text-accent font-bold w-1/3">TradeCoPilot</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.aspect} className="border-b border-border-subtle/30">
                  <td className="py-3 px-4 text-text-secondary font-medium">{row.aspect}</td>
                  <td className="py-3 px-4 text-center text-text-faint">{row.manual}</td>
                  <td className="py-3 px-4 text-center text-bullish-text font-medium">{row.ai}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

/* ── Daily AI Workflow ────────────────────────────────────────────── */

function DailyWorkflow() {
  const events = [
    { time: "09:05 AM", label: "Daily Game Plan", desc: "Top focus symbols + structural notes", color: "text-accent" },
    { time: "09:15 AM", label: "Pre-Market Brief", desc: "Market outlook, key levels, bias", color: "text-purple-400" },
    { time: "09:30 AM", label: "Continuous scanning", desc: "Automated pattern detection through market close", color: "text-bullish-text" },
    { time: "All Day", label: "Chart inquiries", desc: "Pull up any chart, see live structural analysis", color: "text-yellow-400" },
    { time: "All Day", label: "Mobile observations", desc: "Mark Took / Skipped from your phone", color: "text-blue-400" },
    { time: "04:35 PM", label: "EOD Report (public)", desc: "What triggered, what worked, what didn't", color: "text-orange-400" },
    { time: "04:40 PM", label: "Setup replays", desc: "Bar-by-bar replay of every observation", color: "text-yellow-400" },
    { time: "Friday", label: "Weekly Summary", desc: "Pattern performance, recurring lessons", color: "text-purple-400" },
  ];

  return (
    <section className="py-24 px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <Badge variant="blue">A day with the toolkit</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Set it once. Review the data after close.
          </h2>
          <p className="mt-4 text-text-secondary">
            Pre-market prep through end-of-day review — without sitting in front of charts.
          </p>
        </div>

        <div className="space-y-1">
          {events.map((e, i) => (
            <div key={i} className="flex items-center gap-4 bg-surface-1 border border-border-subtle/50 rounded-lg px-5 py-3 hover:border-border-default transition-colors">
              <span className="font-mono text-xs text-text-faint w-20 shrink-0 text-right">{e.time}</span>
              <div className={`w-2 h-2 rounded-full shrink-0 ${e.color.replace("text-", "bg-")}`} />
              <div className="flex-1 min-w-0">
                <span className={`text-sm font-bold ${e.color}`}>{e.label}</span>
                <span className="text-sm text-text-muted ml-2">-- {e.desc}</span>
              </div>
            </div>
          ))}
        </div>

        <p className="text-center text-xs text-text-faint mt-6">
          Crypto symbols (BTC, ETH) are scanned around the clock — markets never close.
        </p>
      </div>
    </section>
  );
}

/* ── Telegram Demo ─────────────────────────────────────────────────── */

function TelegramDemo() {
  return (
    <section className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="blue">Mobile workflow</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Observations delivered to your phone
          </h2>
          <p className="mt-4 text-text-secondary max-w-2xl mx-auto">
            Setup notifications with structural context — entry, stop, target.
            Mark Took or Skipped from anywhere. Pull a fresh chart on any symbol with /spy or /eth.
          </p>
        </div>

        <div className="max-w-sm mx-auto">
          {/* Phone mockup */}
          <div className="bg-surface-1 border border-border-subtle rounded-3xl p-4 shadow-elevated">
            <div className="flex items-center justify-between px-2 py-1 mb-3">
              <span className="text-[10px] text-text-faint font-mono">9:47 AM</span>
              <span className="text-[10px] text-text-faint">TradeCoPilot Bot</span>
              <div className="flex gap-1">
                <div className="w-3 h-2 bg-text-faint/30 rounded-sm" />
                <div className="w-3 h-2 bg-text-faint/30 rounded-sm" />
              </div>
            </div>

            <div className="space-y-3">
              {/* AI Scan LONG */}
              <div className="bg-surface-2 rounded-xl p-3.5 border border-bullish/10">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-[8px] font-bold text-accent bg-accent/10 px-1.5 py-0.5 rounded">SETUP</span>
                  <span className="text-sm font-bold text-text-primary">LONG ETH-USD $2,277</span>
                </div>
                <p className="text-xs text-text-muted mt-1">Entry $2,277 -- Stop $2,270 -- T1 $2,298</p>
                <p className="text-xs text-text-secondary mt-1">PDL bounce held with 1.3x volume</p>
                <p className="text-xs text-accent mt-1">Conviction: HIGH</p>
                <div className="flex gap-2 mt-3">
                  <span className="bg-bullish/20 text-bullish-text text-xs font-bold px-3 py-1.5 rounded-lg">Took It</span>
                  <span className="bg-surface-3 text-text-muted text-xs font-bold px-3 py-1.5 rounded-lg">Skip</span>
                  <span className="bg-bearish/20 text-bearish-text text-xs font-bold px-3 py-1.5 rounded-lg">Exit</span>
                </div>
              </div>

              {/* AI Scan WAIT */}
              <div className="bg-surface-2 rounded-xl p-3 border border-border-subtle">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-[8px] font-bold text-accent bg-accent/10 px-1.5 py-0.5 rounded">SETUP</span>
                  <span className="text-xs font-bold text-text-secondary">ETH-USD $2,285</span>
                </div>
                <p className="text-xs text-text-muted">
                  You already hold 2 LONG positions. Price flat at VWAP with weak volume. Monitor for breakout above $2,298.
                </p>
              </div>

              {/* AI Scan RESISTANCE */}
              <div className="bg-surface-2 rounded-xl p-3.5 border border-orange-500/10">
                <div className="flex items-center gap-1.5 mb-1">
                  <span className="text-[8px] font-bold text-orange-400 bg-orange-500/10 px-1.5 py-0.5 rounded">RESISTANCE</span>
                  <span className="text-sm font-bold text-text-primary">ETH-USD $2,290</span>
                </div>
                <p className="text-xs text-text-muted mt-1">Approaching hourly resistance with low volume (0.6x)</p>
                <p className="text-xs text-orange-400 mt-1">Action: tighten stop / take profits / watch for rejection</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Pricing ──────────────────────────────────────────────────────── */

function Pricing() {
  const plans = [
    {
      name: "Free",
      price: "$0",
      period: "forever",
      desc: "3-day full-access trial, then limited",
      cta: "Try free for 3 days",
      features: [
        "5 symbols on watchlist",
        "Chart inquiries: 3/day",
        "Setup notifications: 3/day",
        "Telegram: 3 commands/day",
        "Today's observations only",
        "1 setup replay/day",
        "Pattern Library access",
      ],
      highlight: false,
    },
    {
      name: "Pro",
      price: "$49",
      period: "/month",
      desc: "For active self-directed investors",
      cta: "Try free for 3 days",
      features: [
        "10 symbols on watchlist",
        "Chart inquiries: 50/day",
        "Unlimited setup notifications",
        "Telegram: 50 commands/day",
        "Real-time Telegram delivery",
        "Unlimited setup replays",
        "Pre-market brief",
        "Daily EOD review",
        "Personal Took/Skipped analytics",
        "30-day observation history",
      ],
      highlight: true,
    },
    {
      name: "Premium",
      price: "$99",
      period: "/month",
      desc: "Full access for serious self-directed investors",
      cta: "Try free for 3 days",
      features: [
        "Everything in Pro",
        "25 symbols on watchlist",
        "Unlimited chart inquiries",
        "Unlimited Telegram",
        "Weekly summary report",
        "Full observation history",
      ],
      highlight: false,
    },
  ];

  return (
    <section id="pricing" className="py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="blue">Pricing</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Simple pricing. Cancel anytime.
          </h2>
          <p className="mt-4 text-text-secondary">No credit card required to start. Free tier available forever.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {plans.map((plan) => (
            <div
              key={plan.name}
              className={`rounded-2xl p-6 flex flex-col ${
                plan.highlight
                  ? "bg-surface-1 border-2 border-bullish/30 shadow-[0_0_40px_rgba(34,197,94,0.08)] relative"
                  : "bg-surface-1 border border-border-subtle"
              }`}
            >
              {plan.highlight && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                  <span className="bg-bullish text-surface-0 text-xs font-bold px-4 py-1 rounded-full">Most Popular</span>
                </div>
              )}

              <div className="mb-6">
                <h3 className="text-lg font-bold text-text-primary">{plan.name}</h3>
                <div className="flex items-baseline gap-1 mt-2">
                  <span className="font-mono text-4xl font-bold text-text-primary">{plan.price}</span>
                  <span className="text-text-muted text-sm">{plan.period}</span>
                </div>
                <p className="text-sm text-text-muted mt-2">{plan.desc}</p>
              </div>

              <ul className="space-y-3 mb-8 flex-1">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2.5 text-sm text-text-secondary">
                    <Check className="h-4 w-4 text-bullish-text shrink-0 mt-0.5" />
                    {f}
                  </li>
                ))}
              </ul>

              <Link
                to="/register"
                className={`w-full text-center py-3 rounded-xl font-semibold text-sm transition-all ${
                  plan.highlight
                    ? "bg-bullish hover:bg-bullish/90 text-surface-0 shadow-[0_0_20px_rgba(34,197,94,0.2)]"
                    : "bg-surface-3 hover:bg-surface-4 text-text-primary border border-border-subtle"
                }`}
              >
                {plan.cta}
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* Trust / Track Record section removed 2026-05-14 — moved to its own
   /track-record page (now backed by the EOD report). */

/* ── Pattern Library Preview ─────────────────────────────────────── */

function PatternPreview() {
  const patterns = [
    { name: "PDL Bounce", difficulty: "Beginner", icon: "Support", color: "text-emerald-400" },
    { name: "VWAP Reclaim", difficulty: "Intermediate", icon: "Reversal", color: "text-yellow-400" },
    { name: "MA Bounce", difficulty: "Intermediate", icon: "Support", color: "text-emerald-400" },
    { name: "PDH Breakout", difficulty: "Intermediate", icon: "Breakout", color: "text-blue-400" },
    { name: "Double Bottom", difficulty: "Beginner", icon: "Support", color: "text-emerald-400" },
    { name: "Inside Day", difficulty: "Advanced", icon: "Breakout", color: "text-purple-400" },
  ];

  return (
    <section className="py-24 px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <Badge>Learn trading patterns</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            14 patterns taught with real data
          </h2>
          <p className="mt-4 text-text-secondary max-w-xl mx-auto">
            Free access. Beginner to advanced. Each pattern includes what it is,
            why it works, how to confirm, and historical performance data from the public EOD archive.
          </p>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-8">
          {patterns.map((p) => (
            <div key={p.name} className="bg-surface-1 border border-border-subtle rounded-xl p-4 hover:border-border-default transition-colors">
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-xs font-medium ${p.color}`}>{p.icon}</span>
              </div>
              <h4 className="text-sm font-bold text-text-primary">{p.name}</h4>
              <span className="text-[10px] text-text-faint">{p.difficulty}</span>
            </div>
          ))}
        </div>

        <div className="text-center">
          <Link
            to="/learn"
            className="inline-flex items-center gap-2 text-accent hover:text-accent-hover font-medium text-sm transition-colors"
          >
            Explore all 14 patterns
            <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ── FAQ ──────────────────────────────────────────────────────────── */

function FAQ() {
  const [open, setOpen] = useState<number | null>(null);

  const faqs = [
    {
      q: "Is this a signal or buy/sell recommendation service?",
      a: "No. TradeCoPilot is a research toolkit and educational platform for self-directed investors. We surface structural observations with entry, stop, and target levels — you decide whether and how to act. Nothing here is investment advice.",
    },
    {
      q: "How is this different from a general AI chatbot?",
      a: "The analysis layer is trained on a specific playbook (14 documented patterns), reads real-time OHLCV bars, computes VWAP from live session data, tracks your watchlist positions, and produces structured setup observations — not generic market commentary.",
    },
    {
      q: "What does WAIT mean on an observation?",
      a: "When the toolkit scans your watchlist and finds no valid setup, it returns WAIT. That's intentional — it tells you nothing matched the playbook this session, which is often more useful than another low-quality signal.",
    },
    {
      q: "What markets do you cover?",
      a: "US equities (SPY, AAPL, TSLA, NVDA, META, and similar) during market hours, plus crypto (ETH, BTC) around the clock using Coinbase data.",
    },
    {
      q: "Do you publish performance numbers?",
      a: "Yes — the public EOD reports show every observation, the outcome, and whether it was Took or Skipped. Per-pattern performance lives in the Pattern Library. We don't headline a single win rate because outcomes vary by pattern and market.",
    },
    {
      q: "Can I use it from my phone?",
      a: "Yes. Telegram is the primary delivery channel. Observations arrive with Took / Skipped / Exit buttons. You can also pull a fresh chart on any symbol via commands like /spy, /eth, or /btc.",
    },
    {
      q: "Do I need to watch charts all day?",
      a: "No — that's the whole point. Scanning runs in the background and only pings you when a documented setup appears. Most users review observations between meetings and study the EOD report after close.",
    },
    {
      q: "Can I try before paying?",
      a: "Yes. The free tier is available forever (5 symbols, 3 inquiries/day). Every new account also gets 3 days of full Pro access to try the complete workflow — no card required.",
    },
    {
      q: "Are these recommendations or guarantees?",
      a: "Neither. Trading involves risk of loss. Past performance does not guarantee future results. Self-directed investors should conduct their own research and consult a qualified professional before making investment decisions.",
    },
    {
      q: "Can I cancel anytime?",
      a: "Yes. No contracts, no cancellation fees. Cancel from Settings and keep access until the end of the billing period.",
    },
  ];

  return (
    <section className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-12">
          <Badge>FAQ</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Common questions
          </h2>
        </div>

        <div className="space-y-2">
          {faqs.map((faq, i) => (
            <div key={i} className="border border-border-subtle rounded-lg overflow-hidden">
              <button
                onClick={() => setOpen(open === i ? null : i)}
                className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-surface-2/30 transition-colors"
              >
                <span className="text-sm font-medium text-text-primary">{faq.q}</span>
                <span className="text-text-faint ml-4 shrink-0">{open === i ? "---" : "+"}</span>
              </button>
              {open === i && (
                <div className="px-5 pb-4">
                  <p className="text-sm text-text-secondary leading-relaxed">{faq.a}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Final CTA ────────────────────────────────────────────────────── */

function FinalCTA() {
  return (
    <section className="py-24 px-6">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-bold text-text-primary">
          Stop staring at charts.<br />Let the toolkit do the watching.
        </h2>
        <p className="mt-4 text-text-secondary max-w-xl mx-auto">
          For self-directed investors who want structured analysis,
          transparent EOD reports, and a pattern library — without quitting the day job.
        </p>
        <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            to="/register"
            className="inline-flex items-center justify-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold text-base px-8 py-4 rounded-xl transition-all shadow-[0_0_30px_rgba(34,197,94,0.25)]"
          >
            Try free for 3 days
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
        <p className="mt-4 text-xs text-text-faint">No card required · For educational and informational purposes only</p>
      </div>
    </section>
  );
}

/* ── Footer ───────────────────────────────────────────────────────── */

function Footer() {
  return (
    <footer className="border-t border-border-subtle py-12 px-6">
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Top row: logo, links */}
        <div className="flex flex-col md:flex-row justify-between items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded bg-accent/20 flex items-center justify-center">
              <Crosshair className="h-3 w-3 text-accent" />
            </div>
            <span className="text-sm text-text-muted">
              <span className="text-accent">Trade</span>CoPilot
            </span>
          </div>
          <div className="flex gap-6 text-xs text-text-faint">
            <Link to="/learn" className="hover:text-text-muted">Pattern Library</Link>
            <Link to="/track-record" className="hover:text-text-muted">EOD Reports</Link>
            <a href="#" className="hover:text-text-muted">Terms</a>
            <a href="#" className="hover:text-text-muted">Privacy</a>
          </div>
        </div>

        {/* Legal disclaimer block — clear self-directed / educational language */}
        <div className="border-t border-border-subtle/50 pt-6">
          <p className="text-[11px] text-text-faint leading-relaxed max-w-3xl mx-auto text-center">
            <span className="font-semibold text-text-muted">Important disclosures.</span>{" "}
            TradeCoPilot is a research and education platform for self-directed investors.
            Content on this site is provided for educational and informational purposes only
            and does not constitute investment advice, a recommendation, or an offer to buy
            or sell any security. Self-directed investors should conduct their own research
            and consult a qualified professional before making investment decisions. Past
            performance, including any analytics or track-record data shown, does not
            guarantee future results. Trading involves risk of loss.
          </p>
        </div>
      </div>
    </footer>
  );
}

/* ── Main Landing Page ────────────────────────────────────────────── */

export default function LandingPage() {
  const track = usePublicTrackRecord();

  return (
    <div className="min-h-screen bg-surface-0 text-text-primary overflow-x-hidden">
      <LandingNav />
      <Hero track={track} />
      <Problem />
      <div id="pillars"><AIPillars /></div>
      <HowItWorks />
      <AIvsManual />
      <DailyWorkflow />
      <TelegramDemo />
      <PatternPreview />
      <div id="pricing"><Pricing /></div>
      <FAQ />
      <FinalCTA />
      <Footer />
    </div>
  );
}
