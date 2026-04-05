/** Pattern Detail — deep-dive into a specific alert type.
 *  Public (no auth). SEO-targetable.
 */

import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  ChevronLeft, ChevronRight, BookOpen,
  Lightbulb, AlertTriangle, Eye, Shield, Check, X,
} from "lucide-react";

interface PatternDetail {
  id: string;
  name: string;
  category: string;
  direction: string;
  difficulty: string;
  tagline: string;
  what_it_is: string;
  how_to_identify: string[];
  why_it_works: string;
  when_it_fails: string;
  common_mistakes: string[];
  pro_tips: string[];
  stats: {
    signal_count: number;
    win_rate: number | null;
    win_count: number;
    loss_count: number;
  };
}

const DIFFICULTY_COLORS: Record<string, string> = {
  beginner: "bg-bullish/10 text-bullish-text border-bullish/20",
  intermediate: "bg-warning/10 text-warning-text border-warning/20",
  advanced: "bg-purple/10 text-purple-text border-purple/20",
};

const DIR_COLORS: Record<string, string> = {
  BUY: "bg-bullish/10 text-bullish-text border-bullish/20",
  SHORT: "bg-bearish/10 text-bearish-text border-bearish/20",
};

export default function PatternDetailPage() {
  const { patternId } = useParams<{ patternId: string }>();
  const [data, setData] = useState<PatternDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!patternId) return;
    setLoading(true);
    fetch(`/api/v1/learn/patterns/${patternId}`)
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [patternId]);

  if (loading) {
    return (
      <div className="min-h-screen bg-surface-0 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-surface-0 flex flex-col items-center justify-center text-text-muted gap-3">
        <p className="text-lg">Pattern not found</p>
        <Link to="/learn" className="text-sm text-accent hover:underline">Back to Signal Library</Link>
      </div>
    );
  }

  const diffClass = DIFFICULTY_COLORS[data.difficulty] || DIFFICULTY_COLORS.beginner;
  const dirClass = DIR_COLORS[data.direction] || "";

  return (
    <div className="min-h-screen bg-surface-0 text-text-primary">
      <nav className="fixed top-0 left-0 right-0 z-50 bg-surface-0/80 backdrop-blur-lg border-b border-border-subtle/50">
        <div className="max-w-4xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link to="/learn" className="flex items-center gap-2 text-sm text-text-muted hover:text-text-primary transition-colors">
            <ChevronLeft className="h-4 w-4" />
            Signal Library
          </Link>
          <Link to="/register" className="bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
            Get Alerts Live
          </Link>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 pt-28 pb-24">
        {/* Header */}
        <div className="mb-10">
          <div className="flex items-center gap-2 mb-3">
            <span className={`text-[10px] font-medium px-2 py-0.5 rounded border ${diffClass}`}>{data.difficulty}</span>
            <span className={`text-[10px] font-medium px-2 py-0.5 rounded border ${dirClass}`}>{data.direction}</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">{data.name}</h1>
          <p className="mt-2 text-lg text-text-secondary">{data.tagline}</p>

          {/* Stats */}
          <div className="mt-6 flex flex-wrap gap-6">
            {data.stats.signal_count > 0 && (
              <div className="flex flex-col">
                <span className="font-mono text-2xl font-bold text-text-primary">{data.stats.signal_count}</span>
                <span className="text-xs text-text-faint">Signals (90 days)</span>
              </div>
            )}
            {data.stats.win_rate != null && (
              <div className="flex flex-col">
                <span className="font-mono text-2xl font-bold text-bullish-text">{data.stats.win_rate}%</span>
                <span className="text-xs text-text-faint">Win rate</span>
              </div>
            )}
            {data.stats.win_count + data.stats.loss_count > 0 && (
              <div className="flex flex-col">
                <span className="font-mono text-2xl font-bold text-text-primary">
                  {data.stats.win_count}W / {data.stats.loss_count}L
                </span>
                <span className="text-xs text-text-faint">Outcomes</span>
              </div>
            )}
          </div>
        </div>

        <div className="space-y-10">
          {/* What it is */}
          <section>
            <h2 className="text-lg font-bold flex items-center gap-2 mb-3">
              <BookOpen className="h-5 w-5 text-accent" />
              What is this pattern?
            </h2>
            <p className="text-text-secondary leading-relaxed">{data.what_it_is}</p>
          </section>

          {/* How to identify */}
          <section>
            <h2 className="text-lg font-bold flex items-center gap-2 mb-3">
              <Eye className="h-5 w-5 text-accent" />
              How to identify it
            </h2>
            <div className="space-y-2.5">
              {data.how_to_identify.map((item, i) => (
                <div key={i} className="flex items-start gap-3 bg-surface-1 border border-border-subtle rounded-lg p-3">
                  <span className="w-6 h-6 rounded-full bg-accent/10 text-accent flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">{i + 1}</span>
                  <p className="text-sm text-text-secondary">{item}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Why it works */}
          <section>
            <h2 className="text-lg font-bold flex items-center gap-2 mb-3">
              <Lightbulb className="h-5 w-5 text-warning" />
              Why it works
            </h2>
            <p className="text-text-secondary leading-relaxed">{data.why_it_works}</p>
          </section>

          {/* When it fails */}
          <section>
            <h2 className="text-lg font-bold flex items-center gap-2 mb-3">
              <AlertTriangle className="h-5 w-5 text-bearish" />
              When it fails
            </h2>
            <div className="bg-bearish/5 border border-bearish/10 rounded-lg p-4">
              <p className="text-text-secondary leading-relaxed">{data.when_it_fails}</p>
            </div>
          </section>

          {/* Common mistakes */}
          <section>
            <h2 className="text-lg font-bold flex items-center gap-2 mb-3">
              <X className="h-5 w-5 text-bearish" />
              Common mistakes
            </h2>
            <div className="space-y-2">
              {data.common_mistakes.map((m, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <X className="h-4 w-4 text-bearish-text shrink-0 mt-0.5" />
                  <p className="text-sm text-text-secondary">{m}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Pro tips */}
          <section>
            <h2 className="text-lg font-bold flex items-center gap-2 mb-3">
              <Shield className="h-5 w-5 text-bullish" />
              Pro tips
            </h2>
            <div className="space-y-2">
              {data.pro_tips.map((tip, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <Check className="h-4 w-4 text-bullish-text shrink-0 mt-0.5" />
                  <p className="text-sm text-text-secondary">{tip}</p>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* CTA */}
        <div className="mt-16 bg-surface-1 border border-border-subtle rounded-xl p-8 text-center">
          <h2 className="text-xl font-bold mb-2">
            Want {data.name.toLowerCase()} alerts on your phone?
          </h2>
          <p className="text-text-muted text-sm mb-6">
            TradeSignal detects this pattern in real time and sends you a complete trade plan
            with entry, stop, targets, and AI analysis.
          </p>
          <Link
            to="/register"
            className="inline-flex items-center gap-2 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold text-sm px-6 py-3 rounded-xl transition-all shadow-[0_0_20px_rgba(34,197,94,0.2)]"
          >
            Start Free Trial
            <ChevronRight className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </div>
  );
}
