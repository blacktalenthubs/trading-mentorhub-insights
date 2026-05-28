/**
 * Storage adapter — always uses Capacitor Preferences.
 *
 * Preferences is iOS Keychain / Android EncryptedSharedPreferences on
 * native, and falls back to localStorage on plain web. By calling it
 * unconditionally we avoid the bridge-not-ready race that was capturing
 * `Capacitor.isNativePlatform()=false` at module load and routing every
 * write to plain WKWebView localStorage — which iOS clears under memory
 * pressure (the cause of the "leave app 20 min, come back signed out"
 * symptom observed 2026-05-28).
 */

import { Preferences } from "@capacitor/preferences";

export const storage = {
  async get(key: string): Promise<string | null> {
    try {
      const { value } = await Preferences.get({ key });
      return value;
    } catch {
      // Bridge truly unavailable (extremely early bootstrap, SSR, tests)
      try { return localStorage.getItem(key); } catch { return null; }
    }
  },

  async set(key: string, value: string): Promise<void> {
    try {
      await Preferences.set({ key, value });
    } catch {
      try { localStorage.setItem(key, value); } catch { /* no-op */ }
    }
  },

  async remove(key: string): Promise<void> {
    try {
      await Preferences.remove({ key });
    } catch {
      try { localStorage.removeItem(key); } catch { /* no-op */ }
    }
  },
};
