/** Admin Dashboard — traffic, growth, alert-engine health, and user management.
 *  Redesigned 2026-06-10: meaningful panels up front, debug/backfill tools moved
 *  into a collapsed Maintenance drawer. Only accessible to admin users.
 */

import { useEffect, useState } from "react";
import { api } from "../api/client";
import {
  Users, Send, RefreshCw, Crown, Search, ChevronDown, ChevronRight,
  Eye, TrendingUp, Activity, Wrench, DollarSign, UserPlus,
} from "lucide-react";

// ───────────────────────── types ─────────────────────────
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
  is_test?: boolean;
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

interface TrafficStats {
  visits_today: number;
  visits_7d: number;
  visits_30d: number;
  unique_today: number;
  unique_7d: number;
  unique_30d: number;
  logged_in_7d: number;
  anon_7d: number;
  top_paths: { path: string; views: number; visitors: number }[];
  daily: { date: string; views: number; visitors: number }[];
}

interface AlertHealth {
  delivered_rows_today: number;
  suppressed_rows_today: number;
  fired_signals_today: number;
  by_type: { alert_type: string; fired_7d: number }[];
  by_direction: { direction: string; fired: number }[];
  suppressed_reasons: { reason: string; rows: number }[];
  daily: { date: string; fired: number }[];
}

interface AIAlertRow {
  id: number;
  symbol: string;
  alert_type: string;
  direction: string;
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
}

// ───────────────────────── small UI helpers ─────────────────────────
function StatCard({ label, value, sub, icon, color }: {
  label: string; value: string | number; sub?: string; icon: React.ReactNode; color?: string;
}) {
  return (
    <div className="bg-surface-1 border border-border-subtle rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-[10px] text-text-faint uppercase tracking-wider font-medium">{label}</span>
      </div>
      <span className={`font-mono text-2xl font-bold ${color || "text-text-primary"}`}>{value}</span>
      {sub && <div className="text-[11px] text-text-faint mt-0.5">{sub}</div>}
    </div>
  );
}

/** Tiny CSS bar chart for a daily trend. */
function MiniBars({ data, color = "bg-accent/60" }: { data: number[]; color?: string }) {
  const max = Math.max(1, ...data);
  return (
    <div className="flex items-end gap-0.5 h-12">
      {data.map((v, i) => (
        <div
          key={i}
          className={`flex-1 rounded-sm ${color}`}
          style={{ height: `${Math.max(3, (v / max) * 100)}%` }}
          title={String(v)}
        />
      ))}
    </div>
  );
}

