import { useState } from "react";
import { useAuthStore } from "../stores/auth";
import {
  useUpdateProfile,
  useChangePassword,
  useNotificationPrefs,
  useUpdateNotificationPrefs,
  useAlertPrefs,
  useUpdateAlertPrefs,
} from "../api/hooks";
import Card from "../components/ui/Card";
import Badge from "../components/ui/Badge";
import { useFeatureGate } from "../hooks/useFeatureGate";

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const { isPro, tier } = useFeatureGate();

  // Profile
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const updateProfile = useUpdateProfile();

  // Password
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [pwMsg, setPwMsg] = useState("");
  const changePassword = useChangePassword();

  // Notifications
  const { data: notifPrefs } = useNotificationPrefs();
  const updateNotifs = useUpdateNotificationPrefs();
  const [telegramOn, setTelegramOn] = useState(true);
  const [emailOn, setEmailOn] = useState(false);
  const [pushOn, setPushOn] = useState(false);

  // Alert Preferences
  const { data: alertPrefs } = useAlertPrefs();
  const updateAlertPrefs = useUpdateAlertPrefs();
  const [catToggles, setCatToggles] = useState<Record<string, boolean>>({});
  const [minScore, setMinScore] = useState(0);
  const [alertPrefsSynced, setAlertPrefsSynced] = useState(false);

  if (alertPrefs && !alertPrefsSynced) {
    const toggles: Record<string, boolean> = {};
    alertPrefs.categories.forEach((c) => { toggles[c.category_id] = c.enabled; });
    setCatToggles(toggles);
    setMinScore(alertPrefs.min_score);
    setAlertPrefsSynced(true);
  }

  // Sync notif state when data loads
  if (notifPrefs && telegramOn !== notifPrefs.telegram_enabled) {
    setTelegramOn(notifPrefs.telegram_enabled);
    setEmailOn(notifPrefs.email_enabled);
    setPushOn(notifPrefs.push_enabled);
  }

  function handleUpdateProfile(e: React.FormEvent) {
    e.preventDefault();
    updateProfile.mutate({ display_name: displayName });
  }

  function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwMsg("");
    changePassword.mutate(
      { current_password: currentPw, new_password: newPw },
      {
        onSuccess: () => {
          setPwMsg("Password updated");
          setCurrentPw("");
          setNewPw("");
        },
        onError: (err) => {
          setPwMsg(err instanceof Error ? err.message : "Failed");
        },
      },
    );
  }

  function handleSaveNotifs() {
    updateNotifs.mutate({
      telegram_enabled: telegramOn,
      email_enabled: emailOn,
      push_enabled: pushOn,
      quiet_hours_start: null,
      quiet_hours_end: null,
    });
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="font-display text-2xl font-bold">Settings</h1>

      {/* Profile */}
      <Card title="Profile">
        <form onSubmit={handleUpdateProfile} className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-text-muted">Email</label>
            <p className="text-sm text-text-secondary">{user?.email}</p>
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">Display Name</label>
            <input
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full rounded border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={updateProfile.isPending}
              className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
            >
              Save
            </button>
            {updateProfile.isSuccess && (
              <span className="text-xs text-bullish-text">Saved</span>
            )}
          </div>
        </form>
      </Card>

      {/* Subscription */}
      <Card title="Subscription">
        <div className="flex items-center gap-3">
          <Badge variant={isPro ? "pro" : "neutral"}>
            {tier.toUpperCase()}
          </Badge>
          {!isPro && (
            <p className="text-sm text-text-muted">
              Upgrade to Pro for real-time alerts, paper trading, and AI coach.
            </p>
          )}
        </div>
      </Card>

      {/* Password */}
      <Card title="Change Password">
        <form onSubmit={handleChangePassword} className="space-y-3">
          <input
            type="password"
            value={currentPw}
            onChange={(e) => setCurrentPw(e.target.value)}
            placeholder="Current password"
            required
            className="w-full rounded border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
          />
          <input
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            placeholder="New password (min 6 chars)"
            required
            minLength={6}
            className="w-full rounded border border-border-subtle bg-surface-3 px-3 py-2 text-sm text-text-primary focus:border-accent focus:outline-none"
          />
          <div className="flex items-center gap-3">
            <button
              type="submit"
              disabled={changePassword.isPending}
              className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
            >
              Update Password
            </button>
            {pwMsg && (
              <span className={`text-xs ${pwMsg === "Password updated" ? "text-bullish-text" : "text-bearish-text"}`}>
                {pwMsg}
              </span>
            )}
          </div>
        </form>
      </Card>

      {/* Notifications */}
      <Card title="Notifications">
        <div className="space-y-3">
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={telegramOn}
              onChange={(e) => setTelegramOn(e.target.checked)}
              className="rounded"
            />
            <span className="text-sm text-text-primary">Telegram alerts</span>
          </label>
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={emailOn}
              onChange={(e) => setEmailOn(e.target.checked)}
              className="rounded"
            />
            <span className="text-sm text-text-primary">Email alerts</span>
          </label>
          <label className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={pushOn}
              onChange={(e) => setPushOn(e.target.checked)}
              className="rounded"
            />
            <span className="text-sm text-text-primary">Push notifications</span>
          </label>
          <button
            onClick={handleSaveNotifs}
            disabled={updateNotifs.isPending}
            className="rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            Save Preferences
          </button>
        </div>
      </Card>

      {/* Trading Style & Alert Preferences */}
      <Card title="Trading Style & Alert Preferences">
        <p className="mb-4 text-xs text-text-muted">
          Choose which trading patterns you want alerts for. Disabled patterns
          still appear on the dashboard — just no push notification.
        </p>

        {alertPrefs ? (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {alertPrefs.categories.map((cat) => (
                <label key={cat.category_id} className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    checked={catToggles[cat.category_id] ?? true}
                    onChange={(e) =>
                      setCatToggles((prev) => ({
                        ...prev,
                        [cat.category_id]: e.target.checked,
                      }))
                    }
                    className="mt-0.5 rounded"
                  />
                  <div>
                    <span className="text-sm font-medium text-text-primary">
                      {cat.name}
                    </span>
                    <p className="text-xs text-text-muted">{cat.description}</p>
                  </div>
                </label>
              ))}
            </div>

            <div className="mt-4">
              <label className="mb-1 block text-xs text-text-muted">
                Minimum Alert Score: {minScore}
              </label>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full"
              />
              <p className="text-xs text-text-muted">
                Alerts below this score won't push. Exit alerts (T1/T2/Stop) always send.
              </p>
            </div>

            <button
              onClick={() =>
                updateAlertPrefs.mutate({
                  categories: catToggles,
                  min_score: minScore,
                })
              }
              disabled={updateAlertPrefs.isPending}
              className="mt-4 rounded bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {updateAlertPrefs.isPending ? "Saving..." : "Save Alert Preferences"}
            </button>
            {updateAlertPrefs.isSuccess && (
              <span className="ml-3 text-xs text-bullish-text">Saved</span>
            )}
          </>
        ) : (
          <p className="text-sm text-text-muted">Loading preferences...</p>
        )}
      </Card>
    </div>
  );
}
