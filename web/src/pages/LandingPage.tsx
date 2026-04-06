/** Landing Page — TradeCoPilot public marketing page.
 *
 *  Standalone page (no app shell, no auth required).
 *  Aesthetic: Precision Terminal — data-dense, confident, dark.
 *  Typography: Bricolage Grotesque (display) + system body + JetBrains Mono (data).
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Crosshair, Brain, Send, BarChart3, LineChart, Shield,
  Check, Zap, Clock, TrendingUp,
  ArrowRight, Eye,
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

/* ── Hero Section ─────────────────────────────────────────────────── */

function Hero({ track }: { track: TrackRecord | null }) {
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
          Live during market hours
        </Badge>

        <h1 className="mt-8 text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight text-text-primary leading-[1.08]">
          Your chart analyst
          <br />
          <span className="text-gradient-ai">that never sleeps.</span>
        </h1>

        <p className="mt-6 text-lg sm:text-xl text-text-secondary max-w-2xl mx-auto leading-relaxed">
          Complete trade plans — entry, stop, targets, AI analysis — delivered
          to your phone. You decide. You learn. You get better.
        </p>

        {/* CTA */}
        <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            to="/register"
            className="inline-flex items-center justify-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold text-base px-8 py-4 rounded-xl transition-all shadow-[0_0_30px_rgba(34,197,94,0.25)] hover:shadow-[0_0_40px_rgba(34,197,94,0.35)]"
          >
            Start Free Trial
            <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/login"
            className="inline-flex items-center justify-center gap-2 bg-surface-2 hover:bg-surface-3 text-text-primary font-medium text-base px-8 py-4 rounded-xl border border-border-subtle transition-colors"
          >
            Sign In
          </Link>
        </div>

        {/* Live metrics ticker */}
        <div className="mt-16 flex flex-wrap justify-center gap-6 sm:gap-10">
          {[
            { label: "Signals tracked", value: track ? `${track.total_signals}` : "—", color: "text-text-primary" },
            { label: "Win rate", value: track ? `${track.win_rate}%` : "—", color: "text-bullish-text" },
            { label: "Wins", value: track ? `${track.wins}` : "—", color: "text-bullish-text" },
            { label: "Losses", value: track ? `${track.losses}` : "—", color: "text-bearish-text" },
          ].map((m) => (
            <div key={m.label} className="flex flex-col items-center">
              <span className={`font-mono text-2xl sm:text-3xl font-bold ${m.color}`}>{m.value}</span>
              <span className="text-xs text-text-faint uppercase tracking-wider mt-1">{m.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Hero visual — mock alert card */}
      <div className="relative z-10 mt-16 max-w-3xl mx-auto w-full px-4">
        <div className="bg-surface-1 border border-border-subtle rounded-2xl p-6 shadow-elevated relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-0.5 bg-bullish" />
          <div className="flex items-start justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-bullish/10 border border-bullish/20 flex items-center justify-center">
                <TrendingUp className="h-5 w-5 text-bullish-text" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-text-primary">NVDA</span>
                  <span className="bg-bullish/10 text-bullish-text text-[10px] font-bold px-2 py-0.5 rounded border border-bullish/20">BUY</span>
                  <span className="text-[10px] text-accent font-mono">Score 94</span>
                </div>
                <span className="text-xs text-text-muted">EMA 20 Bounce · High Conviction</span>
              </div>
            </div>
            <span className="font-mono text-xl font-bold text-text-primary">$124.50</span>
          </div>

          <div className="bg-surface-0 rounded-lg p-3 border border-border-subtle/50 mb-4">
            <p className="text-sm text-text-secondary leading-relaxed">
              <Zap className="inline h-3.5 w-3.5 text-accent mr-1" />
              Breaking out of descending wedge on 3x volume. 20EMA support confirmed with RSI divergence.
              Sector rotation favors semis. High probability setup targeting $130 resistance.
            </p>
          </div>

          <div className="grid grid-cols-4 gap-3 bg-surface-0 rounded-lg p-3 border border-border-subtle/50">
            <div>
              <span className="text-[9px] text-text-faint uppercase">Entry</span>
              <p className="font-mono text-sm font-medium text-text-primary">$124.00</p>
            </div>
            <div>
              <span className="text-[9px] text-bearish-text uppercase">Stop</span>
              <p className="font-mono text-sm font-medium text-bearish-text">$122.80</p>
            </div>
            <div>
              <span className="text-[9px] text-bullish-text uppercase">Target 1</span>
              <p className="font-mono text-sm font-medium text-bullish-text">$128.00</p>
            </div>
            <div>
              <span className="text-[9px] text-text-faint uppercase">R:R</span>
              <p className="font-mono text-sm font-medium text-text-primary">1:3.5</p>
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
          You know <span className="italic text-text-secondary">what</span> to trade.
          <br />
          You just can't watch charts all day.
        </h2>
        <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 gap-6 text-left">
          {[
            { icon: Clock, text: "Chart analysis takes hours — scanning 10+ symbols across multiple timeframes every morning" },
            { icon: Eye, text: "Setups fire while you're at work — the double bottom at $645 happened during your 9 AM meeting" },
            { icon: Send, text: "Alert services give noise, not plans — 'SPY crossed $653' is useless without entry, stop, and targets" },
            { icon: Brain, text: "Education and execution are separated — you learn on YouTube, then struggle to apply it live" },
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

/* ── How It Works ─────────────────────────────────────────────────── */

function HowItWorks() {
  const steps = [
    {
      num: "01",
      title: "Set your watchlist",
      desc: "Add up to 15 symbols. Our engine monitors them every 3 minutes during market hours — and 24/7 for crypto.",
      icon: Crosshair,
    },
    {
      num: "02",
      title: "Get trade plans delivered",
      desc: "When structure aligns — support bounce, breakout, EMA rejection — you get a complete plan: entry, stop, T1, T2, score, and AI explanation.",
      icon: Send,
    },
    {
      num: "03",
      title: "Take or skip. Learn from results.",
      desc: "Mark alerts as Took or Skipped. Track what won, what lost, what you missed. The AI coach shows you patterns in your decisions.",
      icon: BarChart3,
    },
  ];

  return (
    <section className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="blue">How it works</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Three steps to structured trading
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

/* ── Differentiators ──────────────────────────────────────────────── */

function Differentiators() {
  return (
    <section className="py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="green">What makes us different</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Not alerts. Trade plans.
          </h2>
          <p className="mt-4 text-text-secondary max-w-2xl mx-auto">
            Most signal services tell you a price was crossed. We deliver complete trade plans
            with the reasoning, levels, and coaching to make you independent.
          </p>
        </div>

        {/* Comparison */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-16">
          <div className="bg-surface-1 border border-border-subtle rounded-xl p-6">
            <h3 className="text-sm font-bold text-text-faint uppercase tracking-wider mb-4">What others give you</h3>
            <div className="bg-surface-2 rounded-lg p-4 font-mono text-sm text-text-muted border border-border-subtle">
              "SPY crossed above $653"
            </div>
            <p className="mt-3 text-xs text-text-faint">No context. No plan. No education.</p>
          </div>
          <div className="bg-surface-1 border border-bullish/10 rounded-xl p-6 shadow-glow-bullish">
            <h3 className="text-sm font-bold text-bullish-text uppercase tracking-wider mb-4">What TradeCoPilot gives you</h3>
            <div className="bg-surface-2 rounded-lg p-4 text-sm text-text-secondary border border-bullish/10 space-y-1">
              <p className="font-bold text-text-primary">SPY double bottom at $644.72</p>
              <p className="text-xs">Tested 2x across daily bars. EMA200 confluence.</p>
              <p className="font-mono text-xs text-text-muted">Entry $645 · Stop $644 · T1 $653 · T2 $658</p>
              <p className="text-xs text-accent">Score 80 · AI: "High probability retest of PDL with volume confirmation"</p>
            </div>
            <p className="mt-3 text-xs text-bullish-text">Complete plan. Ready to execute.</p>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Features ─────────────────────────────────────────────────────── */

function Features() {
  const features = [
    { icon: Zap, title: "Structural Alerts", desc: "PDL reclaims, MA bounces, consolidation breakouts, double bottoms — real patterns, not price crosses. Scans every 3 min." },
    { icon: Brain, title: "AI Trade Coach", desc: "Ask about any chart. Gets specific prices, targets, and if/then scenarios. Position-aware — knows your open trades." },
    { icon: Send, title: "Telegram Alerts", desc: "Complete trade plans with Took/Skip/Exit buttons. Act from your phone. Swing trades labeled separately from day trades." },
    { icon: BarChart3, title: "Edge Tracker", desc: "Weekly Edge Score (0-10). Track your proven edge, leaks, and what to change. AI coaching based on YOUR trading data." },
    { icon: LineChart, title: "Chart Replay", desc: "Watch any alert play out candle-by-candle. AI narrates entry, price action, and outcome. Learn from every trade." },
    { icon: Shield, title: "Transparent Track Record", desc: "Public win rates. Per-pattern performance. We show what works AND what fails. 90-day rolling data, always live." },
  ];

  return (
    <section className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <Badge>Features</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Everything you need. Nothing you don't.
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {features.map((f) => (
            <div key={f.title} className="bg-surface-1 border border-border-subtle rounded-xl p-6 hover:border-border-default transition-colors group">
              <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center mb-4 group-hover:shadow-glow-accent transition-shadow">
                <f.icon className="h-5 w-5 text-accent" />
              </div>
              <h3 className="text-base font-bold text-text-primary mb-2">{f.title}</h3>
              <p className="text-sm text-text-secondary leading-relaxed">{f.desc}</p>
            </div>
          ))}
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
      period: "3-day Pro trial",
      desc: "Full Pro access for 3 days, then limited",
      cta: "Start Free Trial",
      features: [
        "3 symbols on watchlist",
        "3 alerts visible per session",
        "AI Coach (2 queries/day)",
        "Signal Library access",
        "Today's alerts only",
      ],
      highlight: false,
    },
    {
      name: "Pro",
      price: "$49",
      period: "/month",
      desc: "For active traders who want an edge",
      cta: "Start Free Trial",
      features: [
        "10 symbols on watchlist",
        "Real-time Telegram alerts",
        "AI Trade Coach (20/day)",
        "Full alert history (30 days)",
        "Pre-trade checklist",
        "Daily AI battle plan (9:15 AM)",
        "Weekly Edge Report",
        "Performance analytics",
      ],
      highlight: true,
    },
    {
      name: "Premium",
      price: "$99",
      period: "/month",
      desc: "For serious traders who want full control",
      cta: "Start Free Trial",
      features: [
        "Everything in Pro",
        "25 symbols on watchlist",
        "Unlimited AI Coach",
        "Full alert history",
        "Weekly AI review",
        "Swing trade system",
        "Paper trading simulator",
        "Backtesting engine",
      ],
      highlight: false,
    },
  ];

  return (
    <section className="py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="blue">Pricing</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Simple pricing. Cancel anytime.
          </h2>
          <p className="mt-4 text-text-secondary">Annual plans save 2 months.</p>
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

/* ── Trust / Social Proof ─────────────────────────────────────────── */

function Trust({ track }: { track: TrackRecord | null }) {
  return (
    <section className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-4xl mx-auto text-center">
        <Badge>Radical transparency</Badge>
        <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
          We show everything.<br />Even when it's ugly.
        </h2>
        <p className="mt-4 text-text-secondary max-w-2xl mx-auto">
          Public track record. Per-category win rates. Alerts you skipped that would
          have worked. Most signal services can't survive this level of honesty. We can.
        </p>

        <div className="mt-12 grid grid-cols-1 sm:grid-cols-3 gap-6">
          {[
            { stat: track ? `${track.win_rate}%` : "—", label: "Overall win rate", sub: "Across all entry alerts, last 90 days" },
            { stat: track ? `${track.wins}W / ${track.losses}L` : "—", label: "Win / Loss", sub: "Target hits vs stop outs" },
            { stat: track ? `${track.total_signals}` : "—", label: "Signals tracked", sub: "Entry alerts scored and verified" },
          ].map((item) => (
            <div key={item.label} className="bg-surface-1 border border-border-subtle rounded-xl p-6">
              <span className="font-mono text-3xl font-bold text-bullish-text">{item.stat}</span>
              <p className="text-sm font-medium text-text-primary mt-2">{item.label}</p>
              <p className="text-xs text-text-faint mt-1">{item.sub}</p>
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
          Stop staring at charts.<br />Start trading with a plan.
        </h2>
        <p className="mt-4 text-text-secondary max-w-xl mx-auto">
          Join traders who get complete trade plans delivered to their phone —
          with the AI coaching to get better every day.
        </p>
        <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            to="/register"
            className="inline-flex items-center justify-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold text-base px-8 py-4 rounded-xl transition-all shadow-[0_0_30px_rgba(34,197,94,0.25)]"
          >
            Start Free Trial
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
        <p className="mt-4 text-xs text-text-faint">No credit card required. Free tier available forever.</p>
      </div>
    </section>
  );
}

/* ── Nav ──────────────────────────────────────────────────────────── */

function LandingNav() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-surface-0/80 backdrop-blur-lg border-b border-border-subtle/50">
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
          <a href="#features" className="hover:text-text-primary transition-colors">Features</a>
          <a href="#pricing" className="hover:text-text-primary transition-colors">Pricing</a>
          <Link to="/learn" className="hover:text-text-primary transition-colors">Learn</Link>
          <a href="#track-record" className="hover:text-text-primary transition-colors">Track Record</a>
        </div>

        <div className="flex items-center gap-3">
          <Link to="/login" className="text-sm text-text-muted hover:text-text-primary transition-colors">
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

/* ── Footer ───────────────────────────────────────────────────────── */

function Footer() {
  return (
    <footer className="border-t border-border-subtle py-12 px-6">
      <div className="max-w-5xl mx-auto flex flex-col md:flex-row justify-between items-center gap-6">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded bg-accent/20 flex items-center justify-center">
            <Crosshair className="h-3 w-3 text-accent" />
          </div>
          <span className="text-sm text-text-muted">
            <span className="text-accent">Trade</span>CoPilot
          </span>
        </div>
        <p className="text-xs text-text-faint text-center">
          Educational platform. Not financial advice. Past performance does not guarantee future results. Trade responsibly.
        </p>
        <div className="flex gap-6 text-xs text-text-faint">
          <a href="https://twitter.com/tradecopilot" target="_blank" rel="noopener noreferrer" className="hover:text-text-muted">Twitter/X</a>
          <a href="https://youtube.com/@tradecopilot" target="_blank" rel="noopener noreferrer" className="hover:text-text-muted">YouTube</a>
          <a href="https://tiktok.com/@tradecopilot" target="_blank" rel="noopener noreferrer" className="hover:text-text-muted">TikTok</a>
          <a href="#" className="hover:text-text-muted">Terms</a>
          <a href="#" className="hover:text-text-muted">Privacy</a>
        </div>
      </div>
    </footer>
  );
}

/* ── Telegram Alert Demo ─────────────────────────────────────────── */

function TelegramDemo() {
  return (
    <section className="py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="blue">Alerts on your phone</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Trade from Telegram.
          </h2>
          <p className="mt-4 text-text-secondary max-w-2xl mx-auto">
            Complete trade plans delivered to your phone. Tap Took or Skip.
            Track your decisions. Build your edge.
          </p>
        </div>

        <div className="max-w-sm mx-auto">
          {/* Phone mockup */}
          <div className="bg-surface-1 border border-border-subtle rounded-3xl p-4 shadow-elevated">
            {/* Status bar */}
            <div className="flex items-center justify-between px-2 py-1 mb-3">
              <span className="text-[10px] text-text-faint font-mono">9:47 AM</span>
              <span className="text-[10px] text-text-faint">TradeCoPilot Bot</span>
              <div className="flex gap-1">
                <div className="w-3 h-2 bg-text-faint/30 rounded-sm" />
                <div className="w-3 h-2 bg-text-faint/30 rounded-sm" />
              </div>
            </div>

            {/* Alert messages */}
            <div className="space-y-3">
              {/* BUY alert */}
              <div className="bg-surface-2 rounded-xl p-3.5 border border-bullish/10">
                <p className="text-sm font-bold text-text-primary">LONG SPY $655.83</p>
                <p className="text-xs text-text-muted mt-1">Entry $654.20 · Stop $652.80 · T1 $658.50</p>
                <p className="text-xs text-text-secondary mt-1.5">Prior day low bounce — held above $654</p>
                <p className="text-xs text-accent mt-1">Conviction: HIGH</p>
                <div className="flex gap-2 mt-3">
                  <span className="bg-bullish/20 text-bullish-text text-xs font-bold px-3 py-1.5 rounded-lg">Took It</span>
                  <span className="bg-surface-3 text-text-muted text-xs font-bold px-3 py-1.5 rounded-lg">Skip</span>
                  <span className="bg-bearish/20 text-bearish-text text-xs font-bold px-3 py-1.5 rounded-lg">Exit</span>
                </div>
              </div>

              {/* T1 notification */}
              <div className="bg-surface-2 rounded-xl p-3.5 border border-bullish/10">
                <p className="text-sm font-bold text-bullish-text">T1 REACHED — SPY $658.50</p>
                <p className="text-xs text-text-muted mt-1">Your LONG from $654.20 is at target</p>
                <p className="text-xs text-bullish-text mt-1">P&L: +$4.30 (+0.66%)</p>
                <div className="flex gap-2 mt-3">
                  <span className="bg-bearish/20 text-bearish-text text-xs font-bold px-3 py-1.5 rounded-lg">Exit Trade</span>
                </div>
              </div>

              {/* NOTICE */}
              <div className="bg-surface-2 rounded-xl p-3 border border-border-subtle">
                <p className="text-xs text-text-muted">
                  <span className="font-bold text-text-secondary">NOTICE — ETH-USD $2,118</span>
                  <br />VWAP reclaimed from below — momentum shifting bullish
                </p>
              </div>

              {/* Swing */}
              <div className="bg-surface-2 rounded-xl p-3.5 border border-accent/10">
                <p className="text-sm font-bold text-accent">SWING LONG BTC-USD $68,906</p>
                <p className="text-xs text-text-muted mt-1">Entry $68,906 · Stop $68,400 (daily close)</p>
                <p className="text-xs text-text-secondary mt-1">Weekly support hold — Conviction: HIGH</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}


/* ── Comparison Table ──────────────────────────────────────────────── */

function Comparison() {
  const rows = [
    { feature: "Complete trade plan (entry/stop/T1/T2)", us: true, tv: false, ti: false, disc: false },
    { feature: "AI explains WHY the setup works", us: true, tv: false, ti: false, disc: false },
    { feature: "Per-pattern win rates (transparent)", us: true, tv: false, ti: false, disc: false },
    { feature: "Telegram alerts with Took/Skip/Exit", us: true, tv: false, ti: false, disc: false },
    { feature: "Position sizing calculated for you", us: true, tv: false, ti: true, disc: false },
    { feature: "Works while you're at your day job", us: true, tv: false, ti: false, disc: false },
    { feature: "Mobile-first (phone alerts)", us: true, tv: true, ti: false, disc: true },
    { feature: "AI coaching based on YOUR data", us: true, tv: false, ti: false, disc: false },
    { feature: "Chart replay with AI narration", us: true, tv: false, ti: false, disc: false },
    { feature: "3-day free Pro trial", us: true, tv: false, ti: false, disc: false },
    { feature: "Price", us: "$49/mo", tv: "$15+/mo", ti: "$228/mo", disc: "$50-500/mo" },
  ];

  return (
    <section className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <Badge>How we compare</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Not another alert service.
          </h2>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left py-3 px-4 text-text-muted font-medium">Feature</th>
                <th className="py-3 px-4 text-accent font-bold">TradeCoPilot</th>
                <th className="py-3 px-4 text-text-faint font-medium">TradingView</th>
                <th className="py-3 px-4 text-text-faint font-medium">Trade Ideas</th>
                <th className="py-3 px-4 text-text-faint font-medium">Discord Groups</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.feature} className="border-b border-border-subtle/30">
                  <td className="py-3 px-4 text-text-secondary">{row.feature}</td>
                  {[row.us, row.tv, row.ti, row.disc].map((val, i) => (
                    <td key={i} className="py-3 px-4 text-center">
                      {typeof val === "boolean" ? (
                        val ? <Check className="h-4 w-4 text-bullish-text mx-auto" /> : <span className="text-text-faint">—</span>
                      ) : (
                        <span className={i === 0 ? "font-bold text-accent" : "text-text-faint"}>{val}</span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
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
      q: "Is this financial advice?",
      a: "No. TradeCoPilot is an educational platform that teaches chart structure through real-time pattern detection. Every alert is a learning opportunity — you always decide whether to trade. We never recommend specific trades.",
    },
    {
      q: "How fast are alerts delivered?",
      a: "The scanner checks your watchlist every 3 minutes during market hours. When a pattern is detected, the alert hits your Telegram within seconds — complete with entry, stop, targets, and AI analysis.",
    },
    {
      q: "What's your win rate?",
      a: "Our overall win rate across 600+ tracked signals is 77%. But win rates vary by pattern — VWAP reclaims win 100%, consolidation breakouts win 96%, while some patterns are closer to 65%. We show all of this transparently in our Signal Library.",
    },
    {
      q: "Can I cancel anytime?",
      a: "Yes. No contracts, no cancellation fees. Cancel from your Settings page and you keep access until the end of your billing period. The free tier is available forever.",
    },
    {
      q: "Do I need to watch charts all day?",
      a: "No — that's the whole point. TradeCoPilot watches the charts for you. You get a Telegram notification only when a high-conviction setup appears. Many of our users have full-time jobs and trade from their phone.",
    },
    {
      q: "What markets do you cover?",
      a: "US equities (stocks and ETFs) during market hours (9:30 AM - 4 PM ET), and crypto (BTC, ETH) 24/7. You choose your symbols — up to 10 on Pro, 25 on Premium.",
    },
    {
      q: "What's included in the free trial?",
      a: "Every new account gets 3 days of full Pro access — real-time Telegram alerts, AI Coach, analytics, everything. After the trial, you keep free access with limited features (3 symbols, 2 AI queries/day). Upgrade anytime.",
    },
    {
      q: "Do you auto-close my trades?",
      a: "Never. TradeCoPilot notifies you when stop or target levels are reached, but you always decide when to exit. Close trades from the dashboard or Telegram — you're always in control.",
    },
  ];

  return (
    <section className="py-24 px-6">
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
                <span className="text-text-faint ml-4 shrink-0">{open === i ? "−" : "+"}</span>
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

/* ── Main Landing Page ────────────────────────────────────────────── */

export default function LandingPage() {
  const track = usePublicTrackRecord();

  return (
    <div className="min-h-screen bg-surface-0 text-text-primary overflow-x-hidden">
      <LandingNav />
      <Hero track={track} />
      <Problem />
      <HowItWorks />
      <Differentiators />
      <div id="features"><Features /></div>
      <TelegramDemo />
      <Comparison />
      <div id="pricing"><Pricing /></div>
      <div id="track-record"><Trust track={track} /></div>
      <FAQ />
      <FinalCTA />
      <Footer />
    </div>
  );
}
