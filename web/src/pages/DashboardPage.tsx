import { useState } from "react";
import { Link } from "react-router-dom";
import { useAlertsToday, useSessionSummary, useAckAlert, useOpenTrades, useIntraday } from "../api/hooks";
import { SkeletonGrid } from "../components/LoadingSkeleton";
import { useAlertStream } from "../hooks/useAlertStream";
import { useFeatureGate } from "../hooks/useFeatureGate";
import { Crosshair, BarChart3, ArrowLeftRight, ChevronDown, ChevronUp, type LucideIcon } from "lucide-react";
import Badge from "../components/ui/Badge";
import Card from "../components/ui/Card";
import WatchlistBar from "../components/WatchlistBar";

function StatCard({ label, value, color }: { label: string; value: number | string; color?: string }) {
  return (
    <Card padding="md">
      <p className="text-xs text-text-muted">{label}</p>
      <p className={`mt-1 font-mono text-2xl font-bold ${color || "text-text-primary"}`}>{value}</p>
    </Card>
  );
}

interface QuickLink {
  to: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

const QUICK_LINKS: QuickLink[] = [
  { to: "/trading", label: "Trading", description: "Charts, signals & trade plans", icon: Crosshair },
  { to: "/trades", label: "Trades", description: "P&L and trade history", icon: ArrowLeftRight },
];

/** Compute live P&L for a single open trade given current price. */
function livePnl(trade: { direction: string; entry_price: number; shares: number }, currentPrice: number): number {
  if (trade.direction === "BUY") return (currentPrice - trade.entry_price) * trade.shares;
  return (trade.entry_price - currentPrice) * trade.shares;
}

/** Expandable alert row with detail panel. */
function AlertRow({ a, onAck }: { a: any; onAck: (id: number, action: "took" | "skipped") => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="overflow-hidden rounded-lg border border-border-subtle bg-surface-2 shadow-card">
      {/* Collapsed row */}
      <div className="flex items-center justify-between px-4 py-3">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex flex-1 items-center gap-3 text-left"
        >
          <Badge variant={a.direction === "BUY" ? "bullish" : a.direction === "SELL" ? "bearish" : "warning"}>
            {a.direction}
          </Badge>
          <span className="font-medium text-text-primary">{a.symbol}</span>
          <span className="hidden text-sm text-text-muted sm:inline">{a.alert_type.replace(/_/g, " ")}</span>
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5 text-text-faint" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-text-faint" />
          )}
        </button>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="font-mono text-sm font-medium text-text-primary">${a.price.toFixed(2)}</p>
            {a.entry && (
              <p className="font-mono text-xs text-text-muted">
                E: ${a.entry.toFixed(2)} S: ${a.stop?.toFixed(2)} T: ${a.target_1?.toFixed(2)}
              </p>
            )}
          </div>
          {/* ACK buttons */}
          {!a.user_action && (
            <div className="flex gap-2">
              <button
                onClick={() => onAck(a.id, "took")}
                className="rounded-lg bg-bullish-muted px-3 py-2 text-sm font-medium text-bullish-text hover:bg-bullish/20 active:scale-95"
              >
                Took
              </button>
              <button
                onClick={() => onAck(a.id, "skipped")}
                className="rounded-lg bg-surface-4 px-3 py-2 text-sm font-medium text-text-muted hover:bg-surface-3 active:scale-95"
              >
                Skip
              </button>
            </div>
          )}
          {a.user_action && (
            <Badge variant={a.user_action === "took" ? "bullish" : "neutral"}>
              {a.user_action}
            </Badge>
          )}
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-border-subtle bg-surface-3/30 px-4 py-3 space-y-2">
          <p className="text-sm text-text-muted sm:hidden">{a.alert_type.replace(/_/g, " ")}</p>
          {a.message && (
            <p className="text-sm text-text-secondary leading-relaxed">{a.message}</p>
          )}
          {a.entry != null && (
            <div className="flex flex-wrap gap-4 text-xs">
              <span className="text-text-muted">
                Entry: <span className="font-mono font-medium text-bullish-text">${a.entry.toFixed(2)}</span>
              </span>
              {a.stop != null && (
                <span className="text-text-muted">
                  Stop: <span className="font-mono font-medium text-bearish-text">${a.stop.toFixed(2)}</span>
                </span>
              )}
              {a.target_1 != null && (
                <span className="text-text-muted">
                  T1: <span className="font-mono font-medium text-info-text">${a.target_1.toFixed(2)}</span>
                </span>
              )}
              {a.target_2 != null && (
                <span className="text-text-muted">
                  T2: <span className="font-mono font-medium text-info-text">${a.target_2.toFixed(2)}</span>
                </span>
              )}
              {a.entry > 0 && a.stop > 0 && a.target_1 > 0 && (
                <span className="text-text-muted">
                  R:R: <span className="font-mono font-medium text-text-primary">
                    {((a.target_1 - a.entry) / (a.entry - a.stop)).toFixed(1)}:1
                  </span>
                </span>
              )}
            </div>
          )}
          <p className="text-xs text-text-faint">{a.confidence} confidence · {a.created_at}</p>
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const { data: summary } = useSessionSummary();
  const { data: alerts } = useAlertsToday();
  const { data: openTrades } = useOpenTrades();
  const { isPro } = useFeatureGate();
  const { connected, lastAlert } = useAlertStream();
  const ackAlert = useAckAlert();

