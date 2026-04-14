/** Admin Dashboard — user management + platform stats.
 *  Only accessible to admin users.
 */

import { useEffect, useState } from "react";
import { api } from "../api/client";
import {
  Users, Send, BarChart3, RefreshCw,
  Crown, Search, ChevronDown, ChevronRight,
} from "lucide-react";

interface UserInfo {
  id: number;
  email: string;
  display_name: string;
  created_at: string;
  tier: string;
  status: string;
  trial_days_left: number;
  trial_expired: boolean;
  telegram_linked: boolean;
  watchlist_count: number;
  alert_count: number;
}

interface PlatformStats {
  total_users: number;
  pro_users: number;
  premium_users: number;
  free_users: number;
  trial_users: number;
  telegram_linked: number;
  total_alerts: number;
  alerts_today: number;
  signups_7d: number;
  signups_30d: number;
  monthly_revenue_estimate: number;
}

interface AttributionStats {
  days: number;
  total_signups: number;
  by_source: { source: string; count: number }[];
  by_medium: { medium: string; count: number }[];
  by_campaign: { campaign: string; count: number }[];
}

interface AIAlertRow {
  id: number;
  symbol: string;
  alert_type: string;
  direction: string;
  entry: number | null;
  stop: number | null;
  target_1: number | null;
  target_2: number | null;
  confidence: string | null;
  message: string;
  fired_at: string | null;
  user_copies: number;
}

interface UserDebug {
  user: { id: number; email: string; telegram_enabled: boolean; telegram_chat_id: string | null };
  subscription: { tier: string; status: string; trial_ends_at: string | null } | null;
  resolved_tier: string;
  trial_active: boolean;
  trial_days_left: number;
  limits: {
    ai_scan_alerts_per_day: number | null;
    visible_alerts: number | null;
    telegram_alerts: boolean;
  };
  today_stats: {
    ai_actionable_alerts_in_db: number;
    ai_wait_alerts_in_db: number;
    rule_alerts_in_db: number;
    ai_telegram_delivered_counter: number | null;
    limit_reached_notified: boolean | null;
  };
}

function StatCard({ label, value, icon, color }: {
  label: string; value: string | number; icon: React.ReactNode; color?: string;
}) {
  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl p-5">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-[10px] text-text-faint uppercase tracking-wider font-medium">{label}</span>
      </div>
      <span className={`font-mono text-2xl font-bold ${color || "text-text-primary"}`}>{value}</span>
    </div>
  );
}

