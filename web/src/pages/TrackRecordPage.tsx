/** Public AI Auto-Pilot Track Record (Spec 35 Phase 3)
 *
 *  No login required. The marketing asset — anyone can audit every
 *  simulated trade the AI has fired, with P&L + equity curve.
 */

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  TrendingUp, TrendingDown, Activity, Brain, Filter,
} from "lucide-react";

const API = "/api/v1/auto-trades";

interface Stats {
  total_trades: number;
  open_trades: number;
  closed_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl_dollars: number;
  total_pnl_percent: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  best_trade_pct: number | null;
  worst_trade_pct: number | null;
  total_notional_invested: number;
}

interface Trade {
  id: number;
  symbol: string;
  direction: string;
  setup_type: string | null;
  conviction: string | null;
  entry_price: number;
  stop_price: number | null;
  target_1_price: number | null;
  target_2_price: number | null;
  shares: number;
  status: string;
  exit_price: number | null;
  exit_reason: string | null;
  pnl_dollars: number | null;
  pnl_percent: number | null;
  r_multiple: number | null;
  opened_at: string;
  closed_at: string | null;
  session_date: string;
  market: string | null;
  alert_id: number | null;
}

interface EquityPoint {
  date: string;
  cumulative_pnl_pct: number;
  cumulative_pnl_dollars: number;
  trades_closed: number;
}

interface PatternRow {
  setup_type: string | null;
  trades: number;
  wins: number;
  win_rate: number;
  avg_pnl_pct: number;
}

function usePublicAutoTrades(days: number) {
  const [stats, setStats] = useState<Stats | null>(null);
  const [recent, setRecent] = useState<Trade[]>([]);
  const [openPositions, setOpenPositions] = useState<Trade[]>([]);
  const [equity, setEquity] = useState<EquityPoint[]>([]);
  const [patterns, setPatterns] = useState<PatternRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetch(`${API}/stats?days=${days}`).then((r) => r.json()),
      fetch(`${API}/recent?limit=100`).then((r) => r.json()),
      fetch(`${API}/open`).then((r) => r.json()),
      fetch(`${API}/equity-curve?days=${days}`).then((r) => r.json()),
      fetch(`${API}/by-pattern?days=${days}`).then((r) => r.json()),
    ])
      .then(([s, r, o, e, p]) => {
        setStats(s);
        setRecent(r);
        setOpenPositions(o);
        setEquity(e);
        setPatterns(p);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load track record");
        setLoading(false);
      });
  }, [days]);

  return { stats, recent, openPositions, equity, patterns, loading, error };
}

function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function StatCard({ label, value, sub, color }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl p-4 md:p-5">
      <p className="text-[10px] uppercase tracking-widest text-text-faint mb-1">{label}</p>
      <p className={`font-mono text-2xl md:text-3xl font-bold ${color || "text-text-primary"}`}>
        {value}
      </p>
      {sub && <p className="text-[10px] text-text-faint mt-1">{sub}</p>}
    </div>
  );
}

/* ── Mini sparkline chart for equity curve ──────────────────────── */

