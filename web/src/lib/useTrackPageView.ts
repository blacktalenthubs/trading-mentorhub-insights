/** Fire-and-forget page-view tracking.
 *
 *  Pings POST /api/v1/public/track on every route change so the admin Traffic
 *  panel has data. Deliberately decoupled from the api client — a plain fetch
 *  that never throws and never blocks navigation. An anonymous visitor_id lives
 *  in localStorage (no cookies, no PII); the bearer token, when present, lets
 *  the backend attribute the visit to a logged-in user.
 */
import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useAuthStore } from "../stores/auth";

function getVisitorId(): string {
  try {
    let id = localStorage.getItem("btd_visitor_id");
    if (!id) {
      id =
        (typeof crypto !== "undefined" && crypto.randomUUID)
          ? crypto.randomUUID()
          : `v_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      localStorage.setItem("btd_visitor_id", id);
    }
    return id;
  } catch {
    return "anon";
  }
}

export function useTrackPageView() {
  const location = useLocation();
  useEffect(() => {
    try {
      const token = useAuthStore.getState().accessToken;
      fetch("/api/v1/public/track", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          path: location.pathname,
          visitor_id: getVisitorId(),
          referrer: document.referrer || null,
        }),
        keepalive: true,
      }).catch(() => {});
    } catch {
      /* analytics is best-effort */
    }
  }, [location.pathname]);
}
