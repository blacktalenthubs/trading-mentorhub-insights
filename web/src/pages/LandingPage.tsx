/** Landing Page — TradeSignal public marketing page.
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
            <h3 className="text-sm font-bold text-bullish-text uppercase tracking-wider mb-4">What TradeSignal gives you</h3>
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
    { icon: Zap, title: "Real-time Alerts", desc: "8+ structural rules scan your watchlist every 3 minutes. Support bounces, breakouts, rejections, target/stop exits." },
    { icon: Brain, title: "AI Trade Coach", desc: "Ask about any chart. The AI sees your actual candles, analyzes structure, and gives entry/exit timing with reasoning." },
    { icon: Send, title: "Telegram Delivery", desc: "Alerts with inline Took/Skip buttons right in Telegram. Act from your phone without opening the app." },
    { icon: BarChart3, title: "Decision Analytics", desc: "Track which alerts you took vs skipped. See which setups win for you. Build your edge over time." },
    { icon: LineChart, title: "Live Charts", desc: "TradingView charts with EMA/SMA overlays, entry/stop/target lines, and multi-timeframe analysis." },
    { icon: Shield, title: "Transparent Track Record", desc: "Public win rates by alert type. Per-symbol performance. We show what works AND what doesn't." },
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
      period: "forever",
      desc: "See what the platform can do",
      cta: "Get Started",
      features: [
        "Delayed signal feed (15-min)",
        "Daily EOD summary email",
        "Public track record",
        "3 symbols on watchlist",
      ],
      highlight: false,
    },
    {
      name: "Pro",
      price: "$29",
      period: "/month",
      desc: "For active traders who want an edge",
      cta: "Start Free Trial",
      features: [
        "Real-time signal feed",
        "Telegram + email alerts",
        "AI Trade Coach",
        "15 symbols on watchlist",
        "Full trade analytics",
        "Decision quality tracking",
        "Performance dashboard",
      ],
      highlight: true,
    },
    {
      name: "Premium",
      price: "$79",
      period: "/month",
      desc: "For serious traders who want full control",
      cta: "Start Free Trial",
      features: [
        "Everything in Pro",
        "Unlimited watchlist",
        "Custom alert rules",
        "API webhook delivery",
        "Backtest custom rules",
        "Priority signal delivery",
        "Export reports (CSV/PDF)",
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
            <span className="text-accent">Trade</span>Signal
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
            <span className="text-accent">Trade</span>Signal
          </span>
        </div>
        <p className="text-xs text-text-faint text-center">
          Educational platform. Not financial advice. Past performance does not guarantee future results. Trade responsibly.
        </p>
        <div className="flex gap-6 text-xs text-text-faint">
          <a href="#" className="hover:text-text-muted">Terms</a>
          <a href="#" className="hover:text-text-muted">Privacy</a>
          <a href="#" className="hover:text-text-muted">Contact</a>
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
      <HowItWorks />
      <Differentiators />
      <div id="features"><Features /></div>
      <div id="pricing"><Pricing /></div>
      <div id="track-record"><Trust track={track} /></div>
      <FinalCTA />
      <Footer />
    </div>
  );
}