function TierBadge({ tier, trialDays, trialExpired }: { tier: string; trialDays?: number; trialExpired?: boolean }) {
  const styles: Record<string, string> = {
    pro: "bg-accent/10 text-accent border-accent/20",
    premium: "bg-purple/10 text-purple-text border-purple/20",
    admin: "bg-warning/10 text-warning-text border-warning/20",
    trial: "bg-bullish/10 text-bullish-text border-bullish/20",
    free: "bg-surface-3 text-text-faint border-border-subtle",
    none: "bg-surface-3 text-text-faint border-border-subtle",
  };
  const label = tier === "trial" && trialDays ? `TRIAL ${trialDays}d` : tier.toUpperCase();
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${styles[tier] || styles.free}`}>
        {label}
      </span>
      {trialExpired && <span className="text-[9px] text-bearish-text">expired</span>}
    </span>
  );
}

export default function AdminPage() {
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [attribution, setAttribution] = useState<AttributionStats | null>(null);
  const [debugEmail, setDebugEmail] = useState("");
  const [debugData, setDebugData] = useState<UserDebug | null>(null);
  const [debugError, setDebugError] = useState("");
  const [debugLoading, setDebugLoading] = useState(false);

  function runUserDebug() {
    if (!debugEmail.trim()) return;
    setDebugLoading(true);
    setDebugError("");
    setDebugData(null);
    api.get<UserDebug>(`/admin/user-debug?email=${encodeURIComponent(debugEmail.trim())}`)
      .then((d) => setDebugData(d))
      .catch((err) => setDebugError(err instanceof Error ? err.message : "Lookup failed"))
      .finally(() => setDebugLoading(false));
  }

  // Watchlists overview
  const [watchlists, setWatchlists] = useState<{
    users: { user_id: number; email: string; display_name: string | null; tier: string; symbol_count: number; symbols: string[] }[];
    symbol_popularity: { symbol: string; watchers: number }[];
    total_users: number;
    total_distinct_symbols: number;
  } | null>(null);
  const [watchlistsLoading, setWatchlistsLoading] = useState(false);
  const [watchlistsError, setWatchlistsError] = useState("");

  function loadWatchlists() {
    setWatchlistsLoading(true);
    setWatchlistsError("");
    api.get<typeof watchlists>("/admin/watchlists")
      .then((d) => setWatchlists(d))
      .catch((err) => setWatchlistsError(err instanceof Error ? err.message : "Failed"))
      .finally(() => setWatchlistsLoading(false));
  }

  // AI Alerts Audit
  const [aiAlertsDays, setAiAlertsDays] = useState(1);
  const [aiAlerts, setAiAlerts] = useState<AIAlertRow[] | null>(null);
  const [aiAlertsLoading, setAiAlertsLoading] = useState(false);
  const [aiAlertsError, setAiAlertsError] = useState("");

  function loadAIAlerts(days: number) {
    setAiAlertsDays(days);
    setAiAlertsLoading(true);
    setAiAlertsError("");
    api.get<AIAlertRow[]>(`/admin/recent-ai-alerts?days=${days}`)
      .then(setAiAlerts)
      .catch((err) => setAiAlertsError(err instanceof Error ? err.message : "Failed to load"))
      .finally(() => setAiAlertsLoading(false));
  }
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [expandedUser, setExpandedUser] = useState<number | null>(null);

  function fetchData() {
    setLoading(true);
    setError("");
    Promise.all([
      api.get<PlatformStats>("/admin/stats"),
      api.get<{ total: number; users: UserInfo[] }>("/admin/users"),
      api.get<AttributionStats>("/admin/attribution?days=30"),
    ])
      .then(([s, u, a]) => {
        setStats(s);
        setUsers(u.users);
        setAttribution(a);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Access denied");
        setLoading(false);
      });
  }

  useEffect(() => { fetchData(); }, []);

  const filtered = users.filter((u) =>
    !search || u.email.toLowerCase().includes(search.toLowerCase()) ||
    (u.display_name || "").toLowerCase().includes(search.toLowerCase())
  );

  // Separate real users from test accounts
  const realUsers = filtered.filter((u) => !u.email.includes("test") && !u.email.includes("example"));
  const testUsers = filtered.filter((u) => u.email.includes("test") || u.email.includes("example"));

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-bearish-text">{error}</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-5">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold text-text-primary">Admin Dashboard</h1>
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-1.5 text-xs text-accent hover:text-accent-hover disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        {/* Stats cards */}
        {stats && (<>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
            <StatCard
              label="Total Users"
              value={stats.total_users}
              icon={<Users className="h-4 w-4 text-accent" />}
            />
            <StatCard
              label="Pro Users"
              value={stats.pro_users}
              icon={<Crown className="h-4 w-4 text-warning" />}
              color="text-warning-text"
            />
            <StatCard
              label="Premium"
              value={stats.premium_users}
              icon={<Crown className="h-4 w-4 text-purple-text" />}
              color="text-purple-text"
            />
            <StatCard
              label="Active Trials"
              value={stats.trial_users}
              icon={<Users className="h-4 w-4 text-amber-400" />}
              color="text-amber-400"
            />
            <StatCard
              label="Telegram"
              value={stats.telegram_linked}
              icon={<Send className="h-4 w-4 text-accent" />}
            />
            <StatCard
              label="Total Alerts"
              value={stats.total_alerts.toLocaleString()}
              icon={<BarChart3 className="h-4 w-4 text-bullish" />}
            />
          </div>

          {/* Growth + Revenue row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
            <StatCard
              label="Alerts Today"
              value={stats.alerts_today}
              icon={<BarChart3 className="h-4 w-4 text-accent" />}
            />
            <StatCard
              label="Signups (7d)"
              value={stats.signups_7d}
              icon={<Users className="h-4 w-4 text-bullish" />}
              color="text-bullish-text"
            />
            <StatCard
              label="Signups (30d)"
              value={stats.signups_30d}
              icon={<Users className="h-4 w-4 text-bullish" />}
            />
            <StatCard
              label="Est. MRR"
              value={`$${stats.monthly_revenue_estimate.toLocaleString()}`}
              icon={<Crown className="h-4 w-4 text-bullish" />}
              color="text-bullish-text"
            />
          </div>
        </>)}

        {/* Attribution — where signups came from */}
        {attribution && (
          <section className="mb-8">
            <h2 className="text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-accent" />
              Signup Attribution — last {attribution.days} days ({attribution.total_signups} signups)
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
                <h3 className="text-[10px] uppercase tracking-wider text-text-faint font-medium mb-3">By source</h3>
                {attribution.by_source.length === 0 ? (
                  <p className="text-xs text-text-faint">No signups yet</p>
                ) : (
                  <ul className="space-y-2">
                    {attribution.by_source.map((row) => (
                      <li key={row.source} className="flex items-center justify-between text-sm">
                        <span className="text-text-secondary">{row.source}</span>
                        <span className="font-mono font-bold text-text-primary">{row.count}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
                <h3 className="text-[10px] uppercase tracking-wider text-text-faint font-medium mb-3">By medium</h3>
                {attribution.by_medium.length === 0 ? (
                  <p className="text-xs text-text-faint">No signups yet</p>
                ) : (
                  <ul className="space-y-2">
                    {attribution.by_medium.map((row) => (
                      <li key={row.medium} className="flex items-center justify-between text-sm">
                        <span className="text-text-secondary">{row.medium}</span>
                        <span className="font-mono font-bold text-text-primary">{row.count}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
                <h3 className="text-[10px] uppercase tracking-wider text-text-faint font-medium mb-3">Top campaigns</h3>
                {attribution.by_campaign.length === 0 ? (
                  <p className="text-xs text-text-faint">No campaign-tagged signups yet</p>
                ) : (
                  <ul className="space-y-2">
                    {attribution.by_campaign.slice(0, 8).map((row) => (
                      <li key={row.campaign} className="flex items-center justify-between text-sm">
                        <span className="text-text-secondary truncate mr-2">{row.campaign}</span>
                        <span className="font-mono font-bold text-text-primary shrink-0">{row.count}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </section>
        )}

        {/* Watchlists — who watches what */}
        <section className="mb-8 bg-surface-1 border border-border-subtle rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-text-primary">User Watchlists</h2>
            <button
              onClick={loadWatchlists}
              disabled={watchlistsLoading}
              className="text-xs px-3 py-1.5 rounded-lg bg-accent/10 text-accent hover:bg-accent/20 disabled:opacity-50"
            >
              {watchlistsLoading ? "Loading…" : watchlists ? "Refresh" : "Load"}
            </button>
          </div>
          {watchlistsError && <p className="text-xs text-red-400 mb-2">{watchlistsError}</p>}
          {watchlists && (
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <h3 className="text-[10px] uppercase tracking-wider text-text-faint mb-2">
                  {watchlists.total_users} users · {watchlists.total_distinct_symbols} symbols
                </h3>
                <div className="max-h-96 overflow-y-auto space-y-2">
                  {watchlists.users.map((u) => (
                    <div key={u.user_id} className="bg-surface-2 rounded-lg p-3">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-text-primary truncate mr-2">
                          {u.email}
                        </span>
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-accent/10 text-accent shrink-0">
                          {u.tier} · {u.symbol_count}
                        </span>
                      </div>
                      <div className="text-[11px] text-text-muted">
                        {u.symbols.length > 0 ? u.symbols.join(" · ") : "—"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="text-[10px] uppercase tracking-wider text-text-faint mb-2">
                  Most-watched symbols
                </h3>
                <div className="max-h-96 overflow-y-auto">
                  <table className="w-full text-xs">
                    <tbody>
                      {watchlists.symbol_popularity.map((row) => (
                        <tr key={row.symbol} className="border-b border-border-subtle/50">
                          <td className="py-1.5 font-mono font-medium text-text-primary">{row.symbol}</td>
                          <td className="py-1.5 text-right font-mono text-text-secondary">
                            {row.watchers}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* User Debug — inspect tier + rate limit state for a specific account */}
        <section className="mb-8 bg-surface-1 border border-border-subtle rounded-xl p-5">
          <h2 className="text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
            <Search className="h-4 w-4 text-accent" />
            User Debug — inspect tier + alert limits
          </h2>
          <p className="text-xs text-text-muted mb-3">
            Enter a user's email to see their resolved tier, trial status, today's alert counts, and Telegram rate limit state.
          </p>
          <div className="flex gap-2 mb-4">
            <input
              type="email"
              value={debugEmail}
              onChange={(e) => setDebugEmail(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runUserDebug(); }}
              placeholder="user@example.com"
              className="flex-1 max-w-sm bg-surface-2 border border-border-subtle rounded-lg py-2 px-3 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none"
            />
            <button
              onClick={runUserDebug}
              disabled={debugLoading || !debugEmail.trim()}
              className="bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-xs font-bold px-4 py-2 rounded-lg transition-colors"
            >
              {debugLoading ? "Loading..." : "Inspect"}
            </button>
          </div>

          {debugError && (
            <p className="text-xs text-red-400 mb-2">{debugError}</p>
          )}

          {debugData && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Identity */}
              <div className="bg-surface-2/40 rounded-lg p-3 border border-border-subtle/50">
                <h3 className="text-[10px] uppercase tracking-wider text-text-faint mb-2">Identity</h3>
                <dl className="space-y-1 text-xs">
                  <div className="flex justify-between"><dt className="text-text-muted">ID</dt><dd className="text-text-primary font-mono">{debugData.user.id}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">Email</dt><dd className="text-text-primary truncate ml-2">{debugData.user.email}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">Telegram</dt><dd className={debugData.user.telegram_chat_id ? "text-bullish-text" : "text-text-faint"}>{debugData.user.telegram_chat_id ? "Linked" : "Not linked"}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">TG enabled</dt><dd className={debugData.user.telegram_enabled ? "text-bullish-text" : "text-text-faint"}>{debugData.user.telegram_enabled ? "Yes" : "No"}</dd></div>
                </dl>
              </div>

              {/* Tier */}
              <div className="bg-surface-2/40 rounded-lg p-3 border border-border-subtle/50">
                <h3 className="text-[10px] uppercase tracking-wider text-text-faint mb-2">Tier &amp; Trial</h3>
                <dl className="space-y-1 text-xs">
                  <div className="flex justify-between"><dt className="text-text-muted">Resolved tier</dt><dd className="text-accent font-bold uppercase">{debugData.resolved_tier}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">Sub tier</dt><dd className="text-text-primary">{debugData.subscription?.tier ?? "—"}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">Trial active</dt><dd className={debugData.trial_active ? "text-bullish-text" : "text-text-faint"}>{debugData.trial_active ? "Yes" : "No"}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">Trial days left</dt><dd className="text-text-primary">{debugData.trial_days_left}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">AI cap/day</dt><dd className="text-text-primary">{debugData.limits.ai_scan_alerts_per_day ?? "unlimited"}</dd></div>
                </dl>
              </div>

              {/* Today stats */}
              <div className="bg-surface-2/40 rounded-lg p-3 border border-border-subtle/50">
                <h3 className="text-[10px] uppercase tracking-wider text-text-faint mb-2">Today</h3>
                <dl className="space-y-1 text-xs">
                  <div className="flex justify-between"><dt className="text-text-muted">AI actionable</dt><dd className="text-text-primary font-mono">{debugData.today_stats.ai_actionable_alerts_in_db}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">AI waits</dt><dd className="text-text-faint font-mono">{debugData.today_stats.ai_wait_alerts_in_db}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">Rule alerts</dt><dd className={debugData.today_stats.rule_alerts_in_db > 0 ? "text-yellow-400 font-mono" : "text-text-faint font-mono"}>{debugData.today_stats.rule_alerts_in_db}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">TG delivered</dt><dd className="text-text-primary font-mono">{debugData.today_stats.ai_telegram_delivered_counter ?? "—"}</dd></div>
                  <div className="flex justify-between"><dt className="text-text-muted">Cap hit</dt><dd className={debugData.today_stats.limit_reached_notified ? "text-yellow-400" : "text-text-faint"}>{debugData.today_stats.limit_reached_notified ? "Yes" : "No"}</dd></div>
                </dl>
              </div>
            </div>
          )}
        </section>

        {/* AI Alerts Audit — every distinct AI signal fired (deduped across users) */}
        <section className="mb-8 bg-surface-1 border border-border-subtle rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-bold text-text-primary flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-accent" />
              AI Alerts Audit (LONG / SHORT)
            </h2>
            <div className="flex gap-1">
              {[1, 3, 7, 30].map((d) => (
                <button
                  key={d}
                  onClick={() => loadAIAlerts(d)}
                  className={`text-[10px] font-medium px-2.5 py-1 rounded ${
                    aiAlertsDays === d && aiAlerts != null
                      ? "bg-accent/15 text-accent border border-accent/30"
                      : "bg-surface-2 text-text-muted hover:bg-surface-3 border border-transparent"
                  }`}
                >
                  {d === 1 ? "Today" : `${d}d`}
                </button>
              ))}
            </div>
          </div>
          <p className="text-xs text-text-muted mb-3">
            Every distinct AI LONG/SHORT signal (deduped across per-user copies). Click an alert ID to inspect details + auto-trade status.
          </p>

          {aiAlertsLoading && <p className="text-xs text-text-faint">Loading…</p>}
          {aiAlertsError && <p className="text-xs text-bearish-text">{aiAlertsError}</p>}

          {aiAlerts && (
            aiAlerts.length === 0 ? (
              <p className="text-xs text-text-faint">No AI LONG/SHORT alerts in the selected window.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="text-text-faint">
                    <tr className="border-b border-border-subtle/50">
                      <th className="text-left py-2 pr-3">Time</th>
                      <th className="text-left py-2 pr-3">Symbol</th>
                      <th className="text-left py-2 pr-3">Dir</th>
                      <th className="text-right py-2 pr-3">Entry</th>
                      <th className="text-right py-2 pr-3">Stop</th>
                      <th className="text-right py-2 pr-3">T1</th>
                      <th className="text-right py-2 pr-3">T2</th>
                      <th className="text-left py-2 pr-3">Conv</th>
                      <th className="text-right py-2 pr-3">Users</th>
                      <th className="text-right py-2">ID</th>
                    </tr>
                  </thead>
                  <tbody>
                    {aiAlerts.map((a) => (
                      <tr key={a.id} className="border-b border-border-subtle/20 hover:bg-surface-2/30">
                        <td className="py-2 pr-3 text-text-faint text-[10px]">
                          {a.fired_at ? new Date(a.fired_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"}
                        </td>
                        <td className="py-2 pr-3 font-bold text-text-primary">{a.symbol}</td>
                        <td className="py-2 pr-3">
                          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                            a.direction === "BUY" ? "bg-bullish/10 text-bullish-text" : "bg-bearish/10 text-bearish-text"
                          }`}>
                            {a.direction === "BUY" ? "LONG" : "SHORT"}
                          </span>
                        </td>
                        <td className="py-2 pr-3 text-right font-mono">${a.entry?.toFixed(2) ?? "—"}</td>
                        <td className="py-2 pr-3 text-right font-mono text-bearish-text">${a.stop?.toFixed(2) ?? "—"}</td>
                        <td className="py-2 pr-3 text-right font-mono text-bullish-text">${a.target_1?.toFixed(2) ?? "—"}</td>
                        <td className="py-2 pr-3 text-right font-mono text-bullish-text">${a.target_2?.toFixed(2) ?? "—"}</td>
                        <td className="py-2 pr-3 text-text-muted">{a.confidence ?? "—"}</td>
                        <td className="py-2 pr-3 text-right font-mono text-text-muted">{a.user_copies}</td>
                        <td className="py-2 text-right">
                          <a
                            href={`/api/v1/admin/alert-debug?alert_id=${a.id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-[10px] text-accent hover:text-accent-hover font-mono"
                          >
                            #{a.id} →
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-[10px] text-text-faint mt-2">{aiAlerts.length} distinct signals</p>
              </div>
            )
          )}

          {!aiAlerts && !aiAlertsLoading && (
            <button
              onClick={() => loadAIAlerts(1)}
              className="text-xs bg-accent hover:bg-accent-hover text-white px-4 py-1.5 rounded-md transition-colors"
            >
              Load today's AI alerts
            </button>
          )}
        </section>

        {/* User search */}
        <div className="mb-4">
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-faint" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search users..."
              className="w-full bg-surface-2 border border-border-subtle rounded-lg py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-faint focus:border-accent focus:outline-none"
            />
          </div>
        </div>

        {/* Users table */}
        <div className="bg-surface-1 border border-border-subtle rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-border-subtle bg-surface-2/20">
            <h2 className="text-sm font-semibold text-text-primary">
              Users <span className="text-text-faint font-normal">({realUsers.length} real, {testUsers.length} test)</span>
            </h2>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-text-faint border-b border-border-subtle/50">
                  <th className="px-5 py-2.5 text-left font-medium">User</th>
                  <th className="px-3 py-2.5 text-center font-medium">Tier</th>
                  <th className="px-3 py-2.5 text-center font-medium">Telegram</th>
                  <th className="px-3 py-2.5 text-right font-medium">Watchlist</th>
                  <th className="px-3 py-2.5 text-right font-medium">Alerts</th>
                  <th className="px-5 py-2.5 text-right font-medium">Joined</th>
                </tr>
              </thead>
              <tbody>
                {realUsers.map((u) => (
                  <tr
                    key={u.id}
                    onClick={() => setExpandedUser(expandedUser === u.id ? null : u.id)}
                    className="border-b border-border-subtle/30 hover:bg-surface-2/30 cursor-pointer transition-colors"
                  >
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        {expandedUser === u.id ? <ChevronDown className="h-3 w-3 text-text-faint" /> : <ChevronRight className="h-3 w-3 text-text-faint" />}
                        <div>
                          <div className="font-medium text-text-primary">{u.display_name || u.email.split("@")[0]}</div>
                          <div className="text-[10px] text-text-faint">{u.email}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-center"><TierBadge tier={u.tier} trialDays={u.trial_days_left} trialExpired={u.trial_expired} /></td>
                    <td className="px-3 py-3 text-center">
                      {u.telegram_linked ? (
                        <span className="inline-flex items-center gap-1 text-[10px] text-bullish-text">
                          <span className="w-1.5 h-1.5 rounded-full bg-bullish" /> Linked
                        </span>
                      ) : (
                        <span className="text-[10px] text-text-faint">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-text-muted">{u.watchlist_count}</td>
                    <td className="px-3 py-3 text-right font-mono text-text-muted">{u.alert_count}</td>
                    <td className="px-5 py-3 text-right text-text-faint text-xs">{u.created_at.slice(0, 10)}</td>
                  </tr>
                ))}

                {/* Test accounts collapsed */}
                {testUsers.length > 0 && (
                  <>
                    <tr className="bg-surface-0/50">
                      <td colSpan={6} className="px-5 py-2 text-[10px] text-text-faint uppercase tracking-wider">
                        Test Accounts ({testUsers.length})
                      </td>
                    </tr>
                    {testUsers.map((u) => (
                      <tr key={u.id} className="border-b border-border-subtle/20 opacity-50">
                        <td className="px-5 py-2">
                          <span className="text-xs text-text-faint">{u.email}</span>
                        </td>
                        <td className="px-3 py-2 text-center"><TierBadge tier={u.tier} trialDays={u.trial_days_left} trialExpired={u.trial_expired} /></td>
                        <td className="px-3 py-2 text-center text-[10px] text-text-faint">{u.telegram_linked ? "✓" : "—"}</td>
                        <td className="px-3 py-2 text-right font-mono text-text-faint text-xs">{u.watchlist_count}</td>
                        <td className="px-3 py-2 text-right font-mono text-text-faint text-xs">{u.alert_count}</td>
                        <td className="px-5 py-2 text-right text-text-faint text-[10px]">{u.created_at.slice(0, 10)}</td>
                      </tr>
                    ))}
                  </>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