  // Pick first open trade's symbol for live price lookup
  const firstSymbol = openTrades?.[0]?.symbol ?? "";
  const { data: intradayBars } = useIntraday(firstSymbol);
  const lastPrice = intradayBars?.length ? intradayBars[intradayBars.length - 1].close : null;

  // Compute total unrealized P&L
  const totalUnrealized = openTrades && lastPrice != null
    ? openTrades
        .filter((t) => t.symbol === firstSymbol)
        .reduce((sum, t) => sum + livePnl(t, lastPrice), 0)
    : null;

  function handleAck(id: number, action: "took" | "skipped") {
    ackAlert.mutate({ id, action });
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-bold">Dashboard</h1>
        {isPro && (
          <Badge variant={connected ? "bullish" : "neutral"}>
            {connected ? (
              <>
                <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-bullish" />
                LIVE
              </>
            ) : (
              "OFFLINE"
            )}
          </Badge>
        )}
      </div>

      {/* Watchlist */}
      <Card padding="sm">
        <div className="mb-2 flex items-center justify-between">
          <p className="font-display text-xs font-semibold text-text-muted">WATCHLIST</p>
          <div className="flex items-center gap-2">
            <Link to="/settings" className="text-xs text-text-muted hover:text-text-secondary">
              Manage
            </Link>
            <Link to="/trading" className="text-xs text-accent hover:text-accent-hover">
              Scan all
            </Link>
          </div>
        </div>
        <WatchlistBar compact />
      </Card>

      {/* Quick Links */}
      <div className="grid grid-cols-3 gap-3">
        {QUICK_LINKS.map((link) => {
          const Icon = link.icon;
          return (
            <Link
              key={link.to}
              to={link.to}
              className="group rounded-lg border border-border-subtle bg-surface-2 p-4 shadow-card transition-all hover:border-border-default hover:bg-surface-3 hover:shadow-elevated"
            >
              <Icon className="h-5 w-5 text-accent" />
              <p className="mt-2 text-sm font-medium text-text-primary">{link.label}</p>
              <p className="text-xs text-text-muted">{link.description}</p>
            </Link>
          );
        })}
      </div>

      {/* Session Stats */}
      {!summary && <SkeletonGrid count={7} />}
      {summary && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          <StatCard label="Signals" value={summary.total_alerts} />
          <StatCard label="BUY" value={summary.buy_alerts} color="text-bullish-text" />
          <StatCard label="SELL" value={summary.sell_alerts} color="text-bearish-text" />
          <StatCard label="T1 Hits" value={summary.target_1_hits} color="text-bullish-text" />
          <StatCard label="T2 Hits" value={summary.target_2_hits} color="text-bullish-text" />
          <StatCard label="Stopped" value={summary.stopped_out} color="text-bearish-text" />
          <StatCard label="Active" value={summary.active_entries} color="text-info-text" />
        </div>
      )}

      {/* Live P&L (unrealized) */}
      {openTrades && openTrades.length > 0 && totalUnrealized != null && (
        <Card title="Live P&L (Unrealized)" padding="md">
          <p className={`font-mono text-2xl font-bold ${totalUnrealized >= 0 ? "text-bullish-text" : "text-bearish-text"}`}>
            ${totalUnrealized.toFixed(2)}
          </p>
          <p className="text-xs text-text-muted">{openTrades.length} open position(s)</p>
        </Card>
      )}

      {/* Session Summary */}
      {summary && summary.total_alerts > 0 && (
        <Card title="Session Summary" padding="md">
          <div className="flex gap-4 text-sm">
            <span className="text-text-muted">
              Win rate:{" "}
              <span className="font-mono text-text-primary">
                {summary.target_1_hits + summary.target_2_hits > 0
                  ? (
                      ((summary.target_1_hits + summary.target_2_hits) /
                        Math.max(summary.target_1_hits + summary.target_2_hits + summary.stopped_out, 1)) *
                      100
                    ).toFixed(0)
                  : 0}
                %
              </span>
            </span>
            <span className="text-text-muted">
              Targets: <span className="font-mono text-bullish-text">{summary.target_1_hits + summary.target_2_hits}</span>
            </span>
            <span className="text-text-muted">
              Stops: <span className="font-mono text-bearish-text">{summary.stopped_out}</span>
            </span>
          </div>
        </Card>
      )}

      {/* Latest SSE alert toast */}
      {lastAlert && (
        <div className="rounded-lg border border-accent-muted bg-accent-subtle p-3 shadow-glow-accent">
          <p className="text-xs font-semibold text-info-text">NEW ALERT</p>
          <p className="text-sm font-medium text-text-primary">
            {lastAlert.direction} {lastAlert.symbol} — {lastAlert.alert_type} @{" "}
            <span className="font-mono">${lastAlert.price.toFixed(2)}</span>
          </p>
          <p className="text-xs text-text-muted">{lastAlert.message}</p>
        </div>
      )}

      {/* Alert Feed with expandable details */}
      <div>
        <h2 className="mb-3 font-display text-sm font-semibold text-text-secondary">Today's Alerts</h2>
        {!alerts || alerts.length === 0 ? (
          <p className="text-sm text-text-faint">No alerts fired today</p>
        ) : (
          <div className="space-y-2">
            {alerts.map((a) => (
              <AlertRow key={a.id} a={a} onAck={handleAck} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
