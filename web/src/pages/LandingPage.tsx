/** Landing Page — V2 revamp per Spec 50.
 *
 *  Positioning (FR-201): "TradingView's signal noise, filtered into
 *  conviction-rated trade alerts." Pine + Triage pipeline is the product.
 *
 *  Sections:
 *   1. Sticky nav (Pattern Library, Track Record + Sign in / Get started)
 *   2. Hero — single headline, live win-rate stat (3-state hook), primary CTA
 *   3. What You Get — 4 deliverables (2 live, 2 coming soon)
 *   4. Proof — live numbers from /api/v1/intel/public-track-record
 *   5. Final CTA + footer
 *
 *  The hero stat hook returns a 3-state machine per FR-202b — see
 *  specs/50-landing-revamp/contracts/hero-stat-fallback.md.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight, BookOpen, Check, Clock, Crosshair, Eye, FileText,
  MessageCircle, Menu, X,
} from "lucide-react";

/* ── Track record state machine (FR-202b) ─────────────────────────── */

interface TrackRecord {
  period_days: number;
  total_signals: number;
  wins: number;
  losses: number;
  win_rate: number;
  by_alert_type: Record<string, { wins: number; losses: number }>;
}

type TrackRecordState =
  | { status: "loading" }
  | { status: "ok"; data: TrackRecord }
  | { status: "error" };

function isValidTrackRecord(x: unknown): x is TrackRecord {
  if (typeof x !== "object" || x === null) return false;
  const r = x as Record<string, unknown>;
  return (
    typeof r.period_days === "number" &&
    typeof r.total_signals === "number" &&
    typeof r.wins === "number" &&
    typeof r.losses === "number" &&
    typeof r.win_rate === "number" &&
    Number.isFinite(r.win_rate)
  );
}

