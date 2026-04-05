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
  telegram_linked: boolean;
  watchlist_count: number;
  alert_count: number;
}

interface PlatformStats {
  total_users: number;
  pro_users: number;
  free_users: number;
  telegram_linked: number;
  total_alerts: number;
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

function TierBadge({ tier }: { tier: string }) {
  const styles: Record<string, string> = {
    pro: "bg-accent/10 text-accent border-accent/20",
    premium: "bg-purple/10 text-purple-text border-purple/20",
    admin: "bg-warning/10 text-warning-text border-warning/20",
    free: "bg-surface-3 text-text-faint border-border-subtle",
    none: "bg-surface-3 text-text-faint border-border-subtle",
  };
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${styles[tier] || styles.free}`}>
      {tier.toUpperCase()}
    </span>
  );
}

export default function AdminPage() {
  const [stats, setStats] = useState<PlatformStats | null>(null);
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
    ])
      .then(([s, u]) => {
        setStats(s);
        setUsers(u.users);
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
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
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
              label="Free Users"
              value={stats.free_users}
              icon={<Users className="h-4 w-4 text-text-muted" />}
            />
            <StatCard
              label="Telegram Linked"
              value={stats.telegram_linked}
              icon={<Send className="h-4 w-4 text-accent" />}
            />
            <StatCard
              label="Total Alerts"
              value={stats.total_alerts.toLocaleString()}
              icon={<BarChart3 className="h-4 w-4 text-bullish" />}
            />
          </div>
        )}

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
                    <td className="px-3 py-3 text-center"><TierBadge tier={u.tier} /></td>
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
                        <td className="px-3 py-2 text-center"><TierBadge tier={u.tier} /></td>
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
