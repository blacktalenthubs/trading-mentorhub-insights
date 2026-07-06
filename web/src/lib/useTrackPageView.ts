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

type Attribution = { utm_source?: string; utm_medium?: string; utm_campaign?: string };

/** First-touch attribution. If the current URL carries ?utm_source=… (a link from a
 *  Twitter/TikTok post or campaign), persist it; otherwise return what we stored on the
 *  first visit — so every page-view in the session carries the source, and it's still
 *  there at signup. */
function getAttribution(): Attribution {
  try {
    const KEY = "btd_attribution";
    const p = new URLSearchParams(window.location.search);
    const src = p.get("utm_source");
    if (src) {
      const attr: Attribution = {
        utm_source: src,
        utm_medium: p.get("utm_medium") || undefined,
        utm_campaign: p.get("utm_campaign") || undefined,
      };
      localStorage.setItem(KEY, JSON.stringify(attr));
      return attr;
    }
    const stored = localStorage.getItem(KEY);
    return stored ? (JSON.parse(stored) as Attribution) : {};
  } catch {
    return {};
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
          ...getAttribution(),
        }),
        keepalive: true,
      }).catch(() => {});
    } catch {
      /* analytics is best-effort */
    }
  }, [location.pathname]);
}
