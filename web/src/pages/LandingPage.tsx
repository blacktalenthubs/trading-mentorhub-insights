/** Landing Page — AI Trading Education & Intelligence Platform.
 *
 *  Rebuilt around 5 AI pillars: Coach, CoPilot, Scan, Review, Pattern Library.
 *  Only markets features that are LIVE in production.
 *  Dark terminal aesthetic. Mobile-first.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Crosshair, Brain, Send, BarChart3, Play,
  Check, Zap, Clock,
  ArrowRight, MessageSquare, BookOpen,
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
          <a href="#pillars" className="hover:text-text-primary transition-colors">AI Features</a>
          <a href="#pricing" className="hover:text-text-primary transition-colors">Pricing</a>
          <Link to="/learn" className="hover:text-text-primary transition-colors">Pattern Library</Link>
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
          AI scanning continuously during market hours
        </Badge>

        <h1 className="mt-8 text-5xl sm:text-6xl lg:text-7xl font-bold tracking-tight text-text-primary leading-[1.08]">
          AI finds the trade.
          <br />
          <span className="text-gradient-ai">You decide.</span>
        </h1>

        <p className="mt-6 text-lg sm:text-xl text-text-secondary max-w-2xl mx-auto leading-relaxed">
          AI performs automated scans on your watchlist, identifies entries at key levels,
          and delivers complete trade plans. Entry. Stop. Target. Education.
        </p>

        {/* CTA */}
        <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            to="/register"
            className="inline-flex items-center justify-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold text-base px-8 py-4 rounded-xl transition-all shadow-[0_0_30px_rgba(34,197,94,0.25)] hover:shadow-[0_0_40px_rgba(34,197,94,0.35)]"
          >
            Start Free — 3 Day Pro Trial
            <ArrowRight className="h-4 w-4" />
          </Link>
          <a
            href="#track-record"
            className="inline-flex items-center justify-center gap-2 bg-surface-2 hover:bg-surface-3 text-text-primary font-medium text-base px-8 py-4 rounded-xl border border-border-subtle transition-colors"
          >
            See Live Track Record
          </a>
        </div>

        {/* Live metrics ticker */}
        <div className="mt-16 flex flex-wrap justify-center gap-6 sm:gap-10">
          {[
            { label: "Signals tracked", value: track ? `${track.total_signals}` : "---", color: "text-text-primary" },
            { label: "Win rate", value: track ? `${track.win_rate}%` : "---", color: "text-bullish-text" },
            { label: "Patterns", value: "14", color: "text-accent" },
            { label: "Crypto coverage", value: "24/7", color: "text-purple-400" },
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
                  <span className="text-[8px] font-bold text-accent bg-accent/10 border border-accent/20 px-1.5 py-0.5 rounded">AI SCAN</span>
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
          You know <span className="italic text-text-secondary">what</span> to trade.
          <br />
          You just can't watch charts all day.
        </h2>
        <div className="mt-12 grid grid-cols-1 sm:grid-cols-2 gap-6 text-left">
          {[
            { icon: Clock, text: "Chart analysis takes hours -- scanning 10+ symbols across multiple timeframes every morning" },
            { icon: Target, text: "Setups fire while you're at work -- the PDL bounce at $2,277 happened during your meeting" },
            { icon: Send, text: "Alert services give noise, not plans -- 'ETH crossed $2,280' is useless without entry, stop, and targets" },
            { icon: Brain, text: "You learn patterns on YouTube but struggle to spot them live -- education and execution are separated" },
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
  const pillars = [
    {
      icon: MessageSquare,
      title: "AI Coach",
      subtitle: "Live Trading Guidance",
      color: "accent",
      desc: "Ask any question about any chart. Get a structured trade plan in seconds -- not generic commentary.",
      bullets: [
        "\"Should I buy ETH here?\" -- Entry $2,245, Stop $2,233, T1 $2,275",
        "Knows your open positions -- won't tell you to buy what you hold",
        "Web chat + Telegram commands (/spy, /eth, /btc)",
        "Computes real VWAP from session data -- no hallucinated prices",
      ],
    },
    {
      icon: Brain,
      title: "AI CoPilot",
      subtitle: "Deep Chart Analysis & Education",
      color: "purple-400",
      desc: "Multi-timeframe analysis with confluence scoring. Learn WHY patterns work -- not just WHERE to enter.",
      bullets: [
        "Analyzes 5m, 1H, Daily, and Weekly for full context",
        "Confluence score (0-10) quantifies trade quality",
        "Matches against 14 playbook patterns automatically",
        "Pattern education: what it is, why it works, risk management",
      ],
    },
    {
      icon: Scan,
      title: "AI Scan",
      subtitle: "Automated Entry/Exit Detection",
      color: "bullish-text",
      desc: "Automated scans on your watchlist. Fires when price hits a key level. Says WAIT when there's no trade.",
      bullets: [
        "14 patterns: PDL bounce, VWAP hold, MA bounce, breakouts, more",
        "WAIT signals -- AI tells you when NOT to trade (only we do this)",
        "Position-aware -- won't send duplicate entries for trades you took",
        "24/7 crypto coverage with Coinbase data",
      ],
    },
    {
      icon: Play,
      title: "Trade Review",
      subtitle: "Replay & Validate Every Trade",
      color: "yellow-400",
      desc: "Cinematic animated replay of every alert -- entry to outcome. Share your wins. Learn from losses.",
      bullets: [
        "Full-screen replay with entry, stop, and target lines on chart",
        "Filter by AI vs Rules, Took vs Skipped, by date",
        "Shareable links -- build your public track record",
        "Auto-generated after market close every day",
      ],
    },
    {
      icon: BookOpen,
      title: "Pattern Library",
      subtitle: "14 Setups Taught With Real Data",
      color: "blue-400",
      desc: "Learn support bounces, breakouts, and reversals with difficulty ratings and live win rate data.",
      bullets: [
        "Beginner to Advanced difficulty levels",
        "Click any pattern for deep education: what, why, how, risk",
        "Win rates from real production signals -- not theory",
        "Free access at /learn -- no login required",
      ],
    },
  ];

  const colorMap: Record<string, { bg: string; border: string; text: string }> = {
    "accent": { bg: "bg-accent/10", border: "border-accent/20", text: "text-accent" },
    "purple-400": { bg: "bg-purple-500/10", border: "border-purple-500/20", text: "text-purple-400" },
    "bullish-text": { bg: "bg-bullish/10", border: "border-bullish/20", text: "text-bullish-text" },
    "yellow-400": { bg: "bg-yellow-500/10", border: "border-yellow-500/20", text: "text-yellow-400" },
    "blue-400": { bg: "bg-blue-500/10", border: "border-blue-500/20", text: "text-blue-400" },
  };

  return (
    <section id="pillars" className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="blue">5 AI capabilities</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            AI-powered trading strategies
          </h2>
          <p className="mt-4 text-text-secondary max-w-2xl mx-auto">
            Five AI systems working together: find entries, analyze charts,
            coach you through decisions, replay every trade, and teach you patterns.
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
      title: "Set your watchlist",
      desc: "Add up to 25 symbols. SPY, AAPL, ETH, BTC -- whatever you trade. AI monitors all of them. 24/7 for crypto.",
      icon: Crosshair,
    },
    {
      num: "02",
      title: "AI scans continuously",
      desc: "When price hits a key level, AI identifies the setup and sends a complete plan: entry, stop, T1, T2, conviction. When there's no trade, it says WAIT.",
      icon: Scan,
    },
    {
      num: "03",
      title: "Decide, track, improve",
      desc: "Took It -- track P&L automatically. Skip -- see if you were right to pass. Review -- replay every trade, learn patterns, build your edge.",
      icon: BarChart3,
    },
  ];

  return (
    <section className="py-24 px-6">
      <div className="max-w-5xl mx-auto">
        <div className="text-center mb-16">
          <Badge variant="green">How it works</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            Three steps to AI-powered trading
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
    { aspect: "Watching charts", manual: "Hours every day", ai: "AI scans automatically" },
    { aspect: "Missing setups", manual: "Constantly", ai: "Catches setups 24/7" },
    { aspect: "Entry timing", manual: "Emotional / chasing", ai: "At the structural level" },
    { aspect: "Stop placement", manual: "Arbitrary %", ai: "Below support structure" },
    { aspect: "Alert noise", manual: "100+ alerts/day", ai: "3-5 quality setups" },
    { aspect: "Position tracking", manual: "Spreadsheets", ai: "Auto from Took/Skip" },
    { aspect: "Education", manual: "YouTube + trial/error", ai: "AI explains every trade" },
    { aspect: "Track record", manual: "\"Trust me\"", ai: "Public, auditable" },
  ];

  return (
    <section className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <Badge>Why AI wins</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            AI-powered vs manual trading
          </h2>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border-subtle">
                <th className="text-left py-3 px-4 text-text-muted font-medium w-1/3"></th>
                <th className="py-3 px-4 text-text-faint font-medium w-1/3">Manual Trading</th>
                <th className="py-3 px-4 text-accent font-bold w-1/3">AI Platform</th>
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
    { time: "09:05 AM", label: "AI Game Plan", desc: "Top 3 focus symbols + edge reasoning", color: "text-accent" },
    { time: "09:15 AM", label: "Pre-Market Brief", desc: "Market outlook, key levels, bias", color: "text-purple-400" },
    { time: "09:30 AM", label: "AI Scan Starts", desc: "Automated scans through market close", color: "text-bullish-text" },
    { time: "All Day", label: "AI Coach Available", desc: "Ask about any chart, anytime", color: "text-yellow-400" },
    { time: "All Day", label: "Telegram Alerts", desc: "Took / Skip / Exit from your phone", color: "text-blue-400" },
    { time: "04:35 PM", label: "AI EOD Review", desc: "What worked, what didn't, lessons", color: "text-orange-400" },
    { time: "04:40 PM", label: "Trade Replay", desc: "Auto-generated for every trade", color: "text-yellow-400" },
    { time: "Friday", label: "Weekly Edge Report", desc: "Patterns, performance, coaching", color: "text-purple-400" },
  ];

  return (
    <section className="py-24 px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <Badge variant="blue">The AI trading day</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            AI works for you all day
          </h2>
          <p className="mt-4 text-text-secondary">
            From pre-market prep to end-of-day review. 24/7 for crypto.
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
          Crypto symbols (BTC, ETH) are monitored 24/7 -- AI never stops scanning.
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
          <Badge variant="blue">Trade from your phone</Badge>
          <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
            AI alerts on Telegram
          </h2>
          <p className="mt-4 text-text-secondary max-w-2xl mx-auto">
            Complete trade plans delivered to your phone. Tap Took or Skip.
            Ask AI with /spy or /eth commands. Trade from anywhere.
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
                  <span className="text-[8px] font-bold text-accent bg-accent/10 px-1.5 py-0.5 rounded">AI SCAN</span>
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
                  <span className="text-[8px] font-bold text-accent bg-accent/10 px-1.5 py-0.5 rounded">AI SCAN</span>
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
      desc: "3-day Pro trial, then limited access",
      cta: "Start Free Trial",
      features: [
        "5 symbols on watchlist",
        "AI Coach: 3 queries/day",
        "AI Scan: 3 alerts/day",
        "Telegram: 3 commands/day",
        "Today's alerts only",
        "1 replay/day",
        "Pattern Library access",
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
        "AI Coach: 50 queries/day",
        "AI Scan: unlimited alerts",
        "Telegram: 50 commands/day",
        "Real-time Telegram alerts",
        "Unlimited replay",
        "Pre-market AI Brief",
        "Daily AI EOD Review",
        "Performance Analytics",
        "30-day alert history",
      ],
      highlight: true,
    },
    {
      name: "Premium",
      price: "$99",
      period: "/month",
      desc: "Full access for serious traders",
      cta: "Start Free Trial",
      features: [
        "Everything in Pro",
        "25 symbols on watchlist",
        "Unlimited AI Coach",
        "Unlimited Telegram",
        "Weekly AI Edge Report",
        "Full alert history",
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

/* ── Trust / Track Record ───────────────────────────────────────── */

function Trust({ track }: { track: TrackRecord | null }) {
  return (
    <section id="track-record" className="py-24 px-6 bg-surface-1/50">
      <div className="max-w-4xl mx-auto text-center">
        <Badge>Radical transparency</Badge>
        <h2 className="mt-6 text-3xl sm:text-4xl font-bold text-text-primary">
          We show everything.<br />Even when it's ugly.
        </h2>
        <p className="mt-4 text-text-secondary max-w-2xl mx-auto">
          Public track record. Per-pattern win rates. Alerts you skipped that would
          have worked. Most signal services can't survive this level of honesty. We can.
        </p>

        <div className="mt-12 grid grid-cols-1 sm:grid-cols-3 gap-6">
          {[
            { stat: track ? `${track.win_rate}%` : "---", label: "Overall win rate", sub: "Across all entry alerts, last 90 days" },
            { stat: track ? `${track.wins}W / ${track.losses}L` : "---", label: "Win / Loss", sub: "Target hits vs stop outs" },
            { stat: track ? `${track.total_signals}` : "---", label: "Signals tracked", sub: "Entry alerts scored and verified" },
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
            why it works, how to confirm, and real win rate data from our signals.
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
      q: "Is this a signal service?",
      a: "No. We provide AI-powered analysis and education. Entry, stop, target, reasoning -- you decide whether to trade. The AI teaches you patterns so you develop your own edge over time.",
    },
    {
      q: "How is this different from ChatGPT?",
      a: "Our AI is trained on a specific trading playbook (14 patterns), sees real-time OHLCV bars, computes VWAP from live session data, knows your open positions, and gives structured trade plans -- not generic market commentary.",
    },
    {
      q: "What is a WAIT signal?",
      a: "When AI scans your watchlist and finds no valid setup, it says WAIT. This is a feature -- saving you from bad entries in choppy markets. No other platform tells you when NOT to trade.",
    },
    {
      q: "What markets do you cover?",
      a: "US equities (SPY, AAPL, TSLA, NVDA, META, etc.) during market hours, and crypto (ETH, BTC) 24/7 using Coinbase data for reliable pricing.",
    },
    {
      q: "What's your win rate?",
      a: "Our track record is live and public on this page. Win rates vary by pattern -- we show all of it transparently. Check the Pattern Library for per-setup performance data.",
    },
    {
      q: "Can I use it from my phone?",
      a: "Yes. Telegram is the primary alert channel. You get trade plans with Took/Skip/Exit buttons. You can also ask the AI Coach directly via Telegram commands like /spy, /eth, or /btc.",
    },
    {
      q: "Do I need to watch charts all day?",
      a: "No -- that's the whole point. AI scans your watchlist continuously and sends alerts to your phone only when a setup appears. Many users trade from their phone while at their day job.",
    },
    {
      q: "Can I try before paying?",
      a: "Yes. Free tier is available forever (5 symbols, 3 AI queries/day). Every new account gets 3 days of full Pro access to try everything.",
    },
    {
      q: "Does the AI guarantee profits?",
      a: "No. Trading has risk. Our track record is public -- see exactly what works and what doesn't. We help you find better entries and learn from every trade, not guarantee outcomes.",
    },
    {
      q: "Can I cancel anytime?",
      a: "Yes. No contracts, no cancellation fees. Cancel from Settings and keep access until end of billing period.",
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
          Stop staring at charts.<br />Let AI find your entries.
        </h2>
        <p className="mt-4 text-text-secondary max-w-xl mx-auto">
          Join traders who get AI-powered trade plans delivered to their phone --
          with the coaching to get better every trade.
        </p>
        <div className="mt-10 flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            to="/register"
            className="inline-flex items-center justify-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold text-base px-8 py-4 rounded-xl transition-all shadow-[0_0_30px_rgba(34,197,94,0.25)]"
          >
            Start Free -- 3 Day Pro Trial
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
        <p className="mt-4 text-xs text-text-faint">No credit card required. Free tier available forever.</p>
      </div>
    </section>
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
          <Link to="/learn" className="hover:text-text-muted">Pattern Library</Link>
          <a href="#" className="hover:text-text-muted">Terms</a>
          <a href="#" className="hover:text-text-muted">Privacy</a>
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
      <div id="track-record"><Trust track={track} /></div>
      <div id="pricing"><Pricing /></div>
      <FAQ />
      <FinalCTA />
      <Footer />
    </div>
  );
}
