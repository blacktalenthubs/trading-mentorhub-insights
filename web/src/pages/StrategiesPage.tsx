import { Link } from "react-router-dom";
import { TrendingUp, BarChart3, Layers, Target, Zap, Shield, Activity, Eye } from "lucide-react";

interface Indicator {
  id: string;
  name: string;
  tagline: string;
  what_it_finds: string;
  rules: string[];
  icon: typeof TrendingUp;
}

const INDICATORS: Indicator[] = [
  {
    id: "ma-ema-daily",
    name: "ma-ema-daily",
    tagline: "Moving-average bounce / rejection detection",
    what_it_finds:
      "Monitors 8 daily moving averages (EMA 8/21/50/100/200, SMA 50/100/200) and detects when price tests one and recovers (bounce) or fails (rejection).",
    rules: [
      "EMA bounce — price wicks down to a daily EMA and closes back above on a green bar",
      "EMA reclaim — close was below the MA on the prior bar, this bar's close pushes back above (gap-up recovery)",
      "EMA rejection — symmetric short pattern: wick into the MA from below, close back under",
      "Proximity (NOTICE) — bar respected the level without touching, surfaced as heads-up only",
    ],
    icon: TrendingUp,
  },
  {
    id: "levels-day-vwap",
    name: "levels-day-vwap",
    tagline: "Prior-day high/low + VWAP + stage detection",
    what_it_finds:
      "Tracks the previous session's high (PDH) and low (PDL) along with VWAP. Detects breakouts, reclaims, rejections, and failed breakouts, with stage detection (Stage 1-4) overlaid for regime context.",
    rules: [
      "PDH break — close cleanly above the prior-day high",
      "PDL reclaim — close back above the prior-day low after a sweep",
      "PDH rejection — wick tagged PDH, close back under (short setup)",
      "PDH failed-breakout (trap short) — closed above then back below within sweep window",
      "VWAP reclaim / reject — close back across VWAP after N bars on the wrong side",
    ],
    icon: BarChart3,
  },
  {
    id: "levels-week-month",
    name: "levels-week-month",
    tagline: "Higher-timeframe structural levels (visual only)",
    what_it_finds:
      "Plots prior-week and prior-month highs/lows on the chart. No separate alerts — these levels are unified into the daily alert events as confluence anchors (a PWL reclaim fires the same staged_pdl_reclaim event as a PDL reclaim).",
    rules: [
      "PWH / PWL — prior week high & low, plotted",
      "PMH / PML — prior month high & low, plotted",
      "Weekly EMA 8/21 — optional weekly trend filter",
    ],
    icon: Layers,
  },
  {
    id: "pivots-1h-4h",
    name: "pivots-1h-4h",
    tagline: "Multi-timeframe pivot alignment (1h + 4h)",
    what_it_finds:
      "Fires only when a 1h swing pivot and a 4h swing pivot land within tolerance of each other — multi-TF confluence at a single price. Highest-conviction signal class in the suite.",
    rules: [
      "Pivot break long — close above an aligned 1h+4h resistance",
      "Pivot reclaim long — close back above an aligned 1h+4h support after a sweep",
      "Pivot reject short — wick into aligned resistance, close back under",
      "Pivot break short — close below an aligned 1h+4h support",
    ],
    icon: Target,
  },
];

interface TriageStep {
  step: number;
  title: string;
  description: string;
  icon: typeof Zap;
}

const TRIAGE_FLOW: TriageStep[] = [
  {
    step: 1,
    title: "Raw signal fires on TradingView",
    description: "A Pine indicator (one of the four above) detects a setup and posts to our webhook.",
    icon: Zap,
  },
  {
    step: 2,
    title: "Stored & dedup-checked",
    description: "The alert is persisted to the database, deduplicated against very recent identical fires, and queued for triage.",
    icon: Shield,
  },
  {
    step: 3,
    title: "Sector + index confluence check",
    description:
      "The AI agent looks for peers in the same sector firing the same direction within the last 15 minutes, and checks SPY/QQQ for macro alignment.",
    icon: Activity,
  },
  {
    step: 4,
    title: "Order-flow + volume + cluster check",
    description:
      "Volume ratio, CVD divergence, and historical-cluster proximity are evaluated as additional context.",
    icon: Eye,
  },
  {
    step: 5,
    title: "Verdict assigned",
    description: "🔥 HIGH (sector-aligned + clean math) · ⚪ NORMAL (clean setup, isolated) · 🔕 MUTE (counter-flow or near-duplicate).",
    icon: Target,
  },
  {
    step: 6,
    title: "Delivered to Telegram",
    description: "The alert is formatted with bold reason, structured levels grid, vitals, verdict block, and sector/index/cluster context.",
    icon: TrendingUp,
  },
];