function usePublicTrackRecord(days: number = 90): {
  state: TrackRecordState;
  refresh: () => void;
} {
  const [state, setState] = useState<TrackRecordState>({ status: "loading" });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    fetch(`/api/v1/intel/public-track-record?days=${days}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (cancelled) return;
        if (!isValidTrackRecord(data)) throw new Error("invalid shape");
        setState({ status: "ok", data });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ status: "error" });
      });
    return () => {
      cancelled = true;
    };
  }, [days, nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return { state, refresh };
}

/* ── Nav ──────────────────────────────────────────────────────────── */

function LandingNav() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-surface-0/80 backdrop-blur-lg border-b border-border-subtle/50">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 group" aria-label="TradeCoPilot home">
          <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center group-hover:bg-accent-hover transition-colors">
            <Crosshair className="h-4 w-4 text-white" aria-hidden="true" />
          </div>
          <span className="font-display font-bold text-lg text-text-primary">
            <span className="text-accent">Trade</span>CoPilot
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-8 text-sm text-text-muted">
          <Link to="/learn" className="hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0 rounded">
            Pattern Library
          </Link>
          <Link to="/track-record" className="hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0 rounded">
            Track Record
          </Link>
        </div>

        <div className="flex items-center gap-2 md:gap-3">
          <Link
            to="/login"
            className="hidden sm:inline-block text-sm text-text-muted hover:text-text-primary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0 rounded px-2 py-1"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0"
          >
            Get started
          </Link>
          <button
            type="button"
            className="md:hidden p-2 text-text-muted hover:text-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen(!open)}
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {open && (
        <div className="md:hidden border-t border-border-subtle bg-surface-0">
          <div className="px-6 py-4 flex flex-col gap-3 text-text-muted">
            <Link to="/learn" onClick={close} className="py-2 hover:text-text-primary">Pattern Library</Link>
            <Link to="/track-record" onClick={close} className="py-2 hover:text-text-primary">Track Record</Link>
            <Link to="/login" onClick={close} className="py-2 hover:text-text-primary sm:hidden">Sign in</Link>
          </div>
        </div>
      )}
    </nav>
  );
}

/* ── Hero stat ────────────────────────────────────────────────────── */

function HeroStat({ state, onRefresh }: { state: TrackRecordState; onRefresh: () => void }) {
  if (state.status === "loading") {
    return (
      <div className="text-text-muted animate-pulse motion-reduce:animate-none">
        <span className="text-base">Track record loading…</span>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="text-text-muted text-base">
        Track record unavailable right now ·{" "}
        <button
          type="button"
          onClick={onRefresh}
          className="text-accent hover:text-accent-hover underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded"
        >
          Refresh
        </button>
      </div>
    );
  }

  // status === "ok"
  const { total_signals, win_rate } = state.data;

  if (total_signals === 0) {
    return (
      <div className="space-y-1">
        <div className="text-2xl font-semibold text-accent/80">Track record building</div>
        <div className="text-sm text-text-muted">
          first signals incoming · v2 live
        </div>
      </div>
    );
  }

  const pct = Math.round(win_rate * 100);
  return (
    <div className="space-y-1">
      <div
        className="text-4xl sm:text-5xl font-display font-bold text-accent"
        aria-label={`${pct} percent win rate, last 90 days, ${total_signals} signals`}
      >
        {pct}% <span className="text-text-primary font-normal text-2xl sm:text-3xl">win rate</span>
      </div>
      <div className="text-sm text-text-muted">
        last 90 days · {total_signals.toLocaleString()} signals
      </div>
    </div>
  );
}

/* ── Hero ─────────────────────────────────────────────────────────── */

function Hero({ trackRecord }: { trackRecord: ReturnType<typeof usePublicTrackRecord> }) {
  return (
    <section className="min-h-[calc(100vh-4rem)] flex items-center pt-24 pb-16 px-6">
      <div className="max-w-4xl mx-auto text-center">
        <p className="inline-flex items-center gap-2 text-xs uppercase tracking-wider text-accent font-mono mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse motion-reduce:animate-none" aria-hidden="true" />
          Live · V2 Pine + Triage pipeline
        </p>

        <h1 className="font-display text-4xl sm:text-5xl md:text-6xl font-bold leading-[1.1] text-text-primary mb-6">
          TradingView's signal noise,{" "}
          <span className="text-accent">filtered into conviction-rated trade alerts.</span>
        </h1>

        <p className="text-lg sm:text-xl text-text-muted max-w-2xl mx-auto mb-10 leading-relaxed">
          Every alert that fires gets a second pair of eyes from an LLM before it hits your Telegram. So you only look at the setups worth looking at.
        </p>

        <div className="mb-10 min-h-[5rem] flex items-center justify-center">
          <HeroStat state={trackRecord.state} onRefresh={trackRecord.refresh} />
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link
            to="/register"
            className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover px-8 py-4 rounded-lg text-white font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0"
          >
            Get started · free
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
          <Link
            to="/public/eod-report"
            className="text-accent hover:text-accent-hover text-sm font-medium inline-flex items-center gap-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0 rounded px-2 py-2"
          >
            See today's conviction picks <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ── What You Get ─────────────────────────────────────────────────── */

interface Deliverable {
  icon: React.ComponentType<{ className?: string; "aria-hidden"?: boolean }>;
  label: string;
  headline: string;
  body: string;
  status: "live" | "coming-soon";
  cta?: { label: string; href: string; external?: boolean };
}

const DELIVERABLES: Deliverable[] = [
  {
    icon: MessageCircle,
    label: "Telegram · live channel",
    status: "live",
    headline: "HIGH-conviction alerts in your pocket",
    body: "Every Pine-fired alert is rated by Claude Haiku against the SPY regime, your watchlist, and the setup's structural quality. Only the ones it grades HIGH or NORMAL hit the conviction channel — typically 3–10 per session, not 100.",
  },
  {
    icon: FileText,
    label: "Daily · 16:30 ET",
    status: "live",
    headline: "End-of-day debrief, every trading day",
    body: "Every alert that fired today, every triage verdict, every outcome where the bars resolved. Shareable URL — bookmark today's, send it to a coach.",
    cta: { label: "See today's recap", href: "/public/eod-report" },
  },
  {
    icon: Eye,
    label: "Beta · Pro tier",
    status: "coming-soon",
    headline: "Paste a chart, get a structured trade plan",
    body: "Bias, key levels, entry, stop, first target, runner, invalidation — under 15 seconds. Built on the same engine that grades your Telegram alerts.",
    cta: {
      label: "Join waitlist",
      href: "mailto:hello@tradingwithai.ai?subject=Chart%20Critique%20waitlist",
      external: true,
    },
  },
  {
    icon: BookOpen,
    label: "Beta · all tiers",
    status: "coming-soon",
    headline: "Textbook patterns + today's real matches",
    body: "Every pattern in the library shows you the setup, then shows you the live examples from this week on actual tickers. No more \"imagine a bull flag\" — we'll show you NVDA's, today, with the data.",
    cta: {
      label: "Join waitlist",
      href: "mailto:hello@tradingwithai.ai?subject=Pattern%20Education%20waitlist",
      external: true,
    },
  },
];

function StatusPill({ status }: { status: "live" | "coming-soon" }) {
  if (status === "live") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border bg-bullish/10 text-bullish-text border-bullish/20">
        <Check className="h-3 w-3" aria-hidden="true" />
        LIVE
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border bg-accent-subtle text-accent border-accent/30">
      <Clock className="h-3 w-3" aria-hidden="true" />
      COMING SOON
    </span>
  );
}

function DeliverableCard({ d }: { d: Deliverable }) {
  const Icon = d.icon;
  return (
    <article className="bg-surface-0 border border-border-subtle rounded-2xl p-8 flex flex-col gap-4 hover:border-border-default transition-colors">
      <div className="flex items-start justify-between gap-4">
        <div className="w-12 h-12 rounded-xl bg-accent-subtle text-accent flex items-center justify-center">
          <Icon className="h-6 w-6" aria-hidden={true} />
        </div>
        <StatusPill status={d.status} />
      </div>
      <p className="text-xs uppercase tracking-wider text-text-faint font-mono">{d.label}</p>
      <h3 className="text-xl font-display font-bold text-text-primary leading-snug">
        {d.headline}
      </h3>
      <p className="text-text-muted leading-relaxed flex-1">{d.body}</p>
      {d.cta && (
        <a
          href={d.cta.href}
          target={d.cta.external ? "_blank" : undefined}
          rel={d.cta.external ? "noreferrer" : undefined}
          className="mt-auto inline-flex items-center gap-1.5 text-accent hover:text-accent-hover text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0 rounded"
        >
          {d.cta.label}
          <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      )}
    </article>
  );
}

function WhatYouGet() {
  return (
    <section className="py-24 px-6 bg-surface-1 border-y border-border-subtle">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <p className="text-xs uppercase tracking-wider text-accent font-mono mb-3">
            What lands in your Telegram
          </p>
          <h2 className="text-3xl sm:text-4xl font-display font-bold text-text-primary mb-4">
            Four feeds. Built to be quiet.
          </h2>
          <p className="text-text-muted text-lg max-w-2xl mx-auto leading-relaxed">
            Most "AI trading" products fire on everything. This one fires when our Pine indicators see a real setup AND the LLM agrees it's worth your attention.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {DELIVERABLES.map((d) => (
            <DeliverableCard key={d.headline} d={d} />
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Proof Section ────────────────────────────────────────────────── */

function StatCard({
  value,
  label,
  ariaLabel,
}: {
  value: string;
  label: string;
  ariaLabel?: string;
}) {
  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl p-8 text-center">
      <div
        className="text-4xl sm:text-5xl font-display font-bold text-accent mb-2"
        aria-label={ariaLabel}
      >
        {value}
      </div>
      <div className="text-text-muted text-sm">{label}</div>
    </div>
  );
}

function ProofSection({ trackRecord }: { trackRecord: ReturnType<typeof usePublicTrackRecord> }) {
  const { state } = trackRecord;

  let winRateValue = "—";
  let winRateAria: string | undefined;
  let signalsValue = "—";
  let convictionTodayValue = "—";

  if (state.status === "ok") {
    if (state.data.total_signals > 0) {
      const pct = Math.round(state.data.win_rate * 100);
      winRateValue = `${pct}%`;
      winRateAria = `${pct} percent`;
    } else {
      winRateValue = "—";
      winRateAria = "no data yet";
    }
    signalsValue = state.data.total_signals.toLocaleString();
    // We don't have a today-only stat in the payload; show period total for now.
    // (Future: separate endpoint for "today's conviction picks count.")
    convictionTodayValue = state.data.wins.toLocaleString();
  } else if (state.status === "loading") {
    winRateValue = "…";
    signalsValue = "…";
    convictionTodayValue = "…";
  }
  // status === "error": all show "—"

  return (
    <section className="py-24 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <p className="text-xs uppercase tracking-wider text-accent font-mono mb-3">
            Live numbers, not testimonials
          </p>
          <h2 className="text-3xl sm:text-4xl font-display font-bold text-text-primary mb-4">
            Every alert we've ever sent is public.
          </h2>
          <p className="text-text-muted text-lg max-w-2xl mx-auto leading-relaxed">
            No anonymous "9,576 engineers love us" claims. Just the actual signals, the actual outcomes, dated.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 max-w-4xl mx-auto">
          <StatCard value={winRateValue} label="Win rate · last 90 days" ariaLabel={winRateAria} />
          <StatCard value={signalsValue} label="Signals scored · last 90 days" />
          <StatCard value={convictionTodayValue} label="Resolved as winners" />
        </div>

        <div className="text-center mt-12">
          <Link
            to="/track-record"
            className="inline-flex items-center gap-1.5 text-accent hover:text-accent-hover font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0 rounded px-2 py-2"
          >
            See every alert <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ── Final CTA ────────────────────────────────────────────────────── */

function FinalCTA() {
  return (
    <section className="py-24 px-6 bg-surface-1 border-t border-border-subtle">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl sm:text-4xl font-display font-bold text-text-primary mb-4">
          Stop reading every alert. Read the ones that matter.
        </h2>
        <p className="text-text-muted text-lg mb-8">
          Free to start. Bring your own Pine indicators. Cancel any time. We don't even ask for a credit card on signup.
        </p>
        <Link
          to="/register"
          className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover px-8 py-4 rounded-lg text-white font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface-0"
        >
          Get started · free
          <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}

/* ── Footer ───────────────────────────────────────────────────────── */

function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="py-12 px-6 border-t border-border-subtle">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div className="flex items-center gap-3 text-sm text-text-muted">
            <Crosshair className="h-4 w-4 text-accent" aria-hidden="true" />
            <span>
              <span className="text-text-primary font-medium">TradeCoPilot</span>
              {" · "}
              <span className="text-text-faint">tradingwithai.ai</span>
              {" · "}
              <span>© {year}</span>
            </span>
          </div>
          <nav className="flex gap-6 text-sm text-text-muted">
            <Link to="/learn" className="hover:text-text-primary transition-colors">Pattern Library</Link>
            <Link to="/track-record" className="hover:text-text-primary transition-colors">Track Record</Link>
            <Link to="/public/eod-report" className="hover:text-text-primary transition-colors">EOD Reports</Link>
            <Link to="/login" className="hover:text-text-primary transition-colors">Sign in</Link>
          </nav>
        </div>
        <p className="text-xs text-text-faint text-center mt-8 font-mono">
          Built on the V2 Pine + Triage stack. Spec 48 · 49 · 50.
        </p>
      </div>
    </footer>
  );
}

/* ── Page ─────────────────────────────────────────────────────────── */

export default function LandingPage() {
  const trackRecord = usePublicTrackRecord(90);

  return (
    <div className="min-h-screen bg-surface-0 text-text-primary">
      <LandingNav />
      <main>
        <Hero trackRecord={trackRecord} />
        <WhatYouGet />
        <ProofSection trackRecord={trackRecord} />
        <FinalCTA />
      </main>
      <Footer />
    </div>
  );
}
