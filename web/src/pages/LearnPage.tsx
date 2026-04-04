/** Signal Library — 8 pattern categories with live stats.
 *  Public page (no auth required). Accessible from landing page nav.
 */

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  TrendingUp, Zap, TrendingDown, Target, ShieldAlert,
  ArrowDownRight, BarChart3, BookOpen, ChevronRight, Crosshair,
} from "lucide-react";

const CATEGORY_ICONS: Record<string, typeof TrendingUp> = {
  entry_signals: TrendingUp,
  breakout_signals: Zap,
  short_signals: TrendingDown,
  exit_alerts: Target,
  resistance_warnings: ShieldAlert,
  support_warnings: ArrowDownRight,
  swing_trade: BarChart3,
  informational: BookOpen,
};

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: "bg-bullish/10 text-bullish-text border-bullish/20",
  intermediate: "bg-warning/10 text-warning-text border-warning/20",
  advanced: "bg-purple/10 text-purple-text border-purple/20",
};

interface CategorySummary {
  id: string;
  name: string;
  tagline: string;
  difficulty: string;
  pattern_count: number;
  stats: {
    signal_count: number;
    win_rate: number | null;
    win_count: number;
    loss_count: number;
  };
}

export default function LearnPage() {
  const [categories, setCategories] = useState<CategorySummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/v1/learn/categories")
      .then((r) => r.json())
      .then((data) => { setCategories(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-surface-0 text-text-primary">
      {/* Nav */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-surface-0/80 backdrop-blur-lg border-b border-border-subtle/50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-purple flex items-center justify-center">
              <Crosshair className="h-4 w-4 text-white" />
            </div>
            <span className="font-bold text-lg text-text-primary">
              <span className="text-accent">Trade</span>Signal
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <Link to="/login" className="text-sm text-text-muted hover:text-text-primary transition-colors">Sign in</Link>
            <Link to="/register" className="bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
              Get Started
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="pt-32 pb-12 px-6 text-center">
        <span className="inline-flex items-center gap-1.5 bg-accent/10 text-accent text-xs font-medium px-3 py-1 rounded-full border border-accent/20 mb-6">
          <BookOpen className="h-3 w-3" />
          Free for everyone
        </span>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight">
          Learn the patterns.<br />
          <span className="text-text-secondary">Then trade them live.</span>
        </h1>
        <p className="mt-4 text-text-muted max-w-xl mx-auto">
          Every TradeSignal alert is based on proven chart structure. Understand why each
          pattern works — then let the system find them for you in real time.
        </p>
      </section>

      {/* Category grid */}
      <section className="max-w-5xl mx-auto px-6 pb-24">
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="bg-surface-1 border border-border-subtle rounded-xl h-44 animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {categories.map((cat) => {
              const Icon = CATEGORY_ICONS[cat.id] || BookOpen;
              const diffClass = DIFFICULTY_COLORS[cat.difficulty] || DIFFICULTY_COLORS.beginner;

              return (
                <Link
                  key={cat.id}
                  to={`/learn/${cat.id}`}
                  className="group bg-surface-1 border border-border-subtle rounded-xl p-6 hover:border-accent/30 transition-all"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center group-hover:shadow-glow-accent transition-shadow">
                        <Icon className="h-5 w-5 text-accent" />
                      </div>
                      <div>
                        <h3 className="text-base font-bold text-text-primary">{cat.name}</h3>
                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${diffClass}`}>
                          {cat.difficulty}
                        </span>
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-text-faint group-hover:text-accent transition-colors" />
                  </div>

                  <p className="text-sm text-text-secondary mb-4">{cat.tagline}</p>

                  {/* Stats row */}
                  <div className="flex items-center gap-4 text-xs">
                    <span className="text-text-faint">
                      <span className="font-mono text-text-primary">{cat.pattern_count}</span> patterns
                    </span>
                    {cat.stats.signal_count > 0 && (
                      <span className="text-text-faint">
                        <span className="font-mono text-text-primary">{cat.stats.signal_count}</span> signals (90d)
                      </span>
                    )}
                    {cat.stats.win_rate != null && (
                      <span className="text-text-faint">
                        <span className="font-mono text-bullish-text">{cat.stats.win_rate}%</span> win rate
                      </span>
                    )}
                    {cat.stats.signal_count === 0 && (
                      <span className="text-text-faint italic">Building track record</span>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}

        {/* Bottom CTA */}
        <div className="mt-16 text-center">
          <p className="text-text-muted mb-4">Ready to get these patterns delivered to your phone?</p>
          <Link
            to="/register"
            className="inline-flex items-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold text-sm px-6 py-3 rounded-xl transition-all shadow-[0_0_20px_rgba(34,197,94,0.2)]"
          >
            Start Free Trial
            <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
