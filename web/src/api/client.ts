/** Thin fetch wrapper with auth token injection. */

import { Capacitor } from "@capacitor/core";
import { useAuthStore } from "../stores/auth";

/**
 * On native iOS/Android the app runs from a local file:// origin so relative
 * URLs don't work — we need the full backend URL.  On web (dev / production)
 * we keep the relative path so the Vite proxy / reverse-proxy still works.
 */
const API_HOST = Capacitor.isNativePlatform()
  ? String(import.meta.env.VITE_API_URL || "https://api.aicopilottrader.com")
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
    try {
      const res = await fetch(`${BASE_URL}/auth/refresh`, {
        method: "POST",
        credentials: "include", // send refresh_token cookie
      });
      if (!res.ok) return false;
      const data = await res.json();
      if (data.access_token) {
        useAuthStore.getState().setAccessToken(data.access_token);
        return true;
      }
      return false;
    } catch {
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