export default function StrategiesPage() {
  return (
    <div className="min-h-screen bg-surface-0 text-text-primary">
      <div className="max-w-6xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="text-center mb-16">
          <Link to="/" className="text-sm text-text-muted hover:text-text-primary mb-6 inline-block">
            ← Back to home
          </Link>
          <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight">
            How the system <span className="text-gradient-ai">finds setups</span>
          </h1>
          <p className="mt-4 text-lg text-text-secondary max-w-2xl mx-auto">
            Four TradingView Pine indicators detect structural patterns. An AI triage layer adds sector,
            volume, and order-flow context. Every Telegram alert is the output of both stages.
          </p>
          <p className="mt-3 text-xs text-text-faint">
            Pattern detection is descriptive. <Link to="/disclaimer" className="underline hover:text-text-muted">Not investment advice.</Link>
          </p>
        </div>

        {/* The 4 indicators */}
        <section className="mb-20">
          <h2 className="font-display text-2xl font-bold mb-2">The Pine Indicator Suite</h2>
          <p className="text-text-muted mb-8 max-w-2xl">
            Each indicator targets a specific structural pattern. Pro subscribers receive the Pine source for all four to load into their own TradingView charts.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {INDICATORS.map((ind) => {
              const Icon = ind.icon;
              return (
                <div
                  key={ind.id}
                  className="bg-surface-1 border border-border-subtle rounded-2xl p-6 hover:border-accent/40 transition-colors"
                >
                  <div className="flex items-start gap-4 mb-4">
                    <div className="w-12 h-12 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center shrink-0">
                      <Icon className="h-6 w-6 text-accent" />
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-text-faint font-mono mb-1">
                        {ind.name}
                      </p>
                      <h3 className="font-bold text-lg leading-tight">{ind.tagline}</h3>
                    </div>
                  </div>
                  <p className="text-sm text-text-secondary mb-4 leading-relaxed">{ind.what_it_finds}</p>
                  <p className="text-xs uppercase tracking-wider text-text-faint mb-2">Rules</p>
                  <ul className="space-y-1.5 text-sm text-text-secondary">
                    {ind.rules.map((rule, idx) => (
                      <li key={idx} className="flex gap-2">
                        <span className="text-accent shrink-0">•</span>
                        <span>{rule}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        </section>

        {/* AI Triage flow */}
        <section className="mb-20">
          <h2 className="font-display text-2xl font-bold mb-2">The AI Triage Layer</h2>
          <p className="text-text-muted mb-8 max-w-2xl">
            Raw Pine signals don't go directly to Telegram. Each one passes through an AI agent that
            evaluates sector confluence, index alignment, order flow, and historical cluster — assigning
            a verdict and reason before delivery.
          </p>
          <div className="space-y-3">
            {TRIAGE_FLOW.map((step) => {
              const Icon = step.icon;
              return (
                <div
                  key={step.step}
                  className="flex gap-4 items-start bg-surface-1 border border-border-subtle rounded-xl p-4"
                >
                  <div className="flex flex-col items-center shrink-0">
                    <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center">
                      <Icon className="h-5 w-5 text-accent" />
                    </div>
                    <span className="text-[10px] uppercase tracking-wider text-text-faint font-mono mt-1">
                      Step {step.step}
                    </span>
                  </div>
                  <div>
                    <h3 className="font-bold text-base mb-1">{step.title}</h3>
                    <p className="text-sm text-text-secondary leading-relaxed">{step.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Sample alert visualization */}
        <section className="mb-20">
          <h2 className="font-display text-2xl font-bold mb-2">What an Alert Looks Like</h2>
          <p className="text-text-muted mb-8 max-w-2xl">
            Every Telegram alert is structured the same way — reason in bold caps at the top, levels grid,
            vitals (volume + CVD), verdict block with reason, and sector/index/cluster context.
          </p>
          <div className="bg-surface-1 border border-border-subtle rounded-2xl p-6 max-w-2xl mx-auto font-mono text-sm">
            <p className="text-lg font-bold mb-1">🎯 <span className="uppercase">1h/4h pivot break ↑</span> · 5m</p>
            <p className="text-base font-bold text-bullish-text mb-4">🟢 LONG · NVDA · $217.60</p>
            <pre className="text-xs text-text-secondary leading-relaxed bg-surface-0 rounded p-3 mb-3">
{`  Entry   $217.60
  Stop    $217.16   ↓0.20%
  T1      $218.24   ↑0.29%   1.5R
  T2      $218.89   ↑0.59%   2.9R`}
            </pre>
            <pre className="text-xs text-text-secondary leading-relaxed bg-surface-0 rounded p-3 mb-3">
{`  Vol  3.22× ✅
  CVD  confirming ✅`}
            </pre>
            <p className="text-base font-bold mb-2">🔥 HIGH</p>
            <p className="text-xs text-text-secondary mb-3 leading-relaxed">
              Sector-aligned break (MSFT firing bullish 0m ago) + dual-type confluence at 217.6.
            </p>
            <pre className="text-xs text-text-secondary leading-relaxed bg-surface-0 rounded p-3">
{`  Sector   MSFT (EMA 50 bounce, 0m ago) aligned
  Index    no macro
  Cluster  fresh`}
            </pre>
          </div>
          <p className="text-xs text-text-faint text-center mt-4">
            Sample alert. Educational illustration only.
          </p>
        </section>

        {/* CTAs */}
        <section className="text-center">
          <h2 className="font-display text-2xl font-bold mb-4">Want the framework?</h2>
          <p className="text-text-muted mb-8 max-w-xl mx-auto">
            Start with the Foundations track in the Learn section. Or sign up for Pro to get live alerts
            and the full Pine source code.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              to="/learn"
              className="inline-flex items-center justify-center gap-2 bg-accent hover:bg-accent/90 text-surface-0 font-bold px-6 py-3 rounded-xl"
            >
              Start Learning
            </Link>
            <Link
              to="/register"
              className="inline-flex items-center justify-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold px-6 py-3 rounded-xl"
            >
              Start Pro Trial
            </Link>
          </div>
        </section>

        <p className="text-xs text-text-faint text-center mt-16">
          Educational content. <Link to="/disclaimer" className="underline">Not investment advice.</Link>
        </p>
      </div>
    </div>
  );
}
