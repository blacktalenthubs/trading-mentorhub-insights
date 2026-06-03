/** Thin fetch wrapper with auth token injection. */

import { Capacitor } from "@capacitor/core";
import { useAuthStore } from "../stores/auth";

/**
 * The native iOS/Android app loads the live site over https via capacitor.config
 * `server.url` (www.busytradersdesk.com), so the WebView origin is a real https
 * origin — relative "/api" URLs resolve to that backend exactly like the web
 * build. We use relative URLs everywhere; VITE_API_URL only overrides for
 * local-device dev (point at a LAN IP). The previous hardcoded
 * https://api.aicopilottrader.com host is dead post-rebrand and 500'd/refused
 * every mobile API call ("failed to load" on every page).
 */
const API_HOST = Capacitor.isNativePlatform()
  ? String(import.meta.env.VITE_API_URL || "")
  : "";

const BASE_URL = `${API_HOST}/api/v1`;

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

let _refreshing: Promise<boolean> | null = null;

async function attemptRefresh(): Promise<boolean> {
  // Deduplicate concurrent refresh attempts
  if (_refreshing) return _refreshing;
  _refreshing = (async () => {
    const stored = useAuthStore.getState().refreshToken;
    try {
      // Send refresh token in BOTH cookie (web) AND body (Capacitor mobile).
      // The cookie path is browser-only; cross-origin WebView can't set the
      // cookie reliably, so we also include it in the body when we have one
      // stored in Capacitor Preferences.
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: stored ? JSON.stringify({ refresh_token: stored }) : undefined,
      });
      if (!res.ok) {
        // Diagnostic — surface refresh failures in DevTools/Safari Web
        // Inspector so we can see WHY auto-refresh isn't recovering before
        // the forced logout. Status + body text + whether we had a stored
        // token at all is enough to triage (stale token vs missing vs
        // server-side reject).
        let bodyText = "";
        try { bodyText = await res.text(); } catch { /* ignore */ }
        console.warn(
          "[auth] refresh FAILED — status=%d had_stored_refresh=%s body=%s",
          res.status, stored ? "yes" : "no", bodyText.slice(0, 200),
        );
        return false;
      }
      const data = await res.json();
      if (data.access_token) {
        useAuthStore.getState().setAccessToken(data.access_token);
        if (data.refresh_token) {
          // Backend rotated the refresh token — update storage so next refresh
          // uses the new one. Critical for Capacitor where cookie path doesn't work.
          useAuthStore.getState().setRefreshToken(data.refresh_token);
        }
        return true;
      }
      console.warn("[auth] refresh response had no access_token", data);
      return false;
    } catch (e) {
      console.warn("[auth] refresh threw — network error or fetch aborted:", e);
      return false;
    } finally {
      _refreshing = null;
    }
  })();
  return _refreshing;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (res.status === 401 && !path.startsWith("/auth/")) {
    // Attempt silent token refresh before logging out (skip for auth endpoints)
    const refreshed = await attemptRefresh();
    if (refreshed) {
      // Retry the original request with the new token
      const newToken = useAuthStore.getState().accessToken;
      if (newToken) {
        headers["Authorization"] = `Bearer ${newToken}`;
      }
      const retryRes = await fetch(`${BASE_URL}${path}`, { ...options, headers });
      if (retryRes.ok) {
        if (retryRes.status === 204) return undefined as T;
        return retryRes.json();
      }
    }
    // Forced logout after refresh attempt also failed. Log the path that
    // triggered it so we can correlate to a specific endpoint when debugging.
    console.warn("[auth] forced logout after 401 + refresh failure path=%s", path);
    useAuthStore.getState().logout();
    throw new ApiError(401, "Session expired");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || res.statusText);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export { ApiError };