function Panel({ title, icon, action, children }: {
  title: string; icon: React.ReactNode; action?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section className="bg-surface-1 border border-border-subtle rounded-2xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-text-primary">
          {icon}{title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function TierSelector({ userId, currentTier, onChanged }: {
  userId: number; currentTier: string; onChanged: () => void;
}) {
  const [saving, setSaving] = useState(false);
  async function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    e.stopPropagation();
    const newTier = e.target.value;
    if (newTier === currentTier || newTier === "trial") return;
    if (!confirm(`Change user #${userId} to ${newTier.toUpperCase()}?`)) return;
    setSaving(true);
    try {
      await api.put(`/admin/users/${userId}/tier`, { tier: newTier });
      onChanged();
    } catch (err) {
      alert("Failed: " + (err instanceof Error ? err.message : "unknown"));
    } finally {
      setSaving(false);
    }
  }
  const options = ["free", "comp", "pro", "premium"];
  const value = options.includes(currentTier) ? currentTier : "free";
  return (
    <select
      value={value}
      disabled={saving}
      onClick={(e) => e.stopPropagation()}
      onChange={handleChange}
      className="text-[10px] font-bold px-1.5 py-0.5 rounded border bg-surface-0 border-border-subtle text-text-primary uppercase cursor-pointer hover:border-accent/40 disabled:opacity-50"
    >
      {options.map((t) => <option key={t} value={t}>{t.toUpperCase()}</option>)}
    </select>
  );
}

function TierBadge({ tier, trialDays, trialExpired }: { tier: string; trialDays?: number; trialExpired?: boolean }) {
  const styles: Record<string, string> = {
    pro: "bg-accent/10 text-accent border-accent/20",
    premium: "bg-purple/10 text-purple-text border-purple/20",
    admin: "bg-warning/10 text-warning-text border-warning/20",
    trial: "bg-bullish/10 text-bullish-text border-bullish/20",
    comp: "bg-cyan-500/10 text-cyan-400 border-cyan-500/30",
    free: "bg-surface-3 text-text-faint border-border-subtle",
    none: "bg-surface-3 text-text-faint border-border-subtle",
  };
  const label = tier === "trial" && trialDays ? `TRIAL ${trialDays}d` : tier.toUpperCase();
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${styles[tier] || styles.free}`}>{label}</span>
      {trialExpired && <span className="text-[9px] text-bearish-text">expired</span>}
    </span>
  );
}

// ───────────────────────── page ─────────────────────────
interface TrafficSources {
  days: number;
  sources: { source: string; visitors: number; visits: number }[];
  campaigns: { campaign: string; source: string; visitors: number }[];
}

function TrafficSourcesPanel({ data }: { data: TrafficSources | null }) {
  return (
    <Panel title="Traffic sources" icon={<Eye size={15} className="text-accent" />} action={<span className="text-[11px] text-text-faint">where visitors come from · 30d</span>}>
      {!data || data.sources.length === 0 ? (
        <div className="text-xs text-text-faint">No source data yet — fills in once links with <span className="font-mono">?utm_source=…</span> are shared (or referrers arrive).</div>
      ) : (
        <>
          <div className="grid gap-1.5">
            {data.sources.map((srow) => (
              <div key={srow.source} className="flex items-center justify-between text-[12px]">
                <span className="capitalize text-text-secondary">{srow.source}</span>
                <span className="font-mono text-text-primary">{srow.visitors} <span className="text-text-faint">visitors · {srow.visits} views</span></span>
              </div>
            ))}
          </div>
          {data.campaigns.length > 0 && (
            <div className="mt-4">
              <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">Campaign links</div>
              <div className="flex flex-wrap gap-2">
                {data.campaigns.map((c) => (
                  <span key={c.campaign} className="text-[11px] px-2 py-0.5 rounded bg-surface-2 border border-border-subtle text-text-secondary">
                    <span className="font-mono">{c.campaign}</span> · {c.source} · <span className="font-bold">{c.visitors}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

interface RecentActivity {
  signups: { email: string; name: string | null; source: string | null; campaign: string | null; at: string | null }[];
}

function ActivityPanel({ data }: { data: RecentActivity | null }) {
  const rel = (iso: string | null) => {
    if (!iso) return "";
    const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  };
  return (
    <Panel title="Live activity" icon={<UserPlus size={15} className="text-bullish-text" />} action={<span className="text-[11px] text-text-faint">newest signups</span>}>
      {!data || data.signups.length === 0 ? (
        <div className="text-xs text-text-faint">No signups yet.</div>
      ) : (
        <div className="grid gap-2">
          {data.signups.slice(0, 12).map((u, i) => (
            <div key={u.email + i} className="flex items-center justify-between text-[12px]">
              <span className="text-text-secondary">🟢 <span className="text-text-primary">{u.email}</span>{u.source ? <span className="text-text-faint"> · via {u.source}{u.campaign ? ` (${u.campaign})` : ""}</span> : ""}</span>
              <span className="font-mono text-[11px] text-text-faint">{rel(u.at)}</span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

export default function AdminPage() {
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [traffic, setTraffic] = useState<TrafficStats | null>(null);
  const [health, setHealth] = useState<AlertHealth | null>(null);
  const [attribution, setAttribution] = useState<AttributionStats | null>(null);
  const [trafficSrc, setTrafficSrc] = useState<TrafficSources | null>(null);
  const [activity, setActivity] = useState<RecentActivity | null>(null);
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [expandedUser, setExpandedUser] = useState<number | null>(null);
  const [wlSymbols, setWlSymbols] = useState<Record<number, string[]>>({});
  const [showTest, setShowTest] = useState(false);
  const [testHidden, setTestHidden] = useState(0);

  function fetchData() {
    setLoading(true);
    setError("");
    Promise.all([
      api.get<PlatformStats>("/admin/stats"),
      api.get<{ total: number; users: UserInfo[]; test_hidden?: number }>(`/admin/users${showTest ? "?include_test=true" : ""}`),
      api.get<AttributionStats>("/admin/attribution?days=30"),
      api.get<TrafficStats>("/admin/traffic").catch(() => null),
      api.get<AlertHealth>("/admin/alert-health").catch(() => null),
      api.get<{ users: { user_id: number; symbols: string[] }[] }>("/admin/watchlists").catch(() => null),
      api.get<TrafficSources>("/admin/traffic-sources?days=30").catch(() => null),
      api.get<RecentActivity>("/admin/activity?limit=40").catch(() => null),
    ])
      .then(([s, u, a, t, h, w, ts, act]) => {
        setStats(s);
        setUsers(u.users);
        setTestHidden(u.test_hidden ?? 0);
        setAttribution(a);
        setTraffic(t);
        setHealth(h);
        setTrafficSrc(ts);
        setActivity(act);
        if (w) {
          const map: Record<number, string[]> = {};
          for (const row of w.users) map[row.user_id] = row.symbols;
          setWlSymbols(map);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Access denied");
        setLoading(false);
      });
  }

  useEffect(() => { fetchData(); }, [showTest]);

  const filtered = users.filter(
    (u) =>
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      (u.display_name || "").toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return <div className="p-8 text-text-faint">Loading admin dashboard…</div>;
  }
  if (error) {
    return <div className="p-8 text-bearish-text">{error}</div>;
  }

  return (
    <div className="h-full overflow-y-auto">
    <div className="max-w-6xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-text-primary">Admin</h1>
        <button
          onClick={fetchData}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border border-border-subtle text-text-secondary hover:border-accent/40 hover:text-text-primary"
        >
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      <div className="mb-5 rounded-lg border border-warning/30 bg-warning/5 px-4 py-2.5 text-[12px] text-text-secondary">
        🧪 <b className="text-warning-text">Free test stage</b> — Pro paywall off; optimizing for signups · activation · feedback, not revenue.
      </div>

      <ActivityPanel data={activity} />

      {/* ── Traffic ── */}
      <Panel
        title="Traffic"
        icon={<Eye size={15} className="text-accent" />}
        action={traffic && <span className="text-[11px] text-text-faint">last 14 days</span>}
      >
        {!traffic ? (
          <div className="text-xs text-text-faint">
            No visit data yet — tracking starts once the new build is deployed.
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <StatCard label="Visits today" value={traffic.visits_today} sub={`${traffic.unique_today} unique`} icon={<Eye size={13} className="text-accent" />} />
              <StatCard label="Visits 7d" value={traffic.visits_7d} sub={`${traffic.unique_7d} unique`} icon={<Eye size={13} className="text-text-faint" />} />
              <StatCard label="Visits 30d" value={traffic.visits_30d} sub={`${traffic.unique_30d} unique`} icon={<Eye size={13} className="text-text-faint" />} />
              <StatCard label="Logged-in 7d" value={traffic.logged_in_7d} sub={`${traffic.anon_7d} anonymous`} icon={<Users size={13} className="text-bullish-text" />} />
            </div>
            {traffic.daily.length > 0 && (
              <div className="mb-4">
                <div className="text-[10px] text-text-faint uppercase tracking-wider mb-1">Daily views</div>
                <MiniBars data={traffic.daily.map((d) => d.views)} />
              </div>
            )}
            {traffic.top_paths.length > 0 && (
              <div>
                <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">Top pages (7d)</div>
                <div className="space-y-1">
                  {traffic.top_paths.map((p) => (
                    <div key={p.path} className="flex items-center justify-between text-xs">
                      <span className="font-mono text-text-secondary truncate max-w-[60%]">{p.path}</span>
                      <span className="text-text-faint">{p.views} views · {p.visitors} visitors</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </Panel>

      <TrafficSourcesPanel data={trafficSrc} />

      {/* ── Growth ── */}
      {stats && (
        <Panel title="Growth" icon={<TrendingUp size={15} className="text-bullish-text" />}>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <StatCard label="Total users" value={stats.total_users} icon={<Users size={13} className="text-accent" />} />
            <StatCard label="Signups 7d" value={stats.signups_7d} sub={`${stats.signups_30d} in 30d`} icon={<UserPlus size={13} className="text-bullish-text" />} />
            <StatCard label="Telegram linked" value={stats.telegram_linked} sub={`${Math.round((stats.telegram_linked / Math.max(1, stats.total_users)) * 100)}% of users`} icon={<Send size={13} className="text-accent" />} />
            <StatCard label="Est. MRR" value={`$${stats.monthly_revenue_estimate.toLocaleString()}`} icon={<DollarSign size={13} className="text-bullish-text" />} color="text-bullish-text" />
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              ["FREE", stats.free_users],
              ["TRIAL", stats.trial_users],
              ["PRO", stats.pro_users],
              ["PREMIUM", stats.premium_users],
            ].map(([k, v]) => (
              <span key={k as string} className="text-[11px] px-2.5 py-1 rounded-lg bg-surface-2 border border-border-subtle text-text-secondary">
                <span className="font-bold text-text-primary">{v}</span> {k}
              </span>
            ))}
          </div>
          {attribution && attribution.by_source.length > 0 && (
            <div className="mt-4">
              <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">Signup sources (30d)</div>
              <div className="flex flex-wrap gap-2">
                {attribution.by_source.slice(0, 8).map((s) => (
                  <span key={s.source} className="text-[11px] px-2 py-0.5 rounded bg-surface-2 border border-border-subtle text-text-secondary">
                    {s.source || "direct"} · <span className="font-bold">{s.count}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </Panel>
      )}

      {/* ── Alert engine health ── */}
      <Panel title="Alert engine" icon={<Activity size={15} className="text-purple-text" />}>
        {!health ? (
          <div className="text-xs text-text-faint">No alert data.</div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
              <StatCard label="Fired today" value={health.fired_signals_today} sub="distinct setups" icon={<Activity size={13} className="text-purple-text" />} />
              <StatCard label="Delivered (rows)" value={health.delivered_rows_today.toLocaleString()} icon={<Send size={13} className="text-bullish-text" />} color="text-bullish-text" />
              <StatCard label="Suppressed (rows)" value={health.suppressed_rows_today.toLocaleString()} icon={<Activity size={13} className="text-text-faint" />} />
            </div>
            {health.by_direction.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-4">
                {health.by_direction.map((d) => (
                  <span key={d.direction} className="text-[11px] px-2.5 py-1 rounded-lg bg-surface-2 border border-border-subtle text-text-secondary">
                    <span className="font-bold text-text-primary">{d.fired}</span> {d.direction}
                  </span>
                ))}
              </div>
            )}
            <div className="grid md:grid-cols-2 gap-5">
              {health.by_type.length > 0 && (
                <div>
                  <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">Fired by type (7d)</div>
                  <div className="space-y-1">
                    {health.by_type.map((t) => (
                      <div key={t.alert_type} className="flex items-center justify-between text-xs">
                        <span className="font-mono text-text-secondary truncate max-w-[70%]">{t.alert_type}</span>
                        <span className="text-text-faint">{t.fired_7d}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {health.suppressed_reasons.length > 0 && (
                <div>
                  <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">Top suppressed reasons (7d)</div>
                  <div className="space-y-1">
                    {health.suppressed_reasons.map((r) => (
                      <div key={r.reason} className="flex items-center justify-between text-xs">
                        <span className="font-mono text-text-secondary truncate max-w-[70%]">{r.reason}</span>
                        <span className="text-text-faint">{r.rows.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {health.daily.length > 0 && (
              <div className="mt-4">
                <div className="text-[10px] text-text-faint uppercase tracking-wider mb-1">Daily fired</div>
                <MiniBars data={health.daily.map((d) => d.fired)} color="bg-purple/60" />
              </div>
            )}
          </>
        )}
      </Panel>

      {/* ── Master watchlist (platform universe) ── */}
      <MasterWatchlistPanel />

      {/* ── Users ── */}
      <Panel
        title={`Users (${users.length}${!showTest && testHidden ? ` · ${testHidden} test hidden` : ""})`}
        icon={<Crown size={15} className="text-warning-text" />}
        action={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowTest((v) => !v)}
              title="Show / hide automated smoke + QA test accounts"
              className={`text-[11px] px-2 py-1.5 rounded-lg border transition-colors ${showTest ? "bg-warning/15 text-warning-text border-warning/40" : "bg-surface-1 text-text-faint border-border-subtle hover:bg-surface-2"}`}
            >
              {showTest ? "Hide test accounts" : "Show test accounts"}
            </button>
            <div className="relative">
              <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-text-faint" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search email / name"
                className="text-xs pl-7 pr-2 py-1.5 rounded-lg bg-surface-0 border border-border-subtle text-text-primary w-48 focus:outline-none focus:border-accent/40"
              />
            </div>
          </div>
        }
      >
        <div className="divide-y divide-border-subtle">
          {filtered.map((u) => (
            <div key={u.id}>
              <div
                className="flex items-center gap-3 py-2 cursor-pointer hover:bg-surface-2/40 -mx-2 px-2 rounded-lg"
                onClick={() => setExpandedUser(expandedUser === u.id ? null : u.id)}
              >
                {expandedUser === u.id ? <ChevronDown size={13} className="text-text-faint" /> : <ChevronRight size={13} className="text-text-faint" />}
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-text-primary truncate">{u.display_name || u.email}</div>
                  <div className="text-[11px] text-text-faint truncate">{u.email}</div>
                </div>
                {u.is_test && <span className="text-[9px] px-1 py-0.5 rounded bg-warning/15 text-warning-text shrink-0">TEST</span>}
                {u.telegram_linked && <Send size={12} className="text-accent" />}
                <TierBadge tier={u.tier} trialDays={u.trial_days_left} trialExpired={u.trial_expired} />
                <TierSelector userId={u.id} currentTier={u.tier} onChanged={fetchData} />
              </div>
              {expandedUser === u.id && (
                <div className="ml-6 mb-2 space-y-1.5">
                  <div className="grid grid-cols-3 gap-2 text-[11px] text-text-faint">
                    <span>Joined {new Date(u.created_at).toLocaleDateString()}</span>
                    <span>{u.watchlist_count} watchlist symbols</span>
                    <span>{u.alert_count} alerts</span>
                  </div>
                  {(wlSymbols[u.id]?.length ?? 0) > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {wlSymbols[u.id].map((sym) => (
                        <span key={sym} className="px-1.5 py-0.5 rounded bg-surface-2 text-[10px] text-text-secondary">
                          {sym}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[11px] text-text-faint">No symbols on watchlist.</div>
                  )}
                </div>
              )}
            </div>
          ))}
          {filtered.length === 0 && <div className="py-4 text-xs text-text-faint">No users match.</div>}
        </div>
      </Panel>

      {/* ── Maintenance (collapsed) ── */}
      <MaintenanceDrawer />
    </div>
    </div>
  );
}

// ─────────────────── master watchlist (platform universe) ───────────────────
type MasterWL = { count: number; groups: { id: number; name: string; color: string; symbols: string[] }[]; ungrouped: string[] };

function SymChip({ sym, onRemove, busy }: { sym: string; onRemove: () => void; busy: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-surface-0 border border-border-subtle px-1.5 py-0.5 text-[11px] text-text-secondary">
      {sym}
      <button disabled={busy} onClick={onRemove} title="Remove from universe" className="text-text-faint hover:text-bearish-text disabled:opacity-50 leading-none">×</button>
    </span>
  );
}

function MasterWatchlistPanel() {
  const [data, setData] = useState<MasterWL | null>(null);
  const [adding, setAdding] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api.get<MasterWL>("/admin/master-watchlist").then(setData).catch(() => setData(null));
  useEffect(() => { load(); }, []);
  const add = async () => {
    // Accept one OR many — comma / space / newline separated, so a whole list can be pasted in.
    const syms = adding.split(/[\s,]+/).map((x) => x.trim().toUpperCase()).filter(Boolean);
    if (!syms.length) return;
    setBusy(true);
    try {
      for (const sym of syms) await api.post(`/admin/master-watchlist?symbol=${encodeURIComponent(sym)}`);
      setAdding("");
      await load();
    } finally { setBusy(false); }
  };
  const remove = async (s: string) => {
    setBusy(true);
    try { await api.delete(`/admin/master-watchlist?symbol=${encodeURIComponent(s)}`); await load(); }
    finally { setBusy(false); }
  };
  return (
    <Panel title={`Master watchlist — platform universe${data ? ` (${data.count})` : ""}`} icon={<Crown size={15} className="text-accent" />}>
      <p className="text-[11px] text-text-faint mb-3">
        The universe the scanner fires on + the Sectors template users copy from. Separate from your
        personal watchlist — you (as a user) only get alerts for symbols on <em>your own</em> list.
      </p>
      <div className="flex gap-2 mb-4">
        <input
          value={adding}
          onChange={(e) => setAdding(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="Add ticker(s) — one or many, comma/space separated…"
          className="flex-1 bg-surface-0 border border-border-subtle rounded-lg px-3 py-1.5 text-sm text-text-primary uppercase placeholder:normal-case placeholder:text-text-faint"
        />
        <button disabled={busy || !adding.trim()} onClick={add} className="px-3 py-1.5 rounded-lg bg-accent/15 border border-accent/40 text-accent text-xs font-semibold disabled:opacity-50">Add</button>
      </div>
      {!data ? (
        <div className="text-[12px] text-text-faint">Loading…</div>
      ) : (
        <div className="space-y-3">
          {data.groups.map((g) => (
            <div key={g.id}>
              <div className="text-[11px] font-bold uppercase tracking-wide mb-1" style={{ color: g.color || undefined }}>
                {g.name} <span className="text-text-faint font-normal">{g.symbols.length}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {g.symbols.map((s) => <SymChip key={s} sym={s} onRemove={() => remove(s)} busy={busy} />)}
              </div>
            </div>
          ))}
          {data.ungrouped.length > 0 && (
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wide mb-1 text-text-muted">
                Ungrouped <span className="text-text-faint font-normal">{data.ungrouped.length}</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {data.ungrouped.map((s) => <SymChip key={s} sym={s} onRemove={() => remove(s)} busy={busy} />)}
              </div>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

// ───────────────────────── maintenance drawer ─────────────────────────
function MaintenanceDrawer() {
  const [debugEmail, setDebugEmail] = useState("");
  const [debugData, setDebugData] = useState<UserDebug | null>(null);
  const [debugError, setDebugError] = useState("");
  const [aiAlerts, setAiAlerts] = useState<AIAlertRow[] | null>(null);
  const [busy, setBusy] = useState("");

  function runUserDebug() {
    if (!debugEmail.trim()) return;
    setDebugError("");
    setDebugData(null);
    api.get<UserDebug>(`/admin/user-debug?email=${encodeURIComponent(debugEmail.trim())}`)
      .then(setDebugData)
      .catch((err) => setDebugError(err instanceof Error ? err.message : "Lookup failed"));
  }

  async function runTool(path: string, label: string) {
    if (!confirm(`Run: ${label}?`)) return;
    setBusy(label);
    try {
      const r = await api.post<unknown>(path, {});
      alert(`${label} — done.\n` + JSON.stringify(r).slice(0, 300));
    } catch (err) {
      alert(`${label} failed: ` + (err instanceof Error ? err.message : "unknown"));
    } finally {
      setBusy("");
    }
  }

  return (
    <details className="bg-surface-1 border border-border-subtle rounded-2xl p-5 group">
      <summary className="flex items-center gap-2 text-sm font-semibold text-text-secondary cursor-pointer select-none">
        <Wrench size={15} className="text-text-faint" />
        Maintenance &amp; tools
        <span className="text-[11px] text-text-faint font-normal ml-1">(debug · backfills)</span>
      </summary>

      <div className="mt-4 space-y-5">
        {/* user debug */}
        <div>
          <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">User debug</div>
          <div className="flex gap-2">
            <input
              value={debugEmail}
              onChange={(e) => setDebugEmail(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runUserDebug(); }}
              placeholder="user@email.com"
              className="text-xs px-2 py-1.5 rounded-lg bg-surface-0 border border-border-subtle text-text-primary flex-1"
            />
            <button onClick={runUserDebug} className="text-xs px-3 py-1.5 rounded-lg border border-border-subtle text-text-secondary hover:border-accent/40">Look up</button>
          </div>
          {debugError && <div className="text-[11px] text-bearish-text mt-1">{debugError}</div>}
          {debugData && (
            <pre className="text-[11px] text-text-faint mt-2 bg-surface-0 rounded-lg p-2 overflow-x-auto">
              {JSON.stringify(debugData, null, 2)}
            </pre>
          )}
        </div>

        {/* recent ai alerts */}
        <div>
          <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">Recent AI alerts</div>
          <button
            onClick={() => api.get<AIAlertRow[]>("/admin/recent-ai-alerts?days=1").then(setAiAlerts).catch(() => setAiAlerts([]))}
            className="text-xs px-3 py-1.5 rounded-lg border border-border-subtle text-text-secondary hover:border-accent/40"
          >
            Load today
          </button>
          {aiAlerts && (
            <div className="mt-2 space-y-1 max-h-48 overflow-y-auto">
              {aiAlerts.length === 0 && <div className="text-[11px] text-text-faint">None.</div>}
              {aiAlerts.map((a) => (
                <div key={a.id} className="text-[11px] text-text-secondary flex justify-between">
                  <span className="font-mono">{a.symbol} {a.direction} · {a.alert_type}</span>
                  <span className="text-text-faint">×{a.user_copies}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* one-shot tools */}
        <div>
          <div className="text-[10px] text-text-faint uppercase tracking-wider mb-2">One-shot jobs</div>
          <div className="flex flex-wrap gap-2">
            <button disabled={!!busy} onClick={() => runTool("/admin/backfill-real-outcomes", "Backfill real outcomes")} className="text-xs px-3 py-1.5 rounded-lg border border-border-subtle text-text-secondary hover:border-accent/40 disabled:opacity-50">Backfill outcomes</button>
            <button disabled={!!busy} onClick={() => runTool("/admin/backfill-ai-alerts", "Backfill AI alerts")} className="text-xs px-3 py-1.5 rounded-lg border border-border-subtle text-text-secondary hover:border-accent/40 disabled:opacity-50">Backfill AI alerts</button>
            <button disabled={!!busy} onClick={() => runTool("/admin/run-weekly-retro", "Run weekly retro")} className="text-xs px-3 py-1.5 rounded-lg border border-border-subtle text-text-secondary hover:border-accent/40 disabled:opacity-50">Run weekly retro</button>
            <button disabled={!!busy} onClick={() => runTool("/admin/watchlists/cleanup?dry_run=true", "Watchlist cleanup (dry run)")} className="text-xs px-3 py-1.5 rounded-lg border border-border-subtle text-text-secondary hover:border-accent/40 disabled:opacity-50">Watchlist cleanup (dry)</button>
          </div>
          {busy && <div className="text-[11px] text-text-faint mt-1">Running {busy}…</div>}
        </div>
      </div>
    </details>
  );
}