function EquitySparkline({ points }: { points: EquityPoint[] }) {
  if (points.length < 2) {
    return (
      <div className="h-40 flex items-center justify-center text-xs text-text-faint">
        {points.length === 0 ? "No closed trades yet." : "Need more data for a curve."}
      </div>
    );
  }

  const values = points.map((p) => p.cumulative_pnl_pct);
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const range = max - min || 1;
  const w = 800;
  const h = 160;
  const stepX = w / (points.length - 1);

  const path = points
    .map((p, i) => {
      const x = i * stepX;
      const y = h - ((p.cumulative_pnl_pct - min) / range) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  // Zero-axis
  const zeroY = h - ((0 - min) / range) * h;
  const finalPct = values[values.length - 1];
  const color = finalPct >= 0 ? "#22c55e" : "#ef4444";

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-40">
        <line
          x1={0} y1={zeroY} x2={w} y2={zeroY}
          stroke="rgba(255,255,255,0.08)" strokeDasharray="4 4"
        />
        <path d={path} fill="none" stroke={color} strokeWidth={2} />
        <path
          d={`${path} L${w},${h} L0,${h} Z`}
          fill={color}
          fillOpacity={0.08}
        />
      </svg>
    </div>
  );
}

/* ── Main page ─────────────────────────────────────────────────── */

export default function TrackRecordPage() {
  const [days, setDays] = useState(30);
  const { stats, recent, openPositions, equity, patterns, loading, error } =
    usePublicAutoTrades(days);

  const netPct = stats?.total_pnl_percent ?? 0;
  const netPctColor = netPct >= 0 ? "text-bullish-text" : "text-bearish-text";

  const filtered = useMemo(() => recent.slice(0, 50), [recent]);

  return (
    <div className="min-h-screen bg-surface-0 text-text-primary">
      {/* Header */}
      <header className="border-b border-border-subtle/50 bg-surface-0/80 backdrop-blur-lg sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-5 py-3 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-accent" />
            <span className="font-bold text-text-primary">
              <span className="text-accent">Trade</span>CoPilot
            </span>
          </Link>
          <Link to="/register" className="bg-bullish hover:bg-bullish/90 text-surface-0 text-xs font-bold px-4 py-2 rounded-lg transition-colors">
            Start Free Trial
          </Link>
        </div>
      </header>

      <div className="max-w-6xl mx-auto px-5 py-8 space-y-6">
        {/* Title */}
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-text-primary">AI Auto-Pilot Track Record</h1>
          <p className="text-sm text-text-muted mt-2 max-w-2xl">
            Every signal the AI fires auto-opens a simulated paper trade. The AI's own
            stops and targets manage the exit — no human intervention. Every win and
            every loss is shown below.
          </p>
          <p className="text-[10px] text-text-faint mt-3 italic">
            Simulated trades only. $10,000 fixed notional per signal, no fees, no slippage.
            Past performance does not guarantee future results. Educational analysis, not financial advice.
          </p>
        </div>

        {/* Time range */}
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-text-faint" />
          <span className="text-xs text-text-faint">Window:</span>
          {[7, 30, 90, 365].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1 text-[11px] font-medium rounded-md transition-colors ${
                days === d
                  ? "bg-accent/15 text-accent border border-accent/30"
                  : "bg-surface-2 text-text-muted hover:bg-surface-3"
              }`}
            >
              {d === 365 ? "1 year" : `${d} days`}
            </button>
          ))}
        </div>

        {error && <p className="text-xs text-bearish-text">{error}</p>}
        {loading && <p className="text-xs text-text-faint">Loading…</p>}

        {stats && (
          <>
            {/* Hero stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard
                label="Net P&L"
                value={fmtPct(stats.total_pnl_percent)}
                sub={`$${fmt(stats.total_pnl_dollars)} cumulative`}
                color={netPctColor}
              />
              <StatCard
                label="Win rate"
                value={`${fmt(stats.win_rate, 1)}%`}
                sub={`${stats.wins}W / ${stats.losses}L`}
              />
              <StatCard
                label="Total trades"
                value={`${stats.total_trades}`}
                sub={`${stats.closed_trades} closed · ${stats.open_trades} open`}
              />
              <StatCard
                label="Best / worst"
                value={`${fmtPct(stats.best_trade_pct)} / ${fmtPct(stats.worst_trade_pct)}`}
                sub="Single-trade extremes"
              />
            </div>

            {/* Equity curve */}
            <div className="bg-surface-1 border border-border-subtle rounded-xl p-5">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-sm font-bold flex items-center gap-2">
                  <Activity className="h-4 w-4 text-accent" />
                  Equity Curve (cumulative P&L %)
                </h2>
                <span className="text-[10px] text-text-faint">
                  {equity.length} closing days
                </span>
              </div>
              <EquitySparkline points={equity} />
            </div>

            {/* Currently open */}
            {openPositions.length > 0 && (
              <div className="bg-surface-1 border border-accent/20 rounded-xl p-5">
                <h2 className="text-sm font-bold mb-3 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                  Open Positions <span className="text-text-faint font-normal text-xs">({openPositions.length})</span>
                </h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="text-text-faint">
                      <tr className="border-b border-border-subtle/50">
                        <th className="text-left py-2">Symbol</th>
                        <th className="text-left py-2">Direction</th>
                        <th className="text-left py-2">Setup</th>
                        <th className="text-right py-2">Entry</th>
                        <th className="text-right py-2">Stop</th>
                        <th className="text-right py-2">T1</th>
                        <th className="text-right py-2">Opened</th>
                      </tr>
                    </thead>
                    <tbody>
                      {openPositions.map((t) => (
                        <tr key={t.id} className="border-b border-border-subtle/20">
                          <td className="py-2 font-bold">{t.symbol}</td>
                          <td className="py-2">
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                              t.direction === "BUY"
                                ? "bg-bullish/10 text-bullish-text"
                                : "bg-bearish/10 text-bearish-text"
                            }`}>{t.direction === "BUY" ? "LONG" : "SHORT"}</span>
                          </td>
                          <td className="py-2 text-text-muted">{t.setup_type || "—"}</td>
                          <td className="py-2 text-right font-mono">${fmt(t.entry_price)}</td>
                          <td className="py-2 text-right font-mono text-bearish-text">
                            {t.stop_price ? `$${fmt(t.stop_price)}` : "—"}
                          </td>
                          <td className="py-2 text-right font-mono text-bullish-text">
                            {t.target_1_price ? `$${fmt(t.target_1_price)}` : "—"}
                          </td>
                          <td className="py-2 text-right text-text-faint text-[10px]">
                            {new Date(t.opened_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* By pattern */}
            {patterns.length > 0 && (
              <div className="bg-surface-1 border border-border-subtle rounded-xl p-5">
                <h2 className="text-sm font-bold mb-3">Performance by setup</h2>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="text-text-faint">
                      <tr className="border-b border-border-subtle/50">
                        <th className="text-left py-2">Setup</th>
                        <th className="text-right py-2">Trades</th>
                        <th className="text-right py-2">Win rate</th>
                        <th className="text-right py-2">Avg P&L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {patterns.map((p, i) => (
                        <tr key={i} className="border-b border-border-subtle/20">
                          <td className="py-2 text-text-primary">{p.setup_type || "Unknown"}</td>
                          <td className="py-2 text-right font-mono">{p.trades}</td>
                          <td className="py-2 text-right font-mono">
                            <span className={p.win_rate >= 50 ? "text-bullish-text" : "text-bearish-text"}>
                              {fmt(p.win_rate, 1)}%
                            </span>
                          </td>
                          <td className="py-2 text-right font-mono">
                            <span className={p.avg_pnl_pct >= 0 ? "text-bullish-text" : "text-bearish-text"}>
                              {fmtPct(p.avg_pnl_pct)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Recent closed trades */}
            <div className="bg-surface-1 border border-border-subtle rounded-xl p-5">
              <h2 className="text-sm font-bold mb-3">Recent closed trades ({filtered.length})</h2>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="text-text-faint">
                    <tr className="border-b border-border-subtle/50">
                      <th className="text-left py-2">Date</th>
                      <th className="text-left py-2">Symbol</th>
                      <th className="text-left py-2">Dir</th>
                      <th className="text-left py-2">Setup</th>
                      <th className="text-right py-2">Entry</th>
                      <th className="text-right py-2">Exit</th>
                      <th className="text-right py-2">P&L %</th>
                      <th className="text-right py-2">R</th>
                      <th className="text-right py-2">Replay</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((t) => {
                      const pnl = t.pnl_percent ?? 0;
                      const win = pnl > 0;
                      return (
                        <tr key={t.id} className="border-b border-border-subtle/20 hover:bg-surface-2/30">
                          <td className="py-2 text-text-faint text-[10px]">{t.session_date}</td>
                          <td className="py-2 font-bold">{t.symbol}</td>
                          <td className="py-2">
                            {t.direction === "BUY" ? (
                              <TrendingUp className="h-3 w-3 text-bullish-text" />
                            ) : (
                              <TrendingDown className="h-3 w-3 text-bearish-text" />
                            )}
                          </td>
                          <td className="py-2 text-text-muted truncate max-w-[160px]">{t.setup_type || "—"}</td>
                          <td className="py-2 text-right font-mono">${fmt(t.entry_price)}</td>
                          <td className="py-2 text-right font-mono">${fmt(t.exit_price)}</td>
                          <td className={`py-2 text-right font-mono font-bold ${win ? "text-bullish-text" : "text-bearish-text"}`}>
                            {fmtPct(t.pnl_percent)}
                          </td>
                          <td className={`py-2 text-right font-mono ${(t.r_multiple ?? 0) >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
                            {t.r_multiple != null ? `${t.r_multiple.toFixed(1)}R` : "—"}
                          </td>
                          <td className="py-2 text-right">
                            {t.alert_id ? (
                              <Link
                                to={`/replay/${t.alert_id}`}
                                className="text-[10px] text-accent hover:text-accent-hover"
                              >
                                ▶ Play
                              </Link>
                            ) : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* CTA */}
            <div className="bg-surface-1 border border-accent/20 rounded-xl p-6 text-center">
              <h3 className="text-lg font-bold text-text-primary">Want the AI watching your charts?</h3>
              <p className="text-xs text-text-muted mt-2 max-w-md mx-auto">
                The same AI fires actionable signals to your Telegram. Free forever with limits — 3-day Pro trial included.
              </p>
              <Link
                to="/register"
                className="inline-flex items-center gap-2 mt-4 bg-bullish hover:bg-bullish/90 text-surface-0 font-bold text-sm px-6 py-3 rounded-xl transition-colors"
              >
                Start Free Trial
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
