/** Auth store — persists token via storage adapter, rehydrates on launch.
 *
 * 2026-05-26 — added refresh token storage for Capacitor mobile.
 * Cookies don't survive cross-origin WebView restarts, so we persist the
 * refresh_token alongside the access token and send it in the request body
 * on /auth/refresh. Web flow still uses the HttpOnly cookie unchanged.
 */

import { create } from "zustand";
import type { User } from "../types";
import { storage } from "./storage";

const TOKEN_KEY = "ts_access_token";
const USER_KEY = "ts_user";
const REFRESH_KEY = "ts_refresh_token";

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  /** True once we've attempted to rehydrate from storage. */
  hydrated: boolean;
  setAuth: (user: User, token: string, refreshToken?: string) => Promise<void>;
  setAccessToken: (token: string) => void;
  setRefreshToken: (token: string) => void;
  logout: () => void;
  /** Load persisted session from storage (called once on app boot). */
  hydrate: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  hydrated: false,

  setAuth: async (user, token, refreshToken) => {
    set({ user, accessToken: token, ...(refreshToken ? { refreshToken } : {}) });
    // Await the persistence writes so we can confirm Capacitor Preferences
    // actually accepted them — without awaiting, a force-quit immediately
    // after login could land before the iOS Keychain write committed.
    try {
      await Promise.all([
        storage.set(TOKEN_KEY, token),
        storage.set(USER_KEY, JSON.stringify(user)),
        refreshToken ? storage.set(REFRESH_KEY, refreshToken) : Promise.resolve(),
      ]);
      console.info("[auth] setAuth persisted to Keychain (refresh=%s)", refreshToken ? "yes" : "no");
    } catch (e) {
      console.warn("[auth] setAuth FAILED to persist — next launch will be logged out:", e);
    }
  },

  setAccessToken: (token) => {
    set({ accessToken: token });
    storage.set(TOKEN_KEY, token);
  },

  setRefreshToken: (token) => {
    set({ refreshToken: token });
    storage.set(REFRESH_KEY, token);
  },

  logout: () => {
    set({ user: null, accessToken: null, refreshToken: null });
    storage.remove(TOKEN_KEY);
    storage.remove(USER_KEY);
    storage.remove(REFRESH_KEY);
  },

  hydrate: async () => {
    try {
      const [token, userJson, refreshToken] = await Promise.all([
        storage.get(TOKEN_KEY),
        storage.get(USER_KEY),
        storage.get(REFRESH_KEY),
      ]);
      console.info(
        "[auth] hydrate read storage: access=%s user=%s refresh=%s",
        token ? "yes" : "no",
        userJson ? "yes" : "no",
        refreshToken ? "yes" : "no",
      );
      if (token && userJson) {
        const user: User = JSON.parse(userJson);
        set({ user, accessToken: token, refreshToken, hydrated: true });
        return;
      }
    } catch (e) {
      console.warn("[auth] hydrate threw — falling back to logged-out:", e);
    }
    set({ hydrated: true });
  },
}));
